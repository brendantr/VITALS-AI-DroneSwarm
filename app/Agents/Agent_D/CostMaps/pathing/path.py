from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from math import hypot
from shapely.geometry import Point


DIRECTIONS_4 = [(-1, 0), (1, 0), (0, -1), (0, 1)]
DIRECTIONS_8 = [
    (-1, 0),
    (1, 0),
    (0, -1),
    (0, 1),
    (-1, -1),
    (-1, 1),
    (1, -1),
    (1, 1),
]


@dataclass
class SearchPlan:
    cell_paths: dict[int, list[tuple[int, int]]]
    centroid_paths: dict[int, list]
    fallback_mode: str = "object_search"


@dataclass
class SemanticCluster:
    kind: str
    cells: set[tuple[int, int]]
    road_cells: set[tuple[int, int]] = field(default_factory=set)
    attached_buildings: dict[tuple[int, int], list[set[tuple[int, int]]]] = field(default_factory=dict)
    priority: int = 0
    load_score: int = 0
    raw_cell_count: int = 0


def heuristic(a, b):
    """Manhattan distance on grid coordinates."""
    return abs(int(a[0]) - int(b[0])) + abs(int(a[1]) - int(b[1]))


def _chebyshev_distance(a, b):
    return max(abs(int(a[0]) - int(b[0])), abs(int(a[1]) - int(b[1])))


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


def _tile_feature_keys(tile, key):
    contains = getattr(tile, "contains", {}) or {}
    if not isinstance(contains, dict):
        return tuple()
    values = contains.get(key, [])
    if not values:
        return tuple()
    return tuple(sorted({str(value) for value in values}))


def _tile_has_feature(tile, key):
    if _tile_feature_keys(tile, key):
        return True
    contains_count = getattr(tile, "contains_count", {}) or {}
    return bool(contains_count.get(key, 0))


def _centroid_cell(cells):
    n = max(1, len(cells))
    avg_r = sum(r for (r, _c) in cells) / float(n)
    avg_c = sum(c for (_r, c) in cells) / float(n)
    return (avg_r, avg_c)


def _nearest_cell(ref, cells):
    return min(cells, key=lambda cell: (heuristic(ref, cell), cell[0], cell[1]))


def _neighbors(cell, directions):
    return [(cell[0] + dr, cell[1] + dc) for dr, dc in directions]


def _ordered_component_walk(cells, start, directions):
    if not cells:
        return []
    remaining = set(cells)
    current = _nearest_cell(start, remaining)
    ordered = [current]
    remaining.remove(current)
    while remaining:
        adjacent = [neighbor for neighbor in _neighbors(current, directions) if neighbor in remaining]
        if adjacent:
            current = min(adjacent, key=lambda cell: (heuristic(current, cell), cell[0], cell[1]))
        else:
            current = _nearest_cell(current, remaining)
        ordered.append(current)
        remaining.remove(current)
    return ordered


def _connected_components(cells, directions=DIRECTIONS_4):
    remaining = set(cells)
    components = []
    while remaining:
        start = remaining.pop()
        q = deque([start])
        comp = {start}
        while q:
            cell = q.popleft()
            for neighbor in _neighbors(cell, directions):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    comp.add(neighbor)
                    q.append(neighbor)
        components.append(comp)
    return components


def _dominant_axis(cells):
    rows = [cell[0] for cell in cells]
    cols = [cell[1] for cell in cells]
    width = max(cols) - min(cols) + 1
    height = max(rows) - min(rows) + 1
    return "col" if width >= height else "row"


def _axis_value(cell, axis):
    return cell[1] if axis == "col" else cell[0]


def _cross_axis_value(cell, axis):
    return cell[0] if axis == "col" else cell[1]


def _sort_drone_ids_for_axis(drone_ids, base_positions, axis):
    return sorted(
        drone_ids,
        key=lambda drone_id: (
            _axis_value(base_positions[drone_id], axis),
            _cross_axis_value(base_positions[drone_id], axis),
            drone_id,
        ),
    )


def _axis_band_ranges(cells, count, axis):
    min_axis = min(_axis_value(cell, axis) for cell in cells)
    max_axis = max(_axis_value(cell, axis) for cell in cells)
    span = max_axis - min_axis + 1
    ranges = []
    for index in range(max(0, int(count))):
        start = min_axis + (index * span) // count
        end = min_axis + (((index + 1) * span) // count) - 1
        ranges.append((start, end))
    return ranges


def _partition_cells_by_bands(cells, drone_ids, base_positions):
    assignments = {drone_id: set() for drone_id in drone_ids}
    if not cells or not drone_ids:
        return assignments, "col"

    axis = _dominant_axis(cells)
    ordered_drone_ids = _sort_drone_ids_for_axis(drone_ids, base_positions, axis)
    band_ranges = _axis_band_ranges(cells, len(ordered_drone_ids), axis)

    band_lookup = {}
    for index, (start, end) in enumerate(band_ranges):
        for axis_value in range(start, end + 1):
            band_lookup[axis_value] = index

    for cell in cells:
        axis_value = _axis_value(cell, axis)
        band_index = band_lookup.get(axis_value, len(ordered_drone_ids) - 1)
        drone_id = ordered_drone_ids[band_index]
        assignments[drone_id].add(cell)

    return assignments, axis


def _boustrophedon_order(cells, start, axis):
    if not cells:
        return []

    ordered = []
    lanes = {}
    for cell in cells:
        lane_key = _axis_value(cell, axis)
        lanes.setdefault(lane_key, []).append(cell)

    for lane_index, lane_key in enumerate(sorted(lanes)):
        lane_cells = sorted(lanes[lane_key], key=lambda cell: _cross_axis_value(cell, axis))
        if lane_index % 2 == 1:
            lane_cells.reverse()
        ordered.extend(lane_cells)

    if len(ordered) > 1 and heuristic(start, ordered[-1]) < heuristic(start, ordered[0]):
        ordered.reverse()
    return ordered


def _component_sort_key(component, axis):
    center = _centroid_cell(component)
    primary = center[1] if axis == "col" else center[0]
    secondary = center[0] if axis == "col" else center[1]
    return (primary, secondary)


def _build_band_route(cells, start, axis):
    if not cells:
        return []

    remaining = list(_connected_components(cells))
    remaining.sort(key=lambda component: _component_sort_key(component, axis))

    route = []
    current = start
    while remaining:
        best_index = min(
            range(len(remaining)),
            key=lambda index: (
                heuristic(current, _nearest_cell(current, remaining[index])),
                _component_sort_key(remaining[index], axis),
            ),
        )
        component = remaining.pop(best_index)
        ordered = _boustrophedon_order(component, current, axis)
        route.extend(ordered)
        if ordered:
            current = ordered[-1]
    return route


def _checkerboard_parity(drone_positions):
    parity_counts = {0: 0, 1: 0}
    for row, col in drone_positions:
        parity_counts[(int(row) + int(col)) % 2] += 1
    return 0 if parity_counts[0] >= parity_counts[1] else 1


def _apply_checkerboard_sampling(assignments, search_cells, base_positions):
    sampled_cells = {
        cell
        for cell in search_cells
        if (cell[0] + cell[1]) % 2 == _checkerboard_parity(base_positions.values())
    }
    sampled_assignments = {}
    for drone_id, cells in assignments.items():
        sampled = set(cells) & sampled_cells
        if not sampled and cells:
            sampled = {_nearest_cell(base_positions[drone_id], cells)}
        sampled_assignments[drone_id] = sampled
    return sampled_assignments


def _semantic_priority(kind):
    if kind == "road":
        return 0
    if kind == "building":
        return 1
    return 2


def _cluster_load_score(grid, cells):
    return sum(int(getattr(grid[row][col], "total_count", 0) or 0) for row, col in cells)


def _expand_cells_one_ring(cells, search_cells):
    expanded = set(cells)
    searchable = set(search_cells)
    for cell in list(cells):
        for neighbor in _neighbors(cell, DIRECTIONS_8):
            if neighbor in searchable:
                expanded.add(neighbor)
    return expanded


def _component_distance(a_cells, b_cells):
    return min(heuristic(a_cell, b_cell) for a_cell in a_cells for b_cell in b_cells)


def _component_tiebreak(cells):
    center = _centroid_cell(cells)
    return (round(center[0], 4), round(center[1], 4))


def _extract_semantic_clusters(grid, searchable_cells):
    searchable = set(searchable_cells)
    road_cells = {
        cell
        for cell in searchable
        if _tile_has_feature(grid[cell[0]][cell[1]], "highway")
    }
    building_cells = {
        cell
        for cell in searchable
        if _tile_has_feature(grid[cell[0]][cell[1]], "building") and cell not in road_cells
    }
    water_cells = {
        cell
        for cell in searchable
        if _tile_has_feature(grid[cell[0]][cell[1]], "water")
        and cell not in road_cells
        and cell not in building_cells
    }

    road_components = _connected_components(road_cells, directions=DIRECTIONS_8)
    road_expansions = [_expand_cells_one_ring(component, searchable) for component in road_components]
    road_attachments = {index: [] for index in range(len(road_components))}

    standalone_building_components = []
    for component in _connected_components(building_cells, directions=DIRECTIONS_8):
        candidate_indexes = [
            index
            for index, expanded in enumerate(road_expansions)
            if component & expanded
        ]
        if not candidate_indexes:
            standalone_building_components.append(component)
            continue
        best_index = min(
            candidate_indexes,
            key=lambda index: (
                _component_distance(component, road_components[index]),
                -len(component & road_expansions[index]),
                _component_tiebreak(road_components[index]),
            ),
        )
        road_attachments[best_index].append(component)

    clusters = []
    for index, road_component in enumerate(road_components):
        anchor_map = {}
        cells = set(road_component)
        for building_component in road_attachments.get(index, []):
            anchor = _nearest_cell(_centroid_cell(building_component), road_component)
            anchor_map.setdefault(anchor, []).append(building_component)
            cells.update(building_component)
        clusters.append(
            SemanticCluster(
                kind="road",
                cells=cells,
                road_cells=set(road_component),
                attached_buildings=anchor_map,
                priority=_semantic_priority("road"),
                load_score=_cluster_load_score(grid, cells),
                raw_cell_count=len(cells),
            )
        )

    for component in standalone_building_components:
        clusters.append(
            SemanticCluster(
                kind="building",
                cells=set(component),
                priority=_semantic_priority("building"),
                load_score=_cluster_load_score(grid, component),
                raw_cell_count=len(component),
            )
        )

    for component in _connected_components(water_cells, directions=DIRECTIONS_8):
        clusters.append(
            SemanticCluster(
                kind="water",
                cells=set(component),
                priority=_semantic_priority("water"),
                load_score=_cluster_load_score(grid, component),
                raw_cell_count=len(component),
            )
        )

    return clusters


def _cluster_entry_cell(cluster, reference_cell):
    candidate_cells = cluster.road_cells if cluster.kind == "road" and cluster.road_cells else cluster.cells
    return _nearest_cell(reference_cell, candidate_cells)


def _cluster_sort_key(cluster):
    center = _centroid_cell(cluster.cells)
    return (
        cluster.priority,
        -cluster.load_score,
        -cluster.raw_cell_count,
        round(center[0], 4),
        round(center[1], 4),
    )


def _assign_clusters_to_drones(clusters, base_positions):
    assignments = {drone_id: [] for drone_id in sorted(base_positions)}
    loads = {drone_id: 0 for drone_id in assignments}
    ordered_clusters = sorted(
        clusters,
        key=lambda cluster: (
            -cluster.load_score,
            -cluster.raw_cell_count,
            cluster.priority,
            _cluster_sort_key(cluster),
        ),
    )

    for cluster in ordered_clusters:
        best_drone = min(
            assignments,
            key=lambda drone_id: (
                heuristic(base_positions[drone_id], _cluster_entry_cell(cluster, base_positions[drone_id])),
                loads[drone_id],
                drone_id,
            ),
        )
        assignments[best_drone].append(cluster)
        loads[best_drone] += cluster.load_score

    return assignments


def _direction_vector(a, b):
    dr = float(b[0] - a[0])
    dc = float(b[1] - a[1])
    magnitude = hypot(dr, dc)
    if magnitude == 0:
        return (0.0, 0.0)
    return (dr / magnitude, dc / magnitude)


def _road_neighbor_score(current, candidate, prev_direction, road_cells, unvisited):
    candidate_direction = _direction_vector(current, candidate)
    if prev_direction is None:
        direction_penalty = 0.0
    else:
        direction_penalty = 1.0 - (
            (prev_direction[0] * candidate_direction[0]) + (prev_direction[1] * candidate_direction[1])
        )
    road_degree = sum(1 for neighbor in _neighbors(candidate, DIRECTIONS_8) if neighbor in road_cells)
    unvisited_degree = sum(1 for neighbor in _neighbors(candidate, DIRECTIONS_8) if neighbor in unvisited)
    return (
        direction_penalty,
        -road_degree,
        -unvisited_degree,
        heuristic(current, candidate),
        candidate[0],
        candidate[1],
    )


def _ordered_road_neighbors(current, previous, road_cells, visited):
    prev_direction = None
    if previous is not None and previous != current:
        prev_direction = _direction_vector(previous, current)
    unvisited = set(road_cells) - set(visited)
    candidates = [
        neighbor
        for neighbor in _neighbors(current, DIRECTIONS_8)
        if neighbor in road_cells and neighbor not in visited
    ]
    return sorted(
        candidates,
        key=lambda candidate: _road_neighbor_score(
            current,
            candidate,
            prev_direction,
            road_cells=road_cells,
            unvisited=unvisited,
        ),
    )


def _trim_after_last_new_cell(route):
    seen = set()
    last_new_index = -1
    for index, cell in enumerate(route):
        if cell in seen:
            continue
        seen.add(cell)
        last_new_index = index
    if last_new_index < 0:
        return []
    return route[: last_new_index + 1]


def _direction_preserving_road_walk(road_cells, start):
    if not road_cells:
        return []

    start_cell = _nearest_cell(start, road_cells)
    route = [start_cell]
    visited = {start_cell}
    stack = [
        (
            start_cell,
            None,
            _ordered_road_neighbors(start_cell, start if start != start_cell else None, road_cells, visited),
        )
    ]

    while stack:
        current, previous, candidates = stack[-1]
        next_cell = None
        while candidates:
            candidate = candidates.pop(0)
            if candidate not in visited:
                next_cell = candidate
                break
        if next_cell is None:
            stack.pop()
            if stack:
                _emit_cell(route, stack[-1][0])
            continue

        visited.add(next_cell)
        route.append(next_cell)
        stack.append(
            (
                next_cell,
                current,
                _ordered_road_neighbors(next_cell, current, road_cells, visited),
            )
        )

    return _trim_after_last_new_cell(route)


def _emit_cell(route, cell):
    if not route or route[-1] != cell:
        route.append(cell)


def _route_road_cluster(cluster, start):
    road_order = _direction_preserving_road_walk(cluster.road_cells, start)
    route = []
    handled_components = set()
    for road_index, road_cell in enumerate(road_order):
        _emit_cell(route, road_cell)
        next_road = road_order[road_index + 1] if (road_index + 1) < len(road_order) else None
        building_components = sorted(
            cluster.attached_buildings.get(road_cell, []),
            key=lambda component: (
                heuristic(road_cell, _nearest_cell(road_cell, component)),
                _component_tiebreak(component),
            ),
        )
        for component_index, component in enumerate(building_components):
            component_key = tuple(sorted(component))
            if component_key in handled_components:
                continue
            handled_components.add(component_key)
            excursion = _ordered_component_walk(component, road_cell, DIRECTIONS_8)
            for cell in excursion:
                _emit_cell(route, cell)
            should_return = next_road is not None or component_index < (len(building_components) - 1)
            if should_return:
                for cell in reversed(excursion):
                    _emit_cell(route, cell)
                _emit_cell(route, road_cell)
    return route


def _route_semantic_cluster(cluster, start):
    if cluster.kind == "road":
        return _route_road_cluster(cluster, start)
    return _ordered_component_walk(cluster.cells, start, DIRECTIONS_8)


def _build_semantic_routes(grid, searchable_cells, base_positions):
    clusters = _extract_semantic_clusters(grid, searchable_cells)
    if not clusters:
        return {drone_id: [] for drone_id in sorted(base_positions)}

    cluster_assignments = _assign_clusters_to_drones(clusters, base_positions)
    routes = {drone_id: [] for drone_id in sorted(base_positions)}
    for drone_id in sorted(base_positions):
        current = base_positions[drone_id]
        remaining = list(cluster_assignments.get(drone_id, []))
        while remaining:
            next_index = min(
                range(len(remaining)),
                key=lambda index: (
                    remaining[index].priority,
                    heuristic(current, _cluster_entry_cell(remaining[index], current)),
                    -remaining[index].load_score,
                    -remaining[index].raw_cell_count,
                    _cluster_sort_key(remaining[index]),
                ),
            )
            cluster = remaining.pop(next_index)
            segment = _route_semantic_cluster(cluster, current)
            for cell in segment:
                _emit_cell(routes[drone_id], cell)
            if segment:
                current = segment[-1]
        routes[drone_id] = list(routes[drone_id])
    return routes


def cell_paths_to_centroids(grid, cell_paths):
    centroid_paths = {drone_id: [] for drone_id in sorted(cell_paths)}
    for drone_id, cells in cell_paths.items():
        for r, c in cells:
            polygon = getattr(grid[r][c], "polygon", None)
            centroid_paths[drone_id].append(polygon.centroid if polygon is not None else Point(float(c), float(r)))
    return centroid_paths


def build_search_plan(grid, drone_positions=None, viable_grid_positions=None, num_drones=4):
    """Deterministic assignment with semantic OSM routing and checkerboard fallback."""

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

    searchable_viable_cells = set(viable_positions)
    has_osm_items = bool(searchable_viable_cells)

    if has_osm_items:
        combined = _build_semantic_routes(
            grid,
            searchable_cells=searchable_viable_cells,
            base_positions=base_positions,
        )
        fallback_mode = "object_search"
    else:
        band_assignments, sweep_axis = _partition_cells_by_bands(
            set(searcharea_positions),
            drone_ids=drone_ids,
            base_positions=base_positions,
        )
        sampled_assignments = _apply_checkerboard_sampling(
            band_assignments,
            search_cells=set(searcharea_positions),
            base_positions=base_positions,
        )
        combined = {
            drone_id: _build_band_route(
                sampled_assignments.get(drone_id, set()),
                start=base_positions[drone_id],
                axis=sweep_axis,
            )
            for drone_id in drone_ids
        }
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
