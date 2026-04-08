from __future__ import annotations

from ...CostMaps.terrain_CostMap import (
    Tile,
    build_tile_id,
    find_extreme_coordinates,
    rectangle_side_lengths,
)
from ..postgis.postgis_handler import query_features_in_polygon, query_tile_counts_4326
from rtree import index

def _build_grid_from_tile_counts(tile_rows, search_tags, terrain_id):
    if not tile_rows:
        return None, None

    max_x = max(int(r.get("x_idx", 0)) for r in tile_rows)
    max_y = max(int(r.get("y_idx", 0)) for r in tile_rows)
    width = max_x + 1
    height = max_y + 1

    grid = [[Tile() for _ in range(width)] for _ in range(height)]
    viable = []

    for y in range(height):
        for x in range(width):
            tile = grid[y][x]
            tile.row = y
            tile.col = x
            tile.tile_id = build_tile_id(terrain_id, y, x)
            tile.contains_count = {tag: 0 for tag in search_tags}
            tile.contains = {tag: [] for tag in search_tags}
            tile.total_count = 0
            tile.in_searcharea = False
            tile.polygon = None

    for row in tile_rows:
        x = int(row.get("x_idx", 0))
        y = int(row.get("y_idx", 0))
        tile = grid[y][x]

        counts = row.get("counts", {})
        building_ct = int(counts.get("building", 0))
        water_ct = int(counts.get("water", 0))
        highway_ct = int(counts.get("highway", 0))
        ped_ct = int(counts.get("pedestrian_path", 0))

        tile.polygon = row.get("tile_polygon")
        tile.in_searcharea = True

        if "building" in tile.contains_count:
            tile.contains_count["building"] = building_ct
            tile.contains["building"] = [f"building_{x}_{y}"] * building_ct
        if "water" in tile.contains_count:
            tile.contains_count["water"] = water_ct
            tile.contains["water"] = [f"water_{x}_{y}"] * water_ct
        if "highway" in tile.contains_count:
            tile.contains_count["highway"] = highway_ct + ped_ct
            tile.contains["highway"] = (["highway"] * highway_ct) + (["pedestrian_path"] * ped_ct)

        tile.total_count = int(row.get("total_count", building_ct + water_ct + highway_ct + ped_ct))
        if tile.total_count > 0:
            viable.append((y, x))

    return grid, viable


def _build_visual_rtree_from_tile_counts(tile_rows):
    rtree_index = index.Index()
    for idx, row in enumerate(tile_rows):
        geom = row.get("tile_polygon")
        if geom is None:
            continue

        counts = row.get("counts", {})
        building_ct = int(counts.get("building", 0))
        water_ct = int(counts.get("water", 0))
        highway_ct = int(counts.get("highway", 0))
        ped_ct = int(counts.get("pedestrian_path", 0))

        # Keep the same keys visualizer expects from legacy geometry items.
        item = {
            "osm_id": f"tile_{row.get('x_idx', 0)}_{row.get('y_idx', 0)}",
            "geometry": geom,
            "building": building_ct if building_ct > 0 else None,
            "water": water_ct if water_ct > 0 else None,
            "highway": "highway" if highway_ct > 0 else ("pedestrian_path" if ped_ct > 0 else None),
        }
        rtree_index.insert(idx, geom.bounds, obj=item)

    return rtree_index


def _sanitize_tag_value(value) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return "unknown"
    return "".join(ch if ch.isalnum() else "_" for ch in text).strip("_") or "unknown"


def _feature_membership_token(feature: dict) -> tuple[str, str]:
    feature_type = str(feature.get("feature_type") or "unknown")
    osm_id = feature.get("osm_id")
    if feature_type == "building":
        return "building", f"building:{osm_id}"
    if feature_type == "water":
        return "water", f"water:{osm_id}"
    if feature_type == "highway":
        return "highway", f"highway:{osm_id}:{_sanitize_tag_value(feature.get('tag_value'))}"
    return feature_type, f"{feature_type}:{osm_id}"


def _enrich_grid_with_feature_membership(grid, feature_rows, search_tags):
    if grid is None:
        return

    for row in grid:
        for tile in row:
            contains = getattr(tile, "contains", {}) or {}
            for tag in search_tags:
                contains[tag] = []
            tile.contains = contains

    for feature in feature_rows or []:
        geometry = feature.get("geometry")
        if geometry is None:
            continue
        bucket, token = _feature_membership_token(feature)
        if bucket not in search_tags:
            continue
        for row in grid:
            for tile in row:
                polygon = getattr(tile, "polygon", None)
                if polygon is None or not getattr(tile, "in_searcharea", False):
                    continue
                if not geometry.intersects(polygon):
                    continue
                if token not in tile.contains[bucket]:
                    tile.contains[bucket].append(token)

    for row in grid:
        for tile in row:
            contains = getattr(tile, "contains", {}) or {}
            for tag in search_tags:
                contains[tag] = sorted(set(contains.get(tag, [])))
            tile.contains = contains


def create_search_area(
    polygon_points,
    search_tags,
    useOSMX=False,
    maximum_square_size=60,
    minimum_grid_size=8,
):
    # Legacy OSMnx mode is intentionally removed; only SQL/PostGIS path remains.
    if useOSMX:
        print("OSMnx mode removed. Using PostGIS SQL tile pipeline.")

    extremes = find_extreme_coordinates(polygon_points)
    top_left = (extremes["highest_latitude"], extremes["leftmost_longitude"])
    bottom_right = (extremes["lowest_latitude"], extremes["rightmost_longitude"])

    width_m, height_m = rectangle_side_lengths(top_left[0], top_left[1], bottom_right[0], bottom_right[1])
    size = max(width_m, height_m)

    if size >= minimum_grid_size * maximum_square_size:
        temp = size
        while temp > maximum_square_size:
            temp /= 2.0
        square_size = temp
    else:
        square_size = size / float(minimum_grid_size)

    # polygon_points arrives as (lat, lon) tuples from missionState — pass through as-is.
    postgis_points = polygon_points
    tile_rows = query_tile_counts_4326(postgis_points, tile_size_m=int(round(square_size)))
    if not tile_rows:
        print("PostGIS returned no tile rows; unable to create a search area.")
        return None, None, None

    terrain_id = f"terrain_{abs(hash(tuple(postgis_points)))}"
    grid, viable_grid_positions = _build_grid_from_tile_counts(tile_rows, search_tags, terrain_id)
    if grid is None:
        return None, None, None
    feature_rows = query_features_in_polygon(postgis_points)
    _enrich_grid_with_feature_membership(grid, feature_rows, search_tags)

    rtree_index = _build_visual_rtree_from_tile_counts(tile_rows)
    return rtree_index, grid, viable_grid_positions
