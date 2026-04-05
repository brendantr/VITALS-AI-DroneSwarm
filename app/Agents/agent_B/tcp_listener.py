# agent_b/tcp_listener.py
"""
Asyncio TCP server that accepts newline-delimited JSON (NDJSON) connections
from vision-edge's TCPSender on the Jetson Nano.

Each connected client streams one JSON object per line. The listener parses
each line and feeds it through Agent B's existing ingest pipeline (validate,
dedupe, Parquet, ChromaDB) — the same path as POST /ingest.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Callable, Dict, List, Optional

log = logging.getLogger("agent_b.tcp_listener")

# ---------------------
# Configuration
# ---------------------
TCP_ENABLED = os.getenv("VITALS_TCP_ENABLED", "1") == "1"
TCP_HOST = os.getenv("VITALS_TCP_HOST", "0.0.0.0")
TCP_PORT = int(os.getenv("VITALS_TCP_PORT", "9000"))

# Max messages to batch before flushing to the ingest pipeline.
# Keeps ChromaDB/Parquet writes efficient without adding much latency.
BATCH_SIZE = int(os.getenv("VITALS_TCP_BATCH_SIZE", "10"))

# Seconds to wait for more messages before flushing a partial batch.
BATCH_TIMEOUT = float(os.getenv("VITALS_TCP_BATCH_TIMEOUT", "1.0"))

# Per-line size limit (bytes) to guard against malformed mega-lines.
MAX_LINE_BYTES = 256 * 1024  # 256 KB


class TCPIngestListener:
    """
    Runs an asyncio TCP server that accepts NDJSON streams and routes
    parsed messages into a caller-supplied ingest function.
    """

    def __init__(self, ingest_fn: Callable[[List[Dict[str, Any]]], Dict[str, Any]]):
        """
        Parameters
        ----------
        ingest_fn : callable
            Synchronous function with signature ``(messages: list[dict]) -> dict``.
            This will be the same pipeline used by POST /ingest.
        """
        self._ingest_fn = ingest_fn
        self._server: Optional[asyncio.AbstractServer] = None
        self._active_connections: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        if not TCP_ENABLED:
            log.info("TCP listener disabled (VITALS_TCP_ENABLED=0)")
            return
        self._server = await asyncio.start_server(
            self._handle_client, TCP_HOST, TCP_PORT,
        )
        log.info("TCP listener started on %s:%d", TCP_HOST, TCP_PORT)

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            log.info("TCP listener stopped")

    # ------------------------------------------------------------------
    # Connection handler
    # ------------------------------------------------------------------

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
    ) -> None:
        peer = writer.get_extra_info("peername")
        self._active_connections += 1
        log.info("TCP connection from %s (active=%d)", peer, self._active_connections)

        batch: List[Dict[str, Any]] = []

        try:
            while True:
                try:
                    # readline() returns b"" on EOF; raises on connection reset.
                    line = await asyncio.wait_for(
                        reader.readline(), timeout=BATCH_TIMEOUT,
                    )
                except asyncio.TimeoutError:
                    # No data within the timeout window — flush any pending batch.
                    if batch:
                        await self._flush(batch)
                        batch = []
                    continue

                if not line:
                    # EOF — client disconnected.
                    break

                if len(line) > MAX_LINE_BYTES:
                    log.warning("Dropping oversized line (%d bytes) from %s", len(line), peer)
                    continue

                line = line.strip()
                if not line:
                    continue

                try:
                    msg = json.loads(line)
                except json.JSONDecodeError as exc:
                    log.warning("Bad JSON from %s: %s", peer, exc)
                    continue

                if not isinstance(msg, dict):
                    log.warning("Non-object JSON from %s (type=%s)", peer, type(msg).__name__)
                    continue

                batch.append(msg)

                if len(batch) >= BATCH_SIZE:
                    await self._flush(batch)
                    batch = []

        except ConnectionResetError:
            log.info("Connection reset by %s", peer)
        except Exception:
            log.exception("Unexpected error handling %s", peer)
        finally:
            # Flush any remaining messages before closing.
            if batch:
                await self._flush(batch)
            writer.close()
            self._active_connections -= 1
            log.info("TCP connection closed from %s (active=%d)", peer, self._active_connections)

    # ------------------------------------------------------------------
    # Batch flush
    # ------------------------------------------------------------------

    async def _flush(self, batch: List[Dict[str, Any]]) -> None:
        """Run the synchronous ingest function in a thread to avoid blocking the event loop."""
        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(None, self._ingest_fn, batch)
            stored = result.get("vector_stored", 0)
            deduped = result.get("deduped", 0)
            skipped = result.get("skipped_duplicates", 0)
            log.info(
                "TCP batch ingested: %d msgs -> %d deduped, %d stored, %d skipped",
                len(batch), deduped, stored, skipped,
            )
        except Exception:
            log.exception("TCP batch ingest failed (%d msgs)", len(batch))
