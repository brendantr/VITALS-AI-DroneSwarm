from __future__ import annotations

from typing import Any, Dict

from agents_common.schema_validator import SchemaValidator

from .b_client import AgentBClient
from .models import (
    ACPIntent,
    ACPStatusState,
    AgentBClientInfo,
    AgentBQueryRequest,
    AgentBQueryResponse,
)
from .store import RunStore


def _intent_to_query(intent: ACPIntent) -> str:
    p = intent.payload
    parts: list[str] = [f"intent_kind={p.intent_kind.value}", f"priority={p.priority}"]

    if p.area:
        if p.area.sector:
            parts.append(f"sector={p.area.sector}")
        if p.area.polygon_wgs84:
            parts.append(f"polygon_pts={len(p.area.polygon_wgs84)}")

    if p.point:
        parts.append(f"point=({p.point.lat:.6f},{p.point.lon:.6f})")
        if p.point.alt_m is not None:
            parts.append(f"alt_m={p.point.alt_m}")

    if p.uav_assignment and p.uav_assignment.uav_id:
        parts.append(f"uav_id={p.uav_assignment.uav_id}")

    if p.rationale:
        parts.append(f"rationale={p.rationale}")

    return " | ".join(parts)


class Orchestrator:
    """
    ACP v0.2 policy engine for Agent C.

    Policy (v0.2):
    - On ACP.Intent, call Agent B with AgentB.QueryRequest v0.1
    - Save Agent B response to run context
    - Update run state: planning -> proposed (success) or failed (error)
    - Validate Agent B responses against shared JSON Schemas (agentb.api.v0.1)
    """

    def __init__(self, store: RunStore, b_client: AgentBClient, schema_root: str = "./schemas"):
        self.store = store
        self.b_client = b_client
        self.schema_validator = SchemaValidator(schema_root)

    async def handle_intent(self, msg: ACPIntent) -> Dict[str, Any]:
        corr_id = msg.corr_id
        if not corr_id:
            # This should never happen: main.py assigns corr_id before calling handle_intent
            raise ValueError("corr_id must be set before orchestration")

        self.store.set_state(corr_id, ACPStatusState.planning.value)
        self._bump_count(corr_id, "b_query_sent")

        q = _intent_to_query(msg)
        req = AgentBQueryRequest(
            query=q,
            rerank=False,
            corr_id=corr_id,
            client=AgentBClientInfo(component="AgentC", instance=msg.source.instance or "local"),
        )

        res = await self.b_client.query(req.model_dump())
        if not res.ok:
            self._bump_count(corr_id, "b_query_err")
            self.store.update_context(corr_id, {"agentb_last_error": res.error, "agentb_last_query_response": None})
            self.store.set_state(corr_id, ACPStatusState.failed.value)
            return {"ok": False, "error": res.error}

        # Validate Agent B response against shared JSON Schemas (agentb.api.v0.1)
        schema_errors = []
        for err in self.schema_validator.iter_errors(res.data):
            if isinstance(err, Exception):
                schema_errors.append({"path": "/", "message": str(err)})
                continue
            path = "/" + "/".join(str(p) for p in err.path) if getattr(err, "path", None) else "/"
            schema_errors.append({"path": path, "message": getattr(err, "message", str(err))})

        if schema_errors:
            self._bump_count(corr_id, "b_query_schema_err")
            self.store.update_context(
                corr_id,
                {
                    "agentb_last_error": "agentb.api.v0.1 response failed schema validation",
                    "agentb_last_query_response": res.data,
                    "agentb_schema_errors": schema_errors,
                },
            )
            self.store.set_state(corr_id, ACPStatusState.failed.value)
            return {"ok": False, "error": "agentb response failed schema validation", "schema_errors": schema_errors}

        # Parse for convenience (typed access / normalized JSON)
        try:
            parsed = AgentBQueryResponse.model_validate(res.data)
            payload = parsed.model_dump(mode="json")
        except Exception:
            payload = res.data

        self._bump_count(corr_id, "b_query_ok")
        self.store.update_context(
            corr_id,
            {
                "agentb_last_query_response": payload,
                "agentb_last_error": None,
                "agentb_schema_errors": None,
            },
        )
        self.store.set_state(corr_id, ACPStatusState.proposed.value)
        return {"ok": True, "query": q}

    def _bump_count(self, corr_id: str, field: str) -> None:
        run = self.store.get_run(corr_id)
        dc = run["context"].get("dispatch_counts") or {}
        dc[field] = int(dc.get(field, 0)) + 1
        self.store.update_context(corr_id, {"dispatch_counts": dc})
