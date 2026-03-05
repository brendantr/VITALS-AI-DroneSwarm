from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict

from agent_c.clients.agent_b import AgentBClient
from agent_c.clients.publisher import Publisher
from agent_c.core.models import ACPIntent, ACPStatusState
from agent_c.storage.store import RunStore


ToolFn = Callable[..., Awaitable[Dict[str, Any]]]


@dataclass
class ToolContext:
    corr_id: str
    intent: ACPIntent
    store: RunStore
    agent_b: AgentBClient
    publisher: Publisher


def _utc_ts() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _make_status_msg(corr_id: str, ref_event_id: str, state: str, detail: str | None) -> Dict[str, Any]:
    return {
        "schema": "acp.v0.2",
        "event_id": f"st-{corr_id[:8]}-{ref_event_id[:6]}",
        "ts": _utc_ts(),
        "type": "ACP.Status",
        "corr_id": corr_id,
        "source": {"system": "VITALS", "component": "AgentC", "instance": "agentc"},
        "payload": {"ref_event_id": ref_event_id, "state": state, "detail": detail or ""},
    }


def _make_result_msg(corr_id: str, ref_event_id: str, outcome: str, summary: str | None) -> Dict[str, Any]:
    return {
        "schema": "acp.v0.2",
        "event_id": f"rs-{corr_id[:8]}-{ref_event_id[:6]}",
        "ts": _utc_ts(),
        "type": "ACP.Result",
        "corr_id": corr_id,
        "source": {"system": "VITALS", "component": "AgentC", "instance": "agentc"},
        "payload": {"ref_event_id": ref_event_id, "outcome": outcome, "summary": summary or ""},
    }


async def tool_agentb_query(ctx: ToolContext, *, query: str, rerank: bool = False, where: Dict[str, Any] | None = None) -> Dict[str, Any]:
    where = where or {}
    req = {
        "schema": "agentb.api.v0.1",
        "type": "AgentB.QueryRequest",
        "query": query,
        "rerank": bool(rerank),
        "where": where,
        "corr_id": ctx.corr_id,
        "client": {"component": "AgentC", "instance": ctx.intent.source.instance or "local"},
    }
    res = await ctx.agent_b.query(req)
    if not res.ok:
        ctx.store.update_context(ctx.corr_id, {"agentb_last_error": res.error, "agentb_last_query_response": None})
        ctx.store.set_state(ctx.corr_id, ACPStatusState.failed.value)
        return {"ok": False, "error": res.error}

    ctx.store.update_context(ctx.corr_id, {"agentb_last_query_response": res.data, "agentb_last_error": None})
    return {"ok": True, "results": res.data}


async def tool_emit_status(ctx: ToolContext, *, state: str, detail: str | None = None) -> Dict[str, Any]:
    ctx.store.set_state(ctx.corr_id, state)
    msg = _make_status_msg(ctx.corr_id, ctx.intent.event_id, state, detail)
    key = f"status:{state}:{ctx.intent.event_id}"
    enq = ctx.store.outbox_enqueue(ctx.corr_id, key=key, target="publish", msg=msg)
    return {"ok": True, "enqueued": enq}


async def tool_emit_result(ctx: ToolContext, *, outcome: str, summary: str | None = None) -> Dict[str, Any]:
    msg = _make_result_msg(ctx.corr_id, ctx.intent.event_id, outcome, summary)
    key = f"result:{outcome}:{ctx.intent.event_id}"
    enq = ctx.store.outbox_enqueue(ctx.corr_id, key=key, target="publish", msg=msg)
    return {"ok": True, "enqueued": enq}


def build_tool_registry() -> Dict[str, ToolFn]:
    return {
        "agentb.query": tool_agentb_query,
        "emit.status": tool_emit_status,
        "emit.result": tool_emit_result,
    }
