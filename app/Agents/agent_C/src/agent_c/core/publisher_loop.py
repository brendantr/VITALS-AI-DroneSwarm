from __future__ import annotations

import asyncio
from typing import Optional

from agent_c.clients.publisher import Publisher
from agent_c.storage.store import RunStore


class OutboxPublisher:
    def __init__(self, store: RunStore, publisher: Publisher, poll_s: float = 0.5):
        self.store = store
        self.publisher = publisher
        self.poll_s = poll_s
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except Exception:
                pass
            self._task = None

    async def _loop(self) -> None:
        while True:
            rows = self.store.outbox_peek(limit=20)
            if not rows:
                await asyncio.sleep(self.poll_s)
                continue

            for row in rows:
                res = await self.publisher.publish(row["msg"])
                if res.ok:
                    self.store.outbox_mark_sent(row["id"])
                else:
                    self.store.outbox_mark_failed(row["id"], res.error or "unknown_error")
            await asyncio.sleep(0)
