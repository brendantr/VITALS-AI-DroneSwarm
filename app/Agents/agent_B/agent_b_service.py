# agent_b/agent_b_service.py

from __future__ import annotations

import collections
import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Literal

import logging

import re

import chromadb
import torch
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from jsonschema import ValidationError
from pydantic import BaseModel, Field, ConfigDict
from sentence_transformers import SentenceTransformer, CrossEncoder

from agents_common.schema_validator import SchemaValidator
from agent_b.storage.parquet_events import ParquetEventsWriter, ParquetEventsConfig
from agent_b.storage.ingest_dedupe import IngestDedupeStore
from agent_b.tcp_listener import TCPIngestListener

log = logging.getLogger("agent_b.service")


# -------------------------
# Paths (cwd-independent)
# -------------------------
BASE_DIR = Path(__file__).resolve().parents[1]  # .../app

SCHEMA_ROOT = Path(os.getenv("VITALS_SCHEMA_ROOT", str(BASE_DIR / "schemas")))
CHROMA_PATH = os.getenv("VITALS_CHROMA_PATH", str(BASE_DIR / "agent_b" / "chroma_data"))

PARQUET_BASE_DIR = Path(
    os.getenv("VITALS_PARQUET_DIR", str(BASE_DIR / "agent_b" / "data" / "lake" / "events"))
)

INGEST_DEDUPE_DB = Path(
    os.getenv(
        "VITALS_INGEST_DEDUPE_DB",
        str(BASE_DIR / "agent_b" / "data" / "lake" / "ingest_dedupe.db"),
    )
)

DEBUG_META = os.getenv("VITALS_DEBUG_META", "0") == "1"


# -------------------------
# Config
# -------------------------
EMBED_MODEL = os.getenv("VITALS_EMBED_MODEL", "BAAI/bge-small-en-v1.5")
RERANK_MODEL = os.getenv("VITALS_RERANK_MODEL", "BAAI/bge-reranker-base")

COLLECTION = os.getenv("VITALS_CHROMA_COLLECTION", "vitals_mission")
MAX_RERANK_K = int(os.getenv("VITALS_MAX_RERANK_K", "50"))


# -------------------------
# App + singletons
# -------------------------

validator = SchemaValidator(schema_root=SCHEMA_ROOT)

parquet_writer = ParquetEventsWriter(
    config=ParquetEventsConfig(base_dir=PARQUET_BASE_DIR)
)

dedupe_store = IngestDedupeStore(db_path=INGEST_DEDUPE_DB)

model = SentenceTransformer(EMBED_MODEL)

client = chromadb.PersistentClient(path=str(CHROMA_PATH))
col = client.get_or_create_collection(COLLECTION)

reranker: Optional[CrossEncoder]
try:
    reranker = CrossEncoder(
        RERANK_MODEL,
        device="cuda" if torch.cuda.is_available() else "cpu",
    )
except Exception:
    reranker = None


# -------------------------
# TCP listener (receives NDJSON from vision-edge on Jetson)
# -------------------------
# Initialized here; wired to ingest_messages() below via lifespan.
tcp_listener: Optional[TCPIngestListener] = None


@asynccontextmanager
async def _lifespan(application: FastAPI):
    global tcp_listener
    tcp_listener = TCPIngestListener(ingest_fn=ingest_messages)
    await tcp_listener.start()
    yield
    await tcp_listener.stop()


app = FastAPI(title="VITALS Agent B (Retrieval & Memory)", lifespan=_lifespan)


# -------------------------
# Recent detections buffer — allows missionState to poll for new
# MCP.Detection messages and forward them to Agent D in real time.
# -------------------------
_recent_detections: collections.deque = collections.deque(maxlen=500)
_detections_lock = threading.Lock()


def _buffer_detections(messages: List[Dict[str, Any]]) -> None:
    """Store MCP.Detection and MCP.Caption messages in a bounded ring buffer."""
    for msg in messages:
        if msg.get("type") in ("MCP.Detection", "MCP.Caption"):
            with _detections_lock:
                _recent_detections.append(msg)


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class IngestRequest(BaseModel):
    messages: List[Dict[str, Any]]
    embed: bool = True  # if False, only validate + parquet


def canonical_text(msg: Dict[str, Any]) -> str:
    """
    Prefer msg['text'] if present. Otherwise build a compact, embedding-friendly string.
    IMPORTANT: Do NOT mutate msg (ACP additionalProperties=false).
    """
    if isinstance(msg.get("text"), str) and msg["text"].strip():
        return msg["text"].strip()

    m_type = msg.get("type", "UNKNOWN")
    src = (msg.get("source") or {}).get("component", "UnknownSrc")
    payload = msg.get("payload", {}) or {}

    label = payload.get("label") or payload.get("intent_kind") or payload.get("edit_kind") or ""
    sector = payload.get("sector") or (payload.get("area") or {}).get("sector") or ""
    state = payload.get("state") or ""
    outcome = payload.get("outcome") or ""
    detail = payload.get("detail") or ""
    summary = payload.get("summary") or ""
    artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), dict) else {}
    operation = artifacts.get("operation") or ""

    score = payload.get("confidence")
    if score is None:
        score = payload.get("priority")

    lat = (msg.get("geo") or {}).get("lat")
    lon = (msg.get("geo") or {}).get("lon")

    parts = [f"{m_type}", f"from {src}"]
    if label:
        parts.append(f"label={label}")
    if sector:
        parts.append(f"sector={sector}")
    if state:
        parts.append(f"state={state}")
    if outcome:
        parts.append(f"outcome={outcome}")
    if operation:
        parts.append(f"operation={operation}")
    if isinstance(score, (int, float)):
        parts.append(f"score={float(score):.2f}")
    if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
        parts.append(f"geo=({lat:.6f},{lon:.6f})")
    if summary:
        parts.append(f"summary={summary}")
    if detail:
        parts.append(f"detail={detail}")

    return " | ".join(parts)


# -------------------------
# Chroma metadata sanitization
# -------------------------
def _coerce_meta_value(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, (list, dict)):
        return json.dumps(v, separators=(",", ":"), ensure_ascii=False)
    if isinstance(v, (datetime,)):
        return v.isoformat()
    return str(v)


def chroma_metadata(msg: Dict[str, Any]) -> Dict[str, Any]:
    src = msg.get("source") or {}
    payload = msg.get("payload") or {}

    meta_raw: Dict[str, Any] = {
        "schema": msg.get("schema"),
        "type": msg.get("type"),
        "ts": msg.get("ts") or iso_now(),
        "corr_id": msg.get("corr_id"),
        "idempotency_key": msg.get("idempotency_key"),
        "src_component": src.get("component"),
        "src_instance": src.get("instance"),
    }

    if "sector" in payload:
        meta_raw["sector"] = payload.get("sector")
    if "label" in payload:
        meta_raw["label"] = payload.get("label")
    if "intent_kind" in payload:
        meta_raw["intent_kind"] = payload.get("intent_kind")
    if "confidence" in payload:
        meta_raw["confidence"] = payload.get("confidence")
    if "priority" in payload and "confidence" not in payload:
        meta_raw["priority"] = payload.get("priority")
    if "state" in payload:
        meta_raw["state"] = payload.get("state")
    if "outcome" in payload:
        meta_raw["outcome"] = payload.get("outcome")
    if isinstance(payload.get("artifacts"), dict) and "operation" in payload["artifacts"]:
        meta_raw["operation"] = payload["artifacts"].get("operation")

    meta: Dict[str, Any] = {}
    for k, v in meta_raw.items():
        v2 = _coerce_meta_value(v)
        if v2 is not None:
            meta[k] = v2
    return meta


def _debug_check_meta(metas: List[Dict[str, Any]]) -> None:
    if not DEBUG_META:
        return
    for idx, m in enumerate(metas):
        for k, v in m.items():
            if isinstance(v, (list, dict)):
                print(f"[DEBUG_META] meta[{idx}] key={k} has non-scalar type={type(v)} value={v}")


@app.get("/health")
def health():
    from agent_b.tcp_listener import TCP_ENABLED, TCP_HOST, TCP_PORT
    return {
        "ok": True,
        "model": EMBED_MODEL,
        "reranker": RERANK_MODEL if reranker is not None else None,
        "collection": COLLECTION,
        "chroma_path": str(CHROMA_PATH),
        "schema_root": str(SCHEMA_ROOT),
        "parquet_dir": str(PARQUET_BASE_DIR),
        "ingest_dedupe_db": str(INGEST_DEDUPE_DB),
        "cuda_available": torch.cuda.is_available(),
        "tcp_listener": {
            "enabled": TCP_ENABLED,
            "host": TCP_HOST,
            "port": TCP_PORT,
            "active_connections": tcp_listener._active_connections if tcp_listener else 0,
        },
    }


def ingest_messages(
    messages: List[Dict[str, Any]],
    embed: bool = True,
) -> Dict[str, Any]:
    """
    Core ingest pipeline shared by the HTTP endpoint and the TCP listener.

    Validates, deduplicates, writes to Parquet, and optionally embeds + stores
    in ChromaDB. Returns a stats dict. Raises on Parquet/Chroma failures.
    """
    # 1) Validate all messages
    errors: List[Dict[str, Any]] = []
    for i, msg in enumerate(messages):
        try:
            validator.validate(msg)
        except (ValidationError, ValueError) as e:
            detail = {
                "index": i,
                "error": str(e),
                "schema": msg.get("schema"),
                "type": msg.get("type"),
                "event_id": msg.get("event_id"),
            }
            if isinstance(e, ValidationError):
                detail["path"] = [str(x) for x in e.path]
            errors.append(detail)

    # Drop invalid messages (log but don't crash — TCP has no HTTP 422 to return).
    valid_msgs = [m for i, m in enumerate(messages) if not any(e["index"] == i for e in errors)]
    for err in errors:
        log.warning("Validation failed for message %d: %s", err["index"], err["error"])

    validated_count = len(valid_msgs)

    # 2) Dedupe BEFORE side-effects (Parquet/Chroma)
    deduped: List[Dict[str, Any]] = []
    skipped_duplicates = 0
    dup_idem = 0
    dup_msgid = 0

    for msg in valid_msgs:
        schema = msg.get("schema") or "unknown"
        corr_id = msg.get("corr_id")
        idem = msg.get("idempotency_key")
        msg_id = msg.get("event_id") or msg.get("query_id")
        msg_type = msg.get("type")

        decision = dedupe_store.accept_once(
            schema=str(schema),
            corr_id=str(corr_id) if corr_id is not None else None,
            idempotency_key=str(idem) if idem is not None else None,
            msg_id=str(msg_id) if msg_id is not None else None,
            msg_type=str(msg_type) if msg_type is not None else None,
        )

        if decision.accepted:
            deduped.append(msg)
        else:
            skipped_duplicates += 1
            if decision.reason == "duplicate_idem":
                dup_idem += 1
            elif decision.reason == "duplicate_msgid":
                dup_msgid += 1

    if not deduped:
        return {
            "ok": True,
            "validated": validated_count,
            "deduped": 0,
            "skipped_duplicates": skipped_duplicates,
            "skipped_duplicates_idem": dup_idem,
            "skipped_duplicates_msgid": dup_msgid,
            "parquet_written": 0,
            "vector_stored": 0,
            "validation_errors": len(errors),
        }

    # 3) Compute canonical texts ONCE (NO message mutation)
    texts: List[str] = [canonical_text(m) for m in deduped]

    # 4) Mission ID
    mission_id = os.getenv("VITALS_MISSION_ID", "mission_alpha")

    # 5) Write to Parquet first (durable log)
    parquet_written = parquet_writer.append_messages(deduped, mission_id=mission_id, texts=texts)

    # 6) Optionally embed + store in Chroma
    if not embed:
        return {
            "ok": True,
            "validated": validated_count,
            "deduped": len(deduped),
            "skipped_duplicates": skipped_duplicates,
            "skipped_duplicates_idem": dup_idem,
            "skipped_duplicates_msgid": dup_msgid,
            "parquet_written": parquet_written,
            "vector_stored": 0,
            "validation_errors": len(errors),
        }

    ids: List[str] = []
    docs: List[str] = []
    embs: List[List[float]] = []
    metas: List[Dict[str, Any]] = []

    for msg, text in zip(deduped, texts):
        raw_id = msg.get("event_id") or msg.get("query_id")
        if not raw_id:
            continue

        schema_name = msg.get("schema", "unknown")
        corr_id = msg.get("corr_id")
        idem = msg.get("idempotency_key")

        if corr_id and idem:
            doc_id = f"{schema_name}:{corr_id}:{idem}"
        else:
            doc_id = f"{schema_name}:{raw_id}"

        emb = model.encode(text, normalize_embeddings=True).tolist()
        meta = chroma_metadata(msg)

        ids.append(doc_id)
        docs.append(text)
        embs.append(emb)
        metas.append(meta)

    _debug_check_meta(metas)

    if ids:
        if hasattr(col, "upsert"):
            col.upsert(ids=ids, documents=docs, embeddings=embs, metadatas=metas)
        else:
            col.add(ids=ids, documents=docs, embeddings=embs, metadatas=metas)

    vector_stored = len(ids)

    # Buffer MCP.Detection messages for real-time polling by missionState → Agent D
    _buffer_detections(deduped)

    return {
        "ok": True,
        "validated": validated_count,
        "deduped": len(deduped),
        "skipped_duplicates": skipped_duplicates,
        "skipped_duplicates_idem": dup_idem,
        "skipped_duplicates_msgid": dup_msgid,
        "parquet_written": parquet_written,
        "vector_stored": vector_stored,
        "validation_errors": len(errors),
    }


@app.post("/ingest")
def ingest(req: IngestRequest):
    """HTTP endpoint — delegates to the shared ingest_messages() pipeline."""
    try:
        return ingest_messages(req.messages, embed=req.embed)
    except (ValidationError, ValueError) as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/detections/recent")
def get_recent_detections(since: Optional[str] = None):
    """
    Returns buffered MCP.Detection messages, optionally filtered by timestamp.
    Used by missionState to poll for new detections and forward to Agent D.
    """
    with _detections_lock:
        all_detections = list(_recent_detections)

    if since:
        all_detections = [d for d in all_detections if d.get("ts", "") > since]

    return {"ok": True, "detections": all_detections, "count": len(all_detections)}


class GeoUpdateRequest(BaseModel):
    event_id: str
    geo: Dict[str, Any]  # {"lat": float, "lon": float, "alt_m"?: float}


@app.post("/detections/update-geo")
def update_detection_geo(req: GeoUpdateRequest):
    """
    Update the geo coordinates of a stored detection in ChromaDB.
    Used by missionState to correct GPS with real drone telemetry.
    """
    # Find the document in ChromaDB by event_id suffix in the ID
    results = col.get(where={"type": "MCP.Detection"}, include=["metadatas", "documents", "embeddings"])
    target_idx = None
    for i, doc_id in enumerate(results["ids"]):
        if doc_id.endswith(req.event_id):
            target_idx = i
            break

    if target_idx is None:
        raise HTTPException(status_code=404, detail=f"Detection {req.event_id} not found in ChromaDB")

    doc_id = results["ids"][target_idx]
    old_meta = results["metadatas"][target_idx]
    old_doc = results["documents"][target_idx]

    # Update metadata with new geo
    lat = req.geo.get("lat")
    lon = req.geo.get("lon")
    new_meta = dict(old_meta)
    if lat is not None:
        new_meta["geo_lat"] = lat
    if lon is not None:
        new_meta["geo_lon"] = lon

    # Re-generate embedding text with corrected geo
    new_text = old_doc
    if lat is not None and lon is not None:
        # Append or replace geo in the text for better semantic search
        geo_suffix = f" | geo=({lat:.6f},{lon:.6f})"
        if "geo=(" in old_doc:
            new_text = re.sub(r"\s*\|\s*geo=\([^)]+\)", geo_suffix, old_doc)
        else:
            new_text = old_doc.rstrip(".") + geo_suffix

    new_emb = model.encode(new_text, normalize_embeddings=True).tolist()

    col.update(
        ids=[doc_id],
        documents=[new_text],
        embeddings=[new_emb],
        metadatas=[new_meta],
    )

    # Also update the in-memory buffer so Agent D poll gets corrected coords
    with _detections_lock:
        for det in _recent_detections:
            if det.get("event_id") == req.event_id:
                det["geo"] = req.geo
                break

    return {"ok": True, "event_id": req.event_id, "doc_id": doc_id, "geo": req.geo}


# -------------------------
# Standardized /query v0.1
# -------------------------
class AgentBQueryRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    schema_: Literal["agentb.api.v0.1"] = Field("agentb.api.v0.1", alias="schema")
    type: Literal["AgentB.QueryRequest"] = "AgentB.QueryRequest"

    query: str = Field(min_length=1)
    n_results: int = Field(default=8, ge=1, le=100)
    k_init: int = Field(default=50, ge=1, le=500)

    rerank: bool = False
    where: Dict[str, Any] = Field(default_factory=dict)

    include_scores: bool = True
    include_metadata: bool = True

    corr_id: Optional[str] = None
    client: Optional[Dict[str, str]] = None


class AgentBQueryResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rank: int
    id: str
    text: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    score: Optional[float] = None


class AgentBQueryResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    schema_: Literal["agentb.api.v0.1"] = Field("agentb.api.v0.1", alias="schema")
    type: Literal["AgentB.QueryResponse"] = "AgentB.QueryResponse"

    ok: bool
    query_id: str
    ts: str
    corr_id: Optional[str] = None

    results: List[AgentBQueryResult] = Field(default_factory=list)
    stats: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None


@app.post("/query", response_model=AgentBQueryResponse, response_model_by_alias=True)
def query(req: AgentBQueryRequest):
    t0 = time.time()
    query_id = f"q_{uuid.uuid4().hex}"

    if req.rerank and reranker is None:
        latency_ms = (time.time() - t0) * 1000.0
        return AgentBQueryResponse(
            ok=False,
            query_id=query_id,
            ts=iso_now(),
            corr_id=req.corr_id,
            results=[],
            stats={
                "n_results": req.n_results,
                "k_init": req.k_init,
                "rerank": req.rerank,
                "latency_ms": latency_ms,
            },
            error={
                "code": "RERANK_NOT_CONFIGURED",
                "message": "rerank=true was requested but no reranker is configured in Agent B.",
                "detail": {},
            },
        )

    try:
        initial_k = min(req.k_init, MAX_RERANK_K) if req.rerank else req.n_results
        q_emb = model.encode(req.query, normalize_embeddings=True).tolist()

        query_kwargs: Dict[str, Any] = {
            "query_embeddings": [q_emb],
            "n_results": initial_k,
        }
        if req.where:
            query_kwargs["where"] = req.where

        res = col.query(**query_kwargs)

        docs = res.get("documents", [[]])[0] or []
        metas = res.get("metadatas", [[]])[0] or []
        ids = res.get("ids", [[]])[0] or []

        distances = res.get("distances", [None])[0] if isinstance(res.get("distances"), list) else None
        ranked_indices = list(range(len(ids)))

        rerank_scores: Optional[List[float]] = None
        if req.rerank and reranker is not None and docs:
            pairs = [(req.query, d) for d in docs]
            scores = reranker.predict(pairs, batch_size=8, show_progress_bar=False)
            rerank_scores = [float(s) for s in scores]
            ranked_indices = sorted(range(len(rerank_scores)), key=lambda i: rerank_scores[i], reverse=True)

        results: List[AgentBQueryResult] = []
        for rank, i in enumerate(ranked_indices[: req.n_results], start=1):
            score_val: Optional[float] = None

            if req.include_scores:
                if rerank_scores is not None and i < len(rerank_scores):
                    score_val = rerank_scores[i]
                elif distances is not None and i < len(distances) and isinstance(distances[i], (int, float)):
                    score_val = 1.0 - float(distances[i])

            meta_out = metas[i] if (req.include_metadata and i < len(metas) and isinstance(metas[i], dict)) else {}

            results.append(
                AgentBQueryResult(
                    rank=rank,
                    id=ids[i],
                    text=docs[i],
                    metadata=meta_out,
                    score=score_val,
                )
            )

        latency_ms = (time.time() - t0) * 1000.0
        return AgentBQueryResponse(
            ok=True,
            query_id=query_id,
            ts=iso_now(),
            corr_id=req.corr_id,
            results=results,
            stats={
                "n_results": req.n_results,
                "k_init": req.k_init,
                "k_used": initial_k,
                "rerank": req.rerank,
                "rerank_model": RERANK_MODEL if req.rerank else None,
                "latency_ms": latency_ms,
            },
        )

    except Exception as e:
        latency_ms = (time.time() - t0) * 1000.0
        return AgentBQueryResponse(
            ok=False,
            query_id=query_id,
            ts=iso_now(),
            corr_id=req.corr_id,
            results=[],
            stats={"latency_ms": latency_ms},
            error={"code": "QUERY_FAILED", "message": str(e), "detail": {}},
        )
