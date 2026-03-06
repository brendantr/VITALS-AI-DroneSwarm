from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx


@dataclass
class PublishResult:
    ok: bool
    error: Optional[str] = None


class Publisher:
    async def publish(self, msg: Dict[str, Any]) -> PublishResult:  # pragma: no cover
        raise NotImplementedError


class HttpPublisher(Publisher):
    def __init__(self, url: str, timeout_s: float = 5.0):
        self.url = url.rstrip("/")
        self.timeout = httpx.Timeout(timeout_s)

    async def publish(self, msg: Dict[str, Any]) -> PublishResult:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(self.url, json=msg)
                r.raise_for_status()
            return PublishResult(True)
        except Exception as e:
            return PublishResult(False, error=str(e))


class NullPublisher(Publisher):
    async def publish(self, msg: Dict[str, Any]) -> PublishResult:
        return PublishResult(True)
