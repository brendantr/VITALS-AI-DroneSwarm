from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx


@dataclass
class BClientResult:
    ok: bool
    data: Dict[str, Any]
    error: Optional[str] = None
    status_code: Optional[int] = None


class AgentBClient:
    async def health(self) -> BClientResult:  # pragma: no cover
        raise NotImplementedError

    async def query(self, payload: Dict[str, Any]) -> BClientResult:  # pragma: no cover
        raise NotImplementedError


class HttpAgentBClient(AgentBClient):
    def __init__(self, base_url: str, timeout_s: float = 5.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = httpx.Timeout(timeout_s)

    async def health(self) -> BClientResult:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.get(f"{self.base_url}/health")
                r.raise_for_status()
                return BClientResult(True, r.json(), status_code=r.status_code)
        except Exception as e:
            return BClientResult(False, {}, error=str(e))

    async def query(self, payload: Dict[str, Any]) -> BClientResult:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(f"{self.base_url}/query", json=payload)
                r.raise_for_status()
                j = r.json()
                return BClientResult(True, j if isinstance(j, dict) else {"data": j}, status_code=r.status_code)
        except httpx.HTTPStatusError as e:
            return BClientResult(False, {}, error=f"HTTP {e.response.status_code}: {e.response.text}", status_code=e.response.status_code)
        except Exception as e:
            return BClientResult(False, {}, error=str(e))
