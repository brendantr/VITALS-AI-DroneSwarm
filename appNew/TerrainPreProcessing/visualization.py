from shapely.geometry import Point, Polygon, MultiPolygon, LineString

from .geometry_utils import haversine
from .query_disambiguation import disambiguate
import matplotlib.colors as mcolors
import numpy as np
import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
import matplotlib.pyplot as plt, collections
import matplotlib.ticker as mticker
from collections import Counter
from matplotlib.collections import PatchCollection, LineCollection
from matplotlib.widgets import Button, TextBox
import matplotlib.colors as mcolors
import matplotlib.patches as patches
import matplotlib.collections as col
import random
import matplotlib.animation as animation

class Drone_Path_Navigator:
    def __init__(self, interactive : "Interactive_Visualization"):
        self.interactive = interactive
        self.ax = self.interactive.ax
        self.start_index = 0
        self.end_index = 0
        self.personal_ax = None
        self.personal_components = []
        self.missionState = interactive.missionState
        pass

    def update_plot(self):
        if self.start_index == self.end_index:
            self.traced_path.set_data([self.path[self.start_index, 0]], [self.path[self.start_index, 1]])
        else:
            self.traced_path.set_data(self.path[self.start_index:self.end_index + 1, 0], self.path[self.start_index:self.end_index + 1, 1])

        self.start_textbox.set_val(f'{self.start_index+1}')  # Update the start index in the textbox
        self.end_textbox.set_val(f'{self.end_index+1}')  # Update the end index in the textbox
        plt.draw()
        pass

    def set_start_index(self, text):
        """Sets the start index based on the input from the start textbox."""
        try:
            start = int(text)
            start -= 1
            if 0 <= start <= self.end_index:
                self.start_index = start
            else:
                if start < 0:
                    start = 0
                    self.start_index = start

                if start >= self.end_index:
                    self.end_index = start
                    self.start_index = start
                print(f"Please enter a value between 0 and {self.end_index}. For start")
            self.update_plot()
        except ValueError:
            print("Invalid input. Please enter a valid integer.")

    def set_end_index(self, text):
        """Sets the end index based on the input from the end textbox."""
        try:
            end = int(text)
            end -= 1
            if self.start_index <= end <= len(self.path):
                self.end_index = end
            else:
                if end >= len(self.path):
                    end = len(self.path)-1
                    self.end_index = end
                if end < 0:
                    end = 0
                if self.start_index >= end:
                    self.start_index = end
                    self.end_index = end
    
            self.update_plot()
            print(f"Please enter a value between {self.start_index} and {len(self.path) - 1}.")
        except ValueError:
            print("Invalid input. Please enter a valid integer.")

    def create_ui(self, rect, id, path, drone_color):
        self.id = id
        self.drone_color = drone_color
        self.path = np.array([(point.x,point.y) for point in path])
        self.end_index = len(path)-1
        self.layer_name = f"drone{id+1}"
        self.interactive.create_layer(self.layer_name,self.personal_components)
        
        """
        self.ax.figure.text(rect[0], rect[1], f"Drone {id+1} path", fontsize=12, ha='center', va='center',
        bbox=dict(facecolor=self.color, edgecolor='black', boxstyle='round,pad=0.5'))
        self.personal_ax = self.interactive.create_new_layer(f"drone{id}layer")
        """
        self.button_ax = plt.axes(rect)
        self.button_ax.set_zorder(100)
        self.button = Button(self.button_ax,f'Drone {id+1} path', color=self.drone_color)
        self.interactive.button_store[f"drone{id}button"] = self.button

        def toggle_path(event):
            current_visibility = self.interactive.layer_visible[self.layer_name]
            self.interactive.layer_visible[self.layer_name] = not current_visibility
            self.button.color = self.drone_color if self.interactive.layer_visible[self.layer_name] else "red"
            #self.ax.get_figure().canvas.draw()
            for component in self.personal_components:
                component.set_visible(self.interactive.layer_visible[self.layer_name])
            plt.draw()

        self.button.on_clicked(toggle_path)
        
        
        self.start_textbox_ax = plt.axes([rect[0]+0.075,rect[1]-0.025,0.025,0.025])
        self.start_textbox = TextBox(self.start_textbox_ax, 'Start (1 to {}):'.format(len(path)), initial=str(len(path)))
        self.start_textbox.on_submit(self.set_start_index)

        self.end_textbox_ax = plt.axes([rect[0]+0.075,rect[1]-0.05,0.025,0.025])
        self.end_textbox = TextBox(self.end_textbox_ax, 'End (1 to {}):'.format(len(path)), initial=str(len(path)))
        self.end_textbox.on_submit(self.set_end_index)

        self.traced_path, = self.ax.plot([], [], alpha=0.8,color = drone_color,linewidth=4)  # Traced path
        self.personal_components.append(self.traced_path)
        self.update_plot()
         # Create a scatter plot or an annotation to show the position
        #[0.8, 0.01, 0.1, 0.05]
        """
        self.button_ax = plt.axes(rect)  # Position for button
        self.button_ax.set_zorder(100)
        self.button = Button(self.button_ax,'Next', color=self.color)
        #self.button.on_clicked(self.advance)
        self.button.on_clicked(lambda event: print("Clicked me!"))
        self.interactive.button_store[f"drone{id}button"] = self.button
        """



class Interactive_Visualization:
    def __init__(self, missionState):
        self.drone_colors = ["purple", "blue", "yellow", "green"]
        self.button_store = {}
        self.layer_store = {}
        self.layer_components = {}
        self.layer_visible = {}
        self.saved_animations = []

        self.tile_length = None
        self.missionState = missionState
        #plt.ion()
        
        pass
    
    def create_new_layer(self, name):
        fig = self.ax.get_figure()
        pos = self.ax.get_position()
        new_ax = fig.add_axes(pos, facecolor = "none")
        new_ax.set_xlim(self.ax.get_xlim())
        new_ax.set_ylim(self.ax.get_ylim())
        new_ax.set_picker(False)
        new_ax.set_aspect(self.ax.get_aspect())
        new_ax.set_axis_off()
        #outline_ax.set_aspect(ax.get_aspect())
        new_ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:.3f}"))
        new_ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda y, _: f"{y:.3f}"))
        self.layer_store[name] = new_ax
        plt.xticks(rotation=45)  
        return new_ax
    
    def create_layer(self, name, components):
        self.layer_visible[name] = True
        self.layer_components[name] = components

    def create_grid(self, grid, colors):

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
                        #print(f"Hello?: {actual_values}")
                        for value_type, ct in value_counts.items():
                            value_type = disambiguate(key, value_type)  # Normalize value type
                            if value_type in value_color:
                                #print(f"Key: {key} Value Type: {value_type}, Count: {ct}")
                                #print(f"Value Color: {value_color}")
                                #print(f"Actually used the color: {value_color.get(value_type)}")

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
        current_components = []
        grid_ax = self.ax
        plt.xticks(rotation=45)  
        for i in range(len(grid)):
            for j in range(len(grid)):
                tile = grid[i][j]
                if self.tile_length is None:
                    exterior_coords = list(tile.polygon.exterior.coords)
                    first,second = exterior_coords[:2]
                    self.tile_length = haversine(first[1],first[0], second[1],second[0])
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
                #grid_ax.annotate(position, (centroid.x, centroid.y), color='white', 
                #        fontsize=8, ha='center', va='center', fontweight='bold')
                # Plot the polygon of each tile
                x, y = tile.polygon.exterior.xy  # Get the coordinates of the polygon
                tile_color = mix_tile_colors(tile)
                
                patches = grid_ax.fill(x, y, edgecolor='black', facecolor=tile_color, alpha=0.75, linewidth=1)
                for p in patches:
                    current_components.append(p)
                #current_components
        self.create_layer("grid",current_components)
        annotation_text = f"Tile Length: {self.tile_length:.2f} meters"
        grid_ax.set_title(f"Tile Length: {self.tile_length:.2f} meters", fontsize=10, fontweight='bold', color='black')
        #grid_ax.annotate(annotation_text, xy=(0.1, 0.95), xycoords='figure fraction', 
        #    ha='left', va='top', fontsize=10, color='black', 
        #    fontweight='bold', bbox=dict(facecolor='white', edgecolor='none', alpha=0.7))
    
    def create_outline(self, search_points):
        flipped_coords = [(lon,lat) for lat,lon in search_points]
        new_polygon = Polygon(flipped_coords)
        new_polygon_gdf = gpd.GeoDataFrame(geometry=[new_polygon])
        outline_ax = self.ax
        o = new_polygon_gdf.plot(ax=outline_ax, edgecolor="black", facecolor="none", alpha=1, linewidth = 3)
        patch_collections = [child for child in o.get_children() if isinstance(child,col.PatchCollection) and child not in self.layer_components["geometry"]]
        self.create_layer("outline",patch_collections)

    def create_layer_toggle_button(self, rect, name):
        def toggle_grid_visibility(layer_name, event, button):
            current_visibility = self.layer_visible[layer_name]
            self.layer_visible[layer_name] = not current_visibility
            button.color = "green" if self.layer_visible[name] else "red"
            #self.ax.get_figure().canvas.draw()
            print(f"Layer Name: {layer_name}, Contents: {self.layer_components[layer_name]}")
            for component in self.layer_components[layer_name]:
                component.set_visible(self.layer_visible[layer_name])
            plt.draw()

        button_ax = plt.axes(rect)
        button_ax.set_zorder(100)
        toggle_button = Button(button_ax, name,color='green')
        name = name.lower()
        toggle_button.on_clicked(lambda event: toggle_grid_visibility(name, event, toggle_button))
        self.button_store[name] = toggle_button

    def display_drone_paths(self, drone_paths):
        for i,drone_id in enumerate(drone_paths):
            path = drone_paths[drone_id]
            if len(path) > 1: 
                color = self.drone_colors[drone_id]
                new_nav = Drone_Path_Navigator(self)
                new_nav.create_ui([0, 0.85-i*0.1, 0.1, 0.05], drone_id, path,color)
                # Assign color based on the drone
        pass

    def initalize_plot(self, rtree_index, grid = None, search_points = [], colors = {}, show_grid = True, polygon_darkening_factor = 0.5, drone_paths = {}):
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
                        #print(f"Key: {key}, Previous Value: {value}")
                        value = disambiguate(key, value)
                        if value in value_color:
                            #print(f"Value: {value}, Color: {value_color[value]}")
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

        # Compute the blended color for each row
        gdf["color"] = gdf.apply(mix_colors, axis=1)
        # Convert RGBA tuples to hexadecimal color strings for plotting
        gdf["color_hex"] = gdf["color"].apply(lambda rgba: mcolors.to_hex(rgba))
        
        ax = gdf.plot(color=gdf["color_hex"], edgecolor="black", alpha=1)
        self.ax = ax

        
        # Create a new list to store the cloned patches
        patch_collections = [
            child for child in ax.get_children()
            if isinstance(child, (PatchCollection, LineCollection))
        ]
        self.create_layer("geometry", patch_collections)

        ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:.3f}"))
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda y, _: f"{y:.3f}"))
        ax.set_picker(False)

        if grid and show_grid:
            self.create_grid(grid,colors)
        
        #Plot the search area the user did
        if search_points and show_grid:
            self.create_outline(search_points)

        if drone_paths:
            self.display_drone_paths(drone_paths)
            current_drone = self.missionState.drones[0]
            x,y = current_drone.longitude / 10**7,current_drone.latitude/ 10**7
            
            point, = self.ax.plot([x], [y], marker="o", color="green", markersize=15)  # Blue dot as an example
            point.set_zorder(200)
            # Initialize the plot
            drone_texts = {}
            
            def init():
                point.set_data([], [])  # Initially empty plot
                return [point]

            # Update function for each frame
            def update(frame):
                # Poll the latest coordinates
                x_coords = []
                y_coords = []
                for drone_id in drone_paths:
                    current_drone = self.missionState.drones[drone_id]
                    x,y = current_drone.longitude / 10**7,current_drone.latitude/ 10**7
                    x_coords.append(x)
                    y_coords.append(y)
                    # If text doesn't exist for this drone_id, create it and store it
                    if drone_id not in drone_texts:
                        text_obj = self.ax.text(x, y, str(drone_id+1), color="white", fontsize=10, ha="center", va="center")
                        text_obj.set_zorder(201)
                        drone_texts[drone_id] = text_obj
                    else:
                        # Update the position of the existing text object
                        drone_texts[drone_id].set_position((x, y))
                            # Update the data of the point (or the position of the image)
                point.set_data(x_coords,y_coords)
                #print(f"Long: {x}, Lat:{y}")

                # Return the updated artist
                return [point]

            # Create the animation
            ani = animation.FuncAnimation(self.ax.figure, update, frames=None, init_func=init, blit=False, interval=100)
            pass


        def update_grid(event):
            for inner_ax in self.layer_store.values():
                inner_ax.set_position(ax.get_position())
            #grid_ax.set_position(ax.get_position())
        ax.get_figure().canvas.mpl_connect('resize_event', update_grid)        
        #left, bottom, width, height
        self.create_layer_toggle_button([0.9, 0.5, 0.1, 0.075], "Geometry")


        self.create_layer_toggle_button([0.9, 0.4, 0.1, 0.075], "Grid")
        self.create_layer_toggle_button([0.9, 0.3, 0.1, 0.075], "Outline")
        
        #WARNING: If the buttons come out of scope, you will lose access to it, which is not good!. 
        #plt.show needs to be in here. 
        plt.show()
        return None



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

    #ax_button = plt.axes([0, 0.9, 0.1, 0.025])  # Position of the button
    #button = Button(ax_button, 'Click Me')
    #button.on_clicked(on_button_click)
    #ax.legend()

    #plt.show()


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
    

    ax = gdf.plot(color=gdf["color_hex"], edgecolor="black", alpha=1)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:.3f}"))
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda y, _: f"{y:.3f}"))
    ax.set_picker(False)
    #ax_main.set_axis_off()
    #plt.xticks(rotation=45)  
    #ax_main.set_title("Blended Colors for Mixed Categories")
    #ax_main.set_xlim(shape_ax.get_xlim())
    #ax_main.set_ylim(shape_ax.get_ylim())
    layer_list = {}
    if grid and show_grid:
        tile_length = None
        fig = ax.get_figure()
        pos = ax.get_position()

        grid_ax = fig.add_axes(pos, facecolor="none")
        grid_ax.set_xlim(ax.get_xlim())
        grid_ax.set_ylim(ax.get_ylim())
        grid_ax.set_aspect(ax.get_aspect())
        grid_ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:.3f}"))
        grid_ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda y, _: f"{y:.3f}"))
        grid_ax.set_picker(False)
        layer_list["grid"] = grid_ax
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
        #grid_ax.annotate(annotation_text, xy=(0.05, 0.95), xycoords='axes fraction', 
        #    ha='left', va='top', fontsize=10, color='black', 
        #    fontweight='bold', bbox=dict(facecolor='white', edgecolor='none', alpha=0.7))
    
    #Plot the search area the user did
    
    if search_points and show_grid:
        flipped_coords = [(lon,lat) for lat,lon in search_points]
        new_polygon = Polygon(flipped_coords)
        new_polygon_gdf = gpd.GeoDataFrame(geometry=[new_polygon])
        fig = ax.get_figure()
        pos = ax.get_position()

        outline_ax = fig.add_axes(pos, facecolor="none")
        outline_ax.set_xlim(ax.get_xlim())
        outline_ax.set_ylim(ax.get_ylim())
        outline_ax.set_picker(False)
        #outline_ax.set_aspect(ax.get_aspect())
        outline_ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:.7f}"))
        outline_ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda y, _: f"{y:.7f}"))
        #outline_ax.set_axis_off()
        new_polygon_gdf.plot(ax=outline_ax, edgecolor="black", facecolor="none", alpha=1, linewidth = 3)
        layer_list["outline"] = outline_ax

    def update_grid(event):
        for inner_ax in layer_list.values():
            inner_ax.set_position(ax.get_position())
        #grid_ax.set_position(ax.get_position())
    fig.canvas.mpl_connect('resize_event', update_grid)

    
    def toggle_grid_visibility(layer_ax, event, button):
        current_visibility = layer_ax.get_visible()
        layer_ax.set_visible(not current_visibility)
        button.color = "green" if layer_ax.get_visible() else "red"
        fig.canvas.draw()

    #toggle_button.on_clicked(toggle_grid_visibility)
    button_storage = []
    def create_layer_toggle_button(rect, layer_ax, name, button_storage):
        button_ax = plt.axes(rect)
        button_ax.set_zorder(100)
        toggle_button = Button(button_ax, name,color='green')
        toggle_button.on_clicked(lambda event: toggle_grid_visibility(layer_ax, event, toggle_button))
        button_storage.append(toggle_button)


    #button_ax = plt.axes([0.9, 0.05, 0.1, 0.075])  # adjust position and size as needed
    #button_ax.set_zorder(100)
    #toggle_button = Button(button_ax, 'Toggle Grid')
    
    #left, bottom, width, height
    create_layer_toggle_button([0.9, 0.5, 0.1, 0.075], ax, "Geometry", button_storage)
    create_layer_toggle_button([0.9, 0.4, 0.1, 0.075], layer_list["grid"], "Grid", button_storage)
    create_layer_toggle_button([0.9, 0.3, 0.1, 0.075], layer_list["outline"], "Outline", button_storage)

    

    if insta_plot:
        plt.show()

    #WARNING: If the buttons come out of scope, you will lose access to it, which is not good!. 
    #plt.show needs to be in here. 
    plt.show()
    return None



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
        