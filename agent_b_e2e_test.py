import json
import time
import requests
from schema_validator import SchemaValidator

BASE = "http://localhost:8081"

validator = SchemaValidator(schema_root="schemas")

MCP_GOOD = {
  "schema":"mcp.v0.1",
  "event_id":"evt_e2e_001",
  "ts":"2026-01-24T00:00:00.000Z",
  "type":"MCP.Detection",
  "corr_id":"corr_e2e_001",
  "source":{"system":"VITALS","component":"AgentA","instance":"uav_2"},
  "text":"Person detected near debris field in sector B4, confidence 0.91, UAV_2.",
  "payload":{
    "label":"person",
    "confidence":0.91,
    "sector":"B4",
    "uav_id":"UAV_2",
    "frame_ts":"2026-01-24T00:00:00.000Z"
  }
}

# Intentionally bad (missing payload.confidence)
MCP_BAD = {
  "schema":"mcp.v0.1",
  "event_id":"evt_e2e_bad_001",
  "ts":"2026-01-24T00:00:00.000Z",
  "type":"MCP.Detection",
  "source":{"system":"VITALS","component":"AgentA","instance":"uav_2"},
  "payload":{
    "label":"person",
    "sector":"B4"
  }
}

QUERY_REQ = {
  "schema":"agentb.api.v0.1",
  "type":"AgentB.QueryRequest",
  "query":"human detections near B4",
  "n_results":5,
  "k_init":50,
  "rerank":False,
  "where":{"sector":"B4"},
  "include_scores":True,
  "include_metadata":True,
  "corr_id":"corr_e2e_001",
  "client":{"component":"AgentC","instance":"agentc_01"}
}

def must(cond, msg):
    if not cond:
        raise SystemExit(f"[FAIL] {msg}")
    print(f"[OK] {msg}")

def main():
    # 1) Offline schema validation
    print("== Offline validation ==")
    validator.validate(MCP_GOOD)
    must(True, "MCP_GOOD validates against mcp.v0.1 schema")

    validator.validate(QUERY_REQ)
    must(True, "QUERY_REQ validates against agentb.api.v0.1 schema")

    # 2) Health check
    print("\n== Service health ==")
    r = requests.get(f"{BASE}/health", timeout=5)
    must(r.status_code == 200, f"/health returned 200 (got {r.status_code})")

    # 3) Ingest good MCP
    print("\n== Ingest good MCP ==")
    r = requests.post(f"{BASE}/ingest", json={"messages":[MCP_GOOD]}, timeout=15)
    must(r.status_code == 200, f"/ingest accepted good MCP (got {r.status_code})")
    print("Response:", r.json())

    # 4) Query
    print("\n== Query ==")
    r = requests.post(f"{BASE}/query", json=QUERY_REQ, timeout=15)
    must(r.status_code == 200, f"/query returned 200 (got {r.status_code})")
    data = r.json()
    print(json.dumps(data, indent=2))

    must(data.get("ok") is True, "Query response ok=true")
    texts = [x.get("text","") for x in data.get("results", [])]
    must(any("Person detected" in t for t in texts), "Query returned the ingested fact")

    # 5) Negative test: ingest bad MCP should 422
    print("\n== Negative test (bad MCP) ==")
    r = requests.post(f"{BASE}/ingest", json={"messages":[MCP_BAD]}, timeout=15)
    must(r.status_code == 422, f"/ingest rejected bad MCP with 422 (got {r.status_code})")
    print("422 detail:", r.json())

    print("\nAll tests passed.")

if __name__ == "__main__":
    main()
