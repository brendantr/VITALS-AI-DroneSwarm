from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest
from shapely.geometry import box


APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


from Agents.Agent_D.CostMaps.pathing.path import build_search_plan, cell_paths_to_centroids
from Agents.Agent_D.CostMaps.pathing_CostMap import PathingCostMap
from Agents.Agent_D.CostMaps.terrain_CostMap import Tile, TerrainCostMapRegistry, build_tile_id
from Agents.Agent_D.service import AgentDService, AgentDSession, AgentDValidationError


class RecordingEgress:
    def __init__(self):
        self.agent_c_messages = []
        self.agent_b_messages = []

    def emit_to_agent_c(self, msg):
        self.agent_c_messages.append(copy.deepcopy(msg))
        return {"sent": True, "target": "AgentC"}

    def emit_to_agent_b(self, msg):
        self.agent_b_messages.append(copy.deepcopy(msg))
        return {"sent": True, "target": "AgentB"}


def _make_grid(
    *,
    terrain_id: str,
    rows: int,
    cols: int,
    building_cells: set[tuple[int, int]] | None = None,
    road_cells: set[tuple[int, int]] | None = None,
) -> tuple[list[list[Tile]], list[tuple[int, int]]]:
    building_cells = building_cells or set()
    road_cells = road_cells or set()
    grid: list[list[Tile]] = []
    viable: list[tuple[int, int]] = []
    for row in range(rows):
        grid_row: list[Tile] = []
        for col in range(cols):
            tile = Tile()
            tile.row = row
            tile.col = col
            tile.tile_id = build_tile_id(terrain_id, row, col)
            tile.polygon = box(float(col), float(row), float(col + 1), float(row + 1))
            tile.in_searcharea = True
            tile.contains = {"building": [], "water": [], "highway": []}
            tile.contains_count = {"building": 0, "water": 0, "highway": 0}
            if (row, col) in building_cells:
                tile.contains["building"] = [f"building-{row}-{col}"]
                tile.contains_count["building"] = 1
                tile.total_count += 1
            if (row, col) in road_cells:
                tile.contains["highway"] = [f"road-{row}-{col}"]
                tile.contains_count["highway"] = 1
                tile.total_count += 1
            if tile.total_count > 0:
                viable.append((row, col))
            grid_row.append(tile)
        grid.append(grid_row)
    return grid, viable


def _search_area_message(corr_id: str = "mission-search") -> dict:
    return {
        "schema": "acp.v0.2",
        "event_id": "evt-search-01",
        "ts": "2026-03-31T16:00:00Z",
        "type": "ACP.Intent",
        "corr_id": corr_id,
        "idempotency_key": f"idem-{corr_id}-search",
        "source": {"system": "VITALS", "component": "AgentC", "instance": "coordinator"},
        "target": {"component": "AgentD", "instance": "agentd-core"},
        "payload": {
            "intent_kind": "SearchArea",
            "priority": 50,
            "area": {
                "polygon_wgs84": [
                    {"lat": 0.0, "lon": 0.0},
                    {"lat": 0.0, "lon": 4.0},
                    {"lat": 1.0, "lon": 4.0},
                    {"lat": 1.0, "lon": 0.0},
                ]
            },
        },
    }


def _poi_message(corr_id: str = "mission-poi", lat: float = 1.5, lon: float = 2.5) -> dict:
    return {
        "schema": "acp.v0.2",
        "event_id": "evt-poi-001",
        "ts": "2026-03-31T16:05:00Z",
        "type": "ACP.Intent",
        "corr_id": corr_id,
        "idempotency_key": f"idem-{corr_id}-poi",
        "source": {"system": "VITALS", "component": "GUIAdapter", "instance": "desktop"},
        "target": {"component": "AgentD", "instance": "agentd-core"},
        "payload": {
            "intent_kind": "InvestigatePoint",
            "priority": 80,
            "point": {"lat": lat, "lon": lon},
            "rationale": "manual point",
        },
    }


def _detection_message(corr_id: str = "mission-detect", *, include_geo: bool = True) -> dict:
    message = {
        "schema": "mcp.v0.2",
        "event_id": "evt-detect1",
        "ts": "2026-03-31T16:10:00Z",
        "type": "MCP.Detection",
        "corr_id": corr_id,
        "idempotency_key": f"idem-{corr_id}-detect",
        "source": {"system": "VITALS", "component": "AgentA", "instance": "drone-2"},
        "payload": {"label": "person", "confidence": 0.91, "track_id": "trk-7"},
        "tags": ["vision", "detection"],
        "text": "person detected",
    }
    if include_geo:
        message["geo"] = {"lat": 1.5, "lon": 1.5}
    return message


def _seed_session(service: AgentDService, corr_id: str = "mission-poi") -> AgentDSession:
    grid, _ = _make_grid(terrain_id=corr_id, rows=2, cols=4)
    raw_cell_paths = {
        1: [(0, 0), (0, 1)],
        2: [(0, 3), (1, 3)],
    }
    centroid_paths = cell_paths_to_centroids(grid, raw_cell_paths)
    registry = TerrainCostMapRegistry(terrain_id=corr_id, t_tree=object())
    registry.register_grid(grid)
    cost_map = PathingCostMap.from_centroid_paths(
        centroid_paths=centroid_paths,
        terrain_tile_id=corr_id,
        source="seed",
    )
    registry.add_pathing_cost_map(
        tile_id=corr_id,
        cost_map=cost_map,
        t_tree_node_id=corr_id,
        osm_tile=None,
    )
    session = AgentDSession(
        corr_id=corr_id,
        terrain_id=corr_id,
        polygon_wgs84=[(0.0, 0.0), (0.0, 4.0), (2.0, 4.0), (2.0, 0.0)],
        grid=grid,
        viable_grid_positions=[],
        rtree=object(),
        registry=registry,
        raw_cell_paths=copy.deepcopy(raw_cell_paths),
        centroid_paths=centroid_paths,
        drone_start_cells={1: (0, 0), 2: (0, 3)},
        fallback_mode="cell_search",
        costmap_revision=1,
        current_cost_map=cost_map,
    )
    session.snapshot = service._build_snapshot(session)
    service._sessions[corr_id] = session
    return session


def test_search_area_build_falls_back_to_cell_search_and_emits_results(monkeypatch):
    terrain_id = "mission-search"
    grid, viable = _make_grid(terrain_id=terrain_id, rows=1, cols=4)

    def fake_create_search_area(**_kwargs):
        return object(), grid, viable

    monkeypatch.setattr("Agents.Agent_D.service.create_search_area", fake_create_search_area)
    egress = RecordingEgress()
    service = AgentDService(schema_root=APP_DIR / "schemas", egress=egress)

    result = service.ingest_message(
        _search_area_message(terrain_id),
        context={
            "drones": [
                {"drone_id": 1, "lat": 0.5, "lon": 0.5},
                {"drone_id": 2, "lat": 0.5, "lon": 3.5},
            ],
            "num_drones": 2,
        },
    )

    session = service.get_session(terrain_id)
    assert result["operation"] == "search_area_build"
    assert result["fallback_mode"] == "cell_search"
    assert session is not None
    assert set(session.raw_cell_paths) == {1, 2}
    covered = {cell for cells in session.raw_cell_paths.values() for cell in cells}
    assert covered == {(0, 0), (0, 1), (0, 2), (0, 3)}
    assert all(session.raw_cell_paths[drone_id] for drone_id in (1, 2))
    assert [msg["type"] for msg in egress.agent_c_messages] == [
        "ACP.Status",
        "ACP.Status",
        "ACP.Status",
        "ACP.Result",
    ]
    assert egress.agent_b_messages[0]["type"] == "ACP.Result"
    assert egress.agent_b_messages[0]["payload"]["artifacts"]["snapshot"]["costmap_revision"] == 1


def test_gui_poi_insert_chooses_nearest_route_and_updates_costmap():
    egress = RecordingEgress()
    service = AgentDService(schema_root=APP_DIR / "schemas", egress=egress)
    session = _seed_session(service, "mission-poi")
    before_paths = copy.deepcopy(session.raw_cell_paths)

    result = service.ingest_message(_poi_message("mission-poi", lat=1.5, lon=2.5))

    updated_session = service.get_session("mission-poi")
    assert result["operation"] == "gui_poi_insert"
    assert result["route_updates"] == [{"drone_id": 2, "inserted_index": 2, "tile_id": "mission-poi:1:2"}]
    assert updated_session is not None
    assert updated_session.costmap_revision == 2
    assert updated_session.raw_cell_paths[1] == before_paths[1]
    assert updated_session.raw_cell_paths[2] == [(0, 3), (1, 3), (1, 2)]

    tile_record = updated_session.registry.tiles["mission-poi:1:2"]
    assert tile_record.dynamic_items[-1]["kind"] == "gui_poi"
    assert updated_session.snapshot["costmap_revision"] == 2


def test_vision_detection_register_updates_costmap_without_mutating_routes():
    egress = RecordingEgress()
    service = AgentDService(schema_root=APP_DIR / "schemas", egress=egress)
    _seed_session(service, "mission-detect")
    before_paths = copy.deepcopy(service.get_session("mission-detect").raw_cell_paths)

    result = service.ingest_message(_detection_message("mission-detect"))

    updated_session = service.get_session("mission-detect")
    assert result["operation"] == "vision_detection_register"
    assert result["route_updates"] == []
    assert updated_session is not None
    assert updated_session.costmap_revision == 2
    assert updated_session.raw_cell_paths == before_paths
    assert updated_session.registry.tiles["mission-detect:1:1"].dynamic_items[-1]["kind"] == "vision_detection"


def test_detection_without_geo_is_rejected():
    service = AgentDService(schema_root=APP_DIR / "schemas", egress=RecordingEgress())
    _seed_session(service, "mission-detect")

    with pytest.raises(AgentDValidationError):
        service.ingest_message(_detection_message("mission-detect", include_geo=False))


def test_parquet_text_canonicalization_surfaces_agent_d_status_and_result_fields():
    pytest.importorskip("pyarrow")
    from Agents.agent_B.storage.parquet_events import _canonical_text_fallback

    status = {
        "schema": "acp.v0.2",
        "event_id": "evt-status1",
        "ts": "2026-03-31T17:00:00Z",
        "type": "ACP.Status",
        "corr_id": "mission-text",
        "source": {"system": "VITALS", "component": "AgentD", "instance": "agentd-core"},
        "payload": {
            "ref_event_id": "evt-search-01",
            "state": "completed",
            "detail": "search_area_build finished and published",
        },
    }
    result = {
        "schema": "acp.v0.2",
        "event_id": "evt-result1",
        "ts": "2026-03-31T17:00:10Z",
        "type": "ACP.Result",
        "corr_id": "mission-text",
        "source": {"system": "VITALS", "component": "AgentD", "instance": "agentd-core"},
        "payload": {
            "ref_event_id": "evt-search-01",
            "outcome": "success",
            "summary": "Built search area and registered costmap",
            "artifacts": {"operation": "search_area_build"},
        },
    }

    status_text = _canonical_text_fallback(status)
    result_text = _canonical_text_fallback(result)

    assert "state=completed" in status_text
    assert "detail=search_area_build finished and published" in status_text
    assert "outcome=success" in result_text
    assert "summary=Built search area and registered costmap" in result_text
    assert "operation=search_area_build" in result_text


def test_parquet_writer_accepts_mcp_v0_2_messages():
    pytest.importorskip("pyarrow")
    from Agents.agent_B.storage.parquet_events import ParquetEventsWriter

    writer = ParquetEventsWriter()
    record = writer.normalize_message(_detection_message("mission-store"), mission_id="mission-store")

    assert record["schema"] == "mcp.v0.2"
    assert record["type"] == "MCP.Detection"
    assert record["text"] == "person detected"


def test_build_search_plan_covers_all_cells_when_osm_returns_no_items():
    grid, viable = _make_grid(terrain_id="plan", rows=2, cols=2)

    plan = build_search_plan(
        grid,
        drone_positions=[(0, 0), (1, 1)],
        viable_grid_positions=viable,
        num_drones=2,
    )

    assert plan.fallback_mode == "cell_search"
    assert {cell for cells in plan.cell_paths.values() for cell in cells} == {
        (0, 0),
        (0, 1),
        (1, 0),
        (1, 1),
    }
