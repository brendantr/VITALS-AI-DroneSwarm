# Cost Map - will contain a the class for each cost map for each drone.

class dronePath():
    def __init__(self, drone_id, path_points = []):
        self.drone_id = drone_id
        self.path_points = path_points