from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter

from agent_c.core.models import ACPAck, ACPMessage
from agent_c.utils.security import require_api_key
from agent_c.utils.config import Settings
from agent_c.storage.store import RunStore
from agent_c.clients.agent_b import AgentBClient
from agent_c.clients.trtllm import TRTLLMClient
from agent_c.core.coordinator import Worker
from agent_c.core.publisher_loop import OutboxPublisher

from .deps import (
    get_settings,
    get_schema_validator,
    get_store,
    get_agent_b,
    get_worker,
    get_outbox_publisher,
    get_llm,
)

app = FastAPI(title="Agent C (Coordinator/Planner)", version="0.2.0")
adapter = TypeAdapter(ACPMessage)


@app.on_event("startup")
async def _startup():
    await get_worker().start()
    await get_outbox_publisher().start()


@app.on_event("shutdown")
async def _shutdown():
    await get_outbox_publisher().stop()
    await get_worker().stop()


@app.get("/health")
async def health():
    return {"ok": True, "service": "agent_c", "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}


@app.get("/ready")
async def ready(b: AgentBClient = Depends(get_agent_b), llm: TRTLLMClient = Depends(get_llm)):
    b_health = await b.health()
    llm_ok = await llm.health()
    return {
        "ok": bool(b_health.ok) and bool(llm_ok),
        "service": "agent_c",
        "downstream": {"agent_b": {"ok": b_health.ok, "error": b_health.error}, "trtllm": {"ok": llm_ok}},
    }


@app.post("/messages", response_model=ACPAck)
async def ingest_message(
    msg: dict,
    x_api_key: str | None = Header(default=None),
    s: Settings = Depends(get_settings),
    st: RunStore = Depends(get_store),
    worker: Worker = Depends(get_worker),
    validator=Depends(get_schema_validator),
):
    require_api_key(x_api_key, s.C_API_KEY)

    raw_errors = []
    for err in validator.iter_errors(msg):
        if isinstance(err, Exception):
            raw_errors.append({"path": "/", "message": str(err)})
            continue
        path = "/" + "/".join(str(p) for p in err.path) if getattr(err, "path", None) else "/"
        raw_errors.append({"path": path, "message": getattr(err, "message", str(err))})
    if raw_errors:
        raise HTTPException(status_code=422, detail={"schema": msg.get("schema", "unknown"), "errors": raw_errors})

    parsed: ACPMessage = adapter.validate_python(msg)

    corr_id = parsed.corr_id or str(uuid4())
    msg2 = parsed if parsed.corr_id == corr_id else parsed.model_copy(update={"corr_id": corr_id})
    md = msg2.model_dump()

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
        await worker.enqueue_intent(msg2)  # type: ignore[arg-type]
        return _make_ack(corr_id, md["event_id"], "accepted", "intent_received")

    return _make_ack(corr_id, md["event_id"], "accepted", "message_received")


@app.get("/runs/{corr_id}")
async def get_run(corr_id: str, st: RunStore = Depends(get_store)):
    try:
        return st.get_run(corr_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="run not found")


@app.get("/runs/{corr_id}/events")
async def get_events(corr_id: str, st: RunStore = Depends(get_store), limit: int = 200):
    try:
        return {"corr_id": corr_id, "events": st.list_events(corr_id, limit=limit)}
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
