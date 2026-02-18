from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter

from agents_common.schema_validator import SchemaValidator

from .b_client import AgentBClient, HttpAgentBClient
from .config import Settings
from .models import ACPAck, ACPMessage
from .orchestrator import Orchestrator
from .security import require_api_key
from .store import RunStore

app = FastAPI(title="Agent C (Coordinator)", version="0.1.0")

settings = Settings()
store = RunStore(settings.C_DB_PATH)
b_client = HttpAgentBClient(
    settings.B_BASE_URL,
    timeout_s=settings.B_TIMEOUT_S,
    schema_root=settings.SCHEMA_ROOT,
    validate_responses=True,
)


# Shared JSON Schema validation (same mechanism as Agent B)
schema_validator = SchemaValidator(settings.SCHEMA_ROOT)
acp_adapter = TypeAdapter(ACPMessage)


def get_settings() -> Settings:
    return settings


def get_store() -> RunStore:
    return store


def get_b_client() -> AgentBClient:
    return b_client


def get_orchestrator(
    st: RunStore = Depends(get_store),
    b: AgentBClient = Depends(get_b_client),
) -> Orchestrator:
    # Construct per-request so dependency_overrides on get_b_client work in tests
    return Orchestrator(st, b)


@app.get("/health")
async def health(b: AgentBClient = Depends(get_b_client)):
    b_health = await b.health()
    return {
        "ok": True,
        "service": "agent_c",
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "downstream": {
            "agent_b": {"ok": b_health.ok, "error": b_health.error, "data": b_health.data if b_health.ok else {}},
        },
    }


@app.post("/messages", response_model=ACPAck)
async def ingest_message(
    msg: dict,
    x_api_key: str | None = Header(default=None),
    s: Settings = Depends(get_settings),
    st: RunStore = Depends(get_store),
    o: Orchestrator = Depends(get_orchestrator),
):
    require_api_key(x_api_key, s.C_API_KEY)

    # 1) Validate against shared JSON Schemas in ./schemas (ACP v0.2 only per policy)
    raw_errors = []
    for err in schema_validator.iter_errors(msg):
        # iter_errors may yield Exceptions if selection/registry fails
        if isinstance(err, Exception):
            raw_errors.append({"path": "/", "message": str(err)})
            continue

        # jsonschema.ValidationError
        path = "/" + "/".join(str(p) for p in err.path) if getattr(err, "path", None) else "/"
        raw_errors.append({"path": path, "message": getattr(err, "message", str(err))})

    if raw_errors:
        raise HTTPException(
            status_code=422,
            detail={
                "schema": msg.get("schema", "unknown"),
                "errors": raw_errors,
            },
        )

    # 2) Parse into typed Pydantic model for downstream logic
    parsed: ACPMessage = acp_adapter.validate_python(msg)

    corr_id = parsed.corr_id or str(uuid4())
    msg2 = parsed if parsed.corr_id == corr_id else parsed.model_copy(update={"corr_id": corr_id})
    md = msg2.model_dump()

    # Ensure run exists; store intent payload if present
    intent_payload = md["payload"] if md["type"] == "ACP.Intent" else {}
    st.ensure_run(corr_id, intent=intent_payload, metadata={"created_by": md["source"]["component"]})

    dedupe = st.append_event_deduped(
        corr_id=corr_id,
        event_id=md["event_id"],
        ts_iso=md["ts"].isoformat().replace("+00:00", "Z"),
        type_=md["type"],
        source=md["source"],
        target=md.get("target"),
        span_id=md.get("span_id"),
        idempotency_key=md.get("idempotency_key"),
        payload=md["payload"],
    )

    if not dedupe.inserted:
        return JSONResponse(_make_ack(corr_id, md["event_id"], "accepted", "duplicate_ignored"), status_code=200)

    if md["type"] == "ACP.Intent":
        await o.handle_intent(msg2)  # updates run state/context
        return _make_ack(corr_id, md["event_id"], "accepted", "intent_received")

    return _make_ack(corr_id, md["event_id"], "accepted", "message_received")


@app.get("/runs/{corr_id}")
async def get_run(corr_id: str, st: RunStore = Depends(get_store)):
    try:
        return st.get_run(corr_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="run not found")


@app.post("/runs/{corr_id}/cancel")
async def cancel_run(
    corr_id: str,
    x_api_key: str | None = Header(default=None),
    s: Settings = Depends(get_settings),
    st: RunStore = Depends(get_store),
):
    require_api_key(x_api_key, s.C_API_KEY)
    try:
        st.set_state(corr_id, "paused")
        st.update_context(corr_id, {"cancelled": True})
        return {"ok": True, "corr_id": corr_id, "state": "paused"}
    except KeyError:
        raise HTTPException(status_code=404, detail="run not found")


def _make_ack(corr_id: str, ref_event_id: str, status: str, message: str):
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return {
        "schema": "acp.v0.2",
        "event_id": f"ack-{uuid4().hex[:12]}",
        "ts": now,
        "type": "ACP.Ack",
        "corr_id": corr_id,
        "source": {"system": "VITALS", "component": "AgentC", "instance": "agentc-http"},
        "payload": {"ref_event_id": ref_event_id, "status": status, "message": message},
    }
