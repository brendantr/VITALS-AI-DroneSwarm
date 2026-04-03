from __future__ import annotations

import copy
import sys
from types import SimpleNamespace
from pathlib import Path

import pytest
from shapely.geometry import LineString, Polygon, box


APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


from Agents.Agent_D.CostMaps.pathing.path import build_search_plan, cell_paths_to_centroids
from Agents.Agent_D.CostMaps.pathing_CostMap import PathingCostMap
from Agents.Agent_D.CostMaps.terrain_CostMap import Tile, TerrainCostMapRegistry, build_tile_id
from Agents.Agent_D.OSM_Database.postgis.postgis_handler import _build_feature_records
from Agents.Agent_D.OSM_Database.query.terrain_queries import (
    _build_grid_from_tile_counts,
    _enrich_grid_with_feature_membership,
)
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
    water_cells: set[tuple[int, int]] | None = None,
    searcharea_cells: set[tuple[int, int]] | None = None,
    building_labels: dict[tuple[int, int], list[str] | str] | None = None,
    road_labels: dict[tuple[int, int], list[str] | str] | None = None,
    water_labels: dict[tuple[int, int], list[str] | str] | None = None,
) -> tuple[list[list[Tile]], list[tuple[int, int]]]:
    building_cells = building_cells or set()
    road_cells = road_cells or set()
    water_cells = water_cells or set()
    building_labels = building_labels or {}
    road_labels = road_labels or {}
    water_labels = water_labels or {}
    searcharea_cells = searcharea_cells or {
        (row, col)
        for row in range(rows)
        for col in range(cols)
    }
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
            tile.in_searcharea = (row, col) in searcharea_cells
            tile.contains = {"building": [], "water": [], "highway": []}
            tile.contains_count = {"building": 0, "water": 0, "highway": 0}
            if (row, col) in building_cells:
                labels = building_labels.get((row, col), f"building:{row}:{col}")
                if isinstance(labels, str):
                    labels = [labels]
                tile.contains["building"] = list(labels)
                tile.contains_count["building"] = 1
                tile.total_count += 1
            if (row, col) in road_cells:
                labels = road_labels.get((row, col), f"highway:{row}:{col}:residential")
                if isinstance(labels, str):
                    labels = [labels]
                tile.contains["highway"] = list(labels)
                tile.contains_count["highway"] = 1
                tile.total_count += 1
            if (row, col) in water_cells:
                labels = water_labels.get((row, col), f"water:{row}:{col}")
                if isinstance(labels, str):
                    labels = [labels]
                tile.contains["water"] = list(labels)
                tile.contains_count["water"] = 1
                tile.total_count += 1
            if tile.in_searcharea and tile.total_count > 0:
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
    assert covered == {(0, 0), (0, 2)}
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


def test_build_search_plan_osm_routes_follow_local_road_flow_with_side_excursions():
    road_cells = {
        (1, 0),
        (1, 1),
        (1, 2),
        (1, 3),
        (1, 4),
        (1, 5),
        (2, 2),
        (3, 2),
    }
    building_cells = {
        (2, 1),
        (2, 3),
        (3, 1),
        (3, 3),
    }
    road_labels = {
        (1, 0): ["highway:100:primary"],
        (1, 1): ["highway:100:primary"],
        (1, 2): ["highway:100:primary", "highway:101:residential"],
        (1, 3): ["highway:100:primary"],
        (1, 4): ["highway:100:primary"],
        (1, 5): ["highway:100:primary"],
        (2, 2): ["highway:101:residential"],
        (3, 2): ["highway:101:residential"],
    }
    building_labels = {
        (2, 1): ["building:201"],
        (2, 3): ["building:202"],
        (3, 1): ["building:203"],
        (3, 3): ["building:204"],
    }
    grid, viable = _make_grid(
        terrain_id="osm-flow",
        rows=5,
        cols=7,
        road_cells=road_cells,
        building_cells=building_cells,
        road_labels=road_labels,
        building_labels=building_labels,
    )

    plan = build_search_plan(
        grid,
        drone_positions=[(1, 0)],
        viable_grid_positions=viable,
        num_drones=1,
    )

    route = plan.cell_paths[0]
    first_index = {cell: route.index(cell) for cell in set(route)}
    jumps = [
        max(abs(current[0] - nxt[0]), abs(current[1] - nxt[1]))
        for current, nxt in zip(route, route[1:])
    ]

    assert plan.fallback_mode == "object_search"
    assert set(route) >= road_cells | building_cells
    assert max(jumps) <= 1
    assert first_index[(1, 1)] < first_index[(2, 1)] < first_index[(1, 4)]
    assert first_index[(1, 3)] < first_index[(2, 3)] < first_index[(1, 5)]


def test_build_search_plan_osm_diagonal_roads_remain_one_cluster():
    road_cells = {(0, 0), (1, 1), (2, 2)}
    road_labels = {
        (0, 0): ["highway:310:residential"],
        (1, 1): ["highway:310:residential"],
        (2, 2): ["highway:310:residential"],
    }
    grid, viable = _make_grid(
        terrain_id="diag-road",
        rows=3,
        cols=3,
        road_cells=road_cells,
        road_labels=road_labels,
    )

    plan = build_search_plan(
        grid,
        drone_positions=[(0, 0)],
        viable_grid_positions=viable,
        num_drones=1,
    )

    jumps = [
        max(abs(current[0] - nxt[0]), abs(current[1] - nxt[1]))
        for current, nxt in zip(plan.cell_paths[0], plan.cell_paths[0][1:])
    ]

    assert plan.fallback_mode == "object_search"
    assert set(plan.cell_paths[0]) == road_cells
    assert max(jumps, default=0) <= 1


def test_build_search_plan_fallback_checkerboard_split_rectangular_grid():
    grid, viable = _make_grid(terrain_id="fallback-plan", rows=3, cols=6)

    plan = build_search_plan(
        grid,
        drone_positions=[(0, 0), (2, 5)],
        viable_grid_positions=viable,
        num_drones=2,
    )

    assert plan.fallback_mode == "cell_search"
    assert {cell for cells in plan.cell_paths.values() for cell in cells} == {
        (row, col)
        for row in range(3)
        for col in range(6)
        if (row + col) % 2 == 0
    }
    assert all(cell[1] <= 2 for cell in plan.cell_paths[0])
    assert all(cell[1] >= 3 for cell in plan.cell_paths[1])


def test_build_search_plan_fallback_rescues_empty_band_after_checkerboard_filter():
    grid, viable = _make_grid(terrain_id="fallback-thin", rows=1, cols=2)

    plan = build_search_plan(
        grid,
        drone_positions=[(0, 0), (0, 1)],
        viable_grid_positions=viable,
        num_drones=2,
    )

    assert plan.fallback_mode == "cell_search"
    assert plan.cell_paths[0] == [(0, 0)]
    assert plan.cell_paths[1] == [(0, 1)]


def test_build_search_plan_water_clusters_follow_road_neighborhoods():
    road_cells = {(1, 0), (1, 1), (1, 2)}
    building_cells = {(2, 1)}
    water_cells = {(0, 5), (1, 5)}
    road_labels = {
        (1, 0): ["highway:410:primary"],
        (1, 1): ["highway:410:primary"],
        (1, 2): ["highway:410:primary"],
    }
    building_labels = {(2, 1): ["building:411"]}
    water_labels = {
        (0, 5): ["water:510"],
        (1, 5): ["water:510"],
    }
    grid, viable = _make_grid(
        terrain_id="water-after-road",
        rows=4,
        cols=6,
        road_cells=road_cells,
        building_cells=building_cells,
        water_cells=water_cells,
        road_labels=road_labels,
        building_labels=building_labels,
        water_labels=water_labels,
    )

    plan = build_search_plan(
        grid,
        drone_positions=[(1, 0)],
        viable_grid_positions=viable,
        num_drones=1,
    )

    route = plan.cell_paths[0]
    water_indexes = [index for index, cell in enumerate(route) if cell in water_cells]
    non_water_indexes = [index for index, cell in enumerate(route) if cell in (road_cells | building_cells)]

    assert plan.fallback_mode == "object_search"
    assert water_indexes
    assert max(non_water_indexes) < min(water_indexes)


def test_build_search_plan_multi_drone_keeps_semantic_clusters_single_owner():
    cluster_a_road = {(1, 0), (1, 1), (1, 2)}
    cluster_a_buildings = {(2, 1)}
    cluster_b_road = {(1, 6), (1, 7), (1, 8)}
    cluster_b_buildings = {(2, 7)}
    road_cells = cluster_a_road | cluster_b_road
    building_cells = cluster_a_buildings | cluster_b_buildings
    road_labels = {
        (1, 0): ["highway:601:residential"],
        (1, 1): ["highway:601:residential"],
        (1, 2): ["highway:601:residential"],
        (1, 6): ["highway:701:residential"],
        (1, 7): ["highway:701:residential"],
        (1, 8): ["highway:701:residential"],
    }
    building_labels = {
        (2, 1): ["building:602"],
        (2, 7): ["building:702"],
    }
    grid, viable = _make_grid(
        terrain_id="cluster-owner",
        rows=4,
        cols=10,
        road_cells=road_cells,
        building_cells=building_cells,
        road_labels=road_labels,
        building_labels=building_labels,
    )

    plan = build_search_plan(
        grid,
        drone_positions=[(1, 0), (1, 8)],
        viable_grid_positions=viable,
        num_drones=2,
    )

    route_sets = {drone_id: set(cells) for drone_id, cells in plan.cell_paths.items()}
    cluster_a = cluster_a_road | cluster_a_buildings
    cluster_b = cluster_b_road | cluster_b_buildings

    assert any(cluster_a <= route for route in route_sets.values())
    assert any(cluster_b <= route for route in route_sets.values())
    assert sum(1 for route in route_sets.values() if route & cluster_a) == 1
    assert sum(1 for route in route_sets.values() if route & cluster_b) == 1


def test_build_grid_from_tile_counts_only_marks_nonzero_tiles_as_viable():
    terrain_id = "tile-counts"
    tile_rows = [
        {
            "x_idx": 0,
            "y_idx": 0,
            "tile_polygon": box(0.0, 0.0, 1.0, 1.0),
            "counts": {"building": 1, "water": 0, "highway": 0, "pedestrian_path": 0},
            "total_count": 1,
        },
        {
            "x_idx": 1,
            "y_idx": 0,
            "tile_polygon": box(1.0, 0.0, 2.0, 1.0),
            "counts": {"building": 0, "water": 0, "highway": 0, "pedestrian_path": 0},
            "total_count": 0,
        },
    ]

    grid, viable = _build_grid_from_tile_counts(
        tile_rows,
        search_tags={"building": True, "water": True, "highway": True},
        terrain_id=terrain_id,
    )

    assert grid is not None
    assert viable == [(0, 0)]
    assert grid[0][0].total_count == 1
    assert grid[0][1].total_count == 0


def test_build_feature_records_normalizes_highway_types_and_parses_geometry():
    rows = [
        SimpleNamespace(
            osm_id=7,
            feature_type="pedestrian_path",
            tag_value="footway",
            geom_wkt_4326="LINESTRING(0 0, 1 1)",
        )
    ]

    features = _build_feature_records(rows)

    assert features == [
        {
            "osm_id": 7,
            "feature_type": "highway",
            "tag_value": "footway",
            "geometry": LineString([(0.0, 0.0), (1.0, 1.0)]),
        }
    ]


def test_enrich_grid_with_feature_membership_uses_stable_osm_tokens():
    tile_rows = [
        {
            "x_idx": 0,
            "y_idx": 0,
            "tile_polygon": box(0.0, 0.0, 1.0, 1.0),
            "counts": {"building": 1, "water": 0, "highway": 1, "pedestrian_path": 0},
            "total_count": 2,
        },
        {
            "x_idx": 1,
            "y_idx": 0,
            "tile_polygon": box(1.0, 0.0, 2.0, 1.0),
            "counts": {"building": 0, "water": 0, "highway": 1, "pedestrian_path": 0},
            "total_count": 1,
        },
    ]
    grid, _ = _build_grid_from_tile_counts(
        tile_rows,
        search_tags={"building": True, "water": True, "highway": True},
        terrain_id="stable-membership",
    )
    assert grid is not None

    features = [
        {
            "osm_id": 11,
            "feature_type": "building",
            "tag_value": "house",
            "geometry": Polygon([(0.1, 0.1), (0.8, 0.1), (0.8, 0.8), (0.1, 0.8)]),
        },
        {
            "osm_id": 22,
            "feature_type": "highway",
            "tag_value": "residential",
            "geometry": LineString([(0.0, 0.5), (2.0, 0.5)]),
        },
    ]

    _enrich_grid_with_feature_membership(
        grid,
        feature_rows=features,
        search_tags={"building": True, "water": True, "highway": True},
    )

    assert grid[0][0].contains["building"] == ["building:11"]
    assert grid[0][0].contains["highway"] == ["highway:22:residential"]
    assert grid[0][1].contains["highway"] == ["highway:22:residential"]
