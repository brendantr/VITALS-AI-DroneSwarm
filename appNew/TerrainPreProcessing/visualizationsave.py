from shapely.geometry import Point, Polygon, MultiPolygon, LineString
from .geometry_utils import haversine
from .query_disambiguation import disambiguate
import matplotlib.colors as mcolors
import numpy as np
import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from collections import Counter
from matplotlib.collections import LineCollection
from matplotlib.widgets import Button

def plot_postGIS_data(data, colors = []):
    gdf = gpd.GeoDataFrame(data, crs="EPSG:3857")
    gdf = gdf.to_crs(epsg=4326)
    # Define base colors in RGBA format

    def mix_colors(row):
        """Mix colors based on the categories present in the row."""
        present_colors = [colors[key] for key in colors if row.get(key) is not None]
        
        if not present_colors:
            #print("No color, default grey")
            return (0.5, 0.5, 0.5, 1)  # Default gray if no category is present

        # Convert to NumPy array and average across all present colors
        mixed_color = np.mean(np.array(present_colors), axis=0)
        
        return tuple(mixed_color)  # Return as RGBA tuple

    # Create a new 'color' column in the GeoDataFrame based on mixed colors
    gdf["color"] = gdf.apply(mix_colors, axis=1)

    # Convert RGBA to Hex for plotting
    gdf["color_hex"] = gdf["color"].apply(lambda rgba: mcolors.to_hex(rgba))

    # Plot the map
    ax = gdf.plot(color=gdf["color_hex"], figsize=(10, 6), edgecolor="black", alpha=0.7)
    ax.set_title("Blended Colors for Mixed Categories")

import geopandas as gpd
import numpy as np
import matplotlib.colors as mcolors

def plot_drone_paths(rtree_index, grid = None, search_points = [], colors = {}, show_grid = True, polygon_darkening_factor = 0.5, drone_paths = {}):
    drone_colors = ["purple", "blue", "yellow", "green"]
    drone_ids = list(drone_paths.keys())
    drone_color_map = {drone_ids[i % len(drone_colors)]: drone_colors[i % len(drone_colors)] for i in range(len(drone_ids))}
    print("Hello, should be plotting GIS data for the drone!")
    """
    for drone_id in drone_paths:
            print("Hello, should be plotting GIS data for the drone!")
            ax = plot_postGIS_data(rtree_index,grid,search_points,colors,show_grid,polygon_darkening_factor, False)
            path = drone_paths[drone_id]
            if len(path) > 1:  # Ensure there are enough points to form a line
                flipped_path = [(p.x, p.y) for p in path]  # Flip (lat, lon) to (lon, lat)
                line = LineString(flipped_path)
                line_gdf = gpd.GeoDataFrame(geometry=[line])

                # Assign color based on the drone
                color = drone_color_map[drone_id]

                # Plot the path
                line_gdf.plot(ax=ax, color=color, linewidth=2, alpha=0.7) 

                # Mark the starting point
                start_x, start_y = flipped_path[0]
                ax.scatter(start_x, start_y, color=color, s=100, zorder=3)  # Adjust size (s) as needed

                # Add arrows to indicate direction
                for i in range(len(flipped_path) - 1):
                    x1, y1 = flipped_path[i]
                    x2, y2 = flipped_path[i + 1]

                    # Compute direction vector
                    dx, dy = x2 - x1, y2 - y1
                    ax.quiver(x1, y1, dx, dy, angles="xy", scale_units="xy", scale=1, color=color, width=0.005)
            print("Should've shown")
    """
    ax = plot_postGIS_data(rtree_index,grid,search_points,colors,show_grid,polygon_darkening_factor, False)
    
    def on_button_click(event):
        print("Button clicked!")

    ax_button = plt.axes([0, 0.9, 0.1, 0.025])  # Position of the button
    button = Button(ax_button, 'Click Me')
    button.on_clicked(on_button_click)
    ax.legend()

    plt.show()


def plot_postGIS_data(rtree_index, grid = None, search_points = [], colors = {}, show_grid = True, polygon_darkening_factor = 0.5, insta_plot= True):
    """
    Plots data from a postGIS rtree index where each item is a dictionary
    with keys such as 'osm_id', 'geometry', 'building', 'water', etc.
    
    Parameters:
      - rtree_index: The spatial index whose items are objects with a .object
                     attribute that is a dictionary (with a 'geometry' key).
      - colors: A dictionary mapping category names (e.g., "building", "water")
                to RGBA tuples (each value between 0 and 1).
    """
    # Extract the dictionary objects from the rtree index
    data_list = [item.object for item in rtree_index.intersection(rtree_index.bounds, objects=True)]
    
    # Create a GeoDataFrame using the 'geometry' key from each dictionary.
    gdf = gpd.GeoDataFrame(data_list, geometry="geometry")
    

    def mix_colors(row, darken_factor=0.5):
        darken_factor = polygon_darkening_factor
        """
        For each row, mix the colors based on which category keys are present.
        If a row has a non-None value for a category (e.g. "building", "water"),
        the corresponding color is used in the mix.
        
        Args:
        - row: The row from which we get the colors.
        - darken_factor: A factor to darken the final mixed color. Default is 0.2 (20% darker).
        
        Returns:
        - The mixed color, adjusted to be darker.
        """
        present_colors = []#[np.array(colors[key])
        #                for key in colors if row.get(key) is not None]

        for key in colors:
            if (value := row.get(key)) is not None:
                value_color = colors.get(key)
                if isinstance(value_color, dict):
                    #Need to disambiguite for some keys, since 
                    print(f"Key: {key}, Previous Value: {value}")
                    value = disambiguate(key, value)
                    if value in value_color:
                        print(f"Value: {value}, Color: {value_color[value]}")
                        present_colors.append(np.array(value_color[value]))
                else:
                    present_colors.append(np.array(value_color))
                    #print(f"Key: {key}, Value: {row.get(key)}, Type: {classify_highway(row.get(key))}")
        
        if not present_colors:
            return (0, 0, 0, 1)  # Default to grey if no categories are present
        
        # Average the RGBA colors
        mixed_color = np.mean(present_colors, axis=0)
        
        # Darken the color toward black (or a darker version of itself)
        # darken_factor: 0 = no darkening, 1 = fully darkened (black)
        
        # The darker color is a linear interpolation between the original and black
        darkened_color = (1 - darken_factor) * mixed_color[:3]
        
        # Ensure RGB values stay within valid range (0 to 1)
        darkened_color = np.clip(darkened_color, 0, 1)
        
        # Return the mixed color with the darkened RGB and the original alpha
        return tuple(np.concatenate((darkened_color, [mixed_color[3]])))

    #This first one is for the structure coloring
    def mix_tile_colors(tile):
        present_colors = []
        weights = []
        
        # Collect colors and their corresponding weights (contains_count)
        for key in colors:
            count = tile.contains_count.get(key, 0)
            if count != 0:
                value_color = colors[key]
                
                if isinstance(value_color, dict):
                    actual_values = tile.contains[key]
                    value_counts = Counter(actual_values)  # Count occurrences of each value_type
                    print(f"Hello?: {actual_values}")
                    for value_type, ct in value_counts.items():
                        value_type = disambiguate(key, value_type)  # Normalize value type
                        if value_type in value_color:
                            print(f"Key: {key} Value Type: {value_type}, Count: {ct}")
                            print(f"Value Color: {value_color}")
                            print(f"Actually used the color: {value_color.get(value_type)}")

                            present_colors.append(np.array(value_color.get(value_type)))
                            weights.append(ct)  # Assign the count as the weight
                else:
                    present_colors.append(np.array(colors[key]))    
                    weights.append(count) 
                #present_colors.append(np.array(colors[key]))  # Color for this category
            
        
        if not present_colors:
            return (0, 0, 0, 1)  # Default to black if no categories are present
        
        # Convert weights to a numpy array
        weights = np.array(weights)
        
        # Normalize weights so they sum to 1 (if needed)
        normalized_weights = weights / weights.sum()
        
        # Weighted average of the colors
        mixed_color = np.average(present_colors, axis=0, weights=normalized_weights)
        
        return tuple(mixed_color)

    # Compute the blended color for each row
    gdf["color"] = gdf.apply(mix_colors, axis=1)
    
    # Convert RGBA tuples to hexadecimal color strings for plotting
    gdf["color_hex"] = gdf["color"].apply(lambda rgba: mcolors.to_hex(rgba))
    
    
    # Plot the GeoDataFrame with the blended colors
    grid_ax = gdf.plot(color=gdf["color_hex"], figsize=(10, 6), edgecolor="black", alpha=1)
    grid_ax.set_title("Blended Colors for Mixed Categories")
    grid_ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:.4f}"))
    grid_ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda y, _: f"{y:.4f}"))    
    plt.xticks(rotation=45)  
    
    if grid and show_grid:
        tile_length = None
        for i in range(len(grid)):
            for j in range(len(grid)):
                tile = grid[i][j]
                if tile_length is None:
                    exterior_coords = list(tile.polygon.exterior.coords)
                    first,second = exterior_coords[:2]
                    tile_length = haversine(first[1],first[0], second[1],second[0])
                if not tile.in_searcharea:
                    #Black out all the grids that don't relate to the search area
                    #Actually, not annotating the tiles at all looks even better
                    #ax.fill(x, y, edgecolor='black', facecolor=tile_color, alpha=1, linewidth=1)
                    continue
                centroid = tile.polygon.centroid
                # Annotate with the counts
                text = ",".join(str(tile.contains_count[key]) for key in tile.contains_count)
                #ax.annotate(text, (centroid.x, centroid.y), color='white', 
                #           fontsize=10, ha='center', va='center', fontweight='bold')
                position = f"({i},{j})"
                grid_ax.annotate(position, (centroid.x, centroid.y), color='white', 
                           fontsize=8, ha='center', va='center', fontweight='bold')
                # Plot the polygon of each tile
                x, y = tile.polygon.exterior.xy  # Get the coordinates of the polygon
                tile_color = mix_tile_colors(tile)
                
                grid_ax.fill(x, y, edgecolor='black', facecolor=tile_color, alpha=0.75, linewidth=1)
        annotation_text = f"Tile Length: {tile_length:.2f} meters"
        grid_ax.annotate(annotation_text, xy=(0.05, 0.95), xycoords='axes fraction', 
            ha='left', va='top', fontsize=10, color='black', 
            fontweight='bold', bbox=dict(facecolor='white', edgecolor='none', alpha=0.7))
    
    #Plot the search area the user did
    if search_points and show_grid:
        flipped_coords = [(lon,lat) for lat,lon in search_points]
        new_polygon = Polygon(flipped_coords)
        new_polygon_gdf = gpd.GeoDataFrame(geometry=[new_polygon])
        new_polygon_gdf.plot(ax=grid_ax, edgecolor="black", facecolor="none", alpha=1, linewidth = 3)
    
    if insta_plot:
        plt.show()
    return grid_ax



def plot_advanced(rtree_index, grid, polygon_points, colors = {}):
    all_items = list(rtree_index.intersection(rtree_index.bounds, objects=True))
    preserved_polygons = []
    for r in all_items:
        data = r.object
        #print(data["geometry"])
        preserved_polygons.append(data["geometry"])

    gdf = gpd.GeoDataFrame(geometry=all_items, crs="EPSG:3857")
    gdf = gdf.to_crs(epsg=4326)
    
    def mix_colors(row):
        """Mix colors based on the categories present in the row."""
        present_colors = [colors[key] for key in colors if row.get(key) is not None]
        
        if not present_colors:
            #print("No color, default grey")
            return (0.5, 0.5, 0.5, 1)  # Default gray if no category is present

        # Convert to NumPy array and average across all present colors
        mixed_color = np.mean(np.array(present_colors), axis=0)
        return tuple(mixed_color)
     # Create a new 'color' column in the GeoDataFrame based on mixed colors
    gdf["color"] = gdf.apply(mix_colors, axis=1)

    # Convert RGBA to Hex for plotting
    gdf["color_hex"] = gdf["color"].apply(lambda rgba: mcolors.to_hex(rgba))

    # Plot the map
    ax = gdf.plot(color=gdf["color_hex"], figsize=(10, 6), edgecolor="black", alpha=0.7)
    ax.set_title("Blended Colors for Mixed Categories")
    plt.show()

def plot_search_area(rtree_index, grid, polygon_points):
        all_items = list(rtree_index.intersection(rtree_index.bounds, objects=True))
        preserved_polygons = []
        for r in all_items:
            data = r.object
            #print(data["geometry"])
            preserved_polygons.append(data["geometry"])

        gdf = gpd.GeoDataFrame(geometry=preserved_polygons)
        ax = gdf.plot(edgecolor='black', facecolor='blue')  # Default to blue
        gdf.iloc[[2]].plot(ax=ax, edgecolor='black', facecolor='red')
        #Show the grids
        #overlay_gdf = gpd.GeoDataFrame(geometry=all_poly) 
        # Overlay the new polygons in red with transparency (alpha)
        #overlay_gdf.plot(ax=ax, edgecolor="black", facecolor="red", alpha=0.5)

        for i in range(len(grid)):
            for j in range(len(grid)):
                tile = grid[i][j]
                centroid = tile.polygon.centroid
                # Annotate with the counts
                text = f"{tile.contains_count['building']},{tile.contains_count['water']}"
                ax.annotate(text, (centroid.x, centroid.y), color='white', 
                            fontsize=6, ha='center', va='center', fontweight='bold')
                # Plot the polygon of each tile
                x, y = tile.polygon.exterior.xy  # Get the coordinates of the polygon
                ax.fill(x, y, edgecolor='black', facecolor='red', alpha=0.5, linewidth=1)
                
        #Show the original area
        reversed_search_area = [(point[1], point[0]) for point in polygon_points]
        new_polygon = Polygon(reversed_search_area)
        new_polygon_gdf = gpd.GeoDataFrame(geometry=[new_polygon])
        new_polygon_gdf.plot(ax=ax, edgecolor="black", facecolor="green", alpha=0.3)

        #This fixes the axis issue, and lets it show better. 
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:.4f}"))
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda y, _: f"{y:.4f}"))    
        plt.xticks(rotation=45)  
        plt.show()

def plot_search_area2(rtree_index, grid, polygon_points):
        """
        all_items = list(rtree_index.intersection(rtree_index.bounds, objects=True))
        preserved_polygons = []
        print("Geometry")
        for r in all_items:
            data = r.object
            print(data["geometry"])
            preserved_polygons.append(data["geometry"])

        gdf = gpd.GeoDataFrame(geometry=preserved_polygons, crs='EPSG:4326')
        ax = gdf.plot(edgecolor='black', facecolor='blue')  # Default to blue
        gdf.iloc[[2]].plot(ax=ax, edgecolor='black', facecolor='red')
        #Show the grids
        #overlay_gdf = gpd.GeoDataFrame(geometry=all_poly) 
        # Overlay the new polygons in red with transparency (alpha)
        #overlay_gdf.plot(ax=ax, edgecolor="black", facecolor="red", alpha=0.5)

        for i in range(len(grid)):
            for j in range(len(grid)):
                tile = grid[i][j]
                centroid = tile.polygon.centroid
                # Annotate with the counts
                text = f"{tile.contains_count['building']},{tile.contains_count['water']}"
                ax.annotate(text, (centroid.x, centroid.y), color='white', 
                            fontsize=6, ha='center', va='center', fontweight='bold')
                # Plot the polygon of each tile
                x, y = tile.polygon.exterior.xy  # Get the coordinates of the polygon
                ax.fill(x, y, edgecolor='black', facecolor='red', alpha=0.5, linewidth=1)
        """
        #Show the original area
        # Reverse the coordinates of the polygon points (assuming polygon_points are in 4326)
        reversed_search_area = polygon_points#[(point[1], point[0]) for point in polygon_points]
        print(reversed_search_area)

        # Create a polygon with the reversed coordinates
        new_polygon = Polygon(reversed_search_area)

        # Create GeoDataFrame with CRS EPSG:4326
        new_polygon_gdf = gpd.GeoDataFrame(geometry=[new_polygon], crs="EPSG:4326")
        print(new_polygon_gdf.crs)

        # Ensure we're not inadvertently reprojecting by calling .to_crs()
        # new_polygon_gdf = new_polygon_gdf.to_crs("EPSG:4326")  # Do not reproject if it's already EPSG:4326

        # Plot the GeoDataFrame, keeping in mind the correct CRS
        ax = new_polygon_gdf.plot(edgecolor="black", facecolor="green", alpha=0.3)

        # Set the aspect ratio to 'equal' to maintain correct geographical representation
        ax.set_aspect('equal', 'box')
        
        
        # Get the bounds of the polygon (minx, miny, maxx, maxy)
        lon_values = [point[0] for point in polygon_points]  # Extract longitudes
        lat_values = [point[1] for point in polygon_points]  # Extract latitudes
        plt.xticks(ticks=np.linspace(min(lon_values), max(lon_values), num=5), labels=np.round(np.linspace(min(lon_values), max(lon_values), num=5), 6))
        plt.yticks(ticks=np.linspace(min(lat_values), max(lat_values), num=5), labels=np.round(np.linspace(min(lat_values), max(lat_values), num=5), 6))
       # plt.ticklabel_format(useOffset=False, style='plain')
        # Set the axis limits based on the bounding box of the polygon
        # Show the plot
        plt.show()
        