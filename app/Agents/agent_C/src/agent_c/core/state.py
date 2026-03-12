from __future__ import annotations

from agent_c.core.models import ACPIntent


def intent_to_text(intent: ACPIntent) -> str:
    p = intent.payload
    parts: list[str] = [f"intent_kind={p.intent_kind.value}", f"priority={p.priority}"]

    if p.area:
        if p.area.sector:
            parts.append(f"sector={p.area.sector}")
        if p.area.polygon_wgs84:
            parts.append(f"polygon_pts={len(p.area.polygon_wgs84)}")

    if p.point:
        parts.append(f"point=({p.point.lat:.6f},{p.point.lon:.6f})")
        if p.point.alt_m is not None:
            parts.append(f"alt_m={p.point.alt_m}")

    if p.uav_assignment and p.uav_assignment.uav_id:
        parts.append(f"uav_id={p.uav_assignment.uav_id}")

    if p.rationale:
        parts.append(f"rationale={p.rationale}")

    return " | ".join(parts)
