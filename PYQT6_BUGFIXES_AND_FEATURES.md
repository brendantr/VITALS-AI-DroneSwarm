# PyQt6 Bug Fixes & Feature Implementation Documentation

## Overview

This document details the bug fixes and feature additions made to the `appNew/` (PyQt6) codebase to achieve feature parity with the `app/` (tkinter) version and resolve runtime issues discovered during testing.

**Date:** 2026-02-21
**Scope:** `appNew/` directory only

---

## Bug Fixes

### 1. POI Marker Click Not Working

**Problem:** Clicking a POI marker on the map did nothing — the POI detail popup never appeared.

**Root Cause:** In `LeafletMap.py`, the JavaScript `addMarker()` function generated marker IDs using an internal counter (`marker_0`, `marker_1`, etc.), but the Python side stored a different ID (`py_marker_1`, `py_marker_2`, etc.) by incrementing its own counter and renaming the key in the JS `markers` object. However, the JS click handler was still bound to fire with the original JS-generated ID, so `bridge.onMarkerClick('marker_0')` was called but Python was looking for `'py_marker_1'`.

**Fix (`GUI/Widgets/LeafletMap.py`):**
After renaming the marker in the JS `markers` object, the click handler is now unbound and rebound with the correct Python-assigned ID:

```javascript
marker.off('click');
marker.on('click', function() { if (bridge) bridge.onMarkerClick('{py_id}'); });
```

---

### 2. Missing GUI Methods Called by missionState.py

**Problem:** `missionState.py` called `gui.updateDroneOperatingAltitude()` and `gui.updateDroneVisionModel()` which did not exist in the PyQt6 `GUI.py`, causing `AttributeError` crashes.

**Fix (`GUI/GUI.py`):**
Added both methods with thread-safe GUI updates via the `_Invoker` pattern:

```python
def updateDroneOperatingAltitude(self, drone_id, altitude):
    def _do():
        drone = next((d for d in self.map_page.drones if d.id == drone_id), None)
        if drone is not None:
            drone.info_widget.altitude_label.setText(f"Altitude: {altitude} m (set)")
    self._invoker.invoke(_do)

def updateDroneVisionModel(self, drone_id, model):
    def _do():
        drone = next((d for d in self.map_page.drones if d.id == drone_id), None)
        if drone is not None:
            print(f"Drone {drone_id} vision model updated to {model}")
    self._invoker.invoke(_do)
```

---

### 3. Job Waypoint Markers Not Displayed on Map

**Problem:** When jobs were created, waypoint markers were not rendered on the map because `JobWaypoint` was instantiated without the `map_widget` argument.

**Fix (`GUI/GUI.py` — `add_job_waypoint()`):**
Passed `self.map_page.map_widget` to the `JobWaypoint` constructor so markers are created on the map.

---

### 4. GCS Placement Not Working

**Problem:** After the GCS preview marker (cursor-follow feature) was implemented, clicking to place the GCS had no effect.

**Root Cause:** Two issues:
1. The preview marker was intercepting click events before they reached the map's click handler.
2. Existing drone markers (with high z-index) consumed clicks when the user tried to place the GCS on top of a drone's position.

**Fix (`GUI/Widgets/LeafletMap.py` + `GUI/Pages/MapPage.py`):**
- Added an `interactive` parameter to `addMarker()` — preview markers are created with `interactive=false` so they don't consume clicks.
- Added `setAllMarkersInteractive(enabled)` JS function + Python method that toggles `pointer-events` CSS on all existing markers.
- During GCS placement mode, all existing markers are made non-interactive, allowing clicks to pass through to the map.
- On placement completion or cancellation, interactivity is restored.

```python
# MapPage.py — entering GCS placement mode
self.map_widget.set_all_markers_interactive(False)
self.gcs_preview_marker_id = self.map_widget.add_marker(0, 0, "GCS Preview", icon="gcs", interactive=False)
```

---

### 5. Drone/GCS Tooltip Overlap

**Problem:** The drone label and GCS label overlapped when the GCS was placed near a drone, because both tooltips defaulted to appearing above the marker.

**Fix (`GUI/Widgets/LeafletMap.py` — JS `addMarker()`):**
Tooltip direction and offset are now configured per icon type:
- **Drone markers:** Tooltip on top, closer to icon (`offset: [0, -8]`)
- **GCS markers:** Tooltip on bottom (`direction: 'bottom'`, `offset: [0, 8]`)

Additionally, `zIndexOffset` is set per type to control layering:
- Drone: `1000`, POI: `500`, GCS: `-1000`

---

### 6. Target Found Dialog Blocking POI Interaction

**Problem:** When a detection was made and the "Target Found" dialog appeared, it was modal (`dialog.exec()`), preventing the user from clicking POI markers on the map before deciding whether to continue or end the mission.

**Fix (`GUI/Entities/POI.py`):**
Changed from modal to non-modal dialog:

```python
# Before (blocking)
result = dialog.exec()

# After (non-blocking)
self._target_dialog = TargetFoundDialog(self.name, self.gui_ref)
self._target_dialog.accepted.connect(lambda: self.gui_ref.missionState.end_mission())
self._target_dialog.rejected.connect(lambda: self.gui_ref.missionState.remove_poi_investigate_job(self.id))
self._target_dialog.show()
```

The dialog reference is stored on `self` to prevent garbage collection.

---

### 7. LLM Chat Not Executing Commands

**Problem:** Typing commands in the chat sidebar (e.g., "Send drone 1 to POI 1") produced no visible response or action.

**Root Cause:** Three sub-issues in `ChatSidebar.py`:
1. The LLM's text response (`response.content`) was never displayed in the chat.
2. GUI updates from the background LLM thread were not thread-safe.
3. No error handling — exceptions were silently swallowed.

**Fix (`GUI/Widgets/ChatSidebar.py`):**

```python
def on_complete(future):
    try:
        response = future.result()
    except Exception as e:
        self._invoke_bubble(f"LLM: Error - {e}", "llm")
        return
    if response.content:
        self._invoke_bubble(f"LLM: {response.content}", "llm")
    if response.tool_calls:
        for tool_call in response.tool_calls:
            if tool_call.function.name in available_tools:
                available_tools[tool_call.function.name](**tool_call.function.arguments)

def _invoke_bubble(self, text, sender):
    """Thread-safe: add a chat bubble from any thread."""
    self.gui_ref._invoker.invoke(lambda: self.add_message_bubble(text, sender))
```

---

### 8. TypeError in Job Priority Comparison

**Problem:** After the LLM successfully called `create_poi_investigate_job`, the application crashed with:
```
TypeError: '>' not supported between instances of 'str' and 'int'
```

**Root Cause:** Ollama's tool calls pass all arguments as strings. The LLM sent `priority="5"` (string), which was stored as `Job.job_priority`. When `heapq` compared jobs via `Job.__lt__`, it attempted `"5" > 1` (string vs int).

**Fix (two layers):**
- **`GUI/Widgets/ChatSidebar.py`** — Cast LLM arguments at the entry point:
  ```python
  def call_create_poi_investigate_job(poi_id, drone_id, priority=5):
      self.gui_ref.missionState.create_poi_investigate_job(int(poi_id), int(drone_id), int(priority))
  ```
- **`missionState.py`** — Cast `priority` when creating the Job (safety net):
  ```python
  job = Job(..., self, int(priority))
  ```

---

### 9. New Jobs Not Activated After RTL

**Problem:** After ending a mission (RTL), sending a new command via chat (e.g., "Send drone 1 to POI 1") added the job to the queue but the drone never moved. The CLI showed `Active Job: None` with the new job sitting idle in the queue.

**Root Cause:** In `Drone.addJob()`, the condition for setting a new active job was:
```python
if self.jobQueue.is_empty() and self.active_job is None:
```
After RTL, `setDroneUnavailable()` pushed the old search jobs back into the queue. So when the new job arrived, `jobQueue.is_empty()` was `False` (old jobs present) even though `active_job` was `None` (drone idle). The new job was simply queued with no mechanism to activate it.

**Fix (`missionState.py`):**
```python
# Before — required BOTH empty queue AND no active job
if self.jobQueue.is_empty() and self.active_job is None:

# After — if drone is idle, start the job immediately
if self.active_job is None:
```

This allows `setActiveJob()` to trigger the full `send_waypoints` -> `upload_mission` -> `start_mission` -> `takeoff()` chain, re-arming the drone if grounded.

---

## Feature Additions

### 1. Offline Tile Fallback

**Problem:** The Leaflet map failed to load when no internet connection was available.

**Fix (`GUI/Widgets/LeafletMap.py`):**
Added an internet connectivity check (using `TerrainPreProcessing.check_internet.has_internet()`) at map initialization. When offline, the map loads tiles from a local cache directory instead of the OpenStreetMap CDN.

---

### 2. Send Button Icon

**Problem:** The chat sidebar's send button displayed plain text ("Send") instead of a visual icon like the tkinter version.

**Fix (`GUI/Widgets/ChatSidebar.py`):**
Added icon loading from `assets/send.png` with fallback to text:

```python
send_icon_path = os.path.join(os.path.dirname(__file__), "..", "..", "assets", "send.png")
if os.path.exists(send_icon_path):
    send_button.setIcon(QIcon(send_icon_path))
    send_button.setIconSize(QSize(20, 20))
else:
    send_button.setText("Send")
```

---

### 3. LLM Tool Calling Improvements

**Problem:** The LLM (llama3.2 via Ollama) frequently selected the wrong tool. For example, "Send drone 1 to POI 1" would trigger `call_return_to_launch` instead of `create_poi_investigate_job`.

**Changes (`LangGraph/langChainMain.py`):**

1. **Separated system and user messages** — Previously, instructions and the user prompt were concatenated into a single `"role": "user"` message. Now the system prompt uses `"role": "system"` and the user's text is a separate `"role": "user"` message.

2. **Improved tool descriptions** — Each tool docstring now explicitly states when to use it and when NOT to:
   ```python
   def create_poi_investigate_job(poi_id: int, drone_id: int, priority: int = 5):
       """
       Navigate a drone to a specific Point of Interest (POI) to investigate it.
       Use this when the user wants to SEND a drone TO a POI, FLY to a POI, GO to a POI, or INVESTIGATE a POI.
       """

   def call_return_to_launch(drone_id: int):
       """
       Command a drone to return to its home/launch position (RTL).
       Do NOT use this when the user wants to send a drone to a POI.
       """
   ```

3. **Added explicit mapping rules** in the system prompt:
   ```
   "Send drone X to POI Y" means create_poi_investigate_job(poi_id=Y, drone_id=X).
   "Bring drone X home" means call_return_to_launch(drone_id=X).
   "Start mission" means call_start_mission().
   ```

4. **Added proper type hints** — Parameters annotated with `int` so Ollama generates correct JSON schema types.

5. **Removed dead code** — Unused `create_drone_job` function and broken `Job()` return statements in tool stubs (these tools are schema-only; execution happens in ChatSidebar.py).

---

### 4. Start Mission via Chat

**Problem:** Typing "start mission" in the chat had no corresponding tool, so the LLM incorrectly mapped it to `create_poi_investigate_job` with `poi_id=0`.

**Fix:**
- **`LangGraph/langChainMain.py`** — Added `call_start_mission()` tool definition:
  ```python
  def call_start_mission():
      """
      Start the search mission. This deploys all drones to begin searching the mission area.
      Use this when the user wants to START, BEGIN, or LAUNCH the mission.
      """
      pass
  ```

- **`GUI/Widgets/ChatSidebar.py`** — Added handler that calls the same method as the GUI button:
  ```python
  def call_start_mission(**kwargs):
      self.gui_ref.call_start_mission()
      self._invoke_bubble("LLM: Starting search mission.", "llm")
  ```

  Note: `**kwargs` is used because llama3.2 occasionally hallucinate extra arguments (e.g., passing `drone_id` to a no-argument function).

---

## Files Modified

| File | Changes |
|------|---------|
| `GUI/Widgets/LeafletMap.py` | POI click fix, `interactive` param, `setAllMarkersInteractive()`, per-type tooltips/z-index, offline tiles |
| `GUI/GUI.py` | Added `updateDroneOperatingAltitude()`, `updateDroneVisionModel()`, fixed `add_job_waypoint()` |
| `GUI/Entities/POI.py` | Non-modal Target Found dialog |
| `GUI/Widgets/ChatSidebar.py` | LLM response display, thread-safe bubbles, error handling, send icon, `start_mission`/`end_mission` tools, int casting |
| `GUI/Pages/MapPage.py` | GCS preview marker, marker interactivity toggling during placement |
| `LangGraph/langChainMain.py` | Restructured prompts, improved tool descriptions, added `call_start_mission` tool |
| `missionState.py` | Fixed `addJob()` condition, `int(priority)` cast in `create_poi_investigate_job` |

---

## Summary

A total of **9 bug fixes** and **4 feature additions** were made across **7 files**. The most critical fixes addressed the POI marker click handler (JS/Python ID mismatch), the job scheduling logic after RTL (idle drone not picking up new jobs), and the LLM chat integration (response display, thread safety, tool selection accuracy, and type casting). The appNew PyQt6 version now has functional parity with the tkinter version for all core mission operations.
