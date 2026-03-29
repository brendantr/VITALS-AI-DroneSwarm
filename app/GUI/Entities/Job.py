class Job:
    def __init__(self, start, waypoints, end, path_obj):
        self.start = start
        self.waypoints = waypoints
        self.end = end
        self.path_obj = path_obj


class JobWaypoint:
    def __init__(self, lat, lon, waypointNum, map_widget=None):
        self.lat = lat
        self.lon = lon
        self.waypointNum = waypointNum
        self.marker_id = None
        if map_widget is not None:
            self.marker_id = map_widget.add_marker(lat, lon, str(waypointNum))
