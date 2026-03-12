# test_e2e_agent_c_http.py
"""
End-to-end HTTP test for Agent C (Coordinator).

What it covers (real sockets):
- Starts a fake Agent B HTTP service (FastAPI + uvicorn) with /health and /query.
- Starts Agent C via uvicorn as a subprocess.
- Validates:
  - /health downstream agent_b ok
  - /messages accepts ACP v0.2 Intent, returns ACP.Ack
  - orchestrator calls Agent B and updates run state/context
  - idempotency dedupe works (same corr_id + idempotency_key)
  - schema validation returns structured 422 errors
  - API key enforcement returns 401 + WWW-Authenticate header

Assumptions about repo layout:
- You run pytest from the repo's `app/` directory OR the code below can find `app/` automatically.
- Agent C import path is `agent_c.main:app` (adjust AGENT_C_APP if yours differs).
- Shared schemas live at `app/schemas/...` (SCHEMA_ROOT is set accordingly).
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from threading import Thread
from typing import Any, Dict, Optional

import httpx
import pytest
import uvicorn
from fastapi import FastAPI, Request


# --- Adjust this if your Agent C entrypoint module differs ---
AGENT_C_APP = "agent_c.main:app"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _wait_http_ok(url: str, timeout_s: float = 10.0) -> None:
    deadline = time.time() + timeout_s
    last_err: Optional[str] = None
    while time.time() < deadline:
        try:
            r = httpx.get(url, timeout=1.0)
            if r.status_code < 500:
                return
        except Exception as e:
            last_err = str(e)
        time.sleep(0.1)
    raise RuntimeError(f"Timed out waiting for HTTP: {url} (last_err={last_err})")


class _UvicornThread:
    def __init__(self, app: FastAPI, host: str, port: int):
        self.config = uvicorn.Config(app, host=host, port=port, log_level="warning")
        self.server = uvicorn.Server(self.config)
        self.thread = Thread(target=self.server.run, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=5)


def _find_app_dir() -> Path:
    """
    Try to find the repo's `app/` directory robustly.
    - If current working dir is already `app/`, use it.
    - Otherwise, walk up and look for an `app/` folder containing `schemas/`.
    """
    cwd = Path.cwd().resolve()
    if (cwd / "schemas").exists() and (cwd / "agent_c").exists():
        return cwd

    for parent in [cwd] + list(cwd.parents):
        candidate = parent / "app"
        if (candidate / "schemas").exists() and (candidate / "agent_c").exists():
            return candidate

    raise RuntimeError("Could not find repo app/ directory. Run pytest from repo root or app/.")


@pytest.fixture(scope="session")
def fake_agent_b() -> Dict[str, Any]:
    """
    Start a fake Agent B server.
    """
    app = FastAPI(title="Fake Agent B")

    @app.get("/health")
    async def health():
        return {"ok": True, "service": "agent_b_fake"}

    @app.post("/query")
    async def query(req: Request):
        body = await req.json()
        corr_id = body.get("corr_id")
        return {
            "schema": "agentb.api.v0.1",
            "type": "AgentB.QueryResponse",
            "ok": True,
            "query_id": "qry-12345678",
            "ts": "2026-02-09T12:00:00Z",
            "corr_id": corr_id,
            "results": [
                {"rank": 1, "id": "doc-1", "text": "fake result 1", "metadata": {"src": "fake"}, "score": 0.99},
                {"rank": 2, "id": "doc-2", "text": "fake result 2", "metadata": {"src": "fake"}, "score": 0.88},
            ],
            "stats": {"n_results": 2, "k_init": 50, "rerank": False, "latency_ms": 1.0},
        }

    @app.post("/ingest")
    async def ingest(req: Request):
        _ = await req.json()
        return {"ok": True}

    port = _free_port()
    server = _UvicornThread(app, host="127.0.0.1", port=port)
    server.start()
    _wait_http_ok(f"http://127.0.0.1:{port}/health", timeout_s=10)

    yield {"base_url": f"http://127.0.0.1:{port}", "server": server}

    server.stop()


@pytest.fixture()
def agent_c_server(tmp_path: Path, fake_agent_b: Dict[str, Any]) -> Dict[str, Any]:
    """
    Start Agent C as a real uvicorn subprocess.
    """
    app_dir = _find_app_dir()
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"

    api_key = "test-api-key-123"
    db_path = tmp_path / "agent_c_e2e.db"

    # Use absolute SCHEMA_ROOT so cwd differences don't break schema validation
    schema_root = (app_dir / "schemas").resolve()

    env = os.environ.copy()
    env["PYTHONPATH"] = str(app_dir)  # ensure `import agent_c` works
    env["AGENT_SCHEMA_ROOT"] = str(schema_root)
    env["AGENT_B_BASE_URL"] = fake_agent_b["base_url"]
    env["AGENT_B_TIMEOUT_S"] = "5.0"
    env["AGENT_C_API_KEY"] = api_key
    env["AGENT_C_DB_PATH"] = str(db_path)

    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        AGENT_C_APP,
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--log-level",
        "warning",
    ]
    proc = subprocess.Popen(
        cmd,
        cwd=str(app_dir),  # run from app/ so relative paths behave naturally
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        _wait_http_ok(f"{base_url}/health", timeout_s=15)
        yield {"base_url": base_url, "api_key": api_key, "proc": proc}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def _acp_intent(corr_id: str, event_id: str, idempotency_key: str) -> Dict[str, Any]:
    return {
        "schema": "acp.v0.2",
        "event_id": event_id,
        "ts": "2026-02-09T12:00:00Z",
        "type": "ACP.Intent",
        "corr_id": corr_id,
        "idempotency_key": idempotency_key,
        "source": {"system": "VITALS", "component": "GUIAdapter", "instance": "e2e"},
        "payload": {"intent_kind": "HoldPosition"},
    }


def test_e2e_health(agent_c_server: Dict[str, Any]):
    base = agent_c_server["base_url"]
    r = httpx.get(f"{base}/health", timeout=5.0)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["service"] == "agent_c"
    assert body["downstream"]["agent_b"]["ok"] is True


def test_e2e_messages_intent_updates_run(agent_c_server: Dict[str, Any]):
    base = agent_c_server["base_url"]
    api_key = agent_c_server["api_key"]
    headers = {"x-api-key": api_key}

    corr_id = f"corr-{int(time.time())}"
    msg = _acp_intent(corr_id=corr_id, event_id="evt-aaaaaaaa", idempotency_key="idem-aaaaaaaa")

    r = httpx.post(f"{base}/messages", json=msg, headers=headers, timeout=10.0)
    assert r.status_code == 200
    ack = r.json()
    assert ack["schema"] == "acp.v0.2"
    assert ack["type"] == "ACP.Ack"
    assert ack["corr_id"] == corr_id
    assert ack["payload"]["status"] == "accepted"

    # Run should exist and be updated by orchestrator (Agent B query)
    rr = httpx.get(f"{base}/runs/{corr_id}", timeout=5.0)
    assert rr.status_code == 200
    run = rr.json()
    assert run["corr_id"] == corr_id
    assert run["state"] in ("planning", "proposed", "failed")  # timing-safe

    # Give orchestrator a brief moment if needed
    deadline = time.time() + 5.0
    while time.time() < deadline:
        run = httpx.get(f"{base}/runs/{corr_id}", timeout=5.0).json()
        if run["state"] in ("proposed", "failed"):
            break
        time.sleep(0.1)

    assert run["state"] == "proposed"
    ctx = run["context"]
    assert ctx.get("agentb_last_query_response") is not None
    dc = ctx.get("dispatch_counts") or {}
    assert int(dc.get("b_query_sent", 0)) == 1
    assert int(dc.get("b_query_ok", 0)) == 1


def test_e2e_idempotency_dedupe(agent_c_server: Dict[str, Any]):
    base = agent_c_server["base_url"]
    api_key = agent_c_server["api_key"]
    headers = {"x-api-key": api_key}

    corr_id = f"corr-dedupe-{int(time.time())}"
    idem = "idem-same-key-1234"

    # First intent
    r1 = httpx.post(
        f"{base}/messages",
        json=_acp_intent(corr_id=corr_id, event_id="evt-first-0001", idempotency_key=idem),
        headers=headers,
        timeout=10.0,
    )
    assert r1.status_code == 200

    # Wait until proposed
    deadline = time.time() + 5.0
    while time.time() < deadline:
        run = httpx.get(f"{base}/runs/{corr_id}", timeout=5.0).json()
        if run["state"] in ("proposed", "failed"):
            break
        time.sleep(0.1)
    assert run["state"] == "proposed"
    dc1 = (run["context"].get("dispatch_counts") or {}).copy()

    # Retry with different event_id but same idempotency_key (should be deduped)
    r2 = httpx.post(
        f"{base}/messages",
        json=_acp_intent(corr_id=corr_id, event_id="evt-second-0002", idempotency_key=idem),
        headers=headers,
        timeout=10.0,
    )
    assert r2.status_code == 200
    ack2 = r2.json()
    assert ack2["type"] == "ACP.Ack"
    assert ack2["payload"]["message"] in ("duplicate_ignored", "intent_received")

    # Verify dispatch counts did not increment (dedupe should prevent a second Agent B query)
    run2 = httpx.get(f"{base}/runs/{corr_id}", timeout=5.0).json()
    dc2 = run2["context"].get("dispatch_counts") or {}
    assert int(dc2.get("b_query_sent", 0)) == int(dc1.get("b_query_sent", 0))
    assert int(dc2.get("b_query_ok", 0)) == int(dc1.get("b_query_ok", 0))


def test_e2e_schema_validation_422(agent_c_server: Dict[str, Any]):
    base = agent_c_server["base_url"]
    api_key = agent_c_server["api_key"]
    headers = {"x-api-key": api_key}

    # Missing idempotency_key on ACP.Intent should fail schema validation
    bad = {
        "schema": "acp.v0.2",
        "event_id": "evt-bad-0001",
        "ts": "2026-02-09T12:00:00Z",
        "type": "ACP.Intent",
        "corr_id": "corr-bad",
        "source": {"system": "VITALS", "component": "GUIAdapter"},
        "payload": {"intent_kind": "HoldPosition"},
    }
    r = httpx.post(f"{base}/messages", json=bad, headers=headers, timeout=10.0)
    assert r.status_code == 422
    body = r.json()
    # Expect the structured error style from main.py optional improvement
    assert "detail" in body
    assert "errors" in body["detail"]
    assert isinstance(body["detail"]["errors"], list)
    assert len(body["detail"]["errors"]) >= 1


def test_e2e_api_key_enforced(agent_c_server: Dict[str, Any]):
    base = agent_c_server["base_url"]

    msg = _acp_intent(corr_id="corr-auth", event_id="evt-auth-0001", idempotency_key="idem-auth-0001")

    r = httpx.post(f"{base}/messages", json=msg, timeout=10.0)  # no x-api-key
    assert r.status_code == 401
    # Upgraded security.py: WWW-Authenticate should be present
    assert r.headers.get("www-authenticate") == "ApiKey"
