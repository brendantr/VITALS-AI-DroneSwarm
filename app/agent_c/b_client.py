from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx

from agents_common.schema_validator import SchemaValidator


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

    async def ingest(self, payload: Dict[str, Any]) -> BClientResult:  # pragma: no cover
        raise NotImplementedError


class HttpAgentBClient(AgentBClient):
    """
    HTTP client for Agent B.

    Enhancements vs the minimal client:
    - Reuses a single httpx.AsyncClient (connection pooling)
    - Returns status_code on errors
    - Optionally validates AgentB.QueryResponse against shared JSON Schema
      (schemas/agentb.api/v0.1/query_response.json)
    """

    def __init__(
        self,
        base_url: str,
        timeout_s: float = 5.0,
        schema_root: str = "./schemas",
        validate_responses: bool = True,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = httpx.Timeout(timeout_s)
        self._client = httpx.AsyncClient(timeout=self.timeout)

        self._validate_responses = validate_responses
        self._schema_validator = SchemaValidator(schema_root) if validate_responses else None

    async def aclose(self) -> None:
        await self._client.aclose()

    async def health(self) -> BClientResult:
        try:
            r = await self._client.get(f"{self.base_url}/health")
            r.raise_for_status()
            return BClientResult(True, r.json(), status_code=r.status_code)
        except httpx.HTTPStatusError as e:
            return BClientResult(
                False,
                {},
                error=f"AgentB /health HTTP {e.response.status_code}: {e.response.text}",
                status_code=e.response.status_code,
            )
        except Exception as e:
            return BClientResult(False, {}, error=str(e))

    async def query(self, payload: Dict[str, Any]) -> BClientResult:
        try:
            r = await self._client.post(f"{self.base_url}/query", json=payload)
            r.raise_for_status()
            data = r.json()

            # Optional: validate response against shared schema
            if self._schema_validator is not None:
                # Ensure the schema selection works (needs schema + type)
                # Agent B responses should already have these fields.
                errors = []
                for err in self._schema_validator.iter_errors(data):
                    if isinstance(err, Exception):
                        errors.append({"path": "/", "message": str(err)})
                        continue
                    path = "/" + "/".join(str(p) for p in err.path) if getattr(err, "path", None) else "/"
                    errors.append({"path": path, "message": getattr(err, "message", str(err))})

                if errors:
                    return BClientResult(
                        False,
                        data if isinstance(data, dict) else {},
                        error=f"AgentB.QueryResponse schema validation failed: {errors}",
                        status_code=r.status_code,
                    )

            return BClientResult(True, data if isinstance(data, dict) else {"data": data}, status_code=r.status_code)

        except httpx.HTTPStatusError as e:
            return BClientResult(
                False,
                {},
                error=f"AgentB /query HTTP {e.response.status_code}: {e.response.text}",
                status_code=e.response.status_code,
            )
        except Exception as e:
            return BClientResult(False, {}, error=str(e))

    async def ingest(self, payload: Dict[str, Any]) -> BClientResult:
        try:
            r = await self._client.post(f"{self.base_url}/ingest", json=payload)
            r.raise_for_status()
            data = r.json()
            return BClientResult(True, data if isinstance(data, dict) else {"data": data}, status_code=r.status_code)
        except httpx.HTTPStatusError as e:
            return BClientResult(
                False,
                {},
                error=f"AgentB /ingest HTTP {e.response.status_code}: {e.response.text}",
                status_code=e.response.status_code,
            )
        except Exception as e:
            return BClientResult(False, {}, error=str(e))
