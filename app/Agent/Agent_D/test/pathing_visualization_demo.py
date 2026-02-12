"""Agent D pathing demo with OSM-style mock features and visualization.

This test script does not require missionState.py. It builds a synthetic
search grid from mock OSM-like geometries (buildings, water, highways), runs
`search_grid_with_drones`, and visualizes destinations and destination types.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import math
from pathlib import Path
import random
import sys

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Polygon as MplPolygon
from matplotlib.patches import Circle
from matplotlib.patches import Rectangle
from shapely.geometry import LineString, Point, Polygon


# Allow running from either repo root or app folder.
APP_DIR = Path(__file__).resolve().parents[2]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from Agent_D.CostMaps.pathing.path import search_grid_with_drones  # noqa: E402


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


FEATURE_KEYS = ("building", "water", "highway")
EVENT_TO_WAYPOINT_TYPE = {
    "building": 0,
    "highway": 0,
    "water": 2,  # use loiter type for water event inspections in this demo
    "none": 0,
}


def _create_mock_features(scale: float = 1.0, feature_level: int = 1) -> list[MockFeature]:
    """Create deterministic OSM-like objects used to populate tiles."""

    def _scaled(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
        return [(x * scale, y * scale) for (x, y) in points]

    features: list[MockFeature] = [
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
    extra_buildings = 18 * max(0, feature_level - 1)
    extra_water = 4 * max(0, feature_level - 1)
    extra_roads = max(0, feature_level - 2)

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
    return features


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


def _create_demo_grid(size: int = 42, feature_level: int = 1) -> tuple[list[list[DemoTile]], list[MockFeature], BaseStation]:
    """Create a deterministic grid populated by OSM-like features."""

    scale = size / 14.0
    features = _create_mock_features(scale=scale, feature_level=feature_level)

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
) -> dict[int, list]:
    drone_count = max(1, int(drone_count))
    if auto_scale:
        grid_size, feature_level = _auto_scale_config(drone_count)
    else:
        grid_size = 42
        feature_level = 1

    if force_grid_size is not None:
        grid_size = max(16, int(force_grid_size))

    grid, features, base = _create_demo_grid(size=grid_size, feature_level=feature_level)
    drone_starts = [(base.row, base.col) for _ in range(drone_count)]
    assignments = search_grid_with_drones(grid, drone_positions=drone_starts, num_drones=drone_count)
    jobs = _build_demo_jobs(assignments, grid)

    print(f"\n=== Demo: drones={drone_count}, grid={grid_size}x{grid_size}, feature_level={feature_level} ===")
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Agent D pathing visualization demo with OSM-like features.")
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
    args = parser.parse_args()
    run_demo(
        drone_count=args.drones,
        save_prefix=args.save,
        show_plots=not args.no_show,
        auto_scale=not args.no_auto_scale,
        force_grid_size=args.grid_size,
    )


if __name__ == "__main__":
    main()
