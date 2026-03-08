import math

def estimate_position(lat, lon, alt, pitch, roll, fov, x, y, heading, image_width=1920, image_height=1080):
    """
    Estimate the position of a point in the world given the camera parameters and the image coordinates.

    Args:
    lat (float): Latitude of the camera.
    lon (float): Longitude of the camera.
    alt (float): Altitude of the camera.
    pitch (float): Pitch angle of the camera in degrees.
    roll (float): Roll angle of the camera in degrees.
    fov (float): Field of view of the camera in degrees.
    x (float): x coordinate in the image.
    y (float): y coordinate in the image.
    heading (float): Heading angle of the camera in degrees.
    image_width (int): Width of the image in pixels.
    image_height (int): Height of the image in pixels.

    Returns:
    tuple: Estimated latitude and longitude of the point in the world.
    """
    # Convert angles to radians
    pitch = math.radians(pitch)
    roll = math.radians(roll)
    fov = math.radians(fov)

    # Compute half of the image size
    cx = image_width / 2
    cy = image_height / 2
    
    # Compute pixel offsets from center
    dx = x - cx
    dy = y - cy
    
    # Calculate ground coverage using altitude and pitch
    ground_vertical_coverage = 2 * alt * math.tan(fov / 2)
    
    # Estimate GSD per row (non-uniform along vertical axis)
    gsd_per_row = []
    for row in range(int(cy), int(y) + 1):
        row_angle = pitch + ((row - cy) * (fov / image_height))
        effective_slant_range = alt / math.cos(row_angle)
        gsd = (2 * effective_slant_range * math.tan(fov / 2)) / image_height
        gsd_per_row.append(gsd)
    
    # Sum vertical distances to account for varying ground distances
    ground_vertical_distance = sum(gsd_per_row)
    
    # Compute horizontal GSD (assumed constant if roll is small)
    gsd_horizontal = ground_vertical_coverage / image_width
    ground_horizontal_distance = dx * gsd_horizontal
    
    # Convert ground distances to lat/lon offsets
    d_lat = ground_vertical_distance / 111320  # Convert meters to degrees latitude
    d_lon = ground_horizontal_distance / (111320 * math.cos(math.radians(lat)))  # Longitude depends on latitude
    
    # Compute final estimated GPS coordinates
    est_lat = lat + d_lat
    est_lon = lon + d_lon
    
    #return est_lat, est_lon

    #for debugging purposes add 10 meters at heading to the lat and lon
    earth_radius = 6371000  # in meters
    distance = 10  # distance in meters
    bearing = math.radians(heading)
    lat1 = math.radians(lat)
    lon1 = math.radians(lon)
    lat2 = math.asin(math.sin(lat1) * math.cos(distance / earth_radius) +
                     math.cos(lat1) * math.sin(distance / earth_radius) * math.cos(bearing))
    lon2 = lon1 + math.atan2(math.sin(bearing) * math.sin(distance / earth_radius) * math.cos(lat1),
                             math.cos(distance / earth_radius) - math.sin(lat1) * math.sin(lat2))
    est_lat = math.degrees(lat2)
    est_lon = math.degrees(lon2)
    return est_lat, est_lon

def calculate_distance_between_points(lat1, lon1, lat2, lon2):
    """
    Calculate the distance between two points on the Earth's surface using the Haversine formula.

    Args:
    lat1 (float): Latitude of the first point.
    lon1 (float): Longitude of the first point.
    lat2 (float): Latitude of the second point.
    lon2 (float): Longitude of the second point.

    Returns:
    float: Distance between the two points in meters.
    """
    R = 6371000  # Radius of Earth in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c
