# agent_b/storage/parquet_events.py
from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, DefaultDict
from collections import defaultdict

import pyarrow as pa
import pyarrow.parquet as pq


def _parse_iso_ts(ts: Optional[str]) -> Optional[datetime]:
    """Parse ISO8601 timestamps, accepting trailing 'Z'. Returns None if ts is falsy."""
    if not ts or not isinstance(ts, str):
        return None
    if ts.endswith("Z"):
        ts = ts.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(ts)
    except ValueError:
        return None

    # Ensure timezone-aware + normalized to UTC for consistent Parquet typing
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _iso_date(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).date().isoformat()


def _as_str_list(v: Any) -> List[str]:
    if v is None:
        return []
    if isinstance(v, list):
        out: List[str] = []
        for x in v:
            if x is None:
                continue
            out.append(str(x))
        return out
    return [str(v)]


def _as_float_list(v: Any) -> Optional[List[float]]:
    """Convert bbox_xyxy (or similar) to list[float] if present/valid, else None."""
    if v is None or not isinstance(v, list):
        return None
    out: List[float] = []
    for x in v:
        if isinstance(x, (int, float)):
            out.append(float(x))
        else:
            return None
    return out if out else None


def _safe_part_value(value: str) -> str:
    """Filesystem-safe partition value."""
    value = value.strip()
    value = value.replace("/", "_").replace("\\", "_")
    value = re.sub(r"[^a-zA-Z0-9._-]+", "_", value)
    return value or "unknown"


def _canonical_text_fallback(msg: Dict[str, Any]) -> Optional[str]:
    """
    Build a compact, embedding/log-friendly string WITHOUT mutating msg.
    Useful because ACP forbids extra fields like "text" (additionalProperties=false).
    """
    existing = msg.get("text")
    if isinstance(existing, str) and existing.strip():
        return existing.strip()

    m_type = msg.get("type", "UNKNOWN")
    src = (msg.get("source") or {}).get("component", "UnknownSrc")
    payload = msg.get("payload", {}) or {}

    # Common high-value fields across MCP/ACP
    label = payload.get("label") or payload.get("intent_kind") or payload.get("edit_kind") or ""
    sector = payload.get("sector") or (payload.get("area") or {}).get("sector") or ""
    conf = payload.get("confidence") or payload.get("priority")
    geo = msg.get("geo") or {}
    lat = geo.get("lat")
    lon = geo.get("lon")

    parts = [f"{m_type}", f"from {src}"]
    if label:
        parts.append(f"label={label}")
    if sector:
        parts.append(f"sector={sector}")
    if isinstance(conf, (int, float)):
        # conf might be "priority" on ACP.Intent, still useful context
        parts.append(f"score={float(conf):.2f}")
    if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
        parts.append(f"geo=({lat:.6f},{lon:.6f})")

    out = " | ".join(parts).strip()
    return out if out else None


# Stable schema prevents “schema drift” across parquet files/partitions
EVENT_SCHEMA = pa.schema([
    pa.field("date", pa.string()),
    pa.field("mission_id", pa.string()),

    pa.field("schema", pa.string()),
    pa.field("event_id", pa.string()),
    pa.field("ts", pa.timestamp("us", tz="UTC")),
    pa.field("type", pa.string()),

    pa.field("corr_id", pa.string()),
    pa.field("span_id", pa.string()),
    pa.field("priority", pa.int32()),

    pa.field("src_system", pa.string()),
    pa.field("src_component", pa.string()),
    pa.field("src_instance", pa.string()),

    pa.field("lat", pa.float64()),
    pa.field("lon", pa.float64()),
    pa.field("alt_m", pa.float64()),
    pa.field("geo_frame", pa.string()),

    pa.field("tags", pa.list_(pa.string())),
    pa.field("text", pa.string()),

    pa.field("label", pa.string()),
    pa.field("confidence", pa.float64()),
    pa.field("sector", pa.string()),
    pa.field("uav_id", pa.string()),
    pa.field("frame_ts", pa.timestamp("us", tz="UTC")),
    pa.field("bbox_xyxy", pa.list_(pa.float32())),

    pa.field("payload_json", pa.large_string()),
    pa.field("raw_json", pa.large_string()),
])


@dataclass
class ParquetEventsConfig:
    # Default: app/agent_b/data/lake/events (independent of where uvicorn is launched)
    base_dir: Path = Path(
        os.getenv(
            "VITALS_EVENT_LAKE",
            str(Path(__file__).resolve().parents[1] / "data" / "lake" / "events")
        )
    )
    partition_cols: Optional[List[str]] = None
    compression: str = "zstd"

    def __post_init__(self):
        if self.partition_cols is None:
            self.partition_cols = ["date", "mission_id"]


class ParquetEventsWriter:
    """
    Writes a partitioned Parquet "event lake" (append-only).

    True append semantics:
      - For each ingest call, writes unique file(s) per partition:
          base_dir/date=YYYY-MM-DD/mission_id=<id>/part-<uuid>.parquet

    Supports per-schema normalization:
      - mcp.v0.1
      - acp.v0.1
      - agentb.api.v0.1
      - fallback generic
    """

    def __init__(self, config: Optional[ParquetEventsConfig] = None):
        self.config = config or ParquetEventsConfig()
        os.makedirs(self.config.base_dir, exist_ok=True)

    # ---------------------------
    # Normalization entry points
    # ---------------------------

    def normalize_message(self, msg: Dict[str, Any], mission_id: str) -> Dict[str, Any]:
        schema = msg.get("schema")
        if schema == "mcp.v0.1":
            return self.normalize_mcp_message(msg, mission_id=mission_id)
        if schema == "acp.v0.1":
            return self.normalize_acp_message(msg, mission_id=mission_id)
        if schema == "agentb.api.v0.1":
            return self.normalize_agentb_api_message(msg, mission_id=mission_id)
        return self.normalize_generic_message(msg, mission_id=mission_id)

    def normalize_mcp_message(self, msg: Dict[str, Any], mission_id: str) -> Dict[str, Any]:
        schema = msg.get("schema")
        if schema != "mcp.v0.1":
            raise ValueError(f"Expected schema 'mcp.v0.1', got: {schema!r}")

        event_id = msg.get("event_id")
        ts_raw = msg.get("ts")
        ts = _parse_iso_ts(ts_raw)

        if not isinstance(event_id, str) or len(event_id) < 8:
            raise ValueError("Missing/invalid required field: event_id")
        if ts is None:
            raise ValueError(f"Missing/invalid required field: ts ({ts_raw!r})")

        date = _iso_date(ts)

        source = msg.get("source") or {}
        geo = msg.get("geo") or {}
        payload = msg.get("payload") or {}

        corr_id = msg.get("corr_id")
        span_id = msg.get("span_id")
        priority = msg.get("priority", 50)
        tags = _as_str_list(msg.get("tags", []))

        frame_ts = _parse_iso_ts(payload.get("frame_ts")) if isinstance(payload.get("frame_ts"), str) else None
        bbox_xyxy = _as_float_list(payload.get("bbox_xyxy"))

        text = _canonical_text_fallback(msg)

        record: Dict[str, Any] = {
            "date": date,
            "mission_id": mission_id,

            "schema": schema,
            "event_id": event_id,
            "ts": ts,
            "type": msg.get("type"),

            "corr_id": corr_id,
            "span_id": span_id,
            "priority": int(priority) if isinstance(priority, int) else 50,

            "src_system": source.get("system"),
            "src_component": source.get("component"),
            "src_instance": source.get("instance"),

            "lat": geo.get("lat"),
            "lon": geo.get("lon"),
            "alt_m": geo.get("alt_m"),
            "geo_frame": geo.get("frame"),

            "tags": tags,
            "text": text,

            "label": payload.get("label"),
            "confidence": float(payload["confidence"]) if isinstance(payload.get("confidence"), (int, float)) else None,
            "sector": payload.get("sector"),
            "uav_id": payload.get("uav_id"),
            "frame_ts": frame_ts,
            "bbox_xyxy": bbox_xyxy,

            "payload_json": json.dumps(payload, separators=(",", ":"), ensure_ascii=False),
            "raw_json": json.dumps(msg, separators=(",", ":"), ensure_ascii=False),
        }
        return record

    def normalize_acp_message(self, msg: Dict[str, Any], mission_id: str) -> Dict[str, Any]:
        ts_raw = msg.get("ts")
        ts = _parse_iso_ts(ts_raw) or datetime.now(timezone.utc).astimezone(timezone.utc)
        date = _iso_date(ts)

        event_id = msg.get("event_id")
        if not isinstance(event_id, str) or len(event_id) < 8:
            event_id = f"acp_{uuid.uuid4().hex}"

        source = msg.get("source") or {}
        geo = msg.get("geo") or {}
        payload = msg.get("payload") or {}

        tags = _as_str_list(msg.get("tags", []))
        priority = msg.get("priority", 50)

        text = _canonical_text_fallback(msg)

        record: Dict[str, Any] = {
            "date": date,
            "mission_id": mission_id,

            "schema": "acp.v0.1",
            "event_id": event_id,
            "ts": ts,
            "type": msg.get("type"),

            "corr_id": msg.get("corr_id"),
            "span_id": msg.get("span_id"),
            "priority": int(priority) if isinstance(priority, int) else 50,

            "src_system": source.get("system"),
            "src_component": source.get("component"),
            "src_instance": source.get("instance"),

            "lat": geo.get("lat"),
            "lon": geo.get("lon"),
            "alt_m": geo.get("alt_m"),
            "geo_frame": geo.get("frame"),

            "tags": tags,
            "text": text,

            "label": payload.get("label"),
            "confidence": float(payload["confidence"]) if isinstance(payload.get("confidence"), (int, float)) else None,
            "sector": payload.get("sector") or (payload.get("area") or {}).get("sector"),
            "uav_id": (payload.get("uav_assignment") or {}).get("uav_id") if isinstance(payload.get("uav_assignment"), dict) else payload.get("uav_id"),
            "frame_ts": _parse_iso_ts(payload.get("frame_ts")) if isinstance(payload.get("frame_ts"), str) else None,
            "bbox_xyxy": _as_float_list(payload.get("bbox_xyxy")),

            "payload_json": json.dumps(payload, separators=(",", ":"), ensure_ascii=False),
            "raw_json": json.dumps(msg, separators=(",", ":"), ensure_ascii=False),
        }
        return record

    def normalize_agentb_api_message(self, msg: Dict[str, Any], mission_id: str) -> Dict[str, Any]:
        ts_raw = msg.get("ts")
        ts = _parse_iso_ts(ts_raw) or datetime.now(timezone.utc).astimezone(timezone.utc)
        date = _iso_date(ts)

        event_id = msg.get("query_id") or msg.get("event_id")
        if not isinstance(event_id, str) or len(event_id) < 8:
            event_id = f"agentb_{uuid.uuid4().hex}"

        # For QueryRequest, treat query as "text"
        text = msg.get("query") if isinstance(msg.get("query"), str) else _canonical_text_fallback(msg)

        record: Dict[str, Any] = {
            "date": date,
            "mission_id": mission_id,

            "schema": "agentb.api.v0.1",
            "event_id": event_id,
            "ts": ts,
            "type": msg.get("type"),

            "corr_id": msg.get("corr_id"),
            "span_id": msg.get("span_id"),
            "priority": int(msg.get("priority", 50)) if isinstance(msg.get("priority", 50), int) else 50,

            "src_system": None,
            "src_component": "AgentB",
            "src_instance": None,

            "lat": None,
            "lon": None,
            "alt_m": None,
            "geo_frame": None,

            "tags": _as_str_list(msg.get("tags", [])),
            "text": text,

            "label": None,
            "confidence": None,
            "sector": None,
            "uav_id": None,
            "frame_ts": None,
            "bbox_xyxy": None,

            "payload_json": json.dumps(msg, separators=(",", ":"), ensure_ascii=False),
            "raw_json": json.dumps(msg, separators=(",", ":"), ensure_ascii=False),
        }
        return record

    def normalize_generic_message(self, msg: Dict[str, Any], mission_id: str) -> Dict[str, Any]:
        ts_raw = msg.get("ts")
        ts = _parse_iso_ts(ts_raw) or datetime.now(timezone.utc).astimezone(timezone.utc)
        date = _iso_date(ts)

        event_id = msg.get("event_id")
        if not isinstance(event_id, str) or len(event_id) < 8:
            event_id = f"evt_{uuid.uuid4().hex}"

        source = msg.get("source") or {}
        geo = msg.get("geo") or {}
        payload = msg.get("payload") or {}

        text = _canonical_text_fallback(msg)

        record: Dict[str, Any] = {
            "date": date,
            "mission_id": mission_id,

            "schema": msg.get("schema"),
            "event_id": event_id,
            "ts": ts,
            "type": msg.get("type"),

            "corr_id": msg.get("corr_id"),
            "span_id": msg.get("span_id"),
            "priority": int(msg.get("priority", 50)) if isinstance(msg.get("priority", 50), int) else 50,

            "src_system": source.get("system"),
            "src_component": source.get("component"),
            "src_instance": source.get("instance"),

            "lat": geo.get("lat"),
            "lon": geo.get("lon"),
            "alt_m": geo.get("alt_m"),
            "geo_frame": geo.get("frame"),

            "tags": _as_str_list(msg.get("tags", [])),
            "text": text,

            "label": payload.get("label"),
            "confidence": float(payload["confidence"]) if isinstance(payload.get("confidence"), (int, float)) else None,
            "sector": payload.get("sector"),
            "uav_id": payload.get("uav_id"),
            "frame_ts": _parse_iso_ts(payload.get("frame_ts")) if isinstance(payload.get("frame_ts"), str) else None,
            "bbox_xyxy": _as_float_list(payload.get("bbox_xyxy")),

            "payload_json": json.dumps(payload, separators=(",", ":"), ensure_ascii=False),
            "raw_json": json.dumps(msg, separators=(",", ":"), ensure_ascii=False),
        }
        return record

    # ---------------------------
    # True append write path
    # ---------------------------

    def append_messages(self, msgs: List[Dict[str, Any]], mission_id: str) -> int:
        records = [self.normalize_message(m, mission_id=mission_id) for m in msgs]
        self.append_records(records)
        return len(records)

    def append_mcp_messages(self, msgs: List[Dict[str, Any]], mission_id: str) -> int:
        records = [self.normalize_mcp_message(m, mission_id=mission_id) for m in msgs]
        self.append_records(records)
        return len(records)

    def append_records(self, records: List[Dict[str, Any]]) -> None:
        """
        TRUE APPEND:
          - Writes unique parquet file(s) per call.
          - Groups by partition keys (date, mission_id).
          - Never overwrites existing files.
        """
        if not records:
            return

        part_cols = self.config.partition_cols or []
        grouped: DefaultDict[Tuple[str, ...], List[Dict[str, Any]]] = defaultdict(list)

        for r in records:
            key_vals: List[str] = []
            for c in part_cols:
                v = r.get(c)
                if v is None:
                    raise ValueError(f"Record missing partition column {c!r}: {r}")
                key_vals.append(_safe_part_value(str(v)))
            grouped[tuple(key_vals)].append(r)

        for key, rows in grouped.items():
            part_path = self.config.base_dir
            for col_name, val in zip(part_cols, key):
                part_path = part_path / f"{col_name}={val}"
            os.makedirs(part_path, exist_ok=True)

            filename = f"part-{uuid.uuid4().hex}.parquet"
            filepath = part_path / filename

            # Stable schema avoids type drift across files
            table = pa.Table.from_pylist(rows, schema=EVENT_SCHEMA)

            pq.write_table(
                table,
                str(filepath),
                compression=self.config.compression,
                use_dictionary=True,
                write_statistics=True,
            )
