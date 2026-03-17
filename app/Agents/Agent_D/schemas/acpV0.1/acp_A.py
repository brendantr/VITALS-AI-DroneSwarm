"""ACP protocol contract for Agent D ingesting obstacle feeds from Agent A.

Agent A (Vision) publishes image-derived obstacle detections to Agent D.
This module defines the initial payload shape and lightweight validation
helpers for Agent D consumers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


ACP_VERSION = "0.1"
MESSAGE_TYPE = "realtime_obstacle_feed"


@dataclass(frozen=True)
class ACPEnvelopeA:
    """Transport-level ACP metadata for messages from Agent A."""

    acp_version: str
    source_agent: str
    target_agent: str
    message_type: str
    message_id: str
    sent_at_utc: str


@dataclass(frozen=True)
class BoundingBox:
    """2D image-space bounding box for the detected object."""

    x_min: float
    y_min: float
    x_max: float
    y_max: float


@dataclass(frozen=True)
class GeoPoint:
    """Estimated geo location for an obstacle."""

    lat: float
    lon: float
    alt_m: float | None = None


@dataclass(frozen=True)
class ObstacleDetection:
    """Single obstacle generated from one processed image."""

    detection_id: str
    label: str
    confidence: float
    bbox: BoundingBox
    geo: GeoPoint | None = None
    severity: str = "medium"
    velocity_mps: float | None = None


@dataclass(frozen=True)
class ObstacleFeedPayload:
    """Domain payload Agent D receives from Agent A."""

    frame_id: str
    camera_id: str
    drone_id: str
    captured_at_utc: str
    detections: list[ObstacleDetection] = field(default_factory=list)


@dataclass(frozen=True)
class ACPObstacleFeedMessage:
    envelope: ACPEnvelopeA
    payload: ObstacleFeedPayload


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


def _parse_bbox(raw: dict[str, Any]) -> BoundingBox:
    bbox = BoundingBox(
        x_min=float(raw["x_min"]),
        y_min=float(raw["y_min"]),
        x_max=float(raw["x_max"]),
        y_max=float(raw["y_max"]),
    )
    _require(bbox.x_min < bbox.x_max, "bbox x_min must be < x_max")
    _require(bbox.y_min < bbox.y_max, "bbox y_min must be < y_max")
    return bbox


def _parse_geo(raw: dict[str, Any] | None) -> GeoPoint | None:
    if raw is None:
        return None
    return GeoPoint(
        lat=float(raw["lat"]),
        lon=float(raw["lon"]),
        alt_m=float(raw["alt_m"]) if raw.get("alt_m") is not None else None,
    )


def parse_obstacle_feed(raw: dict[str, Any]) -> ACPObstacleFeedMessage:
    """Parse and validate raw ACP obstacle feed from Agent A."""

    env_raw = raw["envelope"]
    payload_raw = raw["payload"]

    envelope = ACPEnvelopeA(
        acp_version=str(env_raw["acp_version"]),
        source_agent=str(env_raw["source_agent"]),
        target_agent=str(env_raw["target_agent"]),
        message_type=str(env_raw["message_type"]),
        message_id=str(env_raw["message_id"]),
        sent_at_utc=str(env_raw["sent_at_utc"]),
    )

    _require(envelope.acp_version == ACP_VERSION, "Unsupported ACP version")
    _require(envelope.source_agent == "A", "source_agent must be A")
    _require(envelope.target_agent == "D", "target_agent must be D")
    _require(
        envelope.message_type == MESSAGE_TYPE,
        f"message_type must be {MESSAGE_TYPE}",
    )
    _validate_iso_utc(envelope.sent_at_utc, "envelope.sent_at_utc")

    detections: list[ObstacleDetection] = []
    for idx, entry in enumerate(payload_raw.get("detections", [])):
        bbox = _parse_bbox(entry["bbox"])
        confidence = float(entry["confidence"])
        _require(
            0.0 <= confidence <= 1.0,
            f"detections[{idx}].confidence must be in [0, 1]",
        )
        detections.append(
            ObstacleDetection(
                detection_id=str(entry["detection_id"]),
                label=str(entry["label"]),
                confidence=confidence,
                bbox=bbox,
                geo=_parse_geo(entry.get("geo")),
                severity=str(entry.get("severity", "medium")),
                velocity_mps=(
                    float(entry["velocity_mps"])
                    if entry.get("velocity_mps") is not None
                    else None
                ),
            )
        )

    payload = ObstacleFeedPayload(
        frame_id=str(payload_raw["frame_id"]),
        camera_id=str(payload_raw["camera_id"]),
        drone_id=str(payload_raw["drone_id"]),
        captured_at_utc=str(payload_raw["captured_at_utc"]),
        detections=detections,
    )
    _validate_iso_utc(payload.captured_at_utc, "payload.captured_at_utc")

    return ACPObstacleFeedMessage(envelope=envelope, payload=payload)


