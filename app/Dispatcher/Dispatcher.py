
from pymavlink import mavutil
import asyncio
import threading
import time
import math

class mission_item:
    def __init__(self, seq, current, lat, lon, alt):
        self.seq = seq
        self.frame = mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT
        self.command = mavutil.mavlink.MAV_CMD_NAV_WAYPOINT
        self.current = current
        self.auto = 1
        self.param1 = 0.0
        self.param2 = 2.0
        self.param3 = 0
        self.param4 = 0.0
        self.lat = int(1e7 * lat)
        self.lon = int(1e7 * lon)
        self.alt = alt


class Dispatcher:
    def __init__(self, missionState):
        self.master = None
        self.missionState = missionState
        self.uploading_missions = {}
        self.unhandled_clears = [] # list of drones that have sent a mission clear command, awaiting ack
        self.waiting_for_takeoff = []
        self.requeted_missions = []
        self.loop = asyncio.new_event_loop()  # Create a separate event loop for background tasks
        self.mission_thread = threading.Thread(target=self._run_mission_loop, daemon=True)  
        self.mission_thread.start()  # Start the background thread

    def _run_mission_loop(self):
        """Runs an asyncio event loop in a separate thread for mission uploads."""
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def connect(self):
        try:
            self.master = mavutil.mavlink_connection('tcp:127.0.0.1:14550', mavlink_version="2.0")
            self.master.wait_heartbeat()
            print("Connected to MAVLink")
            return True
        except Exception as e:
            print(f"Error connecting to MAVLink: {e}")
            self.master = None
            return False
    

    async def receive_packets(self):
        """Continuously process MAVLink messages with minimal latency."""
        if not self.master:
            print("No MAVLink connection established.")
            return

        try:
            while True:
                # Process ALL available messages before sleeping
                messages_processed = 0
                
                while True:
                    msg = self.master.recv_match(blocking=False)
                    if not msg:
                        break  # No more messages, exit loop

                    messages_processed += 1
                    drone_id = msg.get_srcSystem()
                    msg_type = msg.get_type()

                    if msg_type == "HEARTBEAT":
                        self.missionState.updateDroneStatus(drone_id, msg.system_status)

                    elif msg_type == "GLOBAL_POSITION_INT":
                        for x in self.waiting_for_takeoff:
                            if x[0] == drone_id:
                                await self.handle_check_if_takeoff_complete(drone_id, msg.relative_alt / 1000, x[1])
                        self.missionState.updateDronePosition(
                            drone_id, msg.lat, msg.lon, msg.alt, msg.relative_alt,
                            msg.hdg, msg.vx, msg.vy, msg.vz
                        )
                    elif msg_type == "MISSION_COUNT":
                        print(f"Drone {drone_id} has {msg.count} waypoints stored.")
                        self.requeted_missions.insert(drone_id, {
                            "waypoints": [],
                            "expected_count": msg.count,
                            })

                    elif msg_type == "ATTITUDE":
                        self.missionState.updateDroneTelemetry(
                            drone_id, msg.roll, msg.pitch, msg.yaw
                        )
                    elif msg_type == "MISSION_REQUEST":
                            print(f"Received mission request {msg.seq} from drone {drone_id}")
                            await self.handle_mission_request(drone_id, msg.seq)

                    elif msg_type == "MISSION_ACK":
                            print(f"Mission acknowledgment received from drone {drone_id}: {msg.type}")
                            await self.handle_mission_ack(drone_id, msg.type)

                    elif msg_type == "COMMAND_ACK":
                            print(f"Command acknowledgment received for drone {drone_id}: {msg.command} - {msg.result}")
                    elif msg_type == "MISSION_ITEM_REACHED":
                            self.missionState.handle_reached_waypoint(drone_id, msg.seq)
                    
                    elif msg_type == "MISSION_ITEM":
                            print(f"Received waypoint {msg.seq} from drone {drone_id}: ({msg.x / 1e7}, {msg.y / 1e7}, {msg.z})")
                    elif msg_type == "MISSION_CURRENT":
                            # print(f"Current waypoint count for drone {drone_id}: {msg.total}")
                            self.missionState.handle_mission_state_update(drone_id, msg.mission_state)
                    elif msg_type == "CAMERA_TRIGGER":
                            print(f"Camera triggered by drone {drone_id} at time {msg.time_usec}")

                if messages_processed == 0:
                    await asyncio.sleep(0.001)  # Only sleep if no messages were processed

        except Exception as e:
            print(f"Dispatcher error: {e}")
        finally:
            if self.master:
                self.master.close()

    def clear_mission(self, drone_id):
        self.master.target_system = drone_id
        #self.master.waypoint_clear_all_send()
    
    def arm_drone(self, drone_id):
        print(f"Arming drone {drone_id}")
        print(f"target_component: {self.master.target_component}")
        self.master.target_system = drone_id
        self.master.set_mode(216)
        self.master.arducopter_arm()
    
    def send_mission(self, drone_id, waypoints):
        """Stop current mission and upload new waypoints for a specific drone."""
        if not self.master:
            print(f"Cannot upload waypoints: MAVLink is not connected!")
            return

        async def mission_task():
            await self.stop_current_mission(drone_id)  # Stop the current mission
            await self.upload_mission(drone_id, waypoints)

        asyncio.run_coroutine_threadsafe(mission_task(), self.loop)  # Run coroutine in separate event loop

    async def upload_mission(self, drone_id, waypoints):
        """Initiate mission upload using the correct MAVLink protocol."""
        print(f"Uploading mission to drone {drone_id} with {len(waypoints)} waypoints...")
        print(f"Waypoints: {waypoints}")
        #append home waypoint to the mission
        drone = self.missionState.get_drone(drone_id)
        if not drone:
            print(f"Drone {drone_id} not found.")
            return
        home_lat, home_lon = drone.get_home()
        waypoints.insert(0, (home_lat, home_lon, 10, 1)) # add home waypoint to the start of the mission

            

        # Clear existing mission
        self.master.mav.mission_clear_all_send(drone_id, 0)
        self.unhandled_clears.append(drone_id)
        await asyncio.sleep(1)  # Allow time for clearing

        self.uploading_missions[drone_id] = {
            "waypoints": [],  # Clear old waypoints before storing new ones
            "next_seq": 0,
            "waiting_for_request": True
        }
        self.uploading_missions[drone_id]["waypoints"] = waypoints.copy()
        waypoints_list = self.uploading_missions[drone_id]["waypoints"]
        print(f"uploading waypoints: {waypoints_list}")

        # Send mission count
        mission_count = len(waypoints)
        print(f"Sending MISSION_COUNT for {mission_count} waypoints to drone {drone_id}")
        
        self.master.mav.mission_count_send(drone_id, 0, mission_count)
        await asyncio.sleep(2)  # Allow drone time to process

        #Wait for mission requests and respond accordingly
       


    async def handle_mission_request(self, drone_id, seq):
        """Respond to mission requests from the drone."""
        mission = self.uploading_missions.get(drone_id)
        print(f"Received mission request {seq} from drone {drone_id}")

        if mission and seq < len(mission["waypoints"]):
            lat, lon, alt, type = mission["waypoints"][seq]
            self.send_waypoint(drone_id, seq, lat, lon, alt, type)
            mission["next_seq"] = seq + 1
            mission["waiting_for_request"] = False
        else:
            print(f"Received unexpected mission request {seq} from drone {drone_id}")

    def send_waypoint(self, drone_id, index, lat, lon, alt, waypoint_type=0):
        """Send a specific waypoint in response to a mission request."""
        
        print(f"Sending waypoint {index} to drone {drone_id}: {lat}, {lon}, {alt}")
        if waypoint_type == 0: # Normal Waypoint
            self.master.mav.mission_item_int_send(
                drone_id,  # Target drone
                0,  # Target component
                index,  # Waypoint index
                mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT,
                mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,
                0,  # Current waypoint flag
                1,  # Auto-continue
                0, 2.0, 0, 0,  # Empty params
                int(lat * 1e7), int(lon * 1e7), alt
            )
            print(f"Waypoint {index} sent to drone {drone_id}: {lat}, {lon}, {alt}")
        elif waypoint_type == 1: # Takeoff Command
            self.master.mav.mission_item_int_send(
                drone_id,  # Target drone
                0,  # Target component
                index,  # Waypoint index
                mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT,
                mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
                0,  # Current waypoint flag
                1,  # Auto-continue
                0,  # pitch
                0, 0,  # Empty params
                0, #yaw
                lat, lon, alt
            )
            print(f"Waypoint {index} sent to drone {drone_id}: {lat}, {lon}, {alt}")
        elif waypoint_type == 2: # Loiter turns Command
            self.master.mav.mission_item_int_send(
                drone_id,  # Target drone
                0,  # Target component
                index,  # Waypoint index
                mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT,
                mavutil.mavlink.MAV_CMD_NAV_LOITER_TURNS,
                0,  # Current waypoint flag
                1,  # Auto-continue
                3,  # Number of turns
                0,  # Heading
                12, #Radius (m)
                0,  #NA for copters
                int(lat * 1e7), int(lon * 1e7), alt
            )
            print(f"Waypoint {index} sent to drone {drone_id}: {lat}, {lon}, {alt}")


    async def handle_mission_ack(self, drone_id, ack_type):
        """Handle final mission acknowledgment."""
        if drone_id in self.unhandled_clears:
            self.unhandled_clears.remove(drone_id)
            print(f"Mission cleared for drone {drone_id}.")
            return
        if ack_type == mavutil.mavlink.MAV_MISSION_ACCEPTED:
            print(f"Mission upload to drone {drone_id} completed successfully!")
            await self.start_mission(drone_id)
        else:
            print(f"Mission upload failed for drone {drone_id} with error code {ack_type}")

    async def wait_for_arming(self, drone_id, timeout=10):
        """Wait until the drone is armed before continuing."""
        print(f"Waiting for drone {drone_id} to arm...")
        start_time = time.time()
        while time.time() - start_time < timeout:
            msg = self.master.recv_match(type="HEARTBEAT", blocking=False)
            if msg and msg.get_srcSystem() == drone_id:
                if msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED:
                    print(f"Drone {drone_id} is now armed!")
                    return True
            await asyncio.sleep(0.5)
        print(f"Warning: Drone {drone_id} did not arm within timeout!")
        return False
    
    async def wait_for_mode(self, drone_id, target_mode, timeout=10):
        """Wait until the drone changes to the desired mode."""
        print(f"Waiting for drone {drone_id} to switch to {target_mode} mode...")
        start_time = time.time()
        mode_mapping = {
            "GUIDED": 4,
            "AUTO": 3,
            "LOITER": 5,
            "RTL": 6
        }
        target_mode_id = mode_mapping.get(target_mode)
        if target_mode_id is None:
            print(f"Invalid target mode: {target_mode}")
            return False
        
        while time.time() - start_time < timeout:
            msg = self.master.recv_match(type="HEARTBEAT", blocking=False)
            if msg and msg.get_srcSystem() == drone_id:
                if msg.custom_mode == target_mode_id:
                    print(f"Drone {drone_id} is now in {target_mode} mode!")
                    return True
            await asyncio.sleep(0.5)
        print(f"Warning: Drone {drone_id} did not switch to {target_mode} mode within timeout!")
        return False

    async def start_mission(self, drone_id, takeoff_altitude=10):
        drone = self.missionState.get_drone(drone_id)
        takeoff_altitude = drone.operatingAltitude
        if not drone:
            print(f"Drone {drone_id} not found.")
            return 
        if drone.system_status == 3: #drone is grounded need to add takeoff
            await  self.takeoff(drone_id, takeoff_altitude)
            
            return
        # Set mode to AUTO
        self.master.mav.set_mode_send(
            drone_id,
            mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
            3  # AUTO mode
        )
        if not await self.wait_for_mode(drone_id, "AUTO"):
            print(f"Mission aborted: Drone {drone_id} failed to switch to AUTO mode.")
            return
        # Start the mission
        self.master.mav.command_long_send(
            drone_id, 0,
            mavutil.mavlink.MAV_CMD_MISSION_START,
            0, 0, 0, 0, 0, 0, 0, 0
        )

        
    
    #Handles arming and takeoff of drone when grounded
    async def takeoff(self, drone_id, altitude):
        """Send the takeoff command to the drone."""
        # Step 1: Set mode to GUIDED
        self.master.mav.set_mode_send(
            drone_id,
            mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
            4  # GUIDED mode
        )
        if not await self.wait_for_mode(drone_id, "GUIDED"):
            print(f"Mission aborted: Drone {drone_id} failed to switch to GUIDED mode.")
            return
        # Step 2: Arm the drone and wait for confirmation
        self.master.mav.command_long_send(
            drone_id, 0,
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
            0, 1, 21196, 0, 0, 0, 0, 0
        )
        if not await self.wait_for_arming(drone_id):
            print(f"Mission aborted: Drone {drone_id} failed to arm.")
            return
        
        # Step 3: Takeoff
        drone = self.missionState.get_drone(drone_id)
        if not drone:
            print(f"Drone {drone_id} not found.")
            return 
        self.master.mav.command_long_send(
            drone_id,
            0,
            mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
            0,
            0,
            0,
            0,
            0,
            drone.latitude,
            drone.longitude,
            altitude
        )
        self.waiting_for_takeoff.append((drone_id, altitude))
    
    async def handle_check_if_takeoff_complete(self, drone_id, rel_alt, target_alt, tolerance=.5):
        """Check if the drone has reached the target altitude after takeoff."""
        if abs(rel_alt - target_alt) <= tolerance:
            print(f"Drone {drone_id} has taken off to the target altitude of {target_alt}m.")
            self.waiting_for_takeoff.remove((drone_id, target_alt))
            await self.start_mission(drone_id)
        else:
            print(f"Drone {drone_id} is still climbing. Current altitude: {rel_alt}m, Target altitude: {target_alt}m.")
        

    
    def return_to_launch(self, drone_id):
        """Send the RTL command to the drone."""
        if not self.master:
            print(f"Cannot send RTL command: MAVLink is not connected!")
            return

        print(f"Sending RTL command to drone {drone_id}...")
        self.master.mav.command_long_send(
            drone_id,
            0,  # Target component
            mavutil.mavlink.MAV_CMD_NAV_RETURN_TO_LAUNCH,
            0,  # Confirmation
            0,  # No parameters needed
            0, 0, 0, 0, 0, 0
        )
    
    def ack(self, keyword):
        """wait for the drone to acknowledge a command"""
        print(str(self.master.recv_match(type=keyword, blocking=True)))
    
    def request_mission_list(self, drone_id):
        """Request the mission list from the drone."""
        if not self.master:
            print(f"Cannot request mission list: MAVLink is not connected!")
            return

        print(f"Requesting mission list from drone {drone_id}...")
        self.master.mav.mission_request_list_send(drone_id, 0)


    async def stop_current_mission(self, drone_id):
        """Stop the current mission and set the drone to GUIDED mode."""
        print(f"Stopping current mission for drone {drone_id}...")

        # Switch to GUIDED mode (manual control to prevent mission resuming)
        self.master.mav.set_mode_send(
            drone_id,
            mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
            4  # GUIDED mode
        )
        
        if not await self.wait_for_mode(drone_id, "GUIDED"):
            print(f"Failed to switch drone {drone_id} to GUIDED mode before mission upload!")
            return

        # Clear current mission
        print(f"Clearing current mission for drone {drone_id}...")
        self.master.mav.mission_clear_all_send(drone_id, 0)
        self.unhandled_clears.append(drone_id)

        await asyncio.sleep(1)  # Allow time for mission clearing

    def shutdown(self):
        """Cleanly stops the background event loop and thread."""
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.mission_thread.join()
    
   




if __name__ == "__main__":
    dispatcher = Dispatcher()
    dispatcher.recieve_packets()
