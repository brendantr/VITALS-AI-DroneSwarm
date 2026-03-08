import os
import random
from GUI import GUI
from Dispatcher import Dispatcher
import asyncio
import threading
from TerrainPreProcessing.terrain_queries import create_search_area
from TerrainPreProcessing.visualization import plot_search_area, plot_advanced, plot_postGIS_data, plot_drone_paths
from TerrainPreProcessing.visualization import Interactive_Visualization
from PathPlanning.path import search_grid_with_drones
from LangGraph import langChainMain
import concurrent.futures
from Utils import coordinate_estimation
import heapq
from ComputerVision import objectDetection
import cv2
import threading

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
    roll = None  # Roll angle in degrees
    pitch = None  # Pitch angle in degrees
    yaw = None  # Yaw angle in degrees
    home_latitude = None # Note: this is not a float, it is a int with 7 decimal places
    home_longitude = None # Note: this is not a float, it is a int with 7 decimal places
    jobQueue = None
    active_job = None
    last_mission_state = None
    available = True
    operatingAltitude = 10 # meters
    visionModel = "rf3v1.pt"

    def __init__(self, missionState, drone_id, system_status, operatingAltitude):
        self.missionState = missionState
        self.drone_id = drone_id
        self.system_status = system_status
        self.operatingAltitude = operatingAltitude
        self.jobQueue = jobPriorityQueue()
        

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
        if self.home_latitude is None:
            self.home_latitude = latitude
            self.home_longitude = longitude
        self.missionState.gui.updateDronePosition(self.drone_id, latitude, longitude, altitude, relative_altitude, heading, vx, vy, vz)

    def updateTelemetry(self, roll, pitch, yaw):
        self.roll = roll
        self.pitch = pitch
        self.yaw = yaw
        self.missionState.gui.updateDroneTelemetry(self.drone_id, roll, pitch, yaw)

    def updateStatus(self, system_status):
        self.system_status = system_status
        self.missionState.gui.updateDroneStatus(self.drone_id, system_status)
    
    def addJob(self, job):
        if self.jobQueue.is_empty() and self.active_job is None: 
            self.setActiveJob(job)
        elif self.active_job is not None and (int(job.job_priority) - self.active_job.job_priority) > 3:
            # if the new job has a higher priority than the active job, pause the active job
            self.setActiveJob(job)
        else:
            self.jobQueue.add_job(job)
        self.missionState.gui.updateJobs(self.drone_id, self.active_job, self.jobQueue.queue)

    def setActiveJob(self, job):
        if self.active_job is not None:
            self.pauseJob()
        job.status = "loading"
        self.active_job = job
        waypoint_payload = []
        # append waypoints from last waypoint to the end of the list
        if self.active_job.last_waypoint > 1:
            for i in range(self.active_job.last_waypoint, len(self.active_job.waypoints)):
                waypoint_payload.append(self.active_job.waypoints[i- 1])
        else:
            waypoint_payload = self.active_job.waypoints
        # send the waypoints to the drone
        self.missionState.send_waypoints(self.drone_id, waypoint_payload)
        self.missionState.gui.updateJobs(self.drone_id, self.active_job, self.jobQueue.queue)
    
    def updateJobStatus(self, status):
        self.active_job.job_status = status
        self.missionState.gui.updateJobs(self.drone_id, self.active_job, self.jobQueue.queue)
    
    def pauseJob(self):
        self.active_job.job_status = "paused"
        self.jobQueue.add_job(self.active_job)
        self.active_job = None
        self.missionState.gui.updateJobs(self.drone_id, self.active_job, self.jobQueue.queue)
    
    def setJobRunning(self):
        if self.active_job is not None:
            self.active_job.job_status = "Running"
            self.missionState.gui.updateJobs(self.drone_id, self.active_job, self.jobQueue.queue)
        
    
    def setJobComplete(self):
        if self.active_job is not None:
            print(f"Completing job {self.active_job.job_id}")  # Debugging
            self.active_job.job_status = "Completed"
            self.active_job = None  
            if not self.jobQueue.is_empty():
                next_job = self.jobQueue.get_next_job()
                print(f"Next job: {next_job.job_id}")  # Debugging
                self.setActiveJob(next_job)  # Ensure it's using the new job
            self.missionState.gui.updateJobs(self.drone_id, self.active_job, self.jobQueue.queue)
    
    def setJobFailedUpload(self):
        if self.active_job is not None and self.active_job.upload_try_count < 3:
            self.active_job.job_status = "Failed Upload"
            self.missionState.send_waypoints(self.drone_id, self.active_job.waypoints)
            self.active_job.upload_try_count += 1
        else:
            self.active_job.job_status = "Failed Upload"
            self.active_job = None
            if not self.jobQueue.is_empty():
                next_job = self.jobQueue.get_next_job()
                self.setActiveJob(next_job)
    
    def setLastWaypoint(self, waypoint):
        if self.active_job is not None:
            self.active_job.last_waypoint = waypoint
            self.missionState.gui.updateJobs(self.drone_id, self.active_job, self.jobQueue.queue)
            
    def setDroneUnavailable(self):
        self.available = False
        #  push active job to the back of the queue
        if self.active_job is not None:
            self.jobQueue.add_job(self.active_job)
            self.active_job = None
            self.missionState.gui.updateJobs(self.drone_id, self.active_job, self.jobQueue.queue)
    
    def setDroneAvailable(self):
        self.available = True
        #  if there is a job in the queue, set it as the active job
        if not self.jobQueue.is_empty():
            next_job = self.jobQueue.get_next_job()
            self.setActiveJob(next_job)
    
    def set_operatingAltitude(self, altitude):
        self.operatingAltitude = altitude

        



    #GETTERS
    def get_home(self):
        return (self.home_latitude, self.home_longitude, )
    
    def get_operatingAltitude(self):
        return self.operatingAltitude
    
class Job:
    def __init__(self, job_type, job_status, waypoints, missionState, job_priority):
        self.missionState = missionState
        self.job_id = missionState.jobIDCounter
        missionState.jobIDCounter += 1
        self.job_type = job_type
        self.job_status = job_status
        self.waypoints = waypoints
        self.job_priority = job_priority
        self.last_waypoint = 0
        self.upload_try_count = 0
    
    def __lt__(self, other):
        # Compare jobs based on their priority sorting from high to low since using minheap
        return self.job_priority > other.job_priority

class POI:
    def __init__(self, lat, lon, name, desc, poi_status, poi_type):
        self.lat = lat
        self.lon = lon
        self.name = name
        self.desc = desc
        self.poi_status = poi_status
        self.poi_type = poi_type
        self.poi_target_at_location = False

# a job queue for each drone
class jobPriorityQueue:
    def __init__(self):
        self.queue = []
    
    def add_job(self, job):
        heapq.heappush(self.queue, job)
    
    def get_next_job(self):
        if self.queue:
            return heapq.heappop(self.queue)
        else:
            return None
    
    def peek_next_job(self):
        if self.queue:
            return self.queue[0]
        else:
            return None
    
    def is_empty(self):
        return len(self.queue) == 0


class missionState:

    def __init__(self, gui):
        self.drones = []
        self.pois = []
        self.gcs_location = None  # Global Control Station location (latitude, longitude)
        
        self.missionPolygon = None
        self.mavLinkConnected = False
        self.gui = gui
        self.loop = asyncio.new_event_loop()
        self.dispatcher = Dispatcher.Dispatcher(self)
        self.jobIDCounter = 100
        # TEST VALUES
        self.mission_waypoints = [(28.6013158, -81.2020057, 10, 0 ), (28.6031200, -81.1993369, 10, 0) , (28.6004825, -81.1942729, 10, 0)]
        self.mission_waypoints2  = [(28.6000236, -81.1988032, 10, 2)]
        self.mission_waypoints3 = [(28.5991587, -81.1985403, 10, 0 ), (28.6014194, -81.2027675, 10, 0)]

        #for simulation purposes
        self.detectionPoints = []
        
        
    def connect_to_mavlink(self):
        success = self.dispatcher.connect()
        if success:
            self.dispatcherThread = threading.Thread(target=self.run_asyncio_loop, daemon=True)
            self.dispatcherThread.start()
            self.mavLinkConnected = True
            print("Connected to MAVLink")
            return True
        else:
            print("Failed to connect to MAVLink")
            self.mavLinkConnected = False
            return False

    
    def run_asyncio_loop(self):
        """Runs the asyncio event loop in a separate thread for the dispatcher."""
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.dispatcher.receive_packets())

    def addDrone(self, drone_id, system_status):
        self.drones.append(Drone(self, drone_id, system_status, 10 + (5 * len(self.drones))))
        self.drones.sort(key=lambda x: x.drone_id)
        self.gui.addDrone(drone_id, system_status)

    def updateDronePosition(self, drone_id, latitude, longitude, altitude, relative_altitude, heading, vx, vy, vz):
        drone = next((d for d in self.drones if d.drone_id == drone_id), None)
        if drone is not None:
            drone.updatePosition(latitude, longitude, altitude, relative_altitude, heading, vx, vy, vz)
            #check if drone is within 20 meters of the target detection points
            if self.detectionPoints:
                for point in self.detectionPoints:
                    distance = coordinate_estimation.calculate_distance_between_points(
                        latitude / 1e7, longitude / 1e7,
                        point["lat"], point["lon"]
                    )
                    if distance < 20:  # If within 20 meters and the flag is less than 3
                        print(f"Drone {drone_id} is within 20 meters of detection point {point['lat']}, {point['lon']} num_hits: {point['num_hits']} roll: {drone.roll}")
                        if point["num_hits"] < 1 or (point["num_hits"] <= 3 and abs(drone.roll) > 0.1):  # If the flag is less than 1 or if the drone is pitching significantly
                            point["num_hits"] += 1  # Increment the flag for this detection point
                            self.trigger_image_detection(drone_id)
                        


    def updateDroneTelemetry(self, drone_id, roll, pitch, yaw):
        drone = next((d for d in self.drones if d.drone_id == drone_id), None)
        if drone is not None:
            drone.updateTelemetry(roll, pitch, yaw)

    def addMissionPolygon(self, polygon):
        print("Gotcha!")

        #polygon = [(round(lat, 7), round(lon, 7)) for lat, lon in polygon]
        #polygon = tuple(polygon)
        

        #print(f"Original area: {type(polygon[0][0])}") 
        #polygon = ((28.6055263, -81.2037652), (28.6053378, -81.1950105), (28.5973877, -81.1945813), (28.5971993, -81.2038939))
        #polygon = tuple(polygon)
        #print(f"Check area: {type(polygon[0][0])}") 
        
        rtree, grid, viable_grid_positions = create_search_area(polygon_points=polygon, search_tags={"building":True,"water":True,"highway":True}, useOSMX=True, maximum_square_size=60,minimum_grid_size=8)
        #plot_advanced(rtree,grid, polygon, {"building": (169,169,169,1), "water":(15, 10, 222,1)})
        #plot_postGIS_data(rtree, grid, polygon, {"building": (1, 0, 0, 1.0), "water":(0.0, 0.0, 1.0, 1.0), "highway":{"highway":(1, 0, 0, 1),"pedestrian_path":(0, 0, 1, 1)}}, show_grid=True,polygon_darkening_factor=0)
        self.missionGrid = grid
        self.viable_grid_positions = viable_grid_positions
        self.rtree = rtree
        self.missionPolygon = polygon
        self.doPathPlanning()
        new_visualization = Interactive_Visualization(self)
        #new_visualization.initalize_plot(rtree, grid, polygon, {"building": (1, 0, 0, 1.0), "water":(0.0, 0.0, 1.0, 1.0), "highway":{"highway":(1, 0, 0, 1),"pedestrian_path":(0, 0, 1, 1)}}, show_grid=True,polygon_darkening_factor=0, drone_paths=self.drone_search_destinations)
        self.visualization_thread = threading.Thread(
        target=new_visualization.initalize_plot,
            args=(rtree, grid, polygon, {
                "building": (1, 0, 0, 1.0),
                "water": (0.0, 0.0, 1.0, 1.0),
                "highway": {
                    "highway": (1.0, 0.65, 0.0, 1.0),
                    "pedestrian_path": (0.4, 0.8, 0.4, 1.0)
                }
            }),
            kwargs={
                "show_grid": True,
                "polygon_darkening_factor": 0,
                "drone_paths": self.drone_search_destinations
            },
            daemon=True
        )
        self.visualization_thread.start()
        #plot_postGIS_data(rtree, grid, polygon, {"building": (1, 0, 0, 1.0), "water":(0.0, 0.0, 1.0, 1.0), "highway":{"highway":(1, 0, 0, 1),"pedestrian_path":(0, 0, 1, 1)}}, show_grid=True,polygon_darkening_factor=0, insta_plot=True)
        #Need to calculate the path planning stuff after. 

    def doPathPlanning(self):
        #pass the grid, current_drone_positions(In ID Order, long-lat pairs), and number of drones(If you don't pass the drone positions)
        drone_positions =  []
        for drone in self.drones:
            drone_positions.append((drone.longitude/1e7, drone.latitude/1e7))
        self.drone_search_destinations = search_grid_with_drones(self.missionGrid,drone_positions,self.viable_grid_positions,4)
        pass

    def deployInitialPaths(self):
        for i, drone in enumerate(self.drones):
            converted_waypoints = []
            for j, coord in enumerate(self.drone_search_destinations[i]):
                converted_waypoints.append((coord.y, coord.x, drone.operatingAltitude, 0))
            self.create_job("Initial Search", converted_waypoints, 1, drone.drone_id)


    def startSearchMission(self):
        self.deployInitialPaths()



    def getMissionPolygon(self):
        return self.missionPolygon

    def updateDroneStatus(self, drone_id, system_status):
        # check if drone exists yet 
        drone = next((d for d in self.drones if d.drone_id == drone_id), None)
        if drone is None:
            self.addDrone(drone_id, system_status)
        else:
            drone.updateStatus(system_status)
    
    def getDrones(self):
        return self.drones
    
    def get_drone(self, drone_id):
        return next((d for d in self.drones if d.drone_id == drone_id), None)

    def arm_mission(self, drone_id):
        self.dispatcher.arm_drone(drone_id)
    
    def takeoff_mission(self, drone_id):
        self.dispatcher.takeoff(drone_id, 10)
    
    def send_waypoints(self, drone_id, waypoints):

        print("Sending waypoints")
        self.dispatcher.send_mission(drone_id, waypoints)
    
    def return_to_launch(self, drone_id):
        self.dispatcher.return_to_launch(drone_id)
    
    def send_poi_investigate(self, drone_id, waypoint):
        self.dispatcher.send_poi_investigate(drone_id, waypoint)
    
    def send_mission_list_request(self, drone_id):
        self.dispatcher.request_mission_list(drone_id)
    
    def handle_reached_waypoint(self, drone_id, waypoint):
        drone = next((d for d in self.drones if d.drone_id == drone_id), None)
        if drone is not None:
            drone.setLastWaypoint(waypoint)
    
    def handle_mission_state_update(self, drone_id, mission_state):
        drone = next((d for d in self.drones if d.drone_id == drone_id), None)
        if drone is not None:
            if mission_state == 5:
                if drone.last_mission_state != 5: # this ensures that the drone is not already in the state
                    drone.setJobComplete()
            drone.last_mission_state = mission_state
            
    def create_job(self, job_type, waypoints, job_priority, drone_id):
        drone = next((d for d in self.drones if d.drone_id == drone_id), None)
        if drone is not None:
            job = Job(job_type, "pending", waypoints, self, job_priority)
            drone.addJob(job)
    
    def test_add_job(self, drone_id, use_waypoints):
        drone = next((d for d in self.drones if d.drone_id == drone_id), None)
        if drone is not None:
            if use_waypoints == 1:
                job = Job("Automated Path", "pending", self.mission_waypoints, self, 1)
                drone.addJob(job)
            elif use_waypoints == 2:
                job = Job("Investigate Point", "pending", self.mission_waypoints2, self, 5)
                drone.addJob(job)
            elif use_waypoints == 3:
                job = Job("User Path", "pending", self.mission_waypoints3, self, 5)
                drone.addJob(job)
            
    
    def get_drone(self, drone_id):
        return next((d for d in self.drones if d.drone_id == drone_id), None)
    
    def getDrones(self):
        """returns drone list in a readable format for llm"""
        drone_list = []
        for drone in self.drones:
            drone_list.append({
                "drone_id": drone.drone_id,
                "system_status": drone.system_status,
                "latitude": drone.latitude,
                "longitude": drone.longitude,
                "altitude": drone.altitude,
                "relative_altitude": drone.relative_altitude,
                "heading": drone.heading,
                "vx": drone.vx,
                "vy": drone.vy,
                "vz": drone.vz
            })
        return drone_list
    def getPOIs(self):
        """returns poi list in a readable format for llm"""
        poi_list = []
        for poi in self.pois:
            poi_list.append({
                "lat": poi.lat,
                "lon": poi.lon,
                "name": poi.name,
                "id": poi.id,
            })
        return poi_list
    
    def addPOI(self, poi):
        #create POI directory in mission folder
        os.makedirs(f"Missions/{self.missionID}/POIs/{poi.id}", exist_ok=True)
        self.pois.append(poi)
        self.gui.addPOI(poi)

    
    def create_poi_investigate_job(self, poi_id, drone_id, priority = 5):
        print(f"Creating POI investigate job for drone {drone_id} and poi {poi_id}")
    
        poi = next((p for p in self.pois if p.id == int(poi_id)), None)
        print(f"POI: {poi}")
        if poi is not None:
            drone = next((d for d in self.drones if d.drone_id == int(drone_id)), None)
            if drone is not None:
                job = Job(f"Investigate POI {poi.id} ", "pending", [(poi.lat, poi.lon, int(drone.operatingAltitude), 2)], self, priority)
                drone.addJob(job)
    
    def call_drone_home(self, drone_id):
        drone = next((d for d in self.drones if d.drone_id == int(drone_id)), None)
        if drone is not None:
            drone.setDroneUnavailable()
            self.dispatcher.return_to_launch(int(drone_id))
    
    def end_mission(self):
        for drone in self.drones:
            self.call_drone_home(drone.drone_id)
    
    def set_missionID(self, id):
        self.missionID = id
    
    def get_missionID(self):
        return self.missionID
    
    def trigger_image_detection(self, drone_id):
        random_img_id = random.randint(1,5)
        image_path = f"ComputerVision/temp/drone_testing{random_img_id}.jpg"  # Simulated image path for testing
        self.handle_image_detection(drone_id, image_path)
    
    def handle_image_detection(self, drone_id, image_path):
        # Run the LLM in a separate thread to prevent UI freezing
        def process_image():
            result = langChainMain.give_image_description(image_path)
            return result.content  # Extract the description

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(process_image)
            description = future.result()  # Wait for the result in a non-blocking way

        image, detections = objectDetection.detect_and_draw(image_path)
        if detections is None or len(detections) == 0:
            print("No objects detected in the image.")
            return
        else:
            # Now process the estimated position
            drone = next((d for d in self.drones if d.drone_id == drone_id), None)
            if drone is None:
                return
            
            
            
            estimated_lat, estimated_lon = coordinate_estimation.estimate_position( 
                drone.latitude / 1e7, 
                drone.longitude / 1e7, 
                drone.altitude / 1000, 
                -10, 
                0, 
                90,  # Assuming a FOV of 90 degrees for simplicity
                960,  # x coordinate in the image (center)
                540,  # y coordinate in the image (center)
                drone.heading,
                image_width=1920,
                image_height=1080
            )

            # Check if the detected POI already exists within 20 meters
            for poi in self.pois:
                if coordinate_estimation.calculate_distance_between_points(estimated_lat, estimated_lon, poi.lat, poi.lon) < 40:
                    os.makedirs(f"Missions/{self.missionID}/POIs/{poi.id}", exist_ok=True)
                    cv2.imwrite(f"Missions/{self.missionID}/POIs/{poi.id}/{os.path.basename(image_path)}", image)
                    poi.positive_flags += 1
                    if poi.positive_flags >= 3:
                        poi.target_found(drone_id)  # Mark the POI as found if it has enough positive flags
                        
                    return

            # If no existing POI, create a new one
            poi_id = self.gui.map_page.add_poi(estimated_lat, estimated_lon, "Detected POI", description)
            self.create_poi_investigate_job(poi_id, drone_id, 5)

            # Store image in POI directory
            os.makedirs(f"Missions/{self.missionID}/POIs/{poi_id}", exist_ok=True)
            cv2.imwrite(f"Missions/{self.missionID}/POIs/{poi_id}/{os.path.basename(image_path)}", image)
    
    def set_gcs_location(self, coordinates_tuple):
        self.gcs_location = coordinates_tuple

    def setDetectionPoints(self, points):
        self.detectionPoints = points

    def  get_drone_operatingAltitude(self, drone_id):
        drone = next((d for d in self.drones if d.drone_id == drone_id), None)
        if drone is not None:
            return drone.get_operatingAltitude()
        else:
            return None
    
    def  set_drone_operatingAltitude(self, drone_id, altitude):
        drone = next((d for d in self.drones if d.drone_id == drone_id), None)
        if drone is not None:
            drone.set_operatingAltitude(altitude)
            self.gui.updateDroneOperatingAltitude(drone_id, altitude)
        else:
            return None
    
    def get_drone_vision_model(self, drone_id):
        drone = next((d for d in self.drones if d.drone_id == drone_id), None)
        if drone is not None:
            return drone.visionModel
        else:
            return None
    def set_drone_vision_model(self, drone_id, model):
        drone = next((d for d in self.drones if d.drone_id == drone_id), None)
        if drone is not None:
            drone.visionModel = model
            self.gui.updateDroneVisionModel(drone_id, model)
        else:
            return None
    def remove_poi_investigate_job(self, droneID):
        drone = next((d for d in self.drones if d.drone_id == droneID), None)
        if drone is not None and drone.active_job is not None:
            if drone.active_job.job_type.startswith("Investigate POI"):
                print(f"Removing job {drone.active_job.job_id} for drone {droneID}")
                drone.setJobComplete()
        
        

if __name__ == "__main__":
    gui = GUI.GUI()
    missionState = missionState(gui)
    gui.link_mission_state(missionState)
    gui.run()