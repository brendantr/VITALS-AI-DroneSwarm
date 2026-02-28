from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, ConfigDict
from sentence_transformers import SentenceTransformer
import chromadb
from typing import Any, Dict, List, Optional, Literal
from datetime import datetime, timezone
import uuid
import time

from jsonschema import ValidationError
try:
    from app.Agent.schema_validator import SchemaValidator
except ImportError:
    from schema_validator import SchemaValidator

EMBED_MODEL = "BAAI/bge-small-en-v1.5"
CHROMA_PATH = "./chroma_data"
COLLECTION = "vitals_mission"

app = FastAPI(title="VITALS Agent B (Retrieval & Memory)")

# Load once at startup
model = SentenceTransformer(EMBED_MODEL)
client = chromadb.PersistentClient(path=CHROMA_PATH)
col = client.get_or_create_collection(COLLECTION)

validator = SchemaValidator(schema_root="schemas")

# Optional: reranker placeholder (add later)
reranker = None  # e.g., CrossEncoder("BAAI/bge-reranker-base")


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class IngestRequest(BaseModel):
    messages: List[Dict[str, Any]]
    embed: bool = True  # whether to embed/store in Chroma (still validates either way)


def canonical_text(msg: Dict[str, Any]) -> str:
    """
    Prefer msg['text'] if present. Otherwise build a compact, embedding-friendly string.
    Keep it short and factual.
    """
    if isinstance(msg.get("text"), str) and msg["text"].strip():
        return msg["text"].strip()

    m_type = msg.get("type", "UNKNOWN")
    src = (msg.get("source") or {}).get("component", "UnknownSrc")
    payload = msg.get("payload", {})

    # Lightweight extraction for common fields
    label = payload.get("label") or payload.get("intent_kind") or payload.get("edit_kind") or ""
    sector = payload.get("sector") or (payload.get("area") or {}).get("sector") or ""
    conf = payload.get("confidence")
    lat = (msg.get("geo") or {}).get("lat")
    lon = (msg.get("geo") or {}).get("lon")

    parts = [f"{m_type}", f"from {src}"]
    if label:
        parts.append(f"label={label}")
    if sector:
        parts.append(f"sector={sector}")
    if isinstance(conf, (int, float)):
        parts.append(f"conf={conf:.2f}")
    if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
        parts.append(f"geo=({lat:.6f},{lon:.6f})")

    return " | ".join(parts)


def chroma_metadata(msg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Flatten a few high-value fields for filtering.
    """
    src = msg.get("source") or {}
    payload = msg.get("payload") or {}
    meta: Dict[str, Any] = {
        "schema": msg.get("schema"),
        "type": msg.get("type"),
        "ts": msg.get("ts") or iso_now(),
        "corr_id": msg.get("corr_id"),
        "src_component": src.get("component"),
        "src_instance": src.get("instance"),
    }

    # Common, optional filters
    if "sector" in payload:
        meta["sector"] = payload.get("sector")
    if "label" in payload:
        meta["label"] = payload.get("label")
    if "intent_kind" in payload:
        meta["intent_kind"] = payload.get("intent_kind")
    if isinstance(payload.get("confidence"), (int, float)):
        meta["confidence"] = float(payload["confidence"])

    return {k: v for k, v in meta.items() if v is not None}


@app.get("/health")
def health():
    return {"ok": True, "model": EMBED_MODEL, "collection": COLLECTION, "chroma_path": CHROMA_PATH}


@app.post("/ingest")
def ingest(req: IngestRequest):
    # 1) Validate all messages (fail-fast with clear error)
    for i, msg in enumerate(req.messages):
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
                detail["schema_path"] = [str(x) for x in e.schema_path]
            raise HTTPException(status_code=422, detail=detail)

    # 2) Optionally embed + store in Chroma (you can still validate-only by embed=false)
    if not req.embed:
        return {"ok": True, "validated": len(req.messages), "stored": 0}

    ids, docs, embs, metas = [], [], [], []

    for msg in req.messages:
        event_id = msg.get("event_id") or f"evt_{uuid.uuid4().hex}"
        text = canonical_text(msg)
        emb = model.encode(text, normalize_embeddings=True).tolist()
        meta = chroma_metadata(msg)

        ids.append(event_id)
        docs.append(text)
        embs.append(emb)
        metas.append(meta)

    # Use upsert if available; otherwise add
    if hasattr(col, "upsert"):
        col.upsert(ids=ids, documents=docs, embeddings=embs, metadatas=metas)
    else:
        try:
            col.add(ids=ids, documents=docs, embeddings=embs, metadatas=metas)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Chroma add failed: {e}")

    return {"ok": True, "validated": len(req.messages), "stored": len(ids)}


# -------------------------
# Standardized /query v0.1
# -------------------------

class AgentBQueryRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    # Use schema_ in Python, but keep JSON field name as "schema"
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
    metadata: Dict[str, Any] = Field(default_factory=dict)  # always an object for schema compliance
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

    # If caller requests rerank but reranker is not configured, return a standardized error
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
                "latency_ms": latency_ms
            },
            error={
                "code": "RERANK_NOT_CONFIGURED",
                "message": "rerank=true was requested but no reranker is configured in Agent B.",
                "detail": {}
            }
        )

    try:
        # If rerank is enabled, pull a larger candidate set (k_init) then rerank down to n_results
        initial_k = req.k_init if req.rerank else req.n_results

        q_emb = model.encode(req.query, normalize_embeddings=True).tolist()
        res = col.query(query_embeddings=[q_emb], n_results=initial_k, where=req.where)

        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        ids = res.get("ids", [[]])[0]

        # Optional: Chroma may include distances depending on version/config.
        distances = res.get("distances", [None])[0] if isinstance(res.get("distances"), list) else None

        # Default ranking = Chroma order (nearest first)
        ranked_indices = list(range(len(ids)))

        # Future: apply reranker here (CrossEncoder scoring)
        # if req.rerank and reranker is not None:
        #     pairs = [(req.query, d) for d in docs]
        #     scores = reranker.predict(pairs).tolist()  # higher is better
        #     ranked_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)

        results: List[AgentBQueryResult] = []
        for rank, i in enumerate(ranked_indices[:req.n_results], start=1):
            score_val: Optional[float] = None

            if req.include_scores:
                # If you later add reranker, set score_val to reranker score.
                # For now, optionally expose a rough similarity proxy if distances exist.
                if distances is not None and i < len(distances) and isinstance(distances[i], (int, float)):
                    score_val = 1.0 - float(distances[i])

            meta_out = metas[i] if (req.include_metadata and i < len(metas) and isinstance(metas[i], dict)) else {}

            results.append(AgentBQueryResult(
                rank=rank,
                id=ids[i],
                text=docs[i],
                metadata=meta_out,
                score=score_val
            ))

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
                "rerank": req.rerank,
                "latency_ms": latency_ms
            }
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
            error={"code": "QUERY_FAILED", "message": str(e), "detail": {}}
        )
