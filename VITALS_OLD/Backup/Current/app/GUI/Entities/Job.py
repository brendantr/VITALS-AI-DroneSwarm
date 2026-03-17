class Job:
    def __init__(self, start, waypoints, end, path_obj):
        self.start = start
        self.waypoints = waypoints
        self.end = end
        # this was assigned without self. (changed it to self. on 10/27/25)
        self.path_obj = path_obj


class JobWaypoint:
    def __init__(self, lat, lon, waypointNum, map_widget):
        self.lat = lat
        self.lon = lon
        self.marker = map_widget.set_marker(lat, lon, text=waypointNum)
