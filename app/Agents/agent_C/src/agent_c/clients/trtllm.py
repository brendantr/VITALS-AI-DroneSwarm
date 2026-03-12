from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx

from agent_c.utils.concurrency import AsyncGate


@dataclass
class LLMResult:
    ok: bool
    content: str
    error: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None


class TRTLLMClient:
    def __init__(self, base_url: str, model: str, timeout_s: float, max_concurrency: int = 1):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = httpx.Timeout(timeout_s)
        self.gate = AsyncGate(max_concurrency)

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(2.0)) as client:
                r = await client.get(f"{self.base_url}/health")
                return r.status_code == 200
        except Exception:
            return False

    async def chat(self, messages: list[dict[str, Any]], *, max_tokens: int = 256, temperature: float = 0.0) -> LLMResult:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": float(temperature),
            "max_tokens": int(max_tokens),
        }
        try:
            async with self.gate:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    r = await client.post(f"{self.base_url}/v1/chat/completions", json=payload)
                    r.raise_for_status()
                    raw = r.json()
            content = raw["choices"][0]["message"]["content"]
            return LLMResult(True, content=str(content), raw=raw)
        except Exception as e:
            return LLMResult(False, "", error=str(e))
