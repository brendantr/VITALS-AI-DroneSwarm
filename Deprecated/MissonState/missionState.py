
class Drone:
    drone_id = None
    system_status = None
    latitude = None # Note: this is not a float, it is a int with 7 decimal places
    longitude = None # Note: this is not a float, it is a int with 7 decimal places
    altitude = None # millimeters above sea level
    relative_altitude = None # millimeters above home
    heading = None # degrees
    vx = None # cm per second
    vy = None # cm per second
    vz = None # cm per second

    def __init__(self, drone_id, system_status):
        self.drone_id = drone_id
        self.system_status = system_status

    #SETTERS
    def updatePosition(self, latitude, longitude, altitude, relative_altitude, heading, vx, vy, vz):
        self.latitude = latitude
        self.longitude = longitude
        self.altitude = altitude
        self.relative_altitude = relative_altitude
        self.heading = heading
        self.vx = vx
        self.vy = vy
        self.vz = vz

    
    def updateTelemetry(self, roll, pitch, yaw):
        self.roll = roll
        self.pitch = pitch
        self.yaw = yaw
    def updateStatus(self, system_status):
        self.system_status = system_status
    


class missionState:
    drones = []
    missionPolygon = []
    def __init__(self):
        pass

    def addDrone(self, drone_id, system_status):
        self.drones.append(Drone(drone_id, system_status))
        self.drones.sort(key=lambda x: x.drone_id)

    def updateDronePosition(self, drone_id, latitude, longitude, altitude, relative_altitude, heading):
        drone = next((d for d in self.drones if d.drone_id == drone_id), None)
        if drone is not None:
            drone.updatePosition(latitude, longitude, altitude, relative_altitude, heading, vx, vy, vz)

    def updateDroneTelemetry(self, drone_id, roll, pitch, yaw):
        drone = next((d for d in self.drones if d.drone_id == drone_id), None)
        if drone is not None:
            drone.updateTelemetry(roll, pitch, yaw)
        

    def addMissionPolygon(self, polygon):
        self.missionPolygon = polygon
    def updateDroneStatus(self, drone_id, system_status):
        # check if drone exists yet 
        drone = next((d for d in self.drones if d.drone_id == drone_id), None)
        if drone is None:
            self.addDrone(drone_id, system_status)
        else:
            drone.updateStatus(system_status)
    
    def getDrones(self):
        return self.drones
    

    




    