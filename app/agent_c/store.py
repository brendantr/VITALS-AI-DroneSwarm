from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional


def utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _json_dumps(obj: Any) -> str:
    """
    Safe JSON serialization for stored payloads/metadata.
    - ensure_ascii=False keeps logs readable
    - default=str avoids crashes if a non-JSON type sneaks in (e.g., datetime)
    """
    return json.dumps(obj, ensure_ascii=False, default=str)


@dataclass(frozen=True)
class DedupeResult:
    inserted: bool
    reason: str


class RunStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row

        # Concurrency / reliability improvements
        # WAL reduces writer contention; busy_timeout prevents "database is locked" spikes.
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA synchronous=NORMAL;")
        self._conn.execute("PRAGMA busy_timeout=3000;")  # milliseconds

        self._init_schema()

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    corr_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    created_ts TEXT NOT NULL,
                    updated_ts TEXT NOT NULL,
                    intent_json TEXT NOT NULL,
                    context_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                );
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    corr_id TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    ts TEXT NOT NULL,
                    type TEXT NOT NULL,
                    source_json TEXT NOT NULL,
                    target_json TEXT,
                    span_id TEXT,
                    idempotency_key TEXT,
                    payload_json TEXT NOT NULL,
                    UNIQUE(corr_id, event_id)
                );
                """
            )
            # Partial unique index for idempotency_key (SQLite requires an index, not a table constraint).
            self._conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_events_idempotency
                ON events(corr_id, idempotency_key)
                WHERE idempotency_key IS NOT NULL;
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS outbound_dedupe (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    corr_id TEXT NOT NULL,
                    key TEXT NOT NULL,
                    target TEXT NOT NULL,
                    created_ts TEXT NOT NULL,
                    UNIQUE(corr_id, key, target)
                );
                """
            )

    def ensure_run(self, corr_id: str, intent: Dict[str, Any] | None = None, metadata: Dict[str, Any] | None = None) -> None:
        intent = intent or {}
        metadata = metadata or {}
        now = utc_now_iso()
        with self._lock, self._conn:
            row = self._conn.execute("SELECT corr_id, metadata_json FROM runs WHERE corr_id = ?", (corr_id,)).fetchone()
            if row:
                if intent:
                    self._conn.execute(
                        "UPDATE runs SET intent_json = ?, updated_ts = ? WHERE corr_id = ?",
                        (_json_dumps(intent), now, corr_id),
                    )
                if metadata:
                    m = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
                    m.update(metadata)
                    self._conn.execute(
                        "UPDATE runs SET metadata_json = ?, updated_ts = ? WHERE corr_id = ?",
                        (_json_dumps(m), now, corr_id),
                    )
                return

            self._conn.execute(
                """
                INSERT INTO runs (corr_id, state, created_ts, updated_ts, intent_json, context_json, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (corr_id, "proposed", now, now, _json_dumps(intent), _json_dumps({}), _json_dumps(metadata)),
            )

    def get_run(self, corr_id: str) -> Dict[str, Any]:
        with self._lock:
            row = self._conn.execute("SELECT * FROM runs WHERE corr_id = ?", (corr_id,)).fetchone()
        if not row:
            raise KeyError(f"corr_id not found: {corr_id}")
        return {
            "corr_id": row["corr_id"],
            "state": row["state"],
            "created_ts": row["created_ts"],
            "updated_ts": row["updated_ts"],
            "intent": json.loads(row["intent_json"]),
            "context": json.loads(row["context_json"]),
            "metadata": json.loads(row["metadata_json"]),
        }

    def set_state(self, corr_id: str, state: str) -> None:
        now = utc_now_iso()
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE runs SET state = ?, updated_ts = ? WHERE corr_id = ?",
                (state, now, corr_id),
            )

    def update_context(self, corr_id: str, patch: Dict[str, Any]) -> None:
        now = utc_now_iso()
        with self._lock, self._conn:
            row = self._conn.execute("SELECT context_json FROM runs WHERE corr_id = ?", (corr_id,)).fetchone()
            if not row:
                raise KeyError(f"corr_id not found: {corr_id}")
            context = json.loads(row["context_json"])
            context.update(patch)
            self._conn.execute(
                "UPDATE runs SET context_json = ?, updated_ts = ? WHERE corr_id = ?",
                (_json_dumps(context), now, corr_id),
            )

    def append_event_deduped(
        self,
        corr_id: str,
        event_id: str,
        ts_iso: str,
        type_: str,
        source: Dict[str, Any],
        target: Optional[Dict[str, Any]],
        span_id: Optional[str],
        idempotency_key: Optional[str],
        payload: Dict[str, Any],
    ) -> DedupeResult:
        with self._lock, self._conn:
            try:
                self._conn.execute(
                    """
                    INSERT INTO events (corr_id, event_id, ts, type, source_json, target_json, span_id, idempotency_key, payload_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        corr_id,
                        event_id,
                        ts_iso,
                        type_,
                        _json_dumps(source),
                        _json_dumps(target) if target else None,
                        span_id,
                        idempotency_key,
                        _json_dumps(payload),
                    ),
                )
                return DedupeResult(True, "inserted")
            except sqlite3.IntegrityError:
                return DedupeResult(False, "duplicate_event_or_idempotency_key")

    def outbound_once(self, corr_id: str, key: str, target: str) -> bool:
        with self._lock, self._conn:
            try:
                self._conn.execute(
                    """
                    INSERT INTO outbound_dedupe (corr_id, key, target, created_ts)
                    VALUES (?, ?, ?, ?)
                    """,
                    (corr_id, key, target, utc_now_iso()),
                )
                return True
            except sqlite3.IntegrityError:
                return False
