import math
import osmnx as ox
import geopandas as gpd
import pandas as pd
import matplotlib.pyplot as plt
from rtree import index
from shapely.geometry import Polygon, MultiPolygon, box
from shapely.ops import unary_union
import random


class Tile:
    def __init__(self):
        self.contains = {}
        self.contains_count = {}
        self.in_searcharea = True
        self.total_count = 0


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