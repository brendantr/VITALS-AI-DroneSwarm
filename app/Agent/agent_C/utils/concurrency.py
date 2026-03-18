from __future__ import annotations

import asyncio


class AsyncGate:
    def __init__(self, max_concurrency: int = 1):
        self._sem = asyncio.Semaphore(max(1, int(max_concurrency)))

    async def __aenter__(self):
        await self._sem.acquire()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self._sem.release()
        return False
