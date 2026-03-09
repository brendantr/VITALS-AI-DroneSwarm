from TerrainPreProcessing.terrain_queries import create_search_area
from TerrainPreProcessing.visualization import plot_search_area

# UCF area polygon (same coordinates used in the existing test.py)
polygon_points = (
    (28.6055263, -81.2037652),
    (28.6053378, -81.1950105),
    (28.5973877, -81.1945813),
    (28.5971993, -81.2038939),
)

search_tags = {"building": True, "water": True}

# useOSMX=False forces it to use your local PostGIS database instead of the internet
rtree_index, grid, viable_positions = create_search_area(
    polygon_points, search_tags, useOSMX=False
)

if rtree_index is None:
    print("❌ Failed to create search area - PostGIS query returned no data")
else:
    print(f"✅ Search area created successfully!")
    print(f"   Grid size: {len(grid)} x {len(grid[0])}")
    print(f"   Viable positions: {len(viable_positions)}")

    # Count features found
    total_buildings = 0
    total_water = 0
    for row in grid:
        for tile in row:
            if tile.in_searcharea:
                total_buildings += tile.contains_count.get("building", 0)
                total_water += tile.contains_count.get("water", 0)

    print(f"   Total buildings found: {total_buildings}")
    print(f"   Total water features found: {total_water}")

    # Visualize the result (will open a matplotlib window)
    plot_search_area(rtree_index, grid, polygon_points)