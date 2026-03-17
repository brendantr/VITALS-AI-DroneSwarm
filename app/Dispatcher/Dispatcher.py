from pymavlink import mavutil
import asyncio
import threading
import time
import math
import traceback
import glob
import platform

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

    # ── Initialization & Lifecycle ──────────────────────────────────────

    def __init__(self, missionState):
        self.master = None
        self.missionState = missionState
        self.connected_system_id = None
        self.connected_component_id = None
        self.uploading_missions = {}
        self.unhandled_clears = [] # list of drones that have sent a mission clear command, awaiting ack
        self.waiting_for_takeoff = []
        self.requeted_missions = {}
        self.loop = asyncio.new_event_loop()  # Create a separate event loop for background tasks
        self.mission_thread = threading.Thread(target=self._run_mission_loop, daemon=True)  
        self.mission_thread.start()  # Start the background thread

    def _run_mission_loop(self):
        """Runs an asyncio event loop in a separate thread for mission uploads."""
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def connect(self):
        if platform.system().lower() == "windows":
            connection_targets = [
                "COM10",  # Direct serial connection to drone (57600 baud)
                "tcp:127.0.0.1:14450",  # Mission Planner MAVLink Mirror (TCP)
                "tcp:127.0.0.1:14550",  # QGroundControl forwarding (TCP)
                "udp:127.0.0.1:14445",  # QGroundControl forwarding (UDP)
                "udp:127.0.0.1:14550",  # Standard UDP port
            ]
        else:
            serial_targets = sorted(glob.glob("/dev/cu.usbserial*")) + sorted(glob.glob("/dev/tty.usbserial*"))
            serial_targets += sorted(glob.glob("/dev/cu.usbmodem*")) + sorted(glob.glob("/dev/tty.usbmodem*"))
            connection_targets = serial_targets + [
                "tcp:127.0.0.1:14450",  # Mission Planner MAVLink Mirror (TCP)
                "tcp:127.0.0.1:14550",  # QGroundControl forwarding (TCP)
                "udp:127.0.0.1:14445",  # QGroundControl forwarding (UDP)
                "udp:127.0.0.1:14550",  # Standard UDP port
            ]

        print(f"MAVLink connection targets: {connection_targets}")

        for target in connection_targets:
            try:
                # For serial connections, specify 57600 baud rate (RFD900x standard)
                if target.startswith("COM") or target.startswith("/dev/"):
                    self.master = mavutil.mavlink_connection(target, baud=57600, autoreconnect=False, mavlink_version="2.0")
                else:
                    self.master = mavutil.mavlink_connection(target, autoreconnect=False, mavlink_version="2.0")
                
                heartbeat = self.master.wait_heartbeat(timeout=5)
                if not heartbeat:
                    print(f"MAVLink heartbeat timeout on {target}")
                    self.master = None
                    continue

                self.connected_system_id = heartbeat.get_srcSystem()
                self.connected_component_id = heartbeat.get_srcComponent()
                self.master.target_system = self.connected_system_id
                self.master.target_component = self.connected_component_id

                # Request continuous telemetry streams so UI can populate drone status/position.
                try:
                    self.master.mav.request_data_stream_send(
                        self.connected_system_id,
                        self.connected_component_id,
                        mavutil.mavlink.MAV_DATA_STREAM_ALL,
                        4,  # 4 Hz
                        1   # start
                    )
                    print(f"Requested telemetry stream from system {self.connected_system_id}, component {self.connected_component_id}")
                except Exception as stream_error:
                    print(f"Warning: failed requesting telemetry stream: {stream_error}")

                print(f"Connected to MAVLink via {target}")
                return True
            except Exception as e:
                print(f"Error connecting to MAVLink via {target}: {e}")
                self.master = None

        return False

    def shutdown(self):
        """Cleanly stops the background event loop and thread."""
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.mission_thread.join()

    # ── Core Event Loop ─────────────────────────────────────────────────

    async def receive_packets(self):
        """Continuously process MAVLink messages with minimal latency."""
        if not self.master:
            print("No MAVLink connection established.")
            return

        heartbeat_debug_printed = False
        position_debug_printed = False

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
                        if not heartbeat_debug_printed:
                            print(f"Receiving HEARTBEAT from system {drone_id}")
                            heartbeat_debug_printed = True
                        self.missionState.updateDroneStatus(drone_id, msg.system_status)

                    elif msg_type == "GLOBAL_POSITION_INT":
                        if not position_debug_printed:
                            print(f"Receiving GLOBAL_POSITION_INT from system {drone_id}: lat={msg.lat}, lon={msg.lon}")
                            position_debug_printed = True
                        for x in self.waiting_for_takeoff:
                            if x[0] == drone_id:
                                await self.handle_check_if_takeoff_complete(drone_id, msg.relative_alt / 1000, x[1])
                        self.missionState.updateDronePosition(
                            drone_id, msg.lat, msg.lon, msg.alt, msg.relative_alt,
                            msg.hdg, msg.vx, msg.vy, msg.vz
                        )
                    elif msg_type == "MISSION_COUNT":
                        print(f"Drone {drone_id} has {msg.count} waypoints stored.")
                        self.requeted_missions[drone_id] = {
                            "waypoints": [],
                            "expected_count": msg.count,
                            }

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
                            # Decode specific commands and results
                            command_names = {
                                512: "SET_MODE",
                                521: "ARM_DISARM"
                            }
                            result_codes = {
                                0: "ACCEPTED",
                                1: "TEMPORARILY_REJECTED", 
                                2: "DENIED",
                                3: "UNSUPPORTED",
                                4: "FAILED",
                                5: "IN_PROGRESS"
                            }
                            cmd_name = command_names.get(msg.command, f"CMD_{msg.command}")
                            result_name = result_codes.get(msg.result, f"RESULT_{msg.result}")
                            print(f"  → {cmd_name}: {result_name}")
                            
                            # Decode arm command rejections
                            if msg.command == mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM and msg.result != 0:
                                print(f"ARM COMMAND FAILED: Check drone mode, safety switches, and pre-arm conditions in QGroundControl")
                    elif msg_type == "STATUSTEXT":
                            # Print important status messages (like pre-arm check failures)
                            text = msg.text if isinstance(msg.text, str) else msg.text.decode('utf-8', errors='ignore')
                            print(f"STATUS from drone {drone_id}: {text}")
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
            traceback.print_exc()
        finally:
            if self.master:
                self.master.close()

    # ── Mission Management ──────────────────────────────────────────────

    def send_mission(self, drone_id, waypoints):
        """Stop current mission and upload new waypoints for a specific drone."""
        if not self.master:
            print(f"Cannot upload waypoints: MAVLink is not connected!")
            return

        async def mission_task():
            # Stop current mission and check if successful
            success = await self.stop_current_mission(drone_id)
            if success:
                await self.upload_mission(drone_id, waypoints)
            else:
                print(f"Mission aborted: Could not prepare drone {drone_id} for new mission")

        asyncio.run_coroutine_threadsafe(mission_task(), self.loop)  # Run coroutine in separate event loop

    async def start_mission(self, drone_id, takeoff_altitude=10):
        drone = self.missionState.get_drone(drone_id)
        if not drone:
            print(f"Drone {drone_id} not found.")
            return
        # Don't start mission if drone is unavailable (e.g., RTL in progress)
        if not drone.available:
            print(f"Drone {drone_id} is unavailable (RTL/ended), aborting mission start.")
            return
        takeoff_altitude = drone.operatingAltitude
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
        # Apply max velocity before starting
        if drone.maxVelocity:
            self.set_max_velocity(drone_id, drone.maxVelocity)

        # Start the mission
        self.master.mav.command_long_send(
            drone_id, 0,
            mavutil.mavlink.MAV_CMD_MISSION_START,
            0, 0, 0, 0, 0, 0, 0, 0
        )

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

    # ── Mission Upload Protocol ─────────────────────────────────────────

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
        if home_lat in (None, 0) or home_lon in (None, 0):
            # Fallback to current position if home has not been set yet.
            home_lat = drone.latitude
            home_lon = drone.longitude

        if home_lat is None or home_lon is None:
            print(f"Cannot upload mission for drone {drone_id}: no valid home/current GPS position yet")
            return

        # Convert from MAVLink integer format (1e7) to decimal degrees only when needed.
        if abs(home_lat) > 90 or abs(home_lon) > 180:
            home_lat = home_lat / 1e7
            home_lon = home_lon / 1e7

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
        print( f"uploading waypoints: {self.uploading_missions[drone_id]['waypoints']}")

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
        drone_id = int(drone_id)
        index = int(index)
        waypoint_type = int(waypoint_type)
        x = int(float(lat) * 1e7)
        y = int(float(lon) * 1e7)
        z = float(alt)

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
                x, y, z
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
                x, y, z
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
                x, y, z
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

    def clear_mission(self, drone_id):
        self.master.target_system = drone_id
        #self.master.waypoint_clear_all_send()


            print(f"Cannot request mission list: MAVLink is not connected!")
    def request_mission_list(self, drone_id):
        """Request the mission list from the drone."""
        if not self.master:
            print(f"Cannot request mission list: MAVLink is not connected!")
        print(f"Requesting mission list from drone {drone_id}...")
        self.master.mav.mission_request_list_send(drone_id, 0)

    # ── Drone Commands ──────────────────────────────────────────────────

    def arm_drone(self, drone_id):
        print(f"Arming drone {drone_id}")
        print(f"target_component: {self.master.target_component}")
        self.master.target_system = drone_id
        self.master.set_mode(216)
        self.master.arducopter_arm()

    #Handles arming and takeoff of drone when grounded
    async def takeoff(self, drone_id, altitude):
        """Send the takeoff command to the drone."""
        print(f"Starting takeoff sequence for drone {drone_id} to altitude {altitude}m...")
        
        # Step 1: Wait for manual RC arming (don't switch to GUIDED yet - it's not armable via RC)
        print(f"\n{'='*60}")
        print(f"⚠️  READY TO ARM DRONE {drone_id}")
        print(f"{'='*60}")
        print(f"1. Switch to STABILIZE mode on your flight controller")
        print(f"2. ARM using RC transmitter throttle stick gesture")
        print(f"3. VITALS will detect arming and continue automatically")
        print(f"{'='*60}\n")
        
        if not await self.wait_for_arming(drone_id, timeout=60):
            print(f"Mission aborted: Drone {drone_id} was not armed within 60 seconds.")
            return
        
        # Step 2: Now that drone is armed, switch to GUIDED mode
        print(f"Drone armed! Switching to GUIDED mode...")
        self.master.mav.set_mode_send(
            drone_id,
            mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
            4  # GUIDED mode
        )
        if not await self.wait_for_mode(drone_id, "GUIDED"):
            print(f"Warning: Drone {drone_id} failed to switch to GUIDED mode, attempting takeoff anyway...")
            # Don't abort - some firmwares may accept takeoff commands in other modes
        if not await self.wait_for_mode(drone_id, "GUIDED"):
            print(f"Warning: Drone {drone_id} failed to switch to GUIDED mode, attempting takeoff anyway...")
            # Don't abort - some firmwares may accept takeoff commands in other modes
        
        # Step 3: Send takeoff command
        drone = self.missionState.get_drone(drone_id)
        if not drone:
            print(f"Drone {drone_id} not found.")
            return 
        
        print(f"Sending takeoff command to {altitude}m...")
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

    
    def set_max_velocity(self, drone_id, velocity_ms):
        """Set the max waypoint navigation speed for a drone.

        Args:
            drone_id: Target drone system ID
            velocity_ms: Speed in m/s
        """
        if not self.master:
            print(f"Cannot set velocity: MAVLink is not connected!")
            return

        # Set WPNAV_SPEED parameter (expects cm/s)
        self.master.mav.param_set_send(
            drone_id,
            0,
            b'WPNAV_SPEED',
            float(velocity_ms * 100),  # Convert m/s to cm/s
            mavutil.mavlink.MAV_PARAM_TYPE_REAL32
        )
        print(f"Set WPNAV_SPEED to {velocity_ms * 100} cm/s for drone {drone_id}")

        # Also send DO_CHANGE_SPEED for immediate effect if airborne
        self.master.mav.command_long_send(
            drone_id,
            0,
            mavutil.mavlink.MAV_CMD_DO_CHANGE_SPEED,
            0,
            0,  # Speed type: 0 = groundspeed
            float(velocity_ms),  # Speed in m/s
            -1,  # Throttle (-1 = no change)
            0, 0, 0, 0
        )
        print(f"Sent DO_CHANGE_SPEED {velocity_ms} m/s to drone {drone_id}")

    def return_to_launch(self, drone_id):
        """Switch drone to RTL mode and return to launch, or land immediately if needed."""
        if not self.master:
            print(f"Cannot send RTL command: MAVLink is not connected!")
            return

        print(f"Sending RTL command to drone {drone_id}...")
        # Switch to RTL mode (mode 6)
        self.master.mav.set_mode_send(
            drone_id,
            mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
            6  # RTL mode
        )
        print(f"Switched drone {drone_id} to RTL mode.")

    def land_drone(self, drone_id):
        """Land the drone immediately at current location."""
        if not self.master:
            print(f"Cannot send LAND command: MAVLink is not connected!")
            return

        print(f"Sending LAND command to drone {drone_id}...")
        # Switch to LAND mode (mode 9)
        self.master.mav.set_mode_send(
            drone_id,
            mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
            9  # LAND mode
        )
        print(f"Drone {drone_id} is landing.")
    

    # ── Utilities ───────────────────────────────────────────────────────

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


    def ack(self, keyword):
        """wait for the drone to acknowledge a command"""
        print(str(self.master.recv_match(type=keyword, blocking=True)))




if __name__ == "__main__":
    dispatcher = Dispatcher()
    dispatcher.recieve_packets()
