# agent_b/storage/ingest_dedupe.py
from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


def utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


@dataclass(frozen=True)
class DedupeDecision:
    accepted: bool
    reason: str  # inserted | duplicate_idem | duplicate_msgid | no_keys


class IngestDedupeStore:
    """
    SQLite-backed dedupe index for Agent B ingest side-effects.

    Dedupe rules:
      - Preferred: (schema, corr_id, idempotency_key) when corr_id and idempotency_key present
      - Fallback:  (schema, msg_id) where msg_id := event_id or query_id
    """

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ingest_seen (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    schema TEXT NOT NULL,
                    corr_id TEXT,
                    idempotency_key TEXT,
                    msg_id TEXT,
                    msg_type TEXT,
                    first_seen_ts TEXT NOT NULL
                );
                """
            )

            self._conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_seen_schema_msgid
                ON ingest_seen(schema, msg_id)
                WHERE msg_id IS NOT NULL;
                """
            )

            self._conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_seen_schema_corr_idem
                ON ingest_seen(schema, corr_id, idempotency_key)
                WHERE corr_id IS NOT NULL AND idempotency_key IS NOT NULL;
                """
            )

    def _exists_idem(self, schema: str, corr_id: str, idempotency_key: str) -> bool:
        row = self._conn.execute(
            """
            SELECT 1
            FROM ingest_seen
            WHERE schema = ? AND corr_id = ? AND idempotency_key = ?
            LIMIT 1
            """,
            (schema, corr_id, idempotency_key),
        ).fetchone()
        return row is not None

    def _exists_msgid(self, schema: str, msg_id: str) -> bool:
        row = self._conn.execute(
            """
            SELECT 1
            FROM ingest_seen
            WHERE schema = ? AND msg_id = ?
            LIMIT 1
            """,
            (schema, msg_id),
        ).fetchone()
        return row is not None

    def accept_once(
        self,
        *,
        schema: str,
        corr_id: Optional[str],
        idempotency_key: Optional[str],
        msg_id: Optional[str],
        msg_type: Optional[str],
    ) -> DedupeDecision:
        if not msg_id and not (corr_id and idempotency_key):
            return DedupeDecision(True, "no_keys")

        with self._lock, self._conn:
            if corr_id and idempotency_key:
                if self._exists_idem(schema, corr_id, idempotency_key):
                    return DedupeDecision(False, "duplicate_idem")
            if msg_id:
                if self._exists_msgid(schema, msg_id):
                    return DedupeDecision(False, "duplicate_msgid")

            try:
                self._conn.execute(
                    """
                    INSERT INTO ingest_seen (schema, corr_id, idempotency_key, msg_id, msg_type, first_seen_ts)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (schema, corr_id, idempotency_key, msg_id, msg_type, utc_now_iso()),
                )
                return DedupeDecision(True, "inserted")
            except sqlite3.IntegrityError:
                if corr_id and idempotency_key and self._exists_idem(schema, corr_id, idempotency_key):
                    return DedupeDecision(False, "duplicate_idem")
                if msg_id and self._exists_msgid(schema, msg_id):
                    return DedupeDecision(False, "duplicate_msgid")
                return DedupeDecision(False, "duplicate_idem")
