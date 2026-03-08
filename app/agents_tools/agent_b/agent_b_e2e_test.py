#!/usr/bin/env python3
"""
End-to-end smoke test for VITALS Agent B (Retrieval & Memory) — RERANK demo via “bread analogy” corpus.

Highlights:
- 10-message ingestion corpus (bread analogy) designed to show reranker benefit.
- Runs the same query with rerank OFF vs ON to show improved ranking.

Also includes:
- Offline schema validation (MCP v0.2, ACP v0.2, AgentB API v0.1 QueryRequest)
- /health
- /ingest (MCP + ACP)
- /query (MCP-focused + ACP-focused)
- idempotency/dedupe check (re-ingest same ACP message)
- negative validation tests (expects 422 for bad MCP + bad ACP)

Runnable from ANY working directory (auto-adds /app to sys.path).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests


# -------------------------
# Ensure imports work regardless of CWD
# -------------------------
# File: .../app/agents_tools/agent_b/agent_b_e2e_test.py
APP_DIR = Path(__file__).resolve().parents[2]  # .../app
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from agents_common.schema_validator import SchemaValidator  # noqa: E402


def must(cond: bool, msg: str) -> None:
    if not cond:
        raise SystemExit(f"[FAIL] {msg}")
    print(f"[OK] {msg}")


def _mcp_note(
    event_id: str,
    ts: str,
    text: str,
    *,
    sector: str = "KITCHEN",
    uav_id: str = "UAV_TEST",
    idempotency_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build an MCP.Detection-like message used as a generic 'observation' note.

    MCP v0.2 base supports idempotency_key (optional for now).
    """
    msg: Dict[str, Any] = {
        "schema": "mcp.v0.2",
        "event_id": event_id,
        "ts": ts,
        "type": "MCP.Detection",
        "corr_id": "corr_e2e_001",
        "source": {"system": "VITALS", "component": "AgentA", "instance": "uav_test"},
        "text": text,
        "payload": {
            "label": "note",
            "confidence": 0.99,
            "sector": sector,
            "uav_id": uav_id,
            "frame_ts": ts,
        },
    }
    if idempotency_key is not None:
        msg["idempotency_key"] = idempotency_key
    return msg


def build_bread_corpus_10() -> List[Dict[str, Any]]:
    """
    10 ingestions that mirror the bread analogy:
    - Many semantically related docs (sourdough, crust, baguette, starter, fermentation, etc.)
    - One “best match” doc for the query: sourdough + crispy crust + dutch oven + steam
    """
    base_ts = "2026-01-24T00:10:{:02d}.000Z"
    return [
        _mcp_note(
            "evt_bread_001",
            base_ts.format(1),
            "Bread baking basics: preheat oven well, use a baking stone or steel for better spring.",
            idempotency_key="idem_bread_001",
        ),
        _mcp_note(
            "evt_bread_002",
            base_ts.format(2),
            "Sourdough starter maintenance: feed ratios, peak timing, and how to store in the fridge.",
            idempotency_key="idem_bread_002",
        ),
        _mcp_note(
            "evt_bread_003",
            base_ts.format(3),
            "How yeast fermentation works: bulk fermentation vs proofing and how temperature changes timing.",
            idempotency_key="idem_bread_003",
        ),
        _mcp_note(
            "evt_bread_004",
            base_ts.format(4),
            "Baguette tips: shaping, scoring, and adding steam for a crisp crust (not sourdough-specific).",
            idempotency_key="idem_bread_004",
        ),
        _mcp_note(
            "evt_bread_005",
            base_ts.format(5),
            "Crispy crust techniques: steam early in bake, high heat, venting late, and proper scoring.",
            idempotency_key="idem_bread_005",
        ),
        _mcp_note(
            "evt_bread_006",
            base_ts.format(6),
            "Dutch oven bread method: preheat the Dutch oven, bake covered then uncovered for color.",
            idempotency_key="idem_bread_006",
        ),
        _mcp_note(
            "evt_bread_007",
            base_ts.format(7),
            "Sourdough at home: autolyse, stretch-and-fold, bulk fermentation, and cold retard for flavor.",
            idempotency_key="idem_bread_007",
        ),
        _mcp_note(
            "evt_bread_008",
            base_ts.format(8),
            "Hydration and crumb: higher hydration increases openness; handling and folds affect structure.",
            idempotency_key="idem_bread_008",
        ),
        # Decoy: includes sourdough + dutch oven, but not explicit crispy crust / steam emphasis
        _mcp_note(
            "evt_bread_009",
            base_ts.format(9),
            "Sourdough Dutch oven bake: bake covered 20 min then uncovered; focus on internal temp and timing.",
            idempotency_key="idem_bread_009",
        ),
        # Target: BEST match for query (sourdough + crispy crust + dutch oven + steam)
        _mcp_note(
            "evt_bread_010",
            base_ts.format(10),
            "Sourdough with a crispy crust: preheat a Dutch oven, bake covered to trap steam, "
            "then uncover to crisp and brown the crust. Add extra steam early if needed.",
            idempotency_key="idem_bread_010",
        ),
    ]


def build_test_vectors() -> Dict[str, Any]:
    """
    Build all message payloads here so it's easy to tweak.
    NOTE: ACP v0.2 message does NOT include 'text' (ACP additionalProperties=false).
    """
    mcp_good: Dict[str, Any] = {
        "schema": "mcp.v0.2",
        "event_id": "evt_e2e_001",
        "idempotency_key": "idem_mcp_e2e_001",
        "ts": "2026-01-24T00:00:00.000Z",
        "type": "MCP.Detection",
        "corr_id": "corr_e2e_001",
        "source": {"system": "VITALS", "component": "AgentA", "instance": "uav_2"},
        "text": "Person detected near debris field in sector B4, confidence 0.91, UAV_2.",
        "payload": {
            "label": "person",
            "confidence": 0.91,
            "sector": "B4",
            "uav_id": "UAV_2",
            "frame_ts": "2026-01-24T00:00:00.000Z",
        },
    }

    # Intentionally bad (missing payload.confidence)
    mcp_bad: Dict[str, Any] = {
        "schema": "mcp.v0.2",
        "event_id": "evt_e2e_bad_001",
        "idempotency_key": "idem_mcp_e2e_bad_001",
        "ts": "2026-01-24T00:00:00.000Z",
        "type": "MCP.Detection",
        "source": {"system": "VITALS", "component": "AgentA", "instance": "uav_2"},
        "payload": {
            "label": "person",
            "sector": "B4",
        },
    }

    acp_good: Dict[str, Any] = {
        "schema": "acp.v0.2",
        "event_id": "acp_e2e_001",
        "ts": "2026-01-24T00:00:01.000Z",
        "type": "ACP.Intent",
        "corr_id": "corr_e2e_001",
        "span_id": "span_e2e_001",
        "idempotency_key": "idem_e2e_001",
        "source": {"system": "VITALS", "component": "AgentC", "instance": "agentc_01"},
        "target": {"component": "AgentD", "instance": "agentd_01"},
        "payload": {
            "intent_kind": "SearchArea",
            "priority": 70,
            "constraints": {
                "avoid_nfz": True,
                "min_alt_m": 15.0,
                "max_alt_m": 60.0,
                "time_budget_s": 600,
                "battery_reserve_pct": 25,
            },
            "area": {
                "sector": "B4",
                "polygon_wgs84": [
                    {"lat": 28.602000, "lon": -81.201000},
                    {"lat": 28.602500, "lon": -81.200500},
                    {"lat": 28.601500, "lon": -81.200000},
                ],
            },
            "rationale": "E2E test: request a simple search pattern over sector B4.",
        },
    }

    # Intentionally bad ACP (missing required payload.intent_kind)
    acp_bad: Dict[str, Any] = {
        "schema": "acp.v0.2",
        "event_id": "acp_e2e_bad_001",
        "ts": "2026-01-24T00:00:02.000Z",
        "type": "ACP.Intent",
        "corr_id": "corr_e2e_001",
        "idempotency_key": "idem_e2e_bad_001",
        "source": {"system": "VITALS", "component": "AgentC", "instance": "agentc_01"},
        "payload": {
            # "intent_kind": "SearchArea",  # missing on purpose
            "priority": 70,
            "area": {
                "sector": "B4",
                "polygon_wgs84": [
                    {"lat": 28.602000, "lon": -81.201000},
                    {"lat": 28.602500, "lon": -81.200500},
                    {"lat": 28.601500, "lon": -81.200000},
                ],
            },
        },
    }

    query_req_mcp: Dict[str, Any] = {
        "schema": "agentb.api.v0.1",
        "type": "AgentB.QueryRequest",
        "query": "human detections near B4",
        "n_results": 5,
        "k_init": 50,
        "rerank": False,
        "where": {"sector": "B4"},
        "include_scores": True,
        "include_metadata": True,
        "corr_id": "corr_e2e_001",
        "client": {"component": "AgentC", "instance": "agentc_01"},
    }

    # ACP-focused query: no `where` (ACP sector often nested in payload.area.sector)
    query_req_acp: Dict[str, Any] = {
        "schema": "agentb.api.v0.1",
        "type": "AgentB.QueryRequest",
        "query": "SearchArea sector B4 priority 70",
        "n_results": 5,
        "k_init": 50,
        "rerank": False,
        "where": {},
        "include_scores": True,
        "include_metadata": True,
        "corr_id": "corr_e2e_001",
        "client": {"component": "AgentC", "instance": "agentc_01"},
    }

    # Bread analogy rerank query (same query, rerank toggled)
    bread_query_off: Dict[str, Any] = {
        "schema": "agentb.api.v0.1",
        "type": "AgentB.QueryRequest",
        "query": "How do I bake sourdough bread with a crispy crust in a Dutch oven using steam?",
        "n_results": 5,
        "k_init": 50,
        "rerank": False,
        "where": {"sector": "KITCHEN"},
        "include_scores": True,
        "include_metadata": True,
        "corr_id": "corr_e2e_001",
        "client": {"component": "AgentC", "instance": "agentc_01"},
    }
    bread_query_on: Dict[str, Any] = {**bread_query_off, "rerank": True}

    return {
        "MCP_GOOD": mcp_good,
        "MCP_BAD": mcp_bad,
        "ACP_GOOD": acp_good,
        "ACP_BAD": acp_bad,
        "QUERY_REQ_MCP": query_req_mcp,
        "QUERY_REQ_ACP": query_req_acp,
        "BREAD_CORPUS_10": build_bread_corpus_10(),
        "BREAD_QUERY_OFF": bread_query_off,
        "BREAD_QUERY_ON": bread_query_on,
        "BREAD_TARGET_EVENT_ID": "evt_bread_010",
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000", help="Agent B base URL")
    ap.add_argument(
        "--schema-root",
        default=str(APP_DIR / "schemas"),
        help="Path to schemas root (default: <app>/schemas)",
    )
    args = ap.parse_args()

    base = args.base_url.rstrip("/")
    schema_root = Path(args.schema_root)

    validator = SchemaValidator(schema_root=schema_root)

    tv = build_test_vectors()
    MCP_GOOD = tv["MCP_GOOD"]
    MCP_BAD = tv["MCP_BAD"]
    ACP_GOOD = tv["ACP_GOOD"]
    ACP_BAD = tv["ACP_BAD"]
    QUERY_REQ_MCP = tv["QUERY_REQ_MCP"]
    QUERY_REQ_ACP = tv["QUERY_REQ_ACP"]

    # 1) Offline validation
    print("== Offline validation ==")
    validator.validate(MCP_GOOD)
    must(True, "MCP_GOOD validates against mcp.v0.2 schema")

    validator.validate(ACP_GOOD)
    must(True, "ACP_GOOD validates against acp.v0.2 schema")

    validator.validate(QUERY_REQ_MCP)
    must(True, "QUERY_REQ_MCP validates against agentb.api.v0.1 schema")

    validator.validate(QUERY_REQ_ACP)
    must(True, "QUERY_REQ_ACP validates against agentb.api.v0.1 schema")

    # Validate bread corpus + bread queries offline
    for m in tv["BREAD_CORPUS_10"]:
        validator.validate(m)
    must(True, "BREAD_CORPUS_10 validates against mcp.v0.2 schema (10 messages)")

    validator.validate(tv["BREAD_QUERY_OFF"])
    must(True, "BREAD_QUERY_OFF validates against agentb.api.v0.1 schema")
    validator.validate(tv["BREAD_QUERY_ON"])
    must(True, "BREAD_QUERY_ON validates against agentb.api.v0.1 schema")

    # 2) Health
    print("\n== Service health ==")
    r = requests.get(f"{base}/health", timeout=5)
    must(r.status_code == 200, f"/health returned 200 (got {r.status_code})")
    health = r.json()
    print("Health:", json.dumps(health, indent=2))
    if health.get("reranker") is None:
        print("[WARN] /health reports reranker=None; rerank ON query will likely return ok=false (RERANK_NOT_CONFIGURED).")

    # 3) Ingest MCP (VITALS example)
    print("\n== Ingest good MCP ==")
    r = requests.post(f"{base}/ingest", json={"messages": [MCP_GOOD]}, timeout=15)
    must(r.status_code == 200, f"/ingest accepted good MCP (got {r.status_code})")
    print("Response:", json.dumps(r.json(), indent=2))

    # 3b) Ingest bread analogy corpus (10 messages)
    print("\n== Ingest bread analogy corpus (10 MCP messages) ==")
    r = requests.post(f"{base}/ingest", json={"messages": tv["BREAD_CORPUS_10"]}, timeout=30)
    must(r.status_code == 200, f"/ingest accepted bread corpus (got {r.status_code})")
    print("Response:", json.dumps(r.json(), indent=2))

    # 4) Ingest ACP
    print("\n== Ingest good ACP ==")
    r = requests.post(f"{base}/ingest", json={"messages": [ACP_GOOD]}, timeout=15)
    must(r.status_code == 200, f"/ingest accepted good ACP (got {r.status_code})")
    print("Response:", json.dumps(r.json(), indent=2))

    # 5) Query MCP (VITALS)
    print("\n== Query (MCP-focused) ==")
    r = requests.post(f"{base}/query", json=QUERY_REQ_MCP, timeout=15)
    must(r.status_code == 200, f"/query returned 200 (got {r.status_code})")
    data = r.json()
    print(json.dumps(data, indent=2))
    must(data.get("ok") is True, "Query response ok=true (MCP-focused)")
    texts = [x.get("text", "") for x in data.get("results", [])]
    must(any("Person detected" in t for t in texts), "Query returned the ingested MCP fact")

    # 6) Query ACP (VITALS)
    print("\n== Query (ACP-focused) ==")
    r = requests.post(f"{base}/query", json=QUERY_REQ_ACP, timeout=15)
    must(r.status_code == 200, f"/query returned 200 (got {r.status_code})")
    data = r.json()
    print(json.dumps(data, indent=2))
    must(data.get("ok") is True, "Query response ok=true (ACP-focused)")
    texts = [x.get("text", "") for x in data.get("results", [])]
    must(any(("SearchArea" in t) or ("ACP.Intent" in t) for t in texts), "Query returned an ACP-derived fact")

    # 6b) Rerank showcase (bread analogy)
    print("\n== Rerank showcase (bread analogy: rerank OFF vs ON) ==")

    def print_top(resp: Dict[str, Any], label: str) -> None:
        print(f"\n{label} stats:", json.dumps(resp.get("stats", {}), indent=2))
        for x in (resp.get("results") or [])[:5]:
            print(
                f"  #{x.get('rank')} score={x.get('score')} "
                f"id={x.get('id')} meta_sector={(x.get('metadata') or {}).get('sector')} "
                f"text={(x.get('text') or '')[:120]}"
            )

    # OFF
    r = requests.post(f"{base}/query", json=tv["BREAD_QUERY_OFF"], timeout=30)
    must(r.status_code == 200, f"/query bread rerank=off returned 200 (got {r.status_code})")
    off = r.json()
    must(off.get("ok") is True, "Bread query OFF: ok=true")
    must(off.get("stats", {}).get("rerank") is False, "Bread query OFF: stats.rerank=false")
    print_top(off, "BREAD RERANK OFF")

    # ON
    r = requests.post(f"{base}/query", json=tv["BREAD_QUERY_ON"], timeout=60)
    must(r.status_code == 200, f"/query bread rerank=on returned 200 (got {r.status_code})")
    on = r.json()

    if on.get("ok") is not True:
        err = on.get("error") or {}
        code = err.get("code")
        must(code == "RERANK_NOT_CONFIGURED", f"Bread query ON failed with expected code RERANK_NOT_CONFIGURED (got {code!r})")
        print("[WARN] Reranker not configured; skipping bread ranking assertions.")
    else:
        must(on.get("stats", {}).get("rerank") is True, "Bread query ON: stats.rerank=true")
        print_top(on, "BREAD RERANK ON")

        # Our bread corpus includes idempotency_key now, so IDs will be:
        #   schema:corr_id:idempotency_key  => "mcp.v0.2:corr_e2e_001:idem_bread_010"
        target_id = "mcp.v0.2:corr_e2e_001:idem_bread_010"
        results = on.get("results") or []
        ids = [x.get("id") for x in results]
        must(target_id in ids, f"Rerank ON: target doc_id present in results ({target_id})")

        # Stronger: target promoted to top-2 (usually top-1)
        top2_ids = ids[:2]
        must(target_id in top2_ids, f"Rerank ON: target promoted into top-2 (got top2={top2_ids})")

        if ids and ids[0] == target_id:
            must(True, "Rerank ON: target is rank-1 (best match promoted)")
        else:
            print("[WARN] Target is in top-2 but not rank-1. Still demonstrates reranker benefit; tweak decoys if desired.")

    # 7) Dedupe replay (same ACP message)
    print("\n== Dedupe (re-ingest same ACP) ==")
    r = requests.post(f"{base}/ingest", json={"messages": [ACP_GOOD]}, timeout=15)
    must(r.status_code == 200, f"/ingest returned 200 on replay (got {r.status_code})")
    replay = r.json()
    print("Replay Response:", json.dumps(replay, indent=2))

    if "skipped_duplicates" in replay:
        must(replay.get("skipped_duplicates", 0) >= 1, "Replay ingest reports >=1 skipped duplicate")
    if "skipped_duplicates_idem" in replay:
        must(replay.get("skipped_duplicates_idem", 0) >= 1, "Replay ingest reports duplicate_idem >= 1")
    if "deduped" in replay:
        must(replay.get("deduped", 0) == 0, "Replay ingest deduped=0 (nothing accepted)")
    if "vector_stored" in replay:
        must(replay.get("vector_stored", 0) == 0, "Replay ingest vector_stored=0 (no new vectors)")

    # 8) Negative MCP
    print("\n== Negative test (bad MCP) ==")
    r = requests.post(f"{base}/ingest", json={"messages": [MCP_BAD]}, timeout=15)
    must(r.status_code == 422, f"/ingest rejected bad MCP with 422 (got {r.status_code})")
    print("422 detail:", json.dumps(r.json(), indent=2))

    # 9) Negative ACP
    print("\n== Negative test (bad ACP) ==")
    r = requests.post(f"{base}/ingest", json={"messages": [ACP_BAD]}, timeout=15)
    must(r.status_code == 422, f"/ingest rejected bad ACP with 422 (got {r.status_code})")
    print("422 detail:", json.dumps(r.json(), indent=2))

    print("\nAll tests passed.")


if __name__ == "__main__":
    main()
