from POSGIS.modules_test.terrain_queries import create_search_area
from visualization import plot_search_area
#What points make up the search area
polygon_points = ((28.6055263, -81.2037652), (28.6053378, -81.1950105), (28.5973877, -81.1945813), (28.5971993, -81.2038939))
search_tags = {"building": True, "water": True}
tree, grid = create_search_area(polygon_points,search_tags, useOSMX=True)
plot_search_area(tree,grid, polygon_points)