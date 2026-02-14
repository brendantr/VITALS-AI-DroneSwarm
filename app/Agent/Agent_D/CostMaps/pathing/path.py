import random
from collections import deque


DIRECTIONS = [(-1, 0), (1, 0), (0, -1), (0, 1)]


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


def _assign_objects_to_drones(object_items, drone_positions, num_drones):
    """Assign one object to one drone with nearest-first deterministic ordering."""
    drone_ids = list(range(num_drones))
    assignments = {drone_id: [] for drone_id in drone_ids}
    per_drone_load = {drone_id: 0 for drone_id in drone_ids}
    current_pos = {drone_id: drone_positions[drone_id] for drone_id in drone_ids}

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


def _assign_road_components(road_cells, current_pos, base_positions):
    if not road_cells:
        return {drone_id: [] for drone_id in current_pos}

    drone_ids = sorted(current_pos)
    components = _connected_components(road_cells)
    component_items = []
    for comp in components:
        center = _centroid_cell(comp)
        base_dist = min(heuristic(base_positions[drone_id], center) for drone_id in drone_ids)
        component_items.append({"cells": comp, "center": center, "base_dist": base_dist})
    component_items.sort(key=lambda item: item["base_dist"])

    road_assignments = {drone_id: [] for drone_id in drone_ids}
    for item in component_items:
        cells = item["cells"]
        center = item["center"]
        best_drone = min(drone_ids, key=lambda drone_id: heuristic(current_pos[drone_id], center))
        ordered = _ordered_cells_contiguous(cells, current_pos[best_drone])
        road_assignments[best_drone].extend(ordered)
        if ordered:
            current_pos[best_drone] = ordered[-1]
    return road_assignments


def _cells_to_centroids(grid, assignments_cells):
    precomp_destinations = {drone_id: [] for drone_id in sorted(assignments_cells)}
    for drone_id, cells in assignments_cells.items():
        for r, c in cells:
            precomp_destinations[drone_id].append(grid[r][c].polygon.centroid)
    return precomp_destinations


def search_grid_with_drones(grid, drone_positions=None, viable_grid_positions=None, num_drones=4):
    """Deterministic assignment:
    1) Assign one building/water object to one drone (nearest-first by object).
    2) Within each object, traverse contiguous cells to avoid hopping.
    3) Assign roads by connected segments with contiguous traversal.
    """

    grid_size = len(grid)
    if not drone_positions:
        drone_positions = [(random.randint(0, grid_size - 1), random.randint(0, grid_size - 1)) for _ in range(num_drones)]

    if not viable_grid_positions:
        viable_grid_positions = _build_viable_positions(grid)

    precomp_destinations = {x: [] for x in range(len(drone_positions))}
    if not viable_grid_positions:
        return precomp_destinations

    drone_count = max(0, min(int(num_drones), len(drone_positions)))
    if drone_count <= 0:
        return precomp_destinations

    grouped_objects, road_cells = _object_groups(grid, viable_grid_positions)

    object_items = []
    for (kind, name), cells in grouped_objects.items():
        center = _centroid_cell(cells)
        object_items.append({"key": (kind, name), "cells": set(cells), "center": center})

    # Nearest objects first from base for deterministic outward expansion.
    base_pos = drone_positions[0]
    object_items.sort(key=lambda item: (heuristic(base_pos, item["center"]), item["key"][0], item["key"][1]))

    base_positions = {drone_id: drone_positions[drone_id] for drone_id in range(drone_count)}
    object_assignments, current_pos = _assign_objects_to_drones(object_items, base_positions, drone_count)
    road_assignments = _assign_road_components(road_cells, current_pos=current_pos, base_positions=base_positions)

    combined = {drone_id: [] for drone_id in range(drone_count)}
    for drone_id in range(drone_count):
        combined[drone_id].extend(object_assignments.get(drone_id, []))
        combined[drone_id].extend(road_assignments.get(drone_id, []))

    return _cells_to_centroids(grid, combined)
