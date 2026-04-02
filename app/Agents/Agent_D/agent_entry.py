"""Transport-neutral entrypoint for Agent D ingestion."""

from __future__ import annotations

from typing import Any

from Agents.Agent_D.service import AgentDService


_SERVICE = AgentDService()


def ingest_message(raw: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    return _SERVICE.ingest_message(raw, context=context)


def get_service() -> AgentDService:
    return _SERVICE


def ingest_acp_message(raw: dict[str, Any]) -> dict[str, Any]:
    """Backward-compatible wrapper kept for older imports."""
    return ingest_message(raw)
