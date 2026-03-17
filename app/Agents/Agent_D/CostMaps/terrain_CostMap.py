# Cost Map - R-tree terrain cost map for each terrain.

from __future__ import annotations

import math
import osmnx as ox
import geopandas as gpd
import pandas as pd
import matplotlib.pyplot as plt
from rtree import index
from shapely.geometry import Polygon, MultiPolygon, box
from shapely.ops import unary_union
import random
from dataclasses import dataclass, field
from typing import Any

try:
    from pathing_CostMap import PathingCostMap
except ImportError:  # Script execution fallback.
    from Agents.Agent_D.CostMaps.pathing_CostMap import PathingCostMap  # type: ignore


class Tile:
    def __init__(self):
        self.contains = {}
        self.contains_count = {}
        self.in_searcharea = True
        self.total_count = 0
        # All pathing cost maps that have been computed on this tile.
        self.pathing_cost_maps: list[PathingCostMap] = []

    def add_pathing_cost_map(self, cost_map: PathingCostMap) -> None:
        self.pathing_cost_maps.append(cost_map.clone())


@dataclass
class TerrainTileCostRecord:
    tile_id: str
    t_tree_node_id: str | None = None
    osm_tile: Any = None
    pathing_cost_maps: list[PathingCostMap] = field(default_factory=list)
    dynamic_items: list[dict[str, Any]] = field(default_factory=list)

    def add_pathing_cost_map(self, cost_map: PathingCostMap) -> None:
        copied = cost_map.clone()
        copied.terrain_tile_id = copied.terrain_tile_id or self.tile_id
        self.pathing_cost_maps.append(copied)

    def add_dynamic_item(self, item_kind: str, metadata: dict[str, Any] | None = None) -> None:
        payload = {"kind": str(item_kind), "metadata": dict(metadata or {})}
        self.dynamic_items.append(payload)


@dataclass
class TerrainCostMapRegistry:
    """Registry for pathing cost maps per terrain tile while keeping t-tree linkage."""

    terrain_id: str
    t_tree: Any = None
    tiles: dict[str, TerrainTileCostRecord] = field(default_factory=dict)

    def get_or_create_tile(self, tile_id: str, t_tree_node_id: str | None = None, osm_tile: Any = None) -> TerrainTileCostRecord:
        key = str(tile_id)
        if key not in self.tiles:
            self.tiles[key] = TerrainTileCostRecord(tile_id=key, t_tree_node_id=t_tree_node_id, osm_tile=osm_tile)
        record = self.tiles[key]
        if t_tree_node_id is not None:
            record.t_tree_node_id = t_tree_node_id
        if osm_tile is not None:
            record.osm_tile = osm_tile
        return record

    def add_pathing_cost_map(
        self,
        tile_id: str,
        cost_map: PathingCostMap,
        t_tree_node_id: str | None = None,
        osm_tile: Any = None,
    ) -> None:
        tile_record = self.get_or_create_tile(tile_id=tile_id, t_tree_node_id=t_tree_node_id, osm_tile=osm_tile)
        tile_record.add_pathing_cost_map(cost_map)

    def get_pathing_cost_maps(self, tile_id: str) -> list[PathingCostMap]:
        record = self.tiles.get(str(tile_id))
        if record is None:
            return []
        return [cost_map.clone() for cost_map in record.pathing_cost_maps]

    def add_dynamic_item(
        self,
        tile_id: str,
        item_kind: str,
        metadata: dict[str, Any] | None = None,
        t_tree_node_id: str | None = None,
        osm_tile: Any = None,
    ) -> None:
        tile_record = self.get_or_create_tile(tile_id=tile_id, t_tree_node_id=t_tree_node_id, osm_tile=osm_tile)
        tile_record.add_dynamic_item(item_kind=item_kind, metadata=metadata)


def haversine(lat1, lon1, lat2, lon2):
    """Compute the great-circle distance between two points using the Haversine formula."""
    R = 6371000  # Earth's radius in meters

    # Convert degrees to radians
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    # Haversine formula
    a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c  # Distance in meters


def rectangle_side_lengths(lat1, lon1, lat2, lon2):
    """Calculate the two side lengths of the rectangle between two latitude/longitude points."""
    width = haversine(lat1, lon1, lat1, lon2)  # Distance along latitude (east-west)
    height = haversine(lat1, lon1, lat2, lon1)  # Distance along longitude (north-south)
    return width, height


def add_meters_to_latitude(lat, meters):
    """Adds a specified number of meters to the latitude."""
    meters_per_degree_latitude = 111320  # Roughly constant
    delta_latitude = meters / meters_per_degree_latitude
    return lat + delta_latitude


def add_meters_to_longitude(lat, lon, meters):
    """Adds a specified number of meters to the longitude, adjusting for latitude."""
    meters_per_degree_longitude = 111320 * math.cos(math.radians(lat))
    delta_longitude = meters / meters_per_degree_longitude
    return lon + delta_longitude

def find_extreme_coordinates(coords):
    if not coords:
        return None  # Return None if the list is empty

    min_lat = min(coords, key=lambda x: x[0])[0]  # Lowest latitude
    max_lat = max(coords, key=lambda x: x[0])[0]  # Highest latitude
    min_lon = min(coords, key=lambda x: x[1])[1]  # Leftmost (minimum longitude)
    max_lon = max(coords, key=lambda x: x[1])[1]  # Rightmost (maximum longitude)

    return {
        "lowest_latitude": min_lat,
        "highest_latitude": max_lat,
        "leftmost_longitude": min_lon,
        "rightmost_longitude": max_lon
    }
