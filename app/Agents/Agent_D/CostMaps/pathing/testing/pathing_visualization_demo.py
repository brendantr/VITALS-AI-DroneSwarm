"""Agent D pathing demo with OSM-style mock features and visualization.

This test script does not require missionState.py. It builds a synthetic
search grid from mock OSM-like geometries (buildings, water, highways), runs
`search_grid_with_drones`, and visualizes destinations and destination types.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import math
from pathlib import Path
import random
import sys

import matplotlib.pyplot as plt
from matplotlib.animation import PillowWriter
from matplotlib.lines import Line2D
from matplotlib.patches import Polygon as MplPolygon
from matplotlib.patches import Circle
from matplotlib.patches import Rectangle
from matplotlib.widgets import Button, CheckButtons, Slider, TextBox
from shapely.geometry import GeometryCollection, LineString, MultiLineString, Point, Polygon
from shapely.ops import unary_union


try:
    from ...pathing.path import search_grid_with_drones
    from ...pathing_CostMap import PathingCostMap
    from ...terrain_CostMap import TerrainCostMapRegistry
except ImportError:  # Script execution fallback.
    APP_DIR = Path(__file__).resolve().parents[5]
    if str(APP_DIR) not in sys.path:
        sys.path.insert(0, str(APP_DIR))
    from Agents.Agent_D.CostMaps.pathing.path import search_grid_with_drones  # noqa: E402
    from Agents.Agent_D.CostMaps.pathing_CostMap import PathingCostMap  # noqa: E402
    from Agents.Agent_D.CostMaps.terrain_CostMap import TerrainCostMapRegistry  # noqa: E402


@dataclass
class DemoTile:
    polygon: Polygon
    in_searcharea: bool
    total_count: int
    contains_count: dict[str, int]
    contains: dict[str, list[str]]


@dataclass
class MockFeature:
    geometry: Polygon | LineString | Point
    tags: dict[str, str]


@dataclass
class BaseStation:
    row: int
    col: int
    x: float
    y: float


@dataclass
class NumericControl:
    name: str
    minimum: int
    maximum: int
    default: int
    value: int
    textbox: TextBox
    minus_button: Button
    plus_button: Button


FEATURE_KEYS = ("building", "water", "highway")
EVENT_TO_WAYPOINT_TYPE = {
    "building": 0,
    "highway": 0,
    "water": 2,  # use loiter type for water event inspections in this demo
    "none": 0,
}
DEFAULT_CELL_METERS = 7


def _generated_feature_counts(feature_level: int) -> tuple[int, int, int]:
    level = max(1, int(feature_level))
    return (
        18 * max(0, level - 1),
        4 * max(0, level - 1),
        max(0, level - 2),
    )


def _extract_lines(geometry) -> list[LineString]:
    if isinstance(geometry, LineString):
        return [geometry]
    if isinstance(geometry, MultiLineString):
        return [line for line in geometry.geoms if isinstance(line, LineString)]
    if isinstance(geometry, GeometryCollection):
        lines: list[LineString] = []
        for geom in geometry.geoms:
            lines.extend(_extract_lines(geom))
        return lines
    return []


def _remove_roads_through_buildings(features: list[MockFeature], margin: float) -> list[MockFeature]:
    building_geoms = [feature.geometry for feature in features if "building" in feature.tags and isinstance(feature.geometry, Polygon)]
    if not building_geoms:
        return features

    blocked_region = unary_union(building_geoms).buffer(margin)
    output: list[MockFeature] = []
    for feature in features:
        if "highway" not in feature.tags or not isinstance(feature.geometry, LineString):
            output.append(feature)
            continue

        clipped = feature.geometry.difference(blocked_region)
        kept_any = False
        for idx, segment in enumerate(_extract_lines(clipped)):
            if segment.length < max(0.8, 4.0 * margin):
                continue
            tags = dict(feature.tags)
            if idx > 0:
                tags["highway"] = f"{tags['highway']}_seg{idx + 1}"
            output.append(MockFeature(segment, tags))
            kept_any = True

        if not kept_any:
            continue
    return output


def _feature_kind(feature: MockFeature) -> str:
    if "building" in feature.tags:
        return "building"
    if "water" in feature.tags:
        return "water"
    if "highway" in feature.tags:
        return "highway"
    return "other"


def _spacing_geometry(feature: MockFeature, road_width: float):
    if _feature_kind(feature) == "highway":
        # Treat roads as narrow corridors so spacing checks reflect an actual road footprint.
        return feature.geometry.buffer(max(0.05, road_width), cap_style=2, join_style=2)
    return feature.geometry


def _is_spacing_valid(candidate, accepted: list, min_gap_cells: float) -> bool:
    for existing in accepted:
        if candidate.intersects(existing):
            return False
        if candidate.distance(existing) < min_gap_cells:
            return False
    return True


def _enforce_non_overlapping_spacing(
    features: list[MockFeature],
    min_gap_cells: float,
    road_width: float,
) -> list[MockFeature]:
    """Ensure features do not overlap and keep at least one-cell spacing."""
    priority = {"building": 0, "water": 1, "highway": 2, "other": 3}
    ordered = sorted(enumerate(features), key=lambda item: (priority.get(_feature_kind(item[1]), 3), item[0]))

    accepted_features: list[MockFeature] = []
    accepted_spacing_geoms = []

    for _idx, feature in ordered:
        kind = _feature_kind(feature)
        if kind != "highway":
            candidate = _spacing_geometry(feature, road_width=road_width)
            if _is_spacing_valid(candidate, accepted_spacing_geoms, min_gap_cells=min_gap_cells):
                accepted_features.append(feature)
                accepted_spacing_geoms.append(candidate)
            continue

        # For roads, keep non-conflicting segments instead of dropping entire road objects.
        forbidden = unary_union([geom.buffer(min_gap_cells) for geom in accepted_spacing_geoms]) if accepted_spacing_geoms else None
        road_geom = feature.geometry
        if forbidden is not None and not forbidden.is_empty:
            road_geom = road_geom.difference(forbidden)

        kept_segments = _extract_lines(road_geom)
        for seg_index, segment in enumerate(kept_segments):
            if segment.length < max(1.0, min_gap_cells):
                continue
            seg_feature = MockFeature(segment, dict(feature.tags))
            if seg_index > 0:
                seg_feature.tags["highway"] = f"{seg_feature.tags['highway']}_clip{seg_index + 1}"
            candidate = _spacing_geometry(seg_feature, road_width=road_width)
            if not _is_spacing_valid(candidate, accepted_spacing_geoms, min_gap_cells=min_gap_cells):
                continue
            accepted_features.append(seg_feature)
            accepted_spacing_geoms.append(candidate)

    # Keep stable drawing order after filtering.
    return sorted(
        accepted_features,
        key=lambda feature: {"highway": 2, "building": 0, "water": 1}.get(_feature_kind(feature), 3),
    )


def _create_mock_features(
    scale: float = 1.0,
    feature_level: int = 1,
    extra_buildings_delta: int = 0,
    extra_water_delta: int = 0,
    extra_roads_delta: int = 0,
    include_base_items: bool = True,
) -> list[MockFeature]:
    """Create deterministic OSM-like objects used to populate tiles."""

    def _scaled(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
        return [(x * scale, y * scale) for (x, y) in points]

    features: list[MockFeature] = []
    if include_base_items:
        features = [
            # Larger buildings
            MockFeature(Polygon(_scaled([(2.0, 2.0), (3.1, 2.0), (3.1, 3.2), (2.0, 3.2)])), {"building": "school"}),
            MockFeature(Polygon(_scaled([(5.1, 6.2), (6.2, 6.2), (6.2, 7.4), (5.1, 7.4)])), {"building": "residential_a"}),
            MockFeature(Polygon(_scaled([(8.2, 3.0), (9.2, 3.0), (9.2, 4.1), (8.2, 4.1)])), {"building": "hospital"}),
            MockFeature(Polygon(_scaled([(10.3, 8.8), (11.3, 8.8), (11.3, 9.9), (10.3, 9.9)])), {"building": "warehouse"}),
            # Smaller buildings for denser multi-drone testing
            MockFeature(Polygon(_scaled([(1.7, 5.0), (2.2, 5.0), (2.2, 5.5), (1.7, 5.5)])), {"building": "shed_1"}),
            MockFeature(Polygon(_scaled([(2.8, 9.4), (3.3, 9.4), (3.3, 9.9), (2.8, 9.9)])), {"building": "shed_2"}),
            MockFeature(Polygon(_scaled([(4.2, 4.0), (4.8, 4.0), (4.8, 4.6), (4.2, 4.6)])), {"building": "clinic_annex"}),
            MockFeature(Polygon(_scaled([(6.9, 2.5), (7.5, 2.5), (7.5, 3.1), (6.9, 3.1)])), {"building": "substation"}),
            MockFeature(Polygon(_scaled([(7.2, 10.0), (7.8, 10.0), (7.8, 10.6), (7.2, 10.6)])), {"building": "apartment_a"}),
            MockFeature(Polygon(_scaled([(8.7, 11.0), (9.3, 11.0), (9.3, 11.6), (8.7, 11.6)])), {"building": "apartment_b"}),
            MockFeature(Polygon(_scaled([(10.9, 4.8), (11.4, 4.8), (11.4, 5.3), (10.9, 5.3)])), {"building": "office_small"}),
            MockFeature(Polygon(_scaled([(11.8, 2.3), (12.3, 2.3), (12.3, 2.8), (11.8, 2.8)])), {"building": "garage_east"}),
            MockFeature(Polygon(_scaled([(12.0, 6.8), (12.5, 6.8), (12.5, 7.3), (12.0, 7.3)])), {"building": "storefront"}),
            MockFeature(Polygon(_scaled([(3.7, 11.0), (4.2, 11.0), (4.2, 11.5), (3.7, 11.5)])), {"building": "garage_north"}),
            # Water
            MockFeature(Polygon(_scaled([(3.6, 7.8), (5.8, 7.8), (5.8, 10.1), (3.6, 10.1)])), {"water": "pond_main"}),
            MockFeature(Polygon(_scaled([(8.8, 7.4), (11.2, 7.4), (11.2, 8.5), (8.8, 8.5)])), {"water": "riverbank_west"}),
            MockFeature(Polygon(_scaled([(6.2, 11.7), (7.1, 11.7), (7.1, 12.3), (6.2, 12.3)])), {"water": "retention_1"}),
            MockFeature(Polygon(_scaled([(12.2, 10.8), (13.0, 10.8), (13.0, 11.5), (12.2, 11.5)])), {"water": "retention_2"}),
            # Highways / roads
            MockFeature(LineString(_scaled([(0.9, 1.3), (5.8, 1.6), (10.6, 2.0), (13.2, 2.4)])), {"highway": "primary"}),
            MockFeature(LineString(_scaled([(1.1, 12.9), (6.5, 9.3), (13.0, 6.6)])), {"highway": "secondary"}),
            MockFeature(LineString(_scaled([(6.3, 0.8), (6.3, 13.3)])), {"highway": "residential"}),
            MockFeature(LineString(_scaled([(2.0, 6.0), (12.8, 6.0)])), {"highway": "service"}),
        ]

    # Scale-up features for larger drone counts: more small buildings/water and extra roads.
    rng = random.Random(9000 + feature_level)
    if include_base_items:
        base_extra_buildings, base_extra_water, base_extra_roads = _generated_feature_counts(feature_level)
    else:
        base_extra_buildings, base_extra_water, base_extra_roads = (0, 0, 0)
    extra_buildings = max(0, base_extra_buildings + int(extra_buildings_delta))
    extra_water = max(0, base_extra_water + int(extra_water_delta))
    extra_roads = max(0, base_extra_roads + int(extra_roads_delta))

    for i in range(extra_buildings):
        cx = rng.uniform(1.0, 13.0)
        cy = rng.uniform(1.0, 13.0)
        w = rng.uniform(0.22, 0.55)
        h = rng.uniform(0.22, 0.55)
        features.append(
            MockFeature(
                Polygon(_scaled([(cx - w, cy - h), (cx + w, cy - h), (cx + w, cy + h), (cx - w, cy + h)])),
                {"building": f"generated_{i + 1}"},
            )
        )

    for i in range(extra_water):
        cx = rng.uniform(1.2, 12.8)
        cy = rng.uniform(1.2, 12.8)
        w = rng.uniform(0.35, 0.9)
        h = rng.uniform(0.25, 0.7)
        features.append(
            MockFeature(
                Polygon(_scaled([(cx - w, cy - h), (cx + w, cy - h), (cx + w, cy + h), (cx - w, cy + h)])),
                {"water": f"generated_{i + 1}"},
            )
        )

    for i in range(extra_roads):
        y = 2.0 + (i * (10.0 / max(1, extra_roads)))
        features.append(
            MockFeature(
                LineString(_scaled([(0.8, y), (6.8, y + rng.uniform(-0.6, 0.6)), (13.2, y + rng.uniform(-0.6, 0.6))])),
                {"highway": f"aux_{i + 1}"},
            )
        )
    features = _remove_roads_through_buildings(features, margin=0.06 * scale)
    # Enforce one-cell spacing and no overlaps across buildings/water/roads.
    return _enforce_non_overlapping_spacing(
        features,
        min_gap_cells=1.0,
        road_width=0.18 * scale,
    )


def _dominant_event(tile: DemoTile) -> str:
    if tile.total_count <= 0:
        return "none"

    best_key = "none"
    best_val = -1
    for key in FEATURE_KEYS:
        val = tile.contains_count.get(key, 0)
        if val > best_val:
            best_val = val
            best_key = key
    return best_key


def _create_demo_grid(
    size: int = 42,
    feature_level: int = 1,
    extra_buildings_delta: int = 0,
    extra_water_delta: int = 0,
    extra_roads_delta: int = 0,
    include_items: bool = True,
) -> tuple[list[list[DemoTile]], list[MockFeature], BaseStation]:
    """Create a deterministic grid populated by OSM-like features."""

    scale = size / 14.0
    features = _create_mock_features(
        scale=scale,
        feature_level=feature_level,
        extra_buildings_delta=extra_buildings_delta,
        extra_water_delta=extra_water_delta,
        extra_roads_delta=extra_roads_delta,
        include_base_items=include_items,
    )

    search_area = Polygon([(0.5 * scale, 0.4 * scale), (13.7 * scale, 0.4 * scale), (13.5 * scale, 13.4 * scale), (0.4 * scale, 13.2 * scale)])
    base = BaseStation(row=1, col=size // 2, x=(size // 2) + 0.5, y=1.5)

    grid: list[list[DemoTile]] = []
    for row in range(size):
        row_cells: list[DemoTile] = []
        for col in range(size):
            tile_poly = Polygon(
                [
                    (col, row),
                    (col + 1, row),
                    (col + 1, row + 1),
                    (col, row + 1),
                ]
            )

            in_area = search_area.intersects(tile_poly)
            contains_count = {k: 0 for k in FEATURE_KEYS}
            contains = {k: [] for k in FEATURE_KEYS}
            total_count = 0

            if in_area:
                for feature in features:
                    if not feature.geometry.intersects(tile_poly):
                        continue
                    for key in FEATURE_KEYS:
                        if key in feature.tags:
                            contains_count[key] += 1
                            contains[key].append(feature.tags[key])
                            total_count += 1

            row_cells.append(
                DemoTile(
                    polygon=tile_poly,
                    in_searcharea=in_area,
                    total_count=total_count,
                    contains_count=contains_count,
                    contains=contains,
                )
            )
        grid.append(row_cells)

    return grid, features, base


def _plot_assignments(
    grid: list[list[DemoTile]],
    features: list[MockFeature],
    base: BaseStation,
    queue_positions: list[tuple[float, float]],
    assignments: dict[int, list],
    save_path: str | None = None,
    display: bool = True,
) -> None:
    size = len(grid)
    max_ui_rows = 30

    def _drone_callsign(drone_id: int) -> str:
        return f"{chr(ord('A') + (drone_id % 26))}1"

    def _feature_labels():
        building_count = 1
        water_count = 1
        labeled = []
        for feature in features:
            if "building" in feature.tags:
                code = f"B{building_count}"
                name = feature.tags["building"]
                building_count += 1
                labeled.append({"kind": "building", "code": code, "name": name, "geometry": feature.geometry})
            elif "water" in feature.tags:
                code = f"W{water_count}"
                name = feature.tags["water"]
                water_count += 1
                labeled.append({"kind": "water", "code": code, "name": name, "geometry": feature.geometry})
        return labeled

    def _draw_background(ax) -> dict[tuple[float, float], DemoTile]:
        max_score = max(cell.total_count for row in grid for cell in row) or 1
        tile_by_centroid: dict[tuple[float, float], DemoTile] = {}

        for r in range(size):
            for c in range(size):
                cell = grid[r][c]
                centroid = cell.polygon.centroid
                tile_by_centroid[(round(float(centroid.x), 4), round(float(centroid.y), 4))] = cell

                if not cell.in_searcharea:
                    color = (0.15, 0.15, 0.15, 1.0)
                elif cell.total_count == 0:
                    color = (0.95, 0.95, 0.95, 1.0)
                else:
                    value = cell.total_count / max_score
                    color = (1.0, 1.0 - 0.75 * value, 1.0 - value, 0.75)

                ax.add_patch(Rectangle((c, r), 1, 1, facecolor=color, edgecolor="black", lw=0.3))

        for feature in features:
            if "highway" in feature.tags:
                x, y = feature.geometry.xy
                ax.plot(x, y, color="orange", lw=2.2, alpha=0.95)
            elif "building" in feature.tags:
                x, y = feature.geometry.exterior.xy
                coords = list(zip(x, y))
                ax.add_patch(MplPolygon(coords, closed=True, facecolor=(0.45, 0.45, 0.45, 0.55), edgecolor="black", lw=1.0))
            elif "water" in feature.tags:
                x, y = feature.geometry.exterior.xy
                coords = list(zip(x, y))
                ax.add_patch(MplPolygon(coords, closed=True, facecolor=(0.2, 0.45, 0.95, 0.5), edgecolor="navy", lw=1.0))

        ax.set_xlim(0, size)
        ax.set_ylim(0, size)
        ax.set_aspect("equal")
        ax.set_xlabel("Grid X")
        ax.set_ylabel("Grid Y")
        ax.grid(False)
        return tile_by_centroid

    def _assignment_circle(points: list, fallback_x: float, fallback_y: float) -> tuple[float, float, float]:
        if not points:
            return fallback_x, fallback_y, 0.8
        cx = sum(float(p.x) for p in points) / len(points)
        cy = sum(float(p.y) for p in points) / len(points)
        radius = max((((float(p.x) - cx) ** 2 + (float(p.y) - cy) ** 2) ** 0.5 for p in points), default=0.0)
        return cx, cy, max(0.8, radius + 0.6)

    def _drone_feature_mapping() -> dict[int, list[str]]:
        labeled = _feature_labels()
        mapping = {drone_id: [] for drone_id in assignments}
        for drone_id, points in assignments.items():
            for item in labeled:
                geom = item["geometry"]
                for pt in points:
                    if geom.buffer(0.3).intersects(Point(float(pt.x), float(pt.y))):
                        mapping[drone_id].append(item["code"])
                        break
            mapping[drone_id].sort(key=lambda code: (code[0], int(code[1:])))
        return mapping

    circle_metrics = {}
    for drone_id, points in assignments.items():
        cx, cy, radius = _assignment_circle(points, base.x, base.y)
        circle_metrics[drone_id] = {"cx": cx, "cy": cy, "radius": radius, "n": len(points)}

    drone_colors = ["tab:blue", "tab:orange", "tab:green", "tab:red", "tab:purple", "tab:brown"]
    event_color = {
        "building": "black",
        "highway": "darkorange",
        "water": "navy",
        "none": "dimgray",
    }

    legend_items = [
        Line2D([0], [0], color="orange", lw=2.2, label="Highway"),
        Line2D([0], [0], marker="s", color="w", markerfacecolor="gray", markeredgecolor="black", markersize=8, label="Building"),
        Line2D([0], [0], marker="s", color="w", markerfacecolor=(0.2, 0.45, 0.95, 0.5), markeredgecolor="navy", markersize=8, label="Water"),
    ]

    # First popup: assignment circles with circle-input values in a sidebar.
    fig2, ax2 = plt.subplots(figsize=(12.5, 10))
    _draw_background(ax2)
    ax2.scatter(base.x, base.y, marker="P", color="black", s=170, zorder=10)
    ax2.text(base.x + 0.35, base.y - 0.35, "Base Station", color="black", fontsize=9, zorder=11)
    value_lines = []
    for idx, (drone_id, points) in enumerate(assignments.items()):
        if idx >= max_ui_rows:
            break
        color = drone_colors[drone_id % len(drone_colors)]
        metrics = circle_metrics[drone_id]
        cx = metrics["cx"]
        cy = metrics["cy"]
        radius = metrics["radius"]
        label = _drone_callsign(drone_id)
        value_lines.append(f"{label}: n={metrics['n']} c=({cx:.1f},{cy:.1f}) r={radius:.1f}")
        ax2.add_patch(Circle((cx, cy), radius, fill=False, edgecolor=color, linestyle="--", lw=2.1, zorder=8))
        ax2.scatter(cx, cy, marker="X", color=color, s=130, edgecolor="black", linewidths=0.9, zorder=10)
        ax2.text(cx + 0.22, cy + 0.22, label, color=color, fontsize=9, zorder=11)
        for pt in points:
            ax2.scatter(float(pt.x), float(pt.y), marker="o", color=color, s=30, alpha=0.9, zorder=9)

    if len(assignments) > max_ui_rows:
        value_lines.append(f"... {len(assignments) - max_ui_rows} more drones omitted")
    ax2.text(
        1.02,
        0.98,
        "Circle Inputs\n" + "\n".join(value_lines),
        transform=ax2.transAxes,
        va="top",
        ha="left",
        fontsize=8,
        family="monospace",
        bbox={"boxstyle": "round,pad=0.35", "facecolor": "white", "edgecolor": "black", "alpha": 0.9},
        zorder=30,
    )
    ax2.set_title("Agent D Demo: Drone Assignment Circles")
    ax2.legend(handles=legend_items, loc="lower right")
    if save_path:
        save_root = Path(save_path)
        circles_path = str(save_root.with_name(f"{save_root.stem}_circles{save_root.suffix or '.png'}"))
        fig2.savefig(circles_path, dpi=180, bbox_inches="tight")
        print(f"Saved circle visualization: {circles_path}")

    # Second popup: which items are assigned to each drone + item labels.
    fig3, ax3 = plt.subplots(figsize=(11, 10))
    _draw_background(ax3)
    feature_codes = _feature_labels()
    by_drone = _drone_feature_mapping()
    for item in feature_codes:
        geom = item["geometry"]
        center = geom.centroid
        if item["kind"] == "building":
            ax3.text(center.x, center.y, f"{item['code']} {item['name']}", ha="center", va="center", color="black", fontsize=7, fontweight="bold", zorder=20)
        elif item["kind"] == "water":
            ax3.text(center.x, center.y, f"{item['code']} {item['name']}", ha="center", va="center", color="navy", fontsize=7, fontweight="bold", zorder=20)
    ax3.scatter(base.x, base.y, marker="P", color="black", s=170, zorder=10)
    ax3.text(base.x + 0.35, base.y - 0.35, "Base Station", color="black", fontsize=9, zorder=11)

    item_lines = []
    for idx, drone_id in enumerate(sorted(assignments)):
        if idx >= max_ui_rows:
            item_lines.append(f"... {len(assignments) - max_ui_rows} more drones omitted")
            break
        label = _drone_callsign(drone_id)
        assigned_items = ", ".join(by_drone.get(drone_id, [])) if by_drone.get(drone_id) else "None"
        item_lines.append(f"{label}: {assigned_items}")
    ax3.set_title("Assigned Items By Drone\n" + "\n".join(item_lines), fontsize=10)
    ax3.legend(handles=legend_items, loc="lower right")
    if save_path:
        save_root = Path(save_path)
        items_path = str(save_root.with_name(f"{save_root.stem}_items{save_root.suffix or '.png'}"))
        fig3.savefig(items_path, dpi=180, bbox_inches="tight")
        print(f"Saved item-assignment visualization: {items_path}")

    # Third popup: flight paths from base, no assignment circles.
    fig4, ax4 = plt.subplots(figsize=(10, 10))
    tile_by_centroid = _draw_background(ax4)
    ax4.scatter(base.x, base.y, marker="P", color="black", s=170, zorder=10)
    ax4.text(base.x + 0.35, base.y - 0.35, "Base Station", color="black", fontsize=9, zorder=11)

    drone_line_items: list[Line2D] = []
    for idx, (drone_id, points) in enumerate(assignments.items()):
        if idx >= max_ui_rows:
            break
        color = drone_colors[drone_id % len(drone_colors)]
        queue_x, queue_y = queue_positions[drone_id]
        drone_label = _drone_callsign(drone_id)
        path_x = [base.x]
        path_y = [base.y]
        for pt in points:
            path_x.append(float(pt.x))
            path_y.append(float(pt.y))

        ax4.plot(path_x, path_y, "-", color=color, lw=2, label=drone_label)
        drone_line_items.append(Line2D([0], [0], color=color, lw=2, label=drone_label))
        # Draw a small queued "logo" token for each drone near base and label queue position.
        ax4.scatter(queue_x, queue_y, marker="o", color=color, s=105, edgecolor="black", zorder=12)
        ax4.text(queue_x, queue_y, drone_label, color="white", ha="center", va="center", fontsize=7, zorder=13)

        if len(path_x) > 1:
            for idx in range(1, len(path_x)):
                key = (round(path_x[idx], 4), round(path_y[idx], 4))
                tile = tile_by_centroid.get(key)
                event = _dominant_event(tile) if tile else "none"
                ax4.scatter(
                    path_x[idx],
                    path_y[idx],
                    marker="o",
                    color=color,
                    s=34,
                    edgecolor=event_color[event],
                    linewidths=1.4,
                    zorder=8,
                )
            # Return-to-base leg after final destination.
            ax4.plot(
                [path_x[-1], base.x],
                [path_y[-1], base.y],
                color="black",
                lw=1.0,
                linestyle=":",
                zorder=6,
            )
            ax4.scatter(path_x[-1], path_y[-1], marker="x", color=color, s=90, linewidths=2.0, zorder=14)
            ax4.text(path_x[-1] + 0.24, path_y[-1] + 0.24, f"{drone_label} end", color=color, fontsize=8, zorder=15)

    if len(assignments) > max_ui_rows:
        ax4.set_title(f"Agent D Demo: Drone Paths from Base (No Circles)\nShowing first {max_ui_rows} of {len(assignments)} drones")
    else:
        ax4.set_title("Agent D Demo: Drone Paths from Base (No Circles)")
    ax4.legend(handles=legend_items + drone_line_items, loc="lower right")
    if save_path:
        save_root = Path(save_path)
        paths_path = str(save_root.with_name(f"{save_root.stem}_paths{save_root.suffix or '.png'}"))
        fig4.savefig(paths_path, dpi=180, bbox_inches="tight")
        print(f"Saved path visualization: {paths_path}")
    # Show all demo popups at once; next demo starts after all are closed.
    if display:
        plt.show(block=True)
    else:
        plt.close(fig2)
        plt.close(fig3)
        plt.close(fig4)


def _build_demo_jobs(assignments: dict[int, list], grid: list[list[DemoTile]], altitude_m: int = 20) -> dict[int, list[tuple[float, float, int, int]]]:
    """Convert assigned centroids to job-style waypoint payloads.

    Payload shape follows mission flow: (lat, lon, alt, waypoint_type).
    This demo uses grid coordinates as synthetic lat/lon-like values.
    """

    tile_by_centroid: dict[tuple[float, float], DemoTile] = {}
    for row in grid:
        for tile in row:
            centroid = tile.polygon.centroid
            tile_by_centroid[(round(float(centroid.x), 4), round(float(centroid.y), 4))] = tile

    jobs: dict[int, list[tuple[float, float, int, int]]] = {}
    for drone_id, points in assignments.items():
        payload: list[tuple[float, float, int, int]] = []
        for point in points:
            cx = round(float(point.x), 4)
            cy = round(float(point.y), 4)
            tile = tile_by_centroid.get((cx, cy))
            event = _dominant_event(tile) if tile else "none"
            waypoint_type = EVENT_TO_WAYPOINT_TYPE[event]
            payload.append((cy, cx, altitude_m, waypoint_type))
        jobs[drone_id] = payload
    return jobs


def _auto_scale_config(drone_count: int) -> tuple[int, int]:
    """Return (grid_size, feature_level) that grows with number of drones."""
    level = max(1, int(math.log10(max(1, drone_count))) + 1)
    # 1->42, 10->70, 100->98, 1000->126, 10000->154
    grid_size = 42 + (28 * (level - 1))
    return grid_size, level


def run_demo(
    drone_count: int,
    save_prefix: str | None = None,
    show_plots: bool = True,
    auto_scale: bool = True,
    force_grid_size: int | None = None,
    extra_buildings_delta: int = 0,
    extra_water_delta: int = 0,
    extra_roads_delta: int = 0,
    include_items: bool = True,
) -> dict[int, list]:
    drone_count = max(1, int(drone_count))
    if auto_scale:
        grid_size, feature_level = _auto_scale_config(drone_count)
    else:
        grid_size = 42
        feature_level = 1

    if force_grid_size is not None:
        grid_size = max(16, int(force_grid_size))

    grid, features, base = _create_demo_grid(
        size=grid_size,
        feature_level=feature_level,
        extra_buildings_delta=extra_buildings_delta,
        extra_water_delta=extra_water_delta,
        extra_roads_delta=extra_roads_delta,
        include_items=include_items,
    )
    drone_starts = [(base.row, base.col) for _ in range(drone_count)]
    assignments = search_grid_with_drones(grid, drone_positions=drone_starts, num_drones=drone_count)
    _ = PathingCostMap.from_assignments(assignments)
    jobs = _build_demo_jobs(assignments, grid)

    print(
        f"\n=== Demo: drones={drone_count}, grid={grid_size}x{grid_size}, "
        f"feature_level={feature_level}, include_items={include_items} ==="
    )
    print("Drone destination counts:")
    max_rows = 25
    for idx, drone_id in enumerate(sorted(assignments)):
        if idx >= max_rows:
            print(f"  ... {len(assignments) - max_rows} more drones omitted")
            break
        print(f"  Drone {drone_id + 1}: {len(assignments[drone_id])} destinations")

    print("Mock job payload summary (lat, lon, alt, type):")
    for idx, drone_id in enumerate(sorted(jobs)):
        if idx >= max_rows:
            print(f"  ... {len(jobs) - max_rows} more drones omitted")
            break
        loiter_count = sum(1 for wp in jobs[drone_id] if wp[3] == 2)
        print(f"  Drone {drone_id + 1}: {len(jobs[drone_id])} waypoints, {loiter_count} loiter events")

    if show_plots or save_prefix:
        queue_positions = [(base.x - 1.2 + (0.8 * i), base.y - 0.85) for i in range(drone_count)]
        _plot_assignments(
            grid,
            features,
            base,
            queue_positions,
            assignments,
            save_path=save_prefix,
            display=show_plots,
        )

    return assignments


def _draw_interactive_scene(
    ax,
    grid: list[list[DemoTile]],
    features: list[MockFeature],
    base: BaseStation,
    assignments: dict[int, list],
    cell_size_m: int,
) -> None:
    size = len(grid)
    max_score = max((cell.total_count for row in grid for cell in row), default=1) or 1
    drone_colors = ["tab:blue", "tab:orange", "tab:green", "tab:red", "tab:purple", "tab:brown", "tab:pink", "tab:gray", "tab:olive", "tab:cyan"]
    event_color = {"building": "black", "highway": "darkorange", "water": "navy", "none": "dimgray"}

    ax.clear()
    for r in range(size):
        for c in range(size):
            cell = grid[r][c]
            if not cell.in_searcharea:
                color = (0.15, 0.15, 0.15, 1.0)
            elif cell.total_count == 0:
                color = (0.95, 0.95, 0.95, 1.0)
            else:
                value = cell.total_count / max_score
                color = (1.0, 1.0 - 0.75 * value, 1.0 - value, 0.72)
            ax.add_patch(Rectangle((c, r), 1, 1, facecolor=color, edgecolor="black", lw=0.2))

    for feature in features:
        if "highway" in feature.tags:
            x, y = feature.geometry.xy
            ax.plot(x, y, color="orange", lw=2.0, alpha=0.95, zorder=6)
        elif "building" in feature.tags:
            x, y = feature.geometry.exterior.xy
            ax.add_patch(MplPolygon(list(zip(x, y)), closed=True, facecolor=(0.45, 0.45, 0.45, 0.55), edgecolor="black", lw=0.8, zorder=5))
        elif "water" in feature.tags:
            x, y = feature.geometry.exterior.xy
            ax.add_patch(MplPolygon(list(zip(x, y)), closed=True, facecolor=(0.2, 0.45, 0.95, 0.45), edgecolor="navy", lw=0.8, zorder=5))

    ax.scatter(base.x, base.y, marker="P", color="black", s=150, zorder=10)
    ax.text(base.x + 0.25, base.y - 0.35, "Base", color="black", fontsize=8, zorder=11)

    max_drawn_drones = 60
    for idx, (drone_id, points) in enumerate(assignments.items()):
        if idx >= max_drawn_drones:
            break
        color = drone_colors[drone_id % len(drone_colors)]
        path_x = [base.x] + [float(pt.x) for pt in points]
        path_y = [base.y] + [float(pt.y) for pt in points]
        if len(path_x) > 1:
            ax.plot(path_x, path_y, "-", color=color, lw=1.6, alpha=0.95, zorder=8)
            ax.plot([path_x[-1], base.x], [path_y[-1], base.y], color="black", lw=0.9, linestyle=":", zorder=7)
        for point in points:
            tile = grid[int(point.y)][int(point.x)]
            event = _dominant_event(tile)
            ax.scatter(float(point.x), float(point.y), marker="o", color=color, s=22, edgecolor=event_color[event], linewidths=1.0, zorder=9)

    ax.set_xlim(0, size)
    ax.set_ylim(0, size)
    ax.set_aspect("equal")
    ax.set_xlabel(f"Grid X ({cell_size_m} m/cell)")
    ax.set_ylabel(f"Grid Y ({cell_size_m} m/cell)")
    area_sqkm = ((size * cell_size_m) ** 2) / 1_000_000.0
    ax.set_title(f"Agent D Interactive Pathing | Approx area: {area_sqkm:.2f} sq km")

    bar_m = 100 if (size * cell_size_m) >= 200 else 50
    bar_cells = bar_m / float(cell_size_m)
    x0, y0 = 1.2, 1.2
    ax.plot([x0, x0 + bar_cells], [y0, y0], color="black", lw=3, zorder=20)
    ax.plot([x0, x0], [y0 - 0.3, y0 + 0.3], color="black", lw=1.5, zorder=20)
    ax.plot([x0 + bar_cells, x0 + bar_cells], [y0 - 0.3, y0 + 0.3], color="black", lw=1.5, zorder=20)
    ax.text(x0 + (bar_cells / 2.0), y0 + 0.55, f"{bar_m} m", ha="center", va="bottom", fontsize=8, zorder=21)


def _assignments_to_cells(assignments: dict[int, list]) -> dict[int, list[tuple[int, int]]]:
    mapped: dict[int, list[tuple[int, int]]] = {}
    for drone_id, points in assignments.items():
        mapped[drone_id] = [(int(float(point.y)), int(float(point.x))) for point in points]
    return mapped


def _cells_to_assignments(grid: list[list[DemoTile]], cell_paths: dict[int, list[tuple[int, int]]]) -> dict[int, list]:
    out: dict[int, list] = {}
    for drone_id, cells in cell_paths.items():
        out[drone_id] = [grid[r][c].polygon.centroid for (r, c) in cells]
    return out


def _count_searchable_cells_by_kind(grid: list[list[DemoTile]]) -> dict[str, int]:
    counts = {"building": 0, "water": 0, "road": 0}
    for row in grid:
        for tile in row:
            contains_count = getattr(tile, "contains_count", {}) or {}
            if contains_count.get("building", 0) > 0:
                counts["building"] += 1
            if contains_count.get("water", 0) > 0:
                counts["water"] += 1
            if contains_count.get("highway", 0) > 0:
                counts["road"] += 1
    return counts


def _tile_item_key(tile: DemoTile) -> str:
    """Stable item identity for no-handoff of partially searched items."""
    contains = getattr(tile, "contains", {}) or {}
    if isinstance(contains, dict):
        buildings = contains.get("building", [])
        if buildings:
            return f"building:{str(buildings[0])}"
        waters = contains.get("water", [])
        if waters:
            return f"water:{str(waters[0])}"
        highways = contains.get("highway", [])
        if highways:
            return f"highway:{str(highways[0])}"
    return "none"


def _cell_item_key(grid: list[list[DemoTile]], cell: tuple[int, int]) -> str:
    return _tile_item_key(grid[cell[0]][cell[1]])


def _order_cells_by_nearest(cells: list[tuple[int, int]], start: tuple[int, int]) -> list[tuple[int, int]]:
    if not cells:
        return []
    remaining = set(cells)
    ordered = []
    current = min(remaining, key=lambda cell: abs(cell[0] - start[0]) + abs(cell[1] - start[1]))
    while remaining:
        ordered.append(current)
        remaining.remove(current)
        if not remaining:
            break
        adjacent = [n for n in ((current[0] - 1, current[1]), (current[0] + 1, current[1]), (current[0], current[1] - 1), (current[0], current[1] + 1)) if n in remaining]
        if adjacent:
            current = min(adjacent, key=lambda cell: abs(cell[0] - current[0]) + abs(cell[1] - current[1]))
        else:
            current = min(remaining, key=lambda cell: abs(cell[0] - current[0]) + abs(cell[1] - current[1]))
    return ordered


def _rebalance_for_added_drones(
    grid: list[list[DemoTile]],
    base: BaseStation,
    prev_assignments: dict[int, list],
    new_drone_count: int,
) -> dict[int, list]:
    cell_paths = _assignments_to_cells(prev_assignments)
    prev_count = len(cell_paths)
    for drone_id in range(prev_count, new_drone_count):
        donor_ids = sorted((d for d in range(drone_id) if len(cell_paths.get(d, [])) > 2), key=lambda d: len(cell_paths.get(d, [])), reverse=True)
        if not donor_ids:
            cell_paths[drone_id] = []
            continue
        donor = donor_ids[0]
        donor_path = list(cell_paths.get(donor, []))
        chunk_size = max(1, len(donor_path) // 3)
        moved = donor_path[-chunk_size:]
        kept = donor_path[:-chunk_size]
        base_cell = (base.row, base.col)
        cell_paths[donor] = _order_cells_by_nearest(kept, base_cell)
        cell_paths[drone_id] = _order_cells_by_nearest(moved, base_cell)

    for drone_id in range(new_drone_count):
        cell_paths.setdefault(drone_id, [])
    return _cells_to_assignments(grid, cell_paths)


def run_interactive_demo(initial_include_items: bool = True) -> None:
    fig = plt.figure(figsize=(15, 10))
    ax_map = fig.add_axes([0.05, 0.30, 0.67, 0.66])
    ax_stats = fig.add_axes([0.74, 0.32, 0.24, 0.64])
    ax_stats.axis("off")
    ax_status = fig.add_axes([0.05, 0.26, 0.93, 0.03])
    ax_status.axis("off")
    status_text = ax_status.text(0.0, 0.5, "", va="center", fontsize=10, family="monospace")

    # Right-side control stack centered by layer and positioned above Auto-scale.
    fig.text(0.80, 0.304, "Apply", ha="center", va="bottom", fontsize=9)
    fig.text(0.865, 0.304, "Reset", ha="center", va="bottom", fontsize=9)
    fig.text(0.93, 0.304, "Start", ha="center", va="bottom", fontsize=9)
    fig.text(0.835, 0.244, "Pause", ha="center", va="bottom", fontsize=9)
    fig.text(0.905, 0.244, "Play", ha="center", va="bottom", fontsize=9)
    fig.text(0.845, 0.184, "+D", ha="center", va="bottom", fontsize=9)
    fig.text(0.895, 0.184, "-D", ha="center", va="bottom", fontsize=9)

    # Layer 1: Apply, Reset, Start
    ax_apply = fig.add_axes([0.7725, 0.251, 0.055, 0.045])
    ax_reset = fig.add_axes([0.8375, 0.251, 0.055, 0.045])
    ax_sim = fig.add_axes([0.9025, 0.251, 0.055, 0.045])
    # Layer 2: Pause, Play
    ax_pause = fig.add_axes([0.8075, 0.191, 0.055, 0.045])
    ax_play = fig.add_axes([0.8775, 0.191, 0.055, 0.045])
    # Layer 3: +D, -D
    ax_add_drone = fig.add_axes([0.83, 0.131, 0.03, 0.045])
    ax_remove_drone = fig.add_axes([0.88, 0.131, 0.03, 0.045])
    # Layer 4: +B, +W, +R (inject new items)
    fig.text(0.81, 0.124, "+B", ha="center", va="bottom", fontsize=9)
    fig.text(0.85, 0.124, "+W", ha="center", va="bottom", fontsize=9)
    fig.text(0.89, 0.124, "+R", ha="center", va="bottom", fontsize=9)
    ax_add_building = fig.add_axes([0.795, 0.071, 0.03, 0.045])
    ax_add_water = fig.add_axes([0.835, 0.071, 0.03, 0.045])
    ax_add_road = fig.add_axes([0.875, 0.071, 0.03, 0.045])
    # Layer 5: Export GIF
    fig.text(0.945, 0.124, "Export GIF", ha="center", va="bottom", fontsize=9)
    ax_export_gif = fig.add_axes([0.915, 0.071, 0.06, 0.045])
    # Auto-scale and item toggles below all layers.
    ax_auto = fig.add_axes([0.78, 0.002, 0.20, 0.085])

    apply_button = Button(ax_apply, "")
    reset_button = Button(ax_reset, "")
    simulate_button = Button(ax_sim, "")
    pause_button = Button(ax_pause, "")
    play_button = Button(ax_play, "")
    add_drone_button = Button(ax_add_drone, "")
    remove_drone_button = Button(ax_remove_drone, "")
    add_building_button = Button(ax_add_building, "")
    add_water_button = Button(ax_add_water, "")
    add_road_button = Button(ax_add_road, "")
    export_gif_button = Button(ax_export_gif, "")
    auto_scale_toggle = CheckButtons(
        ax_auto,
        ["Auto-scale grid", "Include items"],
        [True, bool(initial_include_items)],
    )

    controls: dict[str, NumericControl] = {}
    state = {
        "auto_scale": True,
        "include_items": bool(initial_include_items),
        "suspend_submit": False,
        "simulate_running": False,
        "current_grid": None,
        "current_features": None,
        "current_base": None,
        "current_assignments": None,
        "current_cost_map": PathingCostMap(),
        "cost_map_history": [],
        "last_signature": None,
        "last_drone_count": None,
        "sim_drone_delta_request": 0,
        "sim_paused": False,
        "terrain_tile_id": "demo_terrain_tile_0",
        "terrain_cost_registry": TerrainCostMapRegistry(terrain_id="demo_terrain_0", t_tree=None),
        "sim_item_add_requests": {"building": 0, "water": 0, "road": 0},
    }
    pending_deltas = {"building_delta": 0, "water_delta": 0, "road_delta": 0}

    def _set_status(message: str) -> None:
        status_text.set_text(message)
        fig.canvas.draw_idle()

    def _create_numeric_control(
        key: str,
        label: str,
        x: float,
        y: float,
        minimum: int,
        maximum: int,
        default: int,
    ) -> None:
        fig.text(x + 0.030, y + 0.045, label, ha="left", va="bottom", fontsize=9)
        minus_ax = fig.add_axes([x, y, 0.026, 0.042])
        box_ax = fig.add_axes([x + 0.030, y, 0.176, 0.042])
        plus_ax = fig.add_axes([x + 0.219, y, 0.026, 0.042])
        minus = Button(minus_ax, "-")
        box = TextBox(box_ax, "", initial=str(default))
        plus = Button(plus_ax, "+")
        controls[key] = NumericControl(
            name=label,
            minimum=minimum,
            maximum=maximum,
            default=default,
            value=default,
            textbox=box,
            minus_button=minus,
            plus_button=plus,
        )

    def _set_control_value(key: str, value: int, render: bool = False) -> None:
        control = controls[key]
        control.value = max(control.minimum, min(control.maximum, int(value)))
        state["suspend_submit"] = True
        control.textbox.set_val(str(control.value))
        state["suspend_submit"] = False
        if render:
            _render()

    def _submit_control(key: str, raw_text: str) -> None:
        if state["suspend_submit"]:
            return
        control = controls[key]
        previous = control.value
        text = raw_text.strip()
        try:
            parsed = int(text)
        except ValueError:
            _set_status(f"Invalid input for {control.name}: '{raw_text}'. Reverting to {previous}.")
            _set_control_value(key, previous, render=False)
            return

        if parsed < control.minimum or parsed > control.maximum:
            bounded = max(control.minimum, min(control.maximum, parsed))
            _set_status(f"{control.name} out of range [{control.minimum}, {control.maximum}]. Clamped to {bounded}.")
            _set_control_value(key, bounded, render=False)
            return

        _set_control_value(key, parsed, render=False)
        _set_status(f"{control.name} set to {parsed}. Press Apply to update simulation.")

    def _increment_control(key: str, delta: int) -> None:
        control = controls[key]
        next_value = max(control.minimum, min(control.maximum, control.value + delta))
        _set_control_value(key, next_value, render=False)
        _set_status(f"{control.name} set to {next_value}. Press Apply to update simulation.")

    def _on_delta_slider_change(_value: float) -> None:
        pending_deltas["building_delta"] = int(round(s_building_delta.val))
        pending_deltas["water_delta"] = int(round(s_water_delta.val))
        pending_deltas["road_delta"] = int(round(s_road_delta.val))
        _set_status("Delta values changed. Press Apply to update simulation.")

    def _update_delta_sliders() -> None:
        s_building_delta.set_val(int(pending_deltas["building_delta"]))
        s_water_delta.set_val(int(pending_deltas["water_delta"]))
        s_road_delta.set_val(int(pending_deltas["road_delta"]))

    def _current_grid_params() -> tuple[int, int]:
        drones = controls["drones"].value
        feature_level = controls["feature_level"].value
        if state["auto_scale"]:
            grid_size, _ = _auto_scale_config(drones)
        else:
            grid_size = controls["grid_size"].value
        return int(grid_size), int(feature_level)

    def _build_grid_from_pending() -> tuple[list[list[DemoTile]], list[MockFeature], BaseStation]:
        grid_size, feature_level = _current_grid_params()
        return _create_demo_grid(
            size=grid_size,
            feature_level=feature_level,
            extra_buildings_delta=int(pending_deltas["building_delta"]),
            extra_water_delta=int(pending_deltas["water_delta"]),
            extra_roads_delta=int(pending_deltas["road_delta"]),
            include_items=bool(state["include_items"]),
        )

    def _queue_or_apply_item_addition(item_kind: str) -> None:
        if item_kind not in ("building", "water", "road"):
            return
        delta_key = f"{item_kind}_delta"
        if state["simulate_running"]:
            state["sim_item_add_requests"][item_kind] = int(state["sim_item_add_requests"].get(item_kind, 0)) + 1
            _set_status(f"Queued +1 {item_kind} item for live remap.")
            return

        previous_grid = state.get("current_grid")
        if previous_grid is None:
            _render()
            previous_grid = state.get("current_grid")
        if previous_grid is None:
            _set_status("Unable to add item right now. Please try again.")
            return

        old_counts = _count_searchable_cells_by_kind(previous_grid)
        pending_deltas[delta_key] = int(pending_deltas.get(delta_key, 0)) + 1
        candidate_grid, _candidate_features, _candidate_base = _build_grid_from_pending()
        new_counts = _count_searchable_cells_by_kind(candidate_grid)

        if new_counts[item_kind] <= old_counts[item_kind]:
            pending_deltas[delta_key] = int(pending_deltas.get(delta_key, 0)) - 1
            _update_delta_sliders()
            _set_status(f"No valid space to add {item_kind}. Please reset terrain.")
            return

        _update_delta_sliders()
        state["terrain_cost_registry"].add_dynamic_item(
            tile_id=state["terrain_tile_id"],
            item_kind=item_kind,
            metadata={"count": 1, "source": "manual_control"},
            t_tree_node_id=state["terrain_tile_id"],
            osm_tile=None,
        )
        _set_status(f"Added +1 {item_kind} item and remapped.")
        _render()

    def _build_sequences(assignments: dict[int, list], base: BaseStation) -> dict[int, list[tuple[float, float]]]:
        sequences: dict[int, list[tuple[float, float]]] = {}
        for drone_id, points in assignments.items():
            seq = [(base.x, base.y)]
            seq.extend((float(pt.x), float(pt.y)) for pt in points)
            seq.append((base.x, base.y))
            sequences[drone_id] = seq
        return sequences

    def _render(_event=None):
        if state["simulate_running"]:
            _set_status("Simulation is running. Use +D/-D for live drone changes.")
            return

        drones = controls["drones"].value
        feature_level = controls["feature_level"].value
        cell_size_m = controls["cell_size_m"].value
        if state["auto_scale"]:
            grid_size, _ = _auto_scale_config(drones)
            _set_control_value("grid_size", grid_size, render=False)
        else:
            grid_size = controls["grid_size"].value

        building_delta = int(pending_deltas["building_delta"])
        water_delta = int(pending_deltas["water_delta"])
        road_delta = int(pending_deltas["road_delta"])
        signature = (
            grid_size,
            feature_level,
            building_delta,
            water_delta,
            road_delta,
            cell_size_m,
            bool(state["auto_scale"]),
            bool(state["include_items"]),
        )
        grid, features, base = _create_demo_grid(
            size=grid_size,
            feature_level=feature_level,
            extra_buildings_delta=building_delta,
            extra_water_delta=water_delta,
            extra_roads_delta=road_delta,
            include_items=bool(state["include_items"]),
        )
        prev_assignments = state["current_assignments"]
        prev_drone_count = state["last_drone_count"]
        if (
            prev_assignments
            and isinstance(prev_drone_count, int)
            and drones > prev_drone_count
            and state["last_signature"] == signature
        ):
            assignments = _rebalance_for_added_drones(
                grid=grid,
                base=base,
                prev_assignments=prev_assignments,
                new_drone_count=drones,
            )
            _set_status("Added drone(s) incrementally; adjusted existing paths without full re-plan.")
        else:
            drone_starts = [(base.row, base.col) for _ in range(drones)]
            assignments = search_grid_with_drones(grid, drone_positions=drone_starts, num_drones=drones)

        cost_map = PathingCostMap.from_assignments(
            assignments,
            terrain_tile_id=state["terrain_tile_id"],
            source="interactive_apply",
        )
        state["current_cost_map"] = cost_map
        state["cost_map_history"].append(cost_map.clone())
        state["terrain_cost_registry"].add_pathing_cost_map(
            tile_id=state["terrain_tile_id"],
            cost_map=cost_map,
            t_tree_node_id=state["terrain_tile_id"],
            osm_tile=None,
        )
        state["current_grid"] = grid
        state["current_features"] = features
        state["current_base"] = base
        state["current_assignments"] = assignments
        state["last_signature"] = signature
        state["last_drone_count"] = drones
        _draw_interactive_scene(ax_map, grid, features, base, assignments, cell_size_m=cell_size_m)

        if state["include_items"]:
            base_b, base_w, base_r = _generated_feature_counts(feature_level)
        else:
            base_b, base_w, base_r = (0, 0, 0)
        final_b = max(0, base_b + building_delta)
        final_w = max(0, base_w + water_delta)
        final_r = max(0, base_r + road_delta)
        assigned_total = sum(len(v) for v in assignments.values())
        max_assigned = max((len(v) for v in assignments.values()), default=0)
        min_assigned = min((len(v) for v in assignments.values()), default=0)
        avg_assigned = assigned_total / max(1, len(assignments))
        ax_stats.clear()
        ax_stats.axis("off")
        ax_stats.text(
            0.0,
            1.0,
            (
                "Live Simulation\n\n"
                f"Drones: {drones}\n"
                f"Grid: {grid_size}x{grid_size}\n"
                f"Cell size: {cell_size_m} m\n"
                f"Feature level: {feature_level}\n"
                f"Include items: {state['include_items']}\n"
                f"Generated buildings: {final_b}\n"
                f"Generated water: {final_w}\n"
                f"Generated roads: {final_r}\n\n"
                f"Assigned cells total: {assigned_total}\n"
                f"Per-drone avg: {avg_assigned:.2f}\n"
                f"Per-drone min: {min_assigned}\n"
                f"Per-drone max: {max_assigned}\n\n"
                f"Cost map snapshots: {len(state['cost_map_history'])}\n\n"
                "Controls:\n"
                "- Enter integer values\n"
                "- Use +/- for step changes\n"
                "- Use delta sliders for feature deltas\n"
                "- Apply or Reset as needed\n"
                "- Sim animates full mission\n"
                "- +D/-D live replan during sim"
            ),
            va="top",
            fontsize=10,
            family="monospace",
        )
        fig.canvas.draw_idle()

    def _sync_assignments_and_cost_map_from_cells(grid, sim_cell_paths: dict[int, list[tuple[int, int]]]) -> None:
        assignments = _cells_to_assignments(grid, sim_cell_paths)
        state["current_assignments"] = assignments
        cost_map = PathingCostMap.from_assignments(
            assignments,
            terrain_tile_id=state["terrain_tile_id"],
            source="interactive_remap",
        )
        state["current_cost_map"] = cost_map
        state["cost_map_history"].append(cost_map.clone())
        state["terrain_cost_registry"].add_pathing_cost_map(
            tile_id=state["terrain_tile_id"],
            cost_map=cost_map,
            t_tree_node_id=state["terrain_tile_id"],
            osm_tile=None,
        )

    def _replan_simulation_for_drone_count(
        grid: list[list[DemoTile]],
        base: BaseStation,
        sim_cell_paths: dict[int, list[tuple[int, int]]],
        sim_progress: dict[int, int],
        target_count: int,
    ) -> tuple[dict[int, list[tuple[int, int]]], dict[int, int]]:
        target = max(1, min(120, int(target_count)))
        current_ids = sorted(sim_cell_paths)
        if target == len(current_ids):
            return sim_cell_paths, sim_progress

        base_cell = (base.row, base.col)
        completed_by_drone: dict[int, list[tuple[int, int]]] = {}
        locked_remaining_by_drone: dict[int, list[tuple[int, int]]] = {}
        remaining_cells: list[tuple[int, int]] = []
        next_ids = list(range(target))

        for drone_id in current_ids:
            path = list(sim_cell_paths.get(drone_id, []))
            progress = max(0, min(int(sim_progress.get(drone_id, 0)), len(path)))
            completed = path[:progress]
            remaining = path[progress:]
            completed_by_drone[drone_id] = completed
            if drone_id in next_ids:
                locked_remaining_by_drone.setdefault(drone_id, [])

            touched_keys = {_cell_item_key(grid, cell) for cell in completed}
            for cell in remaining:
                item_key = _cell_item_key(grid, cell)
                # Do not hand off partially searched objects to newly added drones.
                if drone_id in next_ids and item_key != "none" and item_key in touched_keys:
                    locked_remaining_by_drone[drone_id].append(cell)
                else:
                    remaining_cells.append(cell)

        unique_remaining = list(dict.fromkeys(remaining_cells))
        starts = []
        for drone_id in next_ids:
            completed = completed_by_drone.get(drone_id, [])
            if completed:
                starts.append(completed[-1])
            else:
                starts.append(base_cell)

        if unique_remaining:
            replanned = search_grid_with_drones(
                grid,
                drone_positions=starts,
                viable_grid_positions=unique_remaining,
                num_drones=target,
            )
            replanned_cells = _assignments_to_cells(replanned)
        else:
            replanned_cells = {drone_id: [] for drone_id in next_ids}

        next_paths: dict[int, list[tuple[int, int]]] = {}
        next_progress: dict[int, int] = {}
        for drone_id in next_ids:
            completed = completed_by_drone.get(drone_id, [])
            locked_remainder = locked_remaining_by_drone.get(drone_id, [])
            remainder = replanned_cells.get(drone_id, [])
            next_paths[drone_id] = completed + locked_remainder + remainder
            next_progress[drone_id] = len(completed)
        return next_paths, next_progress

    def _replan_simulation_for_item_injection(
        old_grid: list[list[DemoTile]],
        new_grid: list[list[DemoTile]],
        base: BaseStation,
        sim_cell_paths: dict[int, list[tuple[int, int]]],
        sim_progress: dict[int, int],
        active_count: int,
    ) -> tuple[dict[int, list[tuple[int, int]]], dict[int, int]]:
        base_cell = (base.row, base.col)
        next_ids = list(range(active_count))
        completed_by_drone: dict[int, list[tuple[int, int]]] = {}
        locked_remaining_by_drone: dict[int, list[tuple[int, int]]] = {drone_id: [] for drone_id in next_ids}

        def _in_bounds(grid_ref: list[list[DemoTile]], cell: tuple[int, int]) -> bool:
            return 0 <= cell[0] < len(grid_ref) and 0 <= cell[1] < len(grid_ref[0])

        visited_cells = set()
        locked_cells = set()
        for drone_id in next_ids:
            path = list(sim_cell_paths.get(drone_id, []))
            progress = max(0, min(int(sim_progress.get(drone_id, 0)), len(path)))
            completed = [cell for cell in path[:progress] if _in_bounds(new_grid, cell)]
            remaining = [cell for cell in path[progress:] if _in_bounds(new_grid, cell)]
            completed_by_drone[drone_id] = completed
            visited_cells.update(completed)

            touched_keys = {_cell_item_key(old_grid, cell) for cell in path[:progress] if _in_bounds(old_grid, cell)}
            for cell in remaining:
                old_key = _cell_item_key(old_grid, cell) if _in_bounds(old_grid, cell) else "none"
                new_key = _cell_item_key(new_grid, cell)
                item_key = new_key if new_key != "none" else old_key
                if item_key != "none" and item_key in touched_keys:
                    locked_remaining_by_drone[drone_id].append(cell)
                    locked_cells.add(cell)

        all_viable = []
        for r in range(len(new_grid)):
            for c in range(len(new_grid[0])):
                cell = new_grid[r][c]
                if cell.in_searcharea and cell.total_count > 0:
                    all_viable.append((r, c))

        free_pool = [cell for cell in all_viable if cell not in visited_cells and cell not in locked_cells]
        starts = []
        for drone_id in next_ids:
            completed = completed_by_drone.get(drone_id, [])
            starts.append(completed[-1] if completed else base_cell)

        if free_pool:
            replanned = search_grid_with_drones(
                new_grid,
                drone_positions=starts,
                viable_grid_positions=free_pool,
                num_drones=active_count,
            )
            replanned_cells = _assignments_to_cells(replanned)
        else:
            replanned_cells = {drone_id: [] for drone_id in next_ids}

        next_paths: dict[int, list[tuple[int, int]]] = {}
        next_progress: dict[int, int] = {}
        for drone_id in next_ids:
            completed = completed_by_drone.get(drone_id, [])
            locked = locked_remaining_by_drone.get(drone_id, [])
            replanned_remaining = replanned_cells.get(drone_id, [])
            next_paths[drone_id] = completed + locked + replanned_remaining
            next_progress[drone_id] = len(completed)
        return next_paths, next_progress

    def _simulate(_event=None):
        assignments = state["current_assignments"]
        base = state["current_base"]
        if not assignments or base is None:
            _set_status("No assignments to simulate. Click Apply first.")
            return
        if state["simulate_running"]:
            state["simulate_running"] = False
            _set_status("Stopping simulation...")
            return

        _set_status("Simulation running...")
        state["simulate_running"] = True
        state["sim_paused"] = False
        grid = state["current_grid"]
        features = state["current_features"]
        cell_size_m = controls["cell_size_m"].value
        sim_cell_paths = _assignments_to_cells(assignments)
        sim_progress = {drone_id: 0 for drone_id in sim_cell_paths}
        sim_leg_phase = {drone_id: 0.0 for drone_id in sim_cell_paths}
        active_ids = sorted(sim_cell_paths)
        transit_leg_phase_step = 0.16  # keep baseline speed between searchable items
        in_item_leg_phase_step = 0.34  # speed up while moving over the same searchable item
        frame_sleep_s = 0.05
        drone_colors = ["tab:blue", "tab:orange", "tab:green", "tab:red", "tab:purple", "tab:brown", "tab:pink", "tab:gray", "tab:olive", "tab:cyan"]
        draw_limit = 60
        line_artists = {}
        marker_artists = {}
        assignment_artists = {}
        base_cell = (base.row, base.col)

        def _cell_to_xy(cell: tuple[int, int]) -> tuple[float, float]:
            return float(cell[1]) + 0.5, float(cell[0]) + 0.5

        def _current_xy(drone_id: int) -> tuple[float, float]:
            progress = sim_progress.get(drone_id, 0)
            path = sim_cell_paths.get(drone_id, [])
            if not path:
                return base.x, base.y
            if progress >= len(path):
                # Optional return-to-base glide once all search cells are visited.
                last_x, last_y = _cell_to_xy(path[-1])
                phase = max(0.0, min(1.0, float(sim_leg_phase.get(drone_id, 0.0))))
                cx = last_x + (base.x - last_x) * phase
                cy = last_y + (base.y - last_y) * phase
                return cx, cy

            start_x, start_y = (base.x, base.y) if progress <= 0 else _cell_to_xy(path[progress - 1])
            end_x, end_y = _cell_to_xy(path[progress])
            phase = max(0.0, min(1.0, float(sim_leg_phase.get(drone_id, 0.0))))
            cx = start_x + (end_x - start_x) * phase
            cy = start_y + (end_y - start_y) * phase
            return cx, cy

        def _trail_xy(drone_id: int) -> tuple[list[float], list[float]]:
            progress = sim_progress.get(drone_id, 0)
            path = sim_cell_paths.get(drone_id, [])
            visited = path[:progress]
            xs = [base.x]
            ys = [base.y]
            for cell in visited:
                px, py = _cell_to_xy(cell)
                xs.append(px)
                ys.append(py)
            cx, cy = _current_xy(drone_id)
            xs.append(cx)
            ys.append(cy)
            return xs, ys

        def _rebuild_artists() -> None:
            for artist in line_artists.values():
                artist.remove()
            for artist in marker_artists.values():
                artist.remove()
            line_artists.clear()
            marker_artists.clear()
            for idx, drone_id in enumerate(active_ids):
                if idx >= draw_limit:
                    break
                color = drone_colors[drone_id % len(drone_colors)]
                (line,) = ax_map.plot([], [], "-", color=color, lw=2.2, zorder=16)
                cx, cy = _current_xy(drone_id)
                marker = ax_map.scatter([cx], [cy], marker="o", color=color, s=70, edgecolor="white", linewidths=1.0, zorder=17)
                line_artists[drone_id] = line
                marker_artists[drone_id] = marker

        def _assignment_xy_by_status(drone_id: int) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
            path = sim_cell_paths.get(drone_id, [])
            progress = max(0, min(int(sim_progress.get(drone_id, 0)), len(path)))
            visited = path[:progress]
            pending = path[progress:]
            visited_xy = [(float(c) + 0.5, float(r) + 0.5) for (r, c) in visited]
            pending_xy = [(float(c) + 0.5, float(r) + 0.5) for (r, c) in pending]
            return visited_xy, pending_xy

        def _rebuild_assignment_markers() -> None:
            for artist in assignment_artists.values():
                if isinstance(artist, tuple):
                    artist[0].remove()
                    artist[1].remove()
                else:
                    artist.remove()
            assignment_artists.clear()
            for idx, drone_id in enumerate(active_ids):
                if idx >= draw_limit:
                    break
                visited_xy, pending_xy = _assignment_xy_by_status(drone_id)
                if not visited_xy and not pending_xy:
                    continue
                color = drone_colors[drone_id % len(drone_colors)]
                visited_marker = ax_map.scatter(
                    [xy[0] for xy in visited_xy],
                    [xy[1] for xy in visited_xy],
                    marker="s",
                    color=color,
                    s=72,
                    edgecolors="black",
                    linewidths=0.25,
                    alpha=0.58,
                    zorder=13.5,
                )
                pending_marker = ax_map.scatter(
                    [xy[0] for xy in pending_xy],
                    [xy[1] for xy in pending_xy],
                    marker="s",
                    color=color,
                    s=72,
                    edgecolors="none",
                    alpha=0.22,
                    zorder=12.5,
                )
                assignment_artists[drone_id] = (visited_marker, pending_marker)

        def _refresh_artists() -> None:
            for drone_id in list(line_artists):
                if drone_id not in active_ids:
                    line_artists[drone_id].remove()
                    marker_artists[drone_id].remove()
                    del line_artists[drone_id]
                    del marker_artists[drone_id]
            for idx, drone_id in enumerate(active_ids):
                if idx >= draw_limit:
                    continue
                if drone_id not in line_artists:
                    color = drone_colors[drone_id % len(drone_colors)]
                    (line,) = ax_map.plot([], [], "-", color=color, lw=2.2, zorder=16)
                    cx, cy = _current_xy(drone_id)
                    marker = ax_map.scatter([cx], [cy], marker="o", color=color, s=70, edgecolor="white", linewidths=1.0, zorder=17)
                    line_artists[drone_id] = line
                    marker_artists[drone_id] = marker

                xs, ys = _trail_xy(drone_id)
                line_artists[drone_id].set_data(xs, ys)
                cx, cy = _current_xy(drone_id)
                marker_artists[drone_id].set_offsets([(cx, cy)])

                if drone_id not in assignment_artists:
                    color = drone_colors[drone_id % len(drone_colors)]
                    visited_marker = ax_map.scatter([], [], marker="s", color=color, s=72, edgecolors="black", linewidths=0.25, alpha=0.58, zorder=13.5)
                    pending_marker = ax_map.scatter([], [], marker="s", color=color, s=72, edgecolors="none", alpha=0.22, zorder=12.5)
                    assignment_artists[drone_id] = (visited_marker, pending_marker)

                visited_xy, pending_xy = _assignment_xy_by_status(drone_id)
                visited_marker, pending_marker = assignment_artists[drone_id]
                visited_marker.set_offsets(visited_xy if visited_xy else [(math.nan, math.nan)])
                pending_marker.set_offsets(pending_xy if pending_xy else [(math.nan, math.nan)])

            fig.canvas.draw_idle()

        _rebuild_artists()
        _rebuild_assignment_markers()

        while state["simulate_running"]:
            if state.get("sim_paused", False):
                plt.pause(0.06)
                continue

            item_requests = state.get("sim_item_add_requests", {})
            total_item_adds = int(item_requests.get("building", 0)) + int(item_requests.get("water", 0)) + int(item_requests.get("road", 0))
            if total_item_adds > 0:
                state["sim_item_add_requests"] = {"building": 0, "water": 0, "road": 0}
                old_grid = grid
                old_paths = dict(sim_cell_paths)
                old_progress = dict(sim_progress)

                applied = {"building": 0, "water": 0, "road": 0}
                rejected = {"building": 0, "water": 0, "road": 0}
                grid_size = controls["grid_size"].value if not state["auto_scale"] else len(grid)
                feature_level = controls["feature_level"].value
                candidate_grid = grid
                candidate_features = features
                candidate_base = base
                kind_to_delta = {"building": "building_delta", "water": "water_delta", "road": "road_delta"}
                kind_to_count_key = {"building": "building", "water": "water", "road": "road"}

                for item_kind in ("building", "water", "road"):
                    steps = int(item_requests.get(item_kind, 0))
                    for _ in range(steps):
                        old_counts = _count_searchable_cells_by_kind(candidate_grid)
                        delta_key = kind_to_delta[item_kind]
                        pending_deltas[delta_key] = int(pending_deltas[delta_key]) + 1
                        test_grid, test_features, test_base = _create_demo_grid(
                            size=int(grid_size),
                            feature_level=int(feature_level),
                            extra_buildings_delta=int(pending_deltas["building_delta"]),
                            extra_water_delta=int(pending_deltas["water_delta"]),
                            extra_roads_delta=int(pending_deltas["road_delta"]),
                            include_items=bool(state["include_items"]),
                        )
                        new_counts = _count_searchable_cells_by_kind(test_grid)
                        count_key = kind_to_count_key[item_kind]
                        if new_counts[count_key] <= old_counts[count_key]:
                            pending_deltas[delta_key] = int(pending_deltas[delta_key]) - 1
                            rejected[item_kind] += 1
                            continue
                        applied[item_kind] += 1
                        candidate_grid = test_grid
                        candidate_features = test_features
                        candidate_base = test_base
                        state["terrain_cost_registry"].add_dynamic_item(
                            tile_id=state["terrain_tile_id"],
                            item_kind=item_kind,
                            metadata={"count": 1, "source": "live_sim_injection"},
                            t_tree_node_id=state["terrain_tile_id"],
                            osm_tile=None,
                        )

                _update_delta_sliders()
                grid = candidate_grid
                features = candidate_features
                base = candidate_base
                state["current_grid"] = grid
                state["current_features"] = features
                state["current_base"] = base
                sim_cell_paths, sim_progress = _replan_simulation_for_item_injection(
                    old_grid=old_grid,
                    new_grid=grid,
                    base=base,
                    sim_cell_paths=old_paths,
                    sim_progress=old_progress,
                    active_count=len(active_ids),
                )
                sim_leg_phase = {drone_id: 0.0 for drone_id in sim_cell_paths}
                active_ids = sorted(sim_cell_paths)
                _sync_assignments_and_cost_map_from_cells(grid, sim_cell_paths)
                _rebuild_artists()
                _rebuild_assignment_markers()
                total_applied = sum(applied.values())
                total_rejected = sum(rejected.values())
                if total_rejected > 0:
                    _set_status("Some items could not be placed with 1-cell spacing. Please reset terrain.")
                elif total_applied > 0:
                    _set_status("Live item injection complete. Paths remapped with new terrain items.")

            requested_delta = int(state.get("sim_drone_delta_request", 0))
            if requested_delta != 0:
                target = len(active_ids) + requested_delta
                state["sim_drone_delta_request"] = 0
                sim_cell_paths, sim_progress = _replan_simulation_for_drone_count(
                    grid=grid,
                    base=base,
                    sim_cell_paths=sim_cell_paths,
                    sim_progress=sim_progress,
                    target_count=target,
                )
                sim_leg_phase = {drone_id: 0.0 for drone_id in sim_cell_paths}
                active_ids = sorted(sim_cell_paths)
                _set_control_value("drones", len(active_ids), render=False)
                state["last_drone_count"] = len(active_ids)
                _sync_assignments_and_cost_map_from_cells(grid, sim_cell_paths)
                _rebuild_artists()
                _rebuild_assignment_markers()
                _set_status(f"Live remap complete. Active drones: {len(active_ids)}")

            step_progress = False
            for drone_id in active_ids:
                path_len = len(sim_cell_paths[drone_id])
                if path_len == 0:
                    continue

                if sim_progress[drone_id] < path_len:
                    progress = sim_progress[drone_id]
                    path = sim_cell_paths[drone_id]
                    start_cell = path[progress - 1] if progress > 0 else None
                    end_cell = path[progress]
                    start_key = _cell_item_key(grid, start_cell) if start_cell is not None else "none"
                    end_key = _cell_item_key(grid, end_cell)
                    phase_step = in_item_leg_phase_step if (end_key != "none" and start_key == end_key) else transit_leg_phase_step
                    sim_leg_phase[drone_id] = min(1.0, sim_leg_phase.get(drone_id, 0.0) + phase_step)
                    if sim_leg_phase[drone_id] >= 1.0:
                        sim_progress[drone_id] += 1
                        sim_leg_phase[drone_id] = 0.0
                    step_progress = True
                elif sim_leg_phase.get(drone_id, 0.0) < 1.0:
                    # Return leg from final cell back to base.
                    sim_leg_phase[drone_id] = min(1.0, sim_leg_phase.get(drone_id, 0.0) + transit_leg_phase_step)
                    step_progress = True
            _refresh_artists()
            if not step_progress:
                break
            plt.pause(frame_sleep_s)

        for artist in list(line_artists.values()):
            artist.remove()
        for artist in list(marker_artists.values()):
            artist.remove()
        for artist in list(assignment_artists.values()):
            artist.remove()
        state["simulate_running"] = False
        state["sim_paused"] = False
        _sync_assignments_and_cost_map_from_cells(grid, sim_cell_paths)
        _draw_interactive_scene(
            ax_map,
            grid=grid,
            features=features,
            base=base,
            assignments=state["current_assignments"],
            cell_size_m=cell_size_m,
        )
        fig.canvas.draw_idle()
        _set_status("Simulation complete.")

    def _pause_simulation(_event):
        if not state["simulate_running"]:
            _set_status("Simulation is not active.")
            return
        state["sim_paused"] = True
        _set_status("Simulation paused.")

    def _play_simulation(_event):
        if not state["simulate_running"]:
            _simulate(None)
            return
        state["sim_paused"] = False
        _set_status("Simulation resumed.")

    def _export_simulation_gif(_event):
        assignments = state["current_assignments"]
        base = state["current_base"]
        grid = state["current_grid"]
        features = state["current_features"]
        if not assignments or base is None or grid is None or features is None:
            _set_status("No simulation available to export. Click Apply first.")
            return

        export_fig, export_ax = plt.subplots(figsize=(10, 10))
        cell_size_m = controls["cell_size_m"].value
        _draw_interactive_scene(
            export_ax,
            grid=grid,
            features=features,
            base=base,
            assignments={},
            cell_size_m=cell_size_m,
        )

        sequences = _build_sequences(assignments, base)
        drone_colors = ["tab:blue", "tab:orange", "tab:green", "tab:red", "tab:purple", "tab:brown", "tab:pink", "tab:gray", "tab:olive", "tab:cyan"]
        draw_limit = 60
        line_artists = {}
        marker_artists = {}
        ordered_ids = sorted(sequences)[:draw_limit]
        for drone_id in ordered_ids:
            color = drone_colors[drone_id % len(drone_colors)]
            (line,) = export_ax.plot([], [], "-", color=color, lw=2.2, zorder=16)
            marker = export_ax.scatter([base.x], [base.y], marker="o", color=color, s=70, edgecolor="white", linewidths=1.0, zorder=17)
            line_artists[drone_id] = line
            marker_artists[drone_id] = marker

        frame_count = max((len(seq) for seq in sequences.values()), default=0)
        out_path = Path(__file__).resolve().parent / f"pathing_simulation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.gif"
        writer = PillowWriter(fps=12)
        with writer.saving(export_fig, str(out_path), dpi=120):
            for frame in range(frame_count):
                for drone_id in ordered_ids:
                    seq = sequences[drone_id]
                    point_index = min(frame, len(seq) - 1)
                    trail = seq[: point_index + 1]
                    xs = [p[0] for p in trail]
                    ys = [p[1] for p in trail]
                    line_artists[drone_id].set_data(xs, ys)
                    marker_artists[drone_id].set_offsets([seq[point_index]])
                writer.grab_frame()

        plt.close(export_fig)
        _set_status(f"GIF exported: {out_path}")

    def _add_drone_live(_event):
        if state["simulate_running"]:
            state["sim_drone_delta_request"] = int(state.get("sim_drone_delta_request", 0)) + 1
            _set_status("Queued +1 drone for live remap.")
            return
        _increment_control("drones", +1)

    def _remove_drone_live(_event):
        if state["simulate_running"]:
            current_count = max(1, int(controls["drones"].value + state.get("sim_drone_delta_request", 0)))
            if current_count <= 1:
                _set_status("Cannot remove below 1 active drone.")
                return
            state["sim_drone_delta_request"] = int(state.get("sim_drone_delta_request", 0)) - 1
            _set_status("Queued -1 drone for live remap.")
            return
        if controls["drones"].value <= 1:
            _set_status("Cannot remove below 1 drone.")
            return
        _increment_control("drones", -1)

    def _add_building_item(_event):
        _queue_or_apply_item_addition("building")

    def _add_water_item(_event):
        _queue_or_apply_item_addition("water")

    def _add_road_item(_event):
        _queue_or_apply_item_addition("road")

    def _toggle_auto(_label):
        statuses = auto_scale_toggle.get_status()
        state["auto_scale"] = bool(statuses[0])
        state["include_items"] = bool(statuses[1])
        _set_status("Options toggled. Press Apply to update simulation.")

    def _reset(_event):
        for key, control in controls.items():
            _set_control_value(key, control.default, render=False)
        s_building_delta.reset()
        s_water_delta.reset()
        s_road_delta.reset()
        pending_deltas["building_delta"] = int(round(s_building_delta.val))
        pending_deltas["water_delta"] = int(round(s_water_delta.val))
        pending_deltas["road_delta"] = int(round(s_road_delta.val))
        state["auto_scale"] = True
        state["current_assignments"] = None
        state["current_cost_map"] = PathingCostMap()
        state["cost_map_history"] = []
        state["terrain_cost_registry"] = TerrainCostMapRegistry(terrain_id="demo_terrain_0", t_tree=None)
        state["last_signature"] = None
        state["last_drone_count"] = None
        state["sim_drone_delta_request"] = 0
        state["sim_paused"] = False
        state["include_items"] = bool(initial_include_items)
        state["sim_item_add_requests"] = {"building": 0, "water": 0, "road": 0}
        if not auto_scale_toggle.get_status()[0]:
            auto_scale_toggle.set_active(0)
        desired_items_enabled = bool(initial_include_items)
        if auto_scale_toggle.get_status()[1] != desired_items_enabled:
            auto_scale_toggle.set_active(1)
        _set_status("Controls reset to defaults.")
        _render()

    _create_numeric_control("drones", "Drones", 0.05, 0.21, 1, 120, 6)
    _create_numeric_control("feature_level", "Feature Level", 0.05, 0.16, 1, 8, 2)
    _create_numeric_control("grid_size", "Grid Size", 0.05, 0.11, 24, 160, 64)
    _create_numeric_control("cell_size_m", "Cell Meters", 0.05, 0.06, 2, 50, DEFAULT_CELL_METERS)
    fig.text(0.34, 0.242, "Building Delta", ha="left", va="bottom", fontsize=9)
    fig.text(0.34, 0.192, "Water Delta", ha="left", va="bottom", fontsize=9)
    fig.text(0.34, 0.142, "Road Delta", ha="left", va="bottom", fontsize=9)
    ax_building_delta = fig.add_axes([0.34, 0.205, 0.29, 0.035])
    ax_water_delta = fig.add_axes([0.34, 0.155, 0.29, 0.035])
    ax_road_delta = fig.add_axes([0.34, 0.105, 0.29, 0.035])
    s_building_delta = Slider(ax_building_delta, "", -60, 160, valinit=0, valstep=1)
    s_water_delta = Slider(ax_water_delta, "", -20, 60, valinit=0, valstep=1)
    s_road_delta = Slider(ax_road_delta, "", -8, 30, valinit=0, valstep=1)
    s_building_delta.on_changed(_on_delta_slider_change)
    s_water_delta.on_changed(_on_delta_slider_change)
    s_road_delta.on_changed(_on_delta_slider_change)

    for key, control in controls.items():
        control.textbox.on_submit(lambda text, _k=key: _submit_control(_k, text))
        control.minus_button.on_clicked(lambda _evt, _k=key: _increment_control(_k, -1))
        control.plus_button.on_clicked(lambda _evt, _k=key: _increment_control(_k, 1))

    apply_button.on_clicked(_render)
    reset_button.on_clicked(_reset)
    simulate_button.on_clicked(_simulate)
    pause_button.on_clicked(_pause_simulation)
    play_button.on_clicked(_play_simulation)
    add_drone_button.on_clicked(_add_drone_live)
    remove_drone_button.on_clicked(_remove_drone_live)
    add_building_button.on_clicked(_add_building_item)
    add_water_button.on_clicked(_add_water_item)
    add_road_button.on_clicked(_add_road_item)
    export_gif_button.on_clicked(_export_simulation_gif)
    auto_scale_toggle.on_clicked(_toggle_auto)

    _render()
    plt.show()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Agent D pathing visualization demo with OSM-like features.")
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Launch interactive simulation UI.",
    )
    parser.add_argument(
        "--save",
        default=None,
        help="Optional output PNG path, e.g. Agent_D/test/pathing_demo.png",
    )
    parser.add_argument(
        "--drones",
        type=int,
        default=6,
        help="Number of drones to simulate in the assignment/path visualization.",
    )
    parser.add_argument(
        "--no-auto-scale",
        action="store_true",
        help="Disable automatic scaling of map size and feature count.",
    )
    parser.add_argument(
        "--no-show",
        action="store_true",
        help="Do not display plots; only print summaries (useful for large runs).",
    )
    parser.add_argument(
        "--grid-size",
        type=int,
        default=None,
        help="Optional override for grid size.",
    )
    parser.add_argument(
        "--no-items",
        action="store_true",
        help="Start the demo without mock OSM items so the fallback pathing behavior is shown.",
    )
    args = parser.parse_args()
    if args.interactive:
        run_interactive_demo(initial_include_items=not args.no_items)
        return

    run_demo(
        drone_count=args.drones,
        save_prefix=args.save,
        show_plots=not args.no_show,
        auto_scale=not args.no_auto_scale,
        force_grid_size=args.grid_size,
        include_items=not args.no_items,
    )


if __name__ == "__main__":
    main()
