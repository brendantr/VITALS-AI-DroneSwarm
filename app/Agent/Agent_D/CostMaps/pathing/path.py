import math
import random

# Directions for moving up, down, left, right
DIRECTIONS = [(-1, 0), (1, 0), (0, -1), (0, 1)]

ROAD_PRIORITY_BONUS = 18.0
BUILDING_PRIORITY_BONUS = 10.0


def heuristic(a, b):
    """Manhattan distance on grid coordinates."""
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _is_highway_cell(cell):
    contains_count = getattr(cell, "contains_count", {}) or {}
    if isinstance(contains_count, dict) and contains_count.get("highway", 0) > 0:
        return True

    contains = getattr(cell, "contains", {}) or {}
    if isinstance(contains, dict):
        return bool(contains.get("highway", []))
    return False


def _is_building_cell(cell):
    contains_count = getattr(cell, "contains_count", {}) or {}
    if isinstance(contains_count, dict) and contains_count.get("building", 0) > 0:
        return True

    contains = getattr(cell, "contains", {}) or {}
    if isinstance(contains, dict):
        return bool(contains.get("building", []))
    return False


def _build_viable_positions(grid):
    positions = []
    for i in range(len(grid)):
        for j in range(len(grid[0])):
            if not grid[i][j].in_searcharea or grid[i][j].total_count == 0:
                continue
            positions.append((i, j))
    return positions


def _weighted_center(grid, assigned_cells):
    if not assigned_cells:
        return None
    total_w = 0.0
    row_sum = 0.0
    col_sum = 0.0
    for r, c in assigned_cells:
        w = max(1.0, float(grid[r][c].total_count))
        row_sum += r * w
        col_sum += c * w
        total_w += w
    return (row_sum / total_w, col_sum / total_w)


def _score_cell(grid, cell, base_pos, center_pos, radius):
    r, c = cell
    tile = grid[r][c]
    priority = float(tile.total_count)
    dist_from_base = heuristic(base_pos, cell)
    dist_from_center = heuristic(center_pos, cell)
    outside_penalty = max(0.0, dist_from_center - radius)

    # Roads are searchable points and high-priority connectors between POIs.
    road_bonus = ROAD_PRIORITY_BONUS if _is_highway_cell(tile) else 0.0
    building_bonus = BUILDING_PRIORITY_BONUS if _is_building_cell(tile) else 0.0

    return (12.0 * priority) + road_bonus + building_bonus - (1.6 * dist_from_base) - (2.8 * outside_penalty)


def search_grid_with_drones(grid, drone_positions=None, viable_grid_positions=None, num_drones=4):
    """Assign search cells to drones one-by-one.

    - Each cell is assigned to only one drone.
    - Roads are treated as high-priority search points (not exclusive to one drone).
    - If there are no assignable building cells left, remaining cells are still assigned one-by-one.
    """

    grid_size = len(grid)
    if not drone_positions:
        drone_positions = [(random.randint(0, grid_size - 1), random.randint(0, grid_size - 1)) for _ in range(num_drones)]

    precomp_destinations = {x: [] for x in range(len(drone_positions))}

    if not viable_grid_positions:
        viable_grid_positions = _build_viable_positions(grid)

    if not viable_grid_positions:
        return precomp_destinations

    unassigned = set(viable_grid_positions)
    active_drone_ids = sorted(range(len(drone_positions)))
    if not active_drone_ids:
        return precomp_destinations

    centers = {drone_id: drone_positions[drone_id] for drone_id in active_drone_ids}
    assigned_cells_by_drone = {drone_id: [] for drone_id in active_drone_ids}

    # One-by-one assignment across drones until nothing is left.
    while unassigned:
        remaining = len(unassigned)
        density = remaining / max(1.0, float(len(viable_grid_positions)))
        quota = max(1, math.ceil(remaining / len(active_drone_ids)))
        radius = max(1.0, math.sqrt(quota / (math.pi * max(density, 1e-9))))

        progress = False
        for drone_id in active_drone_ids:
            if not unassigned:
                break

            center = centers[drone_id]
            best = max(unassigned, key=lambda cell: _score_cell(grid, cell, drone_positions[drone_id], center, radius))
            unassigned.remove(best)
            progress = True

            assigned_cells_by_drone[drone_id].append(best)
            precomp_destinations[drone_id].append(grid[best[0]][best[1]].polygon.centroid)
            drone_positions[drone_id] = best

            weighted_center = _weighted_center(grid, assigned_cells_by_drone[drone_id])
            if weighted_center is not None:
                centers[drone_id] = weighted_center

        if not progress:
            break

    return precomp_destinations

