def classify_highway(highway_value):
    """
    Classify a highway tag into 'road' or 'pedestrian path'.
    
    Parameters:
        highway_value (str): The value of the highway tag.
        
    Returns:
        str: 'road' if the tag represents a vehicular road,
             'pedestrian path' if it represents a trail or footpath,
             or 'unknown' if the tag doesn't match known categories.
    """
    if not highway_value:
        return "unknown"
    
    # Normalize the input
    highway_value = highway_value.lower()
    
    # Define sets of highway values for roads and pedestrian paths.
    road_tags = {
        "motorway", "trunk", "primary", "secondary", "tertiary",
        "residential", "unclassified", "service", "living_street"
    }
    
    pedestrian_tags = {
        "footway", "path", "track", "bridleway", "pedestrian","cycleway"
        # 'cycleway' can sometimes be used, but it's primarily for cyclists.
    }
    
    if highway_value in road_tags:
        return "highway"
    elif highway_value in pedestrian_tags:
        return "pedestrian_path"
    else:
        #return "unknown"
        
        #We default that anything unknown is a road, at least for now.
        return "highway"

# Example usage:
#print(classify_highway("motorway"))   # Outputs: road
#print(classify_highway("footway"))      # Outputs: pedestrian path
#print(classify_highway("cycleway"))     # Outputs: unknown

#If I need a more specific category to actually mean something apart, then here is where it goes.
#For example, a pedestrian trail and a road are not the same.
#Different buildings can abe considered the same, so no disambiguation is done. 
def disambiguate(type, value):
    
    if type == "highway":
        value = classify_highway(value)
        return value
    
    return type