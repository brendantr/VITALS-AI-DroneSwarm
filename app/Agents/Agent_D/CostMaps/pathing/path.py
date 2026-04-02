from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from shapely.geometry import Point


DIRECTIONS = [(-1, 0), (1, 0), (0, -1), (0, 1)]


@dataclass
class SearchPlan:
    cell_paths: dict[int, list[tuple[int, int]]]
    centroid_paths: dict[int, list]
    fallback_mode: str = "object_search"


def heuristic(a, b):
    """Manhattan distance on grid coordinates."""
    return abs(int(a[0]) - int(b[0])) + abs(int(a[1]) - int(b[1]))


def _build_viable_positions(grid):
    positions = []
    for r in range(len(grid)):
        for c in range(len(grid[0])):
            if not grid[r][c].in_searcharea or grid[r][c].total_count <= 0:
                continue
            positions.append((r, c))
    return positions


def _build_searcharea_positions(grid):
    positions = []
    for r in range(len(grid)):
        for c in range(len(grid[0])):
            if grid[r][c].in_searcharea:
                positions.append((r, c))
    return positions


def _default_drone_positions(grid, num_drones, pool):
    if not pool:
        pool = _build_searcharea_positions(grid)
    if not pool:
        return []
    ordered = sorted(pool)
    positions = []
    for idx in range(max(0, int(num_drones))):
        positions.append(ordered[min(idx, len(ordered) - 1)])
    return positions


def _cell_contains(cell, key):
    contains_count = getattr(cell, "contains_count", {}) or {}
    if isinstance(contains_count, dict) and contains_count.get(key, 0) > 0:
        return True

    contains = getattr(cell, "contains", {}) or {}
    if isinstance(contains, dict):
        return bool(contains.get(key, []))
    return False


def _cell_tag_names(cell, key):
    contains = getattr(cell, "contains", {}) or {}
    if not isinstance(contains, dict):
        return tuple()
    names = contains.get(key, [])
    if not names:
        return tuple()
    return tuple(sorted({str(name) for name in names}))


def _first_tag_name(cell, key):
    names = _cell_tag_names(cell, key)
    return names[0] if names else None


def _object_groups(grid, viable_cells):
    """Group building/water cells by object name and road cells separately."""
    grouped_objects = {}
    road_cells = set()
    for cell in viable_cells:
        tile = grid[cell[0]][cell[1]]
        building_name = _first_tag_name(tile, "building")
        water_name = _first_tag_name(tile, "water")
        is_road = _cell_contains(tile, "highway")
        if building_name is not None:
            key = ("building", building_name)
            grouped_objects.setdefault(key, set()).add(cell)
            continue
        if water_name is not None:
            key = ("water", water_name)
            grouped_objects.setdefault(key, set()).add(cell)
            continue
        if is_road:
            road_cells.add(cell)
    return grouped_objects, road_cells


def _centroid_cell(cells):
    n = max(1, len(cells))
    avg_r = sum(r for (r, _c) in cells) / float(n)
    avg_c = sum(c for (_r, c) in cells) / float(n)
    return (avg_r, avg_c)


def _nearest_cell(ref, cells):
    return min(cells, key=lambda cell: heuristic(ref, cell))


def _ordered_cells_contiguous(cells, start):
    """Greedy contiguous walk: prefer adjacent unvisited cells, else nearest."""
    if not cells:
        return []
    remaining = set(cells)
    current = _nearest_cell(start, remaining)
    ordered = [current]
    remaining.remove(current)
    while remaining:
        adjacent = []
        for dr, dc in DIRECTIONS:
            nxt = (current[0] + dr, current[1] + dc)
            if nxt in remaining:
                adjacent.append(nxt)
        if adjacent:
            nxt = min(adjacent, key=lambda c: heuristic(current, c))
        else:
            nxt = _nearest_cell(current, remaining)
        ordered.append(nxt)
        remaining.remove(nxt)
        current = nxt
    return ordered


def _connected_components(cells):
    remaining = set(cells)
    components = []
    while remaining:
        start = remaining.pop()
        q = deque([start])
        comp = {start}
        while q:
            r, c = q.popleft()
            for dr, dc in DIRECTIONS:
                nxt = (r + dr, c + dc)
                if nxt in remaining:
                    remaining.remove(nxt)
                    comp.add(nxt)
                    q.append(nxt)
        components.append(comp)
    return components


def _assign_objects_to_drones(object_items, drone_positions, drone_ids):
    """Assign one object to one drone with nearest-first deterministic ordering."""
    assignments = {drone_id: [] for drone_id in drone_ids}
    per_drone_load = {drone_id: 0 for drone_id in drone_ids}
    current_pos = {
        drone_id: drone_positions[idx]
        for idx, drone_id in enumerate(drone_ids)
    }

    for item in object_items:
        object_cells = item["cells"]
        object_center = item["center"]
        best_drone = min(
            drone_ids,
            key=lambda drone_id: (
                per_drone_load[drone_id],
                heuristic(current_pos[drone_id], object_center),
                drone_id,
            ),
        )
        ordered_cells = _ordered_cells_contiguous(object_cells, current_pos[best_drone])
        assignments[best_drone].extend(ordered_cells)
        per_drone_load[best_drone] += len(ordered_cells)
        current_pos[best_drone] = ordered_cells[-1] if ordered_cells else current_pos[best_drone]

    return assignments, current_pos


def _assign_component_paths(search_cells, current_pos, base_positions):
    if not search_cells:
        return {drone_id: [] for drone_id in current_pos}

    drone_ids = sorted(current_pos)
    components = _connected_components(search_cells)
    component_items = []
    for comp in components:
        center = _centroid_cell(comp)
        base_dist = min(heuristic(base_positions[drone_id], center) for drone_id in drone_ids)
        component_items.append({"cells": comp, "center": center, "base_dist": base_dist})
    component_items.sort(key=lambda item: item["base_dist"])

    assignments = {drone_id: [] for drone_id in drone_ids}
    for item in component_items:
        cells = item["cells"]
        center = item["center"]
        best_drone = min(drone_ids, key=lambda drone_id: heuristic(current_pos[drone_id], center))
        ordered = _ordered_cells_contiguous(cells, current_pos[best_drone])
        assignments[best_drone].extend(ordered)
        if ordered:
            current_pos[best_drone] = ordered[-1]
    return assignments


def _split_component_paths(search_cells, current_pos, base_positions):
    if not search_cells:
        return {drone_id: [] for drone_id in current_pos}

    drone_ids = sorted(current_pos)
    components = _connected_components(search_cells)
    component_items = []
    for comp in components:
        center = _centroid_cell(comp)
        base_dist = min(heuristic(base_positions[drone_id], center) for drone_id in drone_ids)
        component_items.append({"cells": comp, "center": center, "base_dist": base_dist})
    component_items.sort(key=lambda item: item["base_dist"])

    assignments = {drone_id: [] for drone_id in drone_ids}
    for item in component_items:
        center = item["center"]
        ranked_drones = sorted(
            drone_ids,
            key=lambda drone_id: (
                len(assignments[drone_id]),
                heuristic(current_pos[drone_id], center),
                drone_id,
            ),
        )
        lead_drone = ranked_drones[0]
        ordered = _ordered_cells_contiguous(item["cells"], current_pos[lead_drone])
        active_count = min(len(ordered), len(ranked_drones))
        if active_count <= 1:
            assignments[lead_drone].extend(ordered)
            if ordered:
                current_pos[lead_drone] = ordered[-1]
            continue

        base_chunk = len(ordered) // active_count
        extra = len(ordered) % active_count
        start = 0
        for index, drone_id in enumerate(ranked_drones[:active_count]):
            chunk_size = base_chunk + (1 if index < extra else 0)
            chunk = ordered[start:start + chunk_size]
            start += chunk_size
            assignments[drone_id].extend(chunk)
            if chunk:
                current_pos[drone_id] = chunk[-1]
    return assignments


def cell_paths_to_centroids(grid, cell_paths):
    centroid_paths = {drone_id: [] for drone_id in sorted(cell_paths)}
    for drone_id, cells in cell_paths.items():
        for r, c in cells:
            polygon = getattr(grid[r][c], "polygon", None)
            centroid_paths[drone_id].append(polygon.centroid if polygon is not None else Point(float(c), float(r)))
    return centroid_paths


def build_search_plan(grid, drone_positions=None, viable_grid_positions=None, num_drones=4):
    """Deterministic assignment with a cell-search fallback for empty OSM results."""

    if not grid:
        return SearchPlan(cell_paths={}, centroid_paths={}, fallback_mode="empty")

    viable_positions = list(viable_grid_positions or _build_viable_positions(grid))
    searcharea_positions = _build_searcharea_positions(grid)

    if drone_positions:
        normalized_drone_positions = [tuple(map(int, position)) for position in drone_positions]
    else:
        normalized_drone_positions = _default_drone_positions(
            grid,
            num_drones=max(0, int(num_drones)),
            pool=viable_positions or searcharea_positions,
        )

    drone_count = max(0, min(int(num_drones), len(normalized_drone_positions)))
    if drone_count <= 0:
        return SearchPlan(cell_paths={}, centroid_paths={}, fallback_mode="empty")

    drone_ids = list(range(drone_count))
    base_positions = {
        drone_id: normalized_drone_positions[idx]
        for idx, drone_id in enumerate(drone_ids)
    }

    grouped_objects, road_cells = _object_groups(grid, viable_positions)
    has_osm_items = bool(grouped_objects) or bool(road_cells)

    if has_osm_items:
        object_items = []
        for (kind, name), cells in grouped_objects.items():
            center = _centroid_cell(cells)
            object_items.append({"key": (kind, name), "cells": set(cells), "center": center})

        base_pos = base_positions[drone_ids[0]]
        object_items.sort(
            key=lambda item: (heuristic(base_pos, item["center"]), item["key"][0], item["key"][1])
        )

        object_assignments, current_pos = _assign_objects_to_drones(
            object_items,
            normalized_drone_positions,
            drone_ids,
        )
        road_assignments = _assign_component_paths(
            road_cells,
            current_pos=current_pos,
            base_positions=base_positions,
        )

        combined = {drone_id: [] for drone_id in drone_ids}
        for drone_id in drone_ids:
            combined[drone_id].extend(object_assignments.get(drone_id, []))
            combined[drone_id].extend(road_assignments.get(drone_id, []))
        fallback_mode = "object_search"
    else:
        combined = _split_component_paths(
            set(searcharea_positions),
            current_pos=dict(base_positions),
            base_positions=base_positions,
        )
        fallback_mode = "cell_search"

    return SearchPlan(
        cell_paths=combined,
        centroid_paths=cell_paths_to_centroids(grid, combined),
        fallback_mode=fallback_mode,
    )


def _insertion_delta(start_cell, cells, point_cell, insert_at):
    prev_cell = start_cell if insert_at <= 0 else cells[insert_at - 1]
    next_cell = None if insert_at >= len(cells) else cells[insert_at]

    delta = heuristic(prev_cell, point_cell)
    if next_cell is None:
        return delta
    delta += heuristic(point_cell, next_cell)
    delta -= heuristic(prev_cell, next_cell)
    return delta


def best_route_insertion(cell_paths, start_cells, point_cell, candidate_drone_ids=None):
    candidate_ids = sorted(candidate_drone_ids or cell_paths)
    if not candidate_ids:
        raise ValueError("No drone routes are available for insertion")

    best_choice = None
    for drone_id in candidate_ids:
        path = list(cell_paths.get(drone_id, []))
        if point_cell in path:
            insert_at = path.index(point_cell)
            delta = 0
            choice = (delta, len(path), drone_id, insert_at)
            if best_choice is None or choice < best_choice:
                best_choice = choice
            continue

        start_cell = start_cells.get(drone_id)
        if start_cell is None:
            start_cell = point_cell
        if not path:
            choice = (heuristic(start_cell, point_cell), 0, drone_id, 0)
            if best_choice is None or choice < best_choice:
                best_choice = choice
            continue

        for insert_at in range(len(path) + 1):
            delta = _insertion_delta(start_cell, path, point_cell, insert_at)
            choice = (delta, len(path), drone_id, insert_at)
            if best_choice is None or choice < best_choice:
                best_choice = choice

    if best_choice is None:
        raise ValueError("Unable to find a route insertion point")
    _, _, drone_id, insert_at = best_choice
    return drone_id, insert_at


def insert_point_into_cell_paths(cell_paths, start_cells, point_cell, candidate_drone_ids=None):
    next_paths = {drone_id: list(path) for drone_id, path in cell_paths.items()}
    drone_id, insert_at = best_route_insertion(
        next_paths,
        start_cells=start_cells,
        point_cell=point_cell,
        candidate_drone_ids=candidate_drone_ids,
    )
    if point_cell not in next_paths.get(drone_id, []):
        next_paths.setdefault(drone_id, []).insert(insert_at, point_cell)
    return next_paths, drone_id, insert_at


def search_grid_with_drones(grid, drone_positions=None, viable_grid_positions=None, num_drones=4):
    plan = build_search_plan(
        grid,
        drone_positions=drone_positions,
        viable_grid_positions=viable_grid_positions,
        num_drones=num_drones,
    )
    return plan.centroid_paths
