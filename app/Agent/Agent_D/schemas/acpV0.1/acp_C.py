"""ACP protocol contract for Agent D ingesting mission intents from Agent C.

Agent C (Coordinator) publishes normalized command intents to Agent D.
This module defines the initial payload schema and validation helpers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


ACP_VERSION = "0.1"
MESSAGE_TYPE = "coordinator_intent"
PRIORITIES = {"low", "normal", "high", "critical"}
INTENT_KINDS = {
    "navigate",
    "reroute",
    "hold_position",
    "return_to_home",
    "inspect_target",
    "land",
}


@dataclass(frozen=True)
class ACPEnvelopeC:
    """Transport-level ACP metadata for messages from Agent C."""

    acp_version: str
    source_agent: str
    target_agent: str
    message_type: str
    message_id: str
    sent_at_utc: str


@dataclass(frozen=True)
class Waypoint:
    lat: float
    lon: float
    alt_m: float | None = None


@dataclass(frozen=True)
class CoordinatorIntent:
    """Single mission intent emitted by Agent C for Agent D."""

    intent_id: str
    intent_kind: str
    priority: str = "normal"
    drone_id: str | None = None
    mission_id: str | None = None
    ttl_seconds: int | None = None
    goal_waypoints: list[Waypoint] = field(default_factory=list)
    constraints: dict[str, Any] = field(default_factory=dict)
    rationale: str | None = None


@dataclass(frozen=True)
class IntentPayload:
    intents: list[CoordinatorIntent] = field(default_factory=list)


@dataclass(frozen=True)
class ACPIntentMessage:
    envelope: ACPEnvelopeC
    payload: IntentPayload


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


def _parse_waypoints(raw_waypoints: list[dict[str, Any]]) -> list[Waypoint]:
    return [
        Waypoint(
            lat=float(point["lat"]),
            lon=float(point["lon"]),
            alt_m=float(point["alt_m"]) if point.get("alt_m") is not None else None,
        )
        for point in raw_waypoints
    ]


def parse_coordinator_intents(raw: dict[str, Any]) -> ACPIntentMessage:
    """Parse and validate raw ACP intents from Agent C."""

    env_raw = raw["envelope"]
    payload_raw = raw["payload"]

    envelope = ACPEnvelopeC(
        acp_version=str(env_raw["acp_version"]),
        source_agent=str(env_raw["source_agent"]),
        target_agent=str(env_raw["target_agent"]),
        message_type=str(env_raw["message_type"]),
        message_id=str(env_raw["message_id"]),
        sent_at_utc=str(env_raw["sent_at_utc"]),
    )

    _require(envelope.acp_version == ACP_VERSION, "Unsupported ACP version")
    _require(envelope.source_agent == "C", "source_agent must be C")
    _require(envelope.target_agent == "D", "target_agent must be D")
    _require(
        envelope.message_type == MESSAGE_TYPE,
        f"message_type must be {MESSAGE_TYPE}",
    )
    _validate_iso_utc(envelope.sent_at_utc, "envelope.sent_at_utc")

    intents: list[CoordinatorIntent] = []
    for idx, entry in enumerate(payload_raw.get("intents", [])):
        intent_kind = str(entry["intent_kind"])
        priority = str(entry.get("priority", "normal"))
        ttl_seconds = (
            int(entry["ttl_seconds"]) if entry.get("ttl_seconds") is not None else None
        )
        _require(
            intent_kind in INTENT_KINDS,
            f"intents[{idx}].intent_kind is not supported",
        )
        _require(priority in PRIORITIES, f"intents[{idx}].priority is invalid")
        if ttl_seconds is not None:
            _require(ttl_seconds > 0, f"intents[{idx}].ttl_seconds must be > 0")
        intents.append(
            CoordinatorIntent(
                intent_id=str(entry["intent_id"]),
                intent_kind=intent_kind,
                priority=priority,
                drone_id=str(entry["drone_id"]) if entry.get("drone_id") else None,
                mission_id=(
                    str(entry["mission_id"]) if entry.get("mission_id") else None
                ),
                ttl_seconds=ttl_seconds,
                goal_waypoints=_parse_waypoints(entry.get("goal_waypoints", [])),
                constraints=dict(entry.get("constraints", {})),
                rationale=str(entry["rationale"]) if entry.get("rationale") else None,
            )
        )

    return ACPIntentMessage(envelope=envelope, payload=IntentPayload(intents=intents))


