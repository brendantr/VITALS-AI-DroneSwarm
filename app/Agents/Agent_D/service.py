from __future__ import annotations

import hashlib
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from Agents.agents_common.schema_validator import SchemaValidator
from Agents.Agent_D.CostMaps.pathing.path import (
    SearchPlan,
    build_search_plan,
    cell_paths_to_centroids,
    insert_point_into_cell_paths,
)
from Agents.Agent_D.CostMaps.pathing_CostMap import PathingCostMap
from Agents.Agent_D.CostMaps.terrain_CostMap import (
    TerrainCostMapRegistry,
    build_tile_id,
    point_to_grid_cell,
)
from Agents.Agent_D.OSM_Database.query.terrain_queries import create_search_area


class AgentDError(RuntimeError):
    pass


class AgentDValidationError(AgentDError):
    pass


class AgentDStateError(AgentDError):
    pass


@dataclass
class NormalizedOperation:
    kind: str
    corr_id: str
    ref_event_id: str
    source_component: str
    polygon_wgs84: list[tuple[float, float]] = field(default_factory=list)
    point: tuple[float, float] | None = None
    point_alt_m: float | None = None
    uav_assignment: int | None = None
    detection: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentDSession:
    corr_id: str
    terrain_id: str
    polygon_wgs84: list[tuple[float, float]]
    grid: list[list[Any]]
    viable_grid_positions: list[tuple[int, int]]
    rtree: Any
    registry: TerrainCostMapRegistry
    raw_cell_paths: dict[int, list[tuple[int, int]]]
    centroid_paths: dict[int, list[Any]]
    drone_start_cells: dict[int, tuple[int, int]]
    fallback_mode: str
    costmap_revision: int = 1
    current_cost_map: PathingCostMap | None = None
    snapshot: dict[str, Any] = field(default_factory=dict)


class AgentDEgress:
    def __init__(
        self,
        *,
        agent_c_url: str | None = None,
        agent_c_api_key: str | None = None,
        agent_b_ingest_url: str | None = None,
        timeout_s: float = 5.0,
    ):
        self.agent_c_url = agent_c_url.rstrip("/") if agent_c_url else None
        self.agent_c_api_key = agent_c_api_key or ""
        self.agent_b_ingest_url = agent_b_ingest_url.rstrip("/") if agent_b_ingest_url else None
        self.timeout_s = timeout_s

    def emit_to_agent_c(self, msg: dict[str, Any]) -> dict[str, Any]:
        if not self.agent_c_url:
            return {"sent": False, "target": "AgentC"}
        headers = {}
        if self.agent_c_api_key:
            headers["x-api-key"] = self.agent_c_api_key
        response = requests.post(
            self.agent_c_url,
            json=msg,
            headers=headers,
            timeout=self.timeout_s,
        )
        response.raise_for_status()
        return {"sent": True, "target": "AgentC", "status_code": response.status_code}

    def emit_to_agent_b(self, msg: dict[str, Any]) -> dict[str, Any]:
        if not self.agent_b_ingest_url:
            return {"sent": False, "target": "AgentB"}
        response = requests.post(
            self.agent_b_ingest_url,
            json={"messages": [msg]},
            timeout=self.timeout_s,
        )
        response.raise_for_status()
        body = response.json() if response.content else {}
        return {"sent": True, "target": "AgentB", "status_code": response.status_code, "body": body}


def _build_default_egress() -> AgentDEgress:
    agent_c_url = (
        os.getenv("AGENT_D_AGENT_C_URL")
        or os.getenv("AGENT_C_PUBLISH_URL")
        or os.getenv("AGENT_C_MESSAGES_URL")
    )
    agent_b_ingest_url = os.getenv("AGENT_D_AGENT_B_INGEST_URL")
    if not agent_b_ingest_url:
        agent_b_base_url = os.getenv("AGENT_B_BASE_URL")
        if agent_b_base_url:
            agent_b_ingest_url = f"{agent_b_base_url.rstrip('/')}/ingest"

    timeout_s = float(os.getenv("AGENT_D_TIMEOUT_S", os.getenv("AGENT_B_TIMEOUT_S", "5.0")))
    return AgentDEgress(
        agent_c_url=agent_c_url,
        agent_c_api_key=os.getenv("AGENT_D_AGENT_C_API_KEY") or os.getenv("AGENT_C_API_KEY"),
        agent_b_ingest_url=agent_b_ingest_url,
        timeout_s=timeout_s,
    )


class AgentDService:
    SEARCH_TAGS = {"building": True, "water": True, "highway": True}

    def __init__(
        self,
        *,
        schema_root: str | Path | None = None,
        egress: AgentDEgress | None = None,
    ):
        schema_root = schema_root or (Path(__file__).resolve().parents[2] / "schemas")
        self.validator = SchemaValidator(schema_root=schema_root)
        self.egress = egress or _build_default_egress()
        self._sessions: dict[str, AgentDSession] = {}
        self._lock = threading.Lock()

    def get_session(self, corr_id: str) -> AgentDSession | None:
        with self._lock:
            return self._sessions.get(str(corr_id))

    def ingest_message(self, raw: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            self.validator.validate(raw)
        except Exception as exc:
            raise AgentDValidationError(str(exc)) from exc

        operation = self._normalize_operation(raw)
        accepted = self._make_status_message(
            corr_id=operation.corr_id,
            ref_event_id=operation.ref_event_id,
            state="approved",
            detail=f"{operation.kind} accepted",
            costmap_revision=None,
        )
        planning = self._make_status_message(
            corr_id=operation.corr_id,
            ref_event_id=operation.ref_event_id,
            state="planning",
            detail=f"{operation.kind} planning",
            costmap_revision=None,
        )
        emitted = {
            "agent_c": [
                self.egress.emit_to_agent_c(accepted),
                self.egress.emit_to_agent_c(planning),
            ],
            "agent_b": [],
        }

        try:
            result = self._execute_operation(operation, context=context or {})
        except Exception as exc:
            failed = self._make_status_message(
                corr_id=operation.corr_id,
                ref_event_id=operation.ref_event_id,
                state="failed",
                detail=str(exc),
                costmap_revision=None,
            )
            emitted["agent_c"].append(self.egress.emit_to_agent_c(failed))
            raise

        compact = self._make_result_message(
            corr_id=operation.corr_id,
            ref_event_id=operation.ref_event_id,
            outcome="success",
            summary=result["summary"],
            artifacts=result["compact_artifacts"],
            costmap_revision=result["costmap_revision"],
            target_component="AgentC",
        )
        completed = self._make_status_message(
            corr_id=operation.corr_id,
            ref_event_id=operation.ref_event_id,
            state="completed",
            detail=result["summary"],
            costmap_revision=result["costmap_revision"],
        )
        detailed = self._make_result_message(
            corr_id=operation.corr_id,
            ref_event_id=operation.ref_event_id,
            outcome="success",
            summary=result["summary"],
            artifacts=result["detailed_artifacts"],
            costmap_revision=result["costmap_revision"],
            target_component="AgentB",
        )

        emitted["agent_c"].append(self.egress.emit_to_agent_c(completed))
        emitted["agent_c"].append(self.egress.emit_to_agent_c(compact))
        emitted["agent_b"].append(self.egress.emit_to_agent_b(detailed))

        return {
            "ok": True,
            "corr_id": operation.corr_id,
            "operation": operation.kind,
            "costmap_revision": result["costmap_revision"],
            "fallback_mode": result["compact_artifacts"]["fallback_mode"],
            "changed_tiles": result["compact_artifacts"]["changed_tiles"],
            "route_updates": result["compact_artifacts"]["route_updates"],
            "result": result,
            "emitted": emitted,
            "compact_result": compact,
            "detailed_result": detailed,
        }

    def _normalize_operation(self, raw: dict[str, Any]) -> NormalizedOperation:
        schema = raw.get("schema")
        corr_id = raw.get("corr_id")
        if not isinstance(corr_id, str) or not corr_id.strip():
            raise AgentDValidationError("Agent D requires a non-empty corr_id")

        if schema == "acp.v0.2":
            msg_type = raw.get("type")
            source = (raw.get("source") or {}).get("component")
            payload = raw.get("payload") or {}
            if msg_type != "ACP.Intent":
                raise AgentDValidationError(f"Unsupported ACP message type for Agent D: {msg_type!r}")
            if source not in {"AgentC", "GUIAdapter"}:
                raise AgentDValidationError(f"Unsupported ACP source for Agent D: {source!r}")

            intent_kind = payload.get("intent_kind")
            if intent_kind == "SearchArea":
                area = payload.get("area") or {}
                polygon = area.get("polygon_wgs84") or []
                if len(polygon) < 3:
                    raise AgentDValidationError("SearchArea requires payload.area.polygon_wgs84 with at least 3 points")
                return NormalizedOperation(
                    kind="search_area_build",
                    corr_id=corr_id,
                    ref_event_id=str(raw["event_id"]),
                    source_component=str(source),
                    polygon_wgs84=[(float(point["lat"]), float(point["lon"])) for point in polygon],
                )
            if intent_kind == "InvestigatePoint":
                point = payload.get("point")
                if not isinstance(point, dict):
                    raise AgentDValidationError("InvestigatePoint requires payload.point")
                assignment = None
                uav_assignment = payload.get("uav_assignment") or {}
                if uav_assignment.get("uav_id") is not None:
                    assignment = self._coerce_drone_id(uav_assignment["uav_id"])
                return NormalizedOperation(
                    kind="gui_poi_insert",
                    corr_id=corr_id,
                    ref_event_id=str(raw["event_id"]),
                    source_component=str(source),
                    point=(float(point["lat"]), float(point["lon"])),
                    point_alt_m=float(point["alt_m"]) if point.get("alt_m") is not None else None,
                    uav_assignment=assignment,
                )
            raise AgentDValidationError(f"Unsupported ACP intent_kind for Agent D: {intent_kind!r}")

        if schema == "mcp.v0.2":
            msg_type = raw.get("type")
            source = (raw.get("source") or {}).get("component")
            geo = raw.get("geo")
            payload = raw.get("payload") or {}
            if msg_type != "MCP.Detection":
                raise AgentDValidationError(f"Unsupported MCP message type for Agent D: {msg_type!r}")
            if source != "AgentA":
                raise AgentDValidationError(f"Unsupported MCP source for Agent D: {source!r}")
            if not isinstance(geo, dict) or geo.get("lat") is None or geo.get("lon") is None:
                raise AgentDValidationError("MCP.Detection requires geo.lat/lon for Agent D mapping updates")
            return NormalizedOperation(
                kind="vision_detection_register",
                corr_id=corr_id,
                ref_event_id=str(raw["event_id"]),
                source_component=str(source),
                point=(float(geo["lat"]), float(geo["lon"])),
                point_alt_m=float(geo["alt_m"]) if geo.get("alt_m") is not None else None,
                detection={
                    "label": payload.get("label"),
                    "confidence": payload.get("confidence"),
                    "track_id": payload.get("track_id"),
                    "tags": list(raw.get("tags") or []),
                },
            )

        raise AgentDValidationError(f"Unsupported schema for Agent D: {schema!r}")

    def _execute_operation(self, operation: NormalizedOperation, context: dict[str, Any]) -> dict[str, Any]:
        if operation.kind == "search_area_build":
            return self._handle_search_area_build(operation, context)
        if operation.kind == "gui_poi_insert":
            return self._handle_gui_poi_insert(operation)
        if operation.kind == "vision_detection_register":
            return self._handle_vision_detection_register(operation)
        raise AgentDValidationError(f"Unsupported normalized operation: {operation.kind!r}")

    def _handle_search_area_build(self, operation: NormalizedOperation, context: dict[str, Any]) -> dict[str, Any]:
        rtree, grid, viable = create_search_area(
            polygon_points=operation.polygon_wgs84,
            search_tags=self.SEARCH_TAGS,
            useOSMX=False,
            maximum_square_size=60,
            minimum_grid_size=8,
        )
        if grid is None or viable is None:
            raise AgentDStateError("Agent D could not build a search area from the provided polygon")

        terrain_id = operation.corr_id
        self._bind_grid_to_terrain(terrain_id, grid)
        registry = TerrainCostMapRegistry(terrain_id=terrain_id, t_tree=rtree)
        registry.register_grid(grid)

        drone_ids, start_cells = self._resolve_drone_starts(grid, context)
        plan = build_search_plan(
            grid,
            drone_positions=[start_cells[drone_id] for drone_id in drone_ids],
            viable_grid_positions=viable,
            num_drones=len(drone_ids),
        )
        raw_cell_paths = self._remap_route_keys(plan.cell_paths, drone_ids)
        centroid_paths = self._remap_route_keys(plan.centroid_paths, drone_ids)
        cost_map = PathingCostMap.from_centroid_paths(
            centroid_paths=centroid_paths,
            terrain_tile_id=terrain_id,
            source="search_area_build",
        )
        registry.add_pathing_cost_map(
            tile_id=terrain_id,
            cost_map=cost_map,
            t_tree_node_id=terrain_id,
            osm_tile=None,
        )

        session = AgentDSession(
            corr_id=operation.corr_id,
            terrain_id=terrain_id,
            polygon_wgs84=list(operation.polygon_wgs84),
            grid=grid,
            viable_grid_positions=list(viable),
            rtree=rtree,
            registry=registry,
            raw_cell_paths=raw_cell_paths,
            centroid_paths=centroid_paths,
            drone_start_cells=start_cells,
            fallback_mode=plan.fallback_mode,
            costmap_revision=1,
            current_cost_map=cost_map,
        )
        session.snapshot = self._build_snapshot(session)
        with self._lock:
            self._sessions[operation.corr_id] = session

        summary = f"Built search area with {len(drone_ids)} drone routes using {plan.fallback_mode}"
        compact_artifacts = {
            "operation": operation.kind,
            "costmap_revision": session.costmap_revision,
            "fallback_mode": session.fallback_mode,
            "changed_tiles": [],
            "route_updates": [
                {
                    "drone_id": drone_id,
                    "waypoint_count": len(session.centroid_paths.get(drone_id, [])),
                }
                for drone_id in sorted(session.centroid_paths)
            ],
        }
        detailed_artifacts = dict(compact_artifacts)
        detailed_artifacts["snapshot"] = session.snapshot
        return {
            "summary": summary,
            "costmap_revision": session.costmap_revision,
            "compact_artifacts": compact_artifacts,
            "detailed_artifacts": detailed_artifacts,
        }

    def _handle_gui_poi_insert(self, operation: NormalizedOperation) -> dict[str, Any]:
        session = self._require_session(operation.corr_id)
        point_cell = self._resolve_point_cell(session, operation.point)
        tile_id = build_tile_id(session.terrain_id, point_cell[0], point_cell[1])
        candidate_ids = [operation.uav_assignment] if operation.uav_assignment is not None else None
        next_paths, drone_id, insert_at = insert_point_into_cell_paths(
            session.raw_cell_paths,
            start_cells=session.drone_start_cells,
            point_cell=point_cell,
            candidate_drone_ids=candidate_ids,
        )
        session.raw_cell_paths = next_paths
        session.centroid_paths = cell_paths_to_centroids(session.grid, session.raw_cell_paths)
        session.costmap_revision += 1
        session.current_cost_map = PathingCostMap.from_centroid_paths(
            centroid_paths=session.centroid_paths,
            terrain_tile_id=session.terrain_id,
            source="gui_poi_insert",
        )
        session.registry.add_dynamic_item(
            tile_id=tile_id,
            item_kind="gui_poi",
            metadata={
                "lat": operation.point[0],
                "lon": operation.point[1],
                "ref_event_id": operation.ref_event_id,
                "source_component": operation.source_component,
            },
            t_tree_node_id=tile_id,
            osm_tile=session.grid[point_cell[0]][point_cell[1]],
        )
        session.registry.add_pathing_cost_map(
            tile_id=session.terrain_id,
            cost_map=session.current_cost_map,
            t_tree_node_id=session.terrain_id,
            osm_tile=None,
        )
        session.snapshot = self._build_snapshot(session)

        summary = f"Inserted GUI POI into drone {drone_id} route at index {insert_at}"
        route_updates = [{"drone_id": drone_id, "inserted_index": insert_at, "tile_id": tile_id}]
        compact_artifacts = {
            "operation": operation.kind,
            "costmap_revision": session.costmap_revision,
            "fallback_mode": session.fallback_mode,
            "changed_tiles": [tile_id],
            "route_updates": route_updates,
        }
        detailed_artifacts = dict(compact_artifacts)
        detailed_artifacts["snapshot"] = session.snapshot
        return {
            "summary": summary,
            "costmap_revision": session.costmap_revision,
            "compact_artifacts": compact_artifacts,
            "detailed_artifacts": detailed_artifacts,
        }

    def _handle_vision_detection_register(self, operation: NormalizedOperation) -> dict[str, Any]:
        session = self._require_session(operation.corr_id)
        point_cell = self._resolve_point_cell(session, operation.point)
        tile_id = build_tile_id(session.terrain_id, point_cell[0], point_cell[1])
        session.costmap_revision += 1
        session.registry.add_dynamic_item(
            tile_id=tile_id,
            item_kind="vision_detection",
            metadata={
                "lat": operation.point[0],
                "lon": operation.point[1],
                "ref_event_id": operation.ref_event_id,
                "source_component": operation.source_component,
                "label": operation.detection.get("label"),
                "confidence": operation.detection.get("confidence"),
                "track_id": operation.detection.get("track_id"),
                "tags": list(operation.detection.get("tags") or []),
            },
            t_tree_node_id=tile_id,
            osm_tile=session.grid[point_cell[0]][point_cell[1]],
        )
        session.snapshot = self._build_snapshot(session)

        summary = f"Registered vision detection on tile {tile_id} without changing routes"
        compact_artifacts = {
            "operation": operation.kind,
            "costmap_revision": session.costmap_revision,
            "fallback_mode": session.fallback_mode,
            "changed_tiles": [tile_id],
            "route_updates": [],
        }
        detailed_artifacts = dict(compact_artifacts)
        detailed_artifacts["snapshot"] = session.snapshot
        return {
            "summary": summary,
            "costmap_revision": session.costmap_revision,
            "compact_artifacts": compact_artifacts,
            "detailed_artifacts": detailed_artifacts,
        }

    def _require_session(self, corr_id: str) -> AgentDSession:
        session = self.get_session(corr_id)
        if session is None:
            raise AgentDStateError(f"No active Agent D session exists for corr_id={corr_id!r}")
        return session

    def _bind_grid_to_terrain(self, terrain_id: str, grid: list[list[Any]]) -> None:
        for row_index, row in enumerate(grid):
            for col_index, tile in enumerate(row):
                tile.row = row_index
                tile.col = col_index
                tile.tile_id = build_tile_id(terrain_id, row_index, col_index)

    def _resolve_drone_starts(self, grid: list[list[Any]], context: dict[str, Any]) -> tuple[list[int], dict[int, tuple[int, int]]]:
        drones = list(context.get("drones") or [])
        fallback_count = max(1, int(context.get("num_drones") or max(len(drones), 4)))
        ordered_defaults = []
        searcharea_cells = []
        for row_index, row in enumerate(grid):
            for col_index, tile in enumerate(row):
                if getattr(tile, "in_searcharea", False):
                    searcharea_cells.append((row_index, col_index))
        searcharea_cells.sort()
        if searcharea_cells:
            for idx in range(fallback_count):
                ordered_defaults.append(searcharea_cells[min(idx, len(searcharea_cells) - 1)])

        if not drones:
            drone_ids = list(range(fallback_count))
            start_cells = {
                drone_id: ordered_defaults[min(idx, len(ordered_defaults) - 1)]
                for idx, drone_id in enumerate(drone_ids)
            }
            return drone_ids, start_cells

        drone_ids = []
        start_cells = {}
        default_index = 0
        for entry in sorted(drones, key=lambda item: self._coerce_drone_id(item.get("drone_id", 0))):
            drone_id = self._coerce_drone_id(entry.get("drone_id", 0))
            lat = entry.get("lat")
            lon = entry.get("lon")
            cell = None
            if lat is not None and lon is not None:
                cell = point_to_grid_cell(grid, float(lat), float(lon))
            if cell is None:
                if not ordered_defaults:
                    raise AgentDStateError("Unable to derive any starting search cells for the available drones")
                cell = ordered_defaults[min(default_index, len(ordered_defaults) - 1)]
                default_index += 1
            drone_ids.append(drone_id)
            start_cells[drone_id] = cell
        return drone_ids, start_cells

    def _resolve_point_cell(self, session: AgentDSession, point: tuple[float, float] | None) -> tuple[int, int]:
        if point is None:
            raise AgentDValidationError("Operation requires a geo point")
        point_cell = point_to_grid_cell(session.grid, point[0], point[1])
        if point_cell is None:
            raise AgentDStateError("The provided point is outside the active mission polygon")
        return point_cell

    def _remap_route_keys(self, route_map: dict[int, Any], drone_ids: list[int]) -> dict[int, Any]:
        remapped = {}
        for idx, drone_id in enumerate(drone_ids):
            remapped[drone_id] = route_map.get(idx, [])
        return remapped

    def _build_snapshot(self, session: AgentDSession) -> dict[str, Any]:
        return {
            "corr_id": session.corr_id,
            "terrain_id": session.terrain_id,
            "costmap_revision": session.costmap_revision,
            "fallback_mode": session.fallback_mode,
            "polygon_wgs84": [
                {"lat": float(lat), "lon": float(lon)}
                for lat, lon in session.polygon_wgs84
            ],
            "drone_start_cells": {
                str(drone_id): {"row": int(cell[0]), "col": int(cell[1])}
                for drone_id, cell in sorted(session.drone_start_cells.items())
            },
            "cell_paths": {
                str(drone_id): [
                    {"row": int(cell[0]), "col": int(cell[1])}
                    for cell in cells
                ]
                for drone_id, cells in sorted(session.raw_cell_paths.items())
            },
            "centroid_paths": {
                str(drone_id): [
                    {"lat": float(point.y), "lon": float(point.x)}
                    for point in points
                ]
                for drone_id, points in sorted(session.centroid_paths.items())
            },
            "cost_map": session.current_cost_map.to_dict() if session.current_cost_map is not None else None,
            "terrain_registry": session.registry.to_dict(),
        }

    def _make_status_message(
        self,
        *,
        corr_id: str,
        ref_event_id: str,
        state: str,
        detail: str,
        costmap_revision: int | None,
    ) -> dict[str, Any]:
        suffix = self._stable_suffix(corr_id, state, ref_event_id, str(costmap_revision))
        return {
            "schema": "acp.v0.2",
            "event_id": f"st-{suffix}",
            "ts": self._iso_now(),
            "type": "ACP.Status",
            "corr_id": corr_id,
            "idempotency_key": f"agentd:{corr_id}:{state}:{costmap_revision if costmap_revision is not None else 'na'}",
            "source": {"system": "VITALS", "component": "AgentD", "instance": "agentd-core"},
            "target": {"component": "AgentC", "instance": "coordinator"},
            "payload": {"ref_event_id": ref_event_id, "state": state, "detail": detail},
        }

    def _make_result_message(
        self,
        *,
        corr_id: str,
        ref_event_id: str,
        outcome: str,
        summary: str,
        artifacts: dict[str, Any],
        costmap_revision: int,
        target_component: str,
    ) -> dict[str, Any]:
        suffix = self._stable_suffix(corr_id, target_component, ref_event_id, str(costmap_revision))
        return {
            "schema": "acp.v0.2",
            "event_id": f"rs-{suffix}",
            "ts": self._iso_now(),
            "type": "ACP.Result",
            "corr_id": corr_id,
            "idempotency_key": f"agentd:{corr_id}:{artifacts.get('operation')}:{costmap_revision}:{target_component.lower()}",
            "source": {"system": "VITALS", "component": "AgentD", "instance": "agentd-core"},
            "target": {"component": target_component, "instance": target_component.lower()},
            "payload": {
                "ref_event_id": ref_event_id,
                "outcome": outcome,
                "summary": summary,
                "artifacts": artifacts,
            },
        }

    def _iso_now(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def _stable_suffix(self, *parts: str) -> str:
        digest = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()
        return digest[:12]

    def _coerce_drone_id(self, value: Any) -> int:
        if isinstance(value, int):
            return value
        text = str(value)
        digits = "".join(ch for ch in text if ch.isdigit())
        if digits:
            return int(digits)
        raise AgentDValidationError(f"Unable to coerce drone identifier from {value!r}")
