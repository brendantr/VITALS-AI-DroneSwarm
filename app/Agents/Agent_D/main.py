from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException

from Agents.Agent_D.service import AgentDError, AgentDService


app = FastAPI(title="VITALS Agent D (Pathing & Mapping)", version="0.2.0")
service = AgentDService()


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": "agent_d",
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


@app.post("/messages")
def ingest_message(msg: dict):
    try:
        return service.ingest_message(msg)
    except AgentDError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
