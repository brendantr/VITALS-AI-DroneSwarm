from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional


def utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _json_dumps(obj: Any) -> str:
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

        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA synchronous=NORMAL;")
        self._conn.execute("PRAGMA busy_timeout=3000;")

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
            self._conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_events_idempotency
                ON events(corr_id, idempotency_key)
                WHERE idempotency_key IS NOT NULL;
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS outbox (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    corr_id TEXT NOT NULL,
                    target TEXT NOT NULL,
                    key TEXT NOT NULL,
                    msg_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_ts TEXT NOT NULL,
                    sent_ts TEXT,
                    error TEXT,
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

    def list_events(self, corr_id: str, limit: int = 200) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM events WHERE corr_id = ? ORDER BY id ASC LIMIT ?",
                (corr_id, int(limit)),
            ).fetchall()
        out: List[Dict[str, Any]] = []
        for r in rows:
            out.append(
                {
                    "id": r["id"],
                    "corr_id": r["corr_id"],
                    "event_id": r["event_id"],
                    "ts": r["ts"],
                    "type": r["type"],
                    "source": json.loads(r["source_json"]),
                    "target": json.loads(r["target_json"]) if r["target_json"] else None,
                    "span_id": r["span_id"],
                    "idempotency_key": r["idempotency_key"],
                    "payload": json.loads(r["payload_json"]),
                }
            )
        return out

    def outbox_enqueue(self, corr_id: str, key: str, target: str, msg: Dict[str, Any]) -> bool:
        now = utc_now_iso()
        with self._lock, self._conn:
            try:
                self._conn.execute(
                    """
                    INSERT INTO outbox (corr_id, target, key, msg_json, status, created_ts)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (corr_id, target, key, _json_dumps(msg), "pending", now),
                )
                return True
            except sqlite3.IntegrityError:
                return False

    def outbox_peek(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM outbox WHERE status = 'pending' ORDER BY id ASC LIMIT ?",
                (int(limit),),
            ).fetchall()
        out = []
        for r in rows:
            out.append(
                {
                    "id": r["id"],
                    "corr_id": r["corr_id"],
                    "target": r["target"],
                    "key": r["key"],
                    "msg": json.loads(r["msg_json"]),
                    "status": r["status"],
                    "created_ts": r["created_ts"],
                }
            )
        return out

    def outbox_mark_sent(self, row_id: int) -> None:
        now = utc_now_iso()
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE outbox SET status='sent', sent_ts=?, error=NULL WHERE id=?",
                (now, int(row_id)),
            )

    def outbox_mark_failed(self, row_id: int, error: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE outbox SET status='failed', error=? WHERE id=?",
                (str(error)[:500], int(row_id)),
            )
