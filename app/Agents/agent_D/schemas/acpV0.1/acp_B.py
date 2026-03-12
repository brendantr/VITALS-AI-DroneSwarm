"""ACP protocol contract for Agent D ingesting retrieval context from Agent B.

Agent B (Retrieval) can publish context summaries and supporting facts to Agent D
to improve planning quality and reduce repeated lookups.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


ACP_VERSION = "0.1"
MESSAGE_TYPE = "retrieval_context_update"


@dataclass(frozen=True)
class ACPEnvelopeB:
    """Transport-level ACP metadata for messages from Agent B."""

    acp_version: str
    source_agent: str
    target_agent: str
    message_type: str
    message_id: str
    sent_at_utc: str


@dataclass(frozen=True)
class ContextItem:
    """One context record returned from Agent B retrieval."""

    context_id: str
    text: str
    score: float | None = None
    tags: list[str] = field(default_factory=list)
    source_event_id: str | None = None


@dataclass(frozen=True)
class RetrievalContextPayload:
    """Payload Agent D receives from Agent B retrieval."""

    retrieved_at_utc: str
    query_id: str | None = None
    mission_id: str | None = None
    summary: str | None = None
    context_items: list[ContextItem] = field(default_factory=list)


@dataclass(frozen=True)
class ACPRetrievalContextMessage:
    envelope: ACPEnvelopeB
    payload: RetrievalContextPayload


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _validate_iso_utc(timestamp: str, field_name: str) -> None:
    _require(bool(timestamp), f"{field_name} is required")
    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be ISO-8601 UTC format") from exc
    _require(
        dt.tzinfo is not None and dt.utcoffset() == timezone.utc.utcoffset(dt),
        f"{field_name} must include UTC offset or Z",
    )


def parse_retrieval_context(raw: dict[str, Any]) -> ACPRetrievalContextMessage:
    """Parse and validate raw ACP retrieval context from Agent B."""

    env_raw = raw["envelope"]
    payload_raw = raw["payload"]

    envelope = ACPEnvelopeB(
        acp_version=str(env_raw["acp_version"]),
        source_agent=str(env_raw["source_agent"]),
        target_agent=str(env_raw["target_agent"]),
        message_type=str(env_raw["message_type"]),
        message_id=str(env_raw["message_id"]),
        sent_at_utc=str(env_raw["sent_at_utc"]),
    )

    _require(envelope.acp_version == ACP_VERSION, "Unsupported ACP version")
    _require(envelope.source_agent == "B", "source_agent must be B")
    _require(envelope.target_agent == "D", "target_agent must be D")
    _require(
        envelope.message_type == MESSAGE_TYPE,
        f"message_type must be {MESSAGE_TYPE}",
    )
    _validate_iso_utc(envelope.sent_at_utc, "envelope.sent_at_utc")

    context_items: list[ContextItem] = []
    for idx, entry in enumerate(payload_raw.get("context_items", [])):
        score_raw = entry.get("score")
        score = float(score_raw) if score_raw is not None else None
        if score is not None:
            _require(0.0 <= score <= 1.0, f"context_items[{idx}].score must be in [0, 1]")
        context_items.append(
            ContextItem(
                context_id=str(entry["context_id"]),
                text=str(entry["text"]),
                score=score,
                tags=[str(t) for t in entry.get("tags", [])],
                source_event_id=(
                    str(entry["source_event_id"]) if entry.get("source_event_id") else None
                ),
            )
        )

    payload = RetrievalContextPayload(
        retrieved_at_utc=str(payload_raw["retrieved_at_utc"]),
        query_id=str(payload_raw["query_id"]) if payload_raw.get("query_id") else None,
        mission_id=str(payload_raw["mission_id"]) if payload_raw.get("mission_id") else None,
        summary=str(payload_raw["summary"]) if payload_raw.get("summary") else None,
        context_items=context_items,
    )
    _validate_iso_utc(payload.retrieved_at_utc, "payload.retrieved_at_utc")

    return ACPRetrievalContextMessage(envelope=envelope, payload=payload)
