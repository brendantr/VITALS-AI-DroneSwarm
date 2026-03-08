# VITALS — Optimizations and Redesign Document

## Date: March 7, 2026

This document outlines all changes, bug fixes, optimizations, and UI redesigns made to the VITALS application during this development session.

---

## Table of Contents

1. [LLM Tool Calling Fix — RTL Misinterpretation](#1-llm-tool-calling-fix--rtl-misinterpretation)
2. [Drone Availability State Machine](#2-drone-availability-state-machine)
3. [POI Investigation & RTL Race Condition Fixes](#3-poi-investigation--rtl-race-condition-fixes)
4. [Detection Suppression During Investigation and RTL](#4-detection-suppression-during-investigation-and-rtl)
5. [Async Mission Upload Race Condition Fix](#5-async-mission-upload-race-condition-fix)
6. [Duplicate POI Dialog Fix](#6-duplicate-poi-dialog-fix)
7. [Simplified POI Discovery Flow](#7-simplified-poi-discovery-flow)
8. [Traversal Complete Dialog](#8-traversal-complete-dialog)
9. [Mission Lifecycle Reset Fix](#9-mission-lifecycle-reset-fix)
10. [MAVLink Reconnection Fix](#10-mavlink-reconnection-fix)
11. [HomePage Redesign](#11-homepage-redesign)
12. [Settings Dialog with Gear Icon](#12-settings-dialog-with-gear-icon)
13. [Max Velocity Enforcement via MAVLink](#13-max-velocity-enforcement-via-mavlink)

---

## 1. LLM Tool Calling Fix — RTL Misinterpretation

**Problem:** When the operator issued an "RTL drone 1" command via the LLM chat, the language model incorrectly interpreted "RTL" as a start mission command, calling `call_start_mission` instead of `call_return_to_launch`.

**Root Cause:** The LLM tool descriptions and system prompt did not include explicit keyword mappings for RTL-related commands, leading to confusion between mission start and return-to-launch.

**Fix (LangGraph/langChainMain.py):**
- Updated the `call_return_to_launch` tool description to include explicit trigger keywords: "RTL", "return to launch", "bring home", "recall", "send back"
- Added anti-confusion rules: "Do NOT confuse this with call_start_mission. RTL means GO HOME, not start."
- Updated the system prompt with critical rules:
  ```
  CRITICAL RULES:
  - "bring drone X home" or "RTL drone X" = call_return_to_launch(drone_id=X)
  - The words RTL, HOME, RETURN, RECALL, BACK always mean call_return_to_launch
  - Never confuse RTL with START. RTL means RETURN HOME, not start mission.
  ```

---

## 2. Drone Availability State Machine

**Problem:** Multiple subsystems (job scheduling, detection, mission start) did not respect whether a drone was available or in an RTL/ended state, causing commands to be ignored or overridden.

**Fix (missionState.py — Drone class):**
- `addJob()`: Added `self.available` check to both the initial assignment and the preemption condition. A job will not be assigned or preempt the active job if the drone is unavailable.
  ```python
  def addJob(self, job):
      if self.active_job is None and self.available:
          self.setActiveJob(job)
      elif self.available and self.active_job is not None and (int(job.job_priority) - self.active_job.job_priority) > 3:
          self.setActiveJob(job)
      else:
          self.jobQueue.add_job(job)
  ```
- `setJobComplete()`: Added `self.available` guard before popping the next job from the queue. Prevents new jobs from starting when the drone is RTL'ing.
  ```python
  def setJobComplete(self):
      if self.active_job is not None:
          completed_job_type = self.active_job.job_type
          self.active_job.job_status = "Completed"
          self.active_job = None
          if self.available and not self.jobQueue.is_empty():
              next_job = self.jobQueue.get_next_job()
              self.setActiveJob(next_job)
          elif self.available and self.jobQueue.is_empty() and completed_job_type == "Initial Search":
              self.missionState.on_search_traversal_complete(self.drone_id)
  ```

---

## 3. POI Investigation & RTL Race Condition Fixes

**Problem:** When an operator issued an RTL command while a drone was investigating a POI, the drone continued its investigation instead of returning home. Additionally, if a drone detected another POI while circling during investigation, it would trigger a new investigation job that overrode the RTL command.

**Fix:**
- The `addJob()` availability check (Section 2) prevents new investigate jobs from being assigned when the drone is unavailable (RTL state).
- `setDroneUnavailable()` pushes the active job to the queue and clears it, allowing the RTL command to take priority immediately.

---

## 4. Detection Suppression During Investigation and RTL

**Problem:** The position-update-based detection system (`updateDronePosition`) triggered image detection on every position update regardless of the drone's current state. This caused false POI detections while the drone was circling a POI during investigation or flying home during RTL.

**Fix (missionState.py — updateDronePosition):**
- Added a compound guard condition that checks:
  1. `drone.available` — Skip detection if the drone is RTL'ing or ended
  2. `drone.active_job is None or not drone.active_job.job_type.startswith("Investigate POI")` — Skip detection if the drone is currently investigating a POI
  ```python
  if self.detectionPoints and drone.available and (drone.active_job is None or not drone.active_job.job_type.startswith("Investigate POI")):
      # ... detection logic ...
  ```

---

## 5. Async Mission Upload Race Condition Fix

**Problem:** When the operator issued an "end mission" command, the `send_mission` function had already initiated an asynchronous mission upload in the background. After the RTL command was sent, the async upload completed and called `start_mission`, which switched the drone back to AUTO mode — effectively overriding the RTL command.

**Fix (Dispatcher/Dispatcher.py — start_mission):**
- Added a `drone.available` check at the beginning of `start_mission()`. If the drone has been set to unavailable (RTL/ended), the mission start is aborted.
  ```python
  async def start_mission(self, drone_id, takeoff_altitude=10):
      drone = self.missionState.get_drone(drone_id)
      if not drone:
          return
      if not drone.available:
          print(f"Drone {drone_id} is unavailable (RTL/ended), aborting mission start.")
          return
      # ... rest of start_mission logic ...
  ```

---

## 6. Duplicate POI Dialog Fix

**Problem:** The dialog box asking whether to continue or end a mission after a POI was established could trigger multiple times for a single POI. The condition `positive_flags >= 3` triggered on every subsequent detection, and the `poi_target_at_location` guard was not properly preventing re-triggers.

**Fix (missionState.py — handle_image_detection):**
- Simplified the POI confirmation flow. When a detected object matches an existing POI (within 40m), the image is saved and `positive_flags` is incremented with an early return — no dialog is shown.
  ```python
  for poi in self.pois:
      if distance < 40:
          cv2.imwrite(f"Missions/{self.missionID}/POIs/{poi.id}/...", image)
          poi.positive_flags += 1
          return
  ```

---

## 7. Simplified POI Discovery Flow

**Problem:** The previous design showed a popup dialog mid-investigation asking the operator whether to continue or end the mission each time a POI was confirmed. This was disruptive and unnecessary — the operator should be able to RTL or end the mission at any time independently of POI discovery.

**Redesign:**
- Removed the `TargetFoundDialog` class and `showTargetFoundDialog` method entirely
- Removed the `target_found()` method from the POI entity
- POI discovery now follows a simplified flow:
  1. Drone detects object near detection point
  2. POI is created, investigate job is queued
  3. Drone circles POI (3 turns, 12m radius via MAV_CMD_NAV_LOITER_TURNS)
  4. Investigation completes, drone continues to next waypoint or next queued job
  5. Operator can RTL or end mission at any time, regardless of investigation state

---

## 8. Traversal Complete Dialog

**Problem:** There was no notification when a drone completed its entire search path traversal.

**New Feature (GUI/Entities/POI.py, GUI/GUI.py, missionState.py):**
- Added `TraversalCompleteDialog` class — a dialog shown when a drone finishes all waypoints in its Initial Search job with no remaining jobs in the queue
- Dialog presents two options:
  - **End Mission** — Calls `missionState.end_mission()`, RTLs all drones
  - **Repeat Traversal** — Calls `missionState.repeat_search_traversal(drone_id)`, re-deploys the initial search path for that drone
- Detection in `Drone.setJobComplete()`: When the completed job type is "Initial Search" and the queue is empty, triggers `missionState.on_search_traversal_complete(drone_id)`
- `repeat_search_traversal()` re-creates the Initial Search job from the stored `drone_search_destinations`

---

## 9. Mission Lifecycle Reset Fix

**Problem:** After ending a mission and returning to the home page, starting a new mission failed — the drone never lifted off. The `reset_for_new_mission()` method did not fully reset drone state from the previous mission.

**Root Cause:** `drone.available` remained `False` from the previous mission's `end_mission()` call. `drone.active_job` and `drone.last_mission_state` also retained stale values.

**Fix (missionState.py — reset_for_new_mission):**
```python
def reset_for_new_mission(self):
    self.pois = []
    self.detectionPoints = []
    self.visualization_ready = False
    self.missionPolygon = None
    self.missionGrid = None
    self.rtree = None
    self.viable_grid_positions = None
    self.drone_search_destinations = None
    self.gcs_location = None
    for drone in self.drones:
        drone.position_history = []
        drone._last_history_time = 0
        drone.available = True
        drone.active_job = None
        drone.last_mission_state = None
        drone.jobQueue = jobPriorityQueue()
```

---

## 10. MAVLink Reconnection Fix

**Problem:** Attempting to reconnect to MAVLink after ending a mission raised an `asyncio.RuntimeError` because a new event loop was being created while one was already running.

**Fix (missionState.py — connect_to_mavlink):**
- Added an early return if already connected, preventing duplicate connection attempts.
```python
def connect_to_mavlink(self):
    if self.mavLinkConnected:
        print("Already connected to MAVLink")
        return True
    # ... original connection logic ...
```

---

## 11. HomePage Redesign

**Problem:** The landing page displayed "Start Mission" and "Mission Review" buttons. Mission Review had no functionality, and the actual mission type selection (Simulation vs Real Mission) was on a second page behind "Start Mission."

**Redesign (GUI/Pages/HomePage.py):**
- Removed the QStackedWidget, initial menu, Mission Review button, and Back button
- The landing page now directly displays:
  - Lockheed Martin logo (400x400)
  - VITALS logo (200x200, at most half the size of the LM logo)
  - "Select Mission Type" label
  - "Simulation" button — sets `isSimulation = True`, navigates to MapPage
  - "Real Mission" button — sets `isSimulation = False`, navigates to MapPage
  - Info label explaining simulation mode

---

## 12. Settings Dialog with Gear Icon

**New Feature (GUI/Pages/MapPage.py):**
- Added a settings gear icon button in the sidebar header, next to the "VITALS" title
- Uses the `GEAR_ICON.png` asset scaled to 24x24 pixels
- Button is 32x32 with transparent background and a subtle hover effect
- Falls back to a unicode gear character if the image asset is not found
- Opens `SettingsDialog` with per-drone settings:
  - **Operating Altitude** — QSpinBox, range 5-120m
  - **Max Velocity** — QDoubleSpinBox, range 0.5-20.0 m/s, default 10.0 m/s
- Apply button calls `missionState.set_drone_operatingAltitude()` and `missionState.set_drone_maxVelocity()`

---

## 13. Max Velocity Enforcement via MAVLink

**Problem:** The max velocity setting was stored in the Drone object (`drone.maxVelocity`) but was never sent to the drone via MAVLink — the drone did not respect the velocity limit.

**Fix (Dispatcher/Dispatcher.py, missionState.py):**

### New Method — `Dispatcher.set_max_velocity(drone_id, velocity_ms)`
Sends two MAVLink commands to enforce the speed:

1. **`WPNAV_SPEED` parameter** — Sets the waypoint navigation speed parameter on the flight controller. Value is in cm/s (velocity * 100). This persistently governs AUTO mode waypoint speed.
   ```python
   self.master.mav.param_set_send(
       drone_id, 0, b'WPNAV_SPEED',
       float(velocity_ms * 100),
       mavutil.mavlink.MAV_PARAM_TYPE_REAL32
   )
   ```

2. **`MAV_CMD_DO_CHANGE_SPEED`** — Sends an immediate speed change command for airborne drones. Uses groundspeed type.
   ```python
   self.master.mav.command_long_send(
       drone_id, 0,
       mavutil.mavlink.MAV_CMD_DO_CHANGE_SPEED,
       0, 0, float(velocity_ms), -1, 0, 0, 0, 0
   )
   ```

### Integration Points
- **Settings change (missionState.py):** `set_drone_maxVelocity()` now calls `self.dispatcher.set_max_velocity()` when MAVLink is connected, providing immediate mid-flight speed changes.
- **Mission start (Dispatcher.py):** `start_mission()` applies `set_max_velocity()` right before sending `MAV_CMD_MISSION_START`, ensuring the speed is enforced from the beginning of every mission.

---

## Files Modified

| File | Changes |
|------|---------|
| `appNew/GUI/Pages/HomePage.py` | Simplified landing page, removed QStackedWidget, direct mission type selection |
| `appNew/GUI/Pages/MapPage.py` | Added gear icon settings button in title row, removed old text settings button, added SettingsDialog class |
| `appNew/GUI/Entities/POI.py` | Removed TargetFoundDialog, added TraversalCompleteDialog |
| `appNew/GUI/GUI.py` | Replaced showTargetFoundDialog with showTraversalCompleteDialog |
| `appNew/missionState.py` | Drone availability guards, detection suppression, reset fixes, MAVLink reconnection guard, traversal complete handling, max velocity dispatch |
| `appNew/Dispatcher/Dispatcher.py` | Added set_max_velocity(), drone availability check in start_mission(), max velocity applied at mission start |
| `appNew/LangGraph/langChainMain.py` | RTL keyword mapping, anti-confusion rules in tool descriptions and system prompt |
