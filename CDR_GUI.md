# VITALS GUI — Critical Design Review

---

## Slide 1: Agenda

Three phases of GUI development:

1. **Refactoring** — From one monolithic file to a modular architecture
2. **UX Improvements** — Eliminating dead ends and unrecoverable states
3. **Framework Migration** — From tkinter to PyQt6 for a modern, professional interface

---

## Slide 2: Where We Started — The Monolithic GUI

The original GUI was a **1,393-line, two-file implementation** built on customtkinter and tkintermapview.

| File | Lines | Contents |
|------|-------|----------|
| GUI.py | 1,261 | 12 classes — everything from widgets to mission control |
| Drone.py | 132 | Drone entity with position, telemetry, and job management |
| **Total** | **1,393** | **All GUI logic in two files** |

**12 classes packed into GUI.py:**

| Class | Lines | Responsibility |
|-------|-------|----------------|
| Drone | 15–178 | Drone state, map markers, heading visualization, job management |
| Job | 181–186 | 4-line data container |
| POI | 188–231 | Point of Interest detection, popup interaction |
| POIInfoBox | 291–306 | POI sidebar display widget |
| ChatSidebar | 308–475 | LLM chat interface with async threading |
| jobInfoContainer | 477–490 | Scrollable container for drone job lists |
| jobInfoItem | 491–523 | Individual job card widget |
| DroneInfoBox | 526–662 | Drone telemetry display with settings modal |
| MapPage | 664–967 | Map interface, polygon drawing, GCS, drones, POIs |
| HomePage | 969–986 | 17-line welcome page |
| JobWaypoint | 988–993 | 5-line waypoint marker wrapper |
| GUI | 995–1261 | Main application controller |

---

## Slide 3: Problems with the Monolithic Design

### Tight Coupling
- The `Drone` class directly called `self.map_widget.set_path()` and `self.map_widget.set_marker()` — it couldn't exist without the map
- POI creation required passing `map_widget`, `info_container`, `poi_count`, and `gui_ref` — four dependencies for one entity
- The GUI class was a god object handling window setup, page switching, chat, debug functions, drone updates, and mission lifecycle all at once

### No Separation of Concerns
- UI styling mixed with event handling mixed with business logic
- Modifying the chat sidebar meant editing a 1,261-line file
- Adding a new widget meant navigating through 12 unrelated classes

### Maintenance Risk
- A single syntax error anywhere in GUI.py could crash the entire application
- No way to unit test individual components
- New team members had to understand the full 1,261 lines before making changes

---

## Slide 4: The Refactored Architecture

We split the monolithic file into **8 focused modules** across 3 directories:

```
GUI/
├── GUI.py                   (279 lines)  Main controller
├── Entities/
│   ├── Drone.py             (168 lines)  Drone state & visualization
│   ├── POI.py               (122 lines)  POI entity + info widget
│   └── Job.py               ( 14 lines)  Job & waypoint data classes
├── Pages/
│   ├── HomePage.py          ( 81 lines)  Mission type selection
│   └── MapPage.py           (520 lines)  Map interface & controls
└── Widgets/
    ├── ChatSidebar.py       (172 lines)  LLM chat with async calls
    └── DroneWidgets.py      (186 lines)  Drone info cards & job lists
```

**Total: 1,542 lines across 8 files** (vs. 1,393 in 2 files)

The line count increased slightly because we added new features during refactoring, but no single file exceeds 520 lines.

---

## Slide 5: Refactoring — Responsibility Separation

### Import Dependency Graph

```
GUI.py (Controller)
├── Pages/HomePage.py
└── Pages/MapPage.py
    ├── Entities/Drone.py
    │   └── Widgets/DroneWidgets.py
    ├── Entities/POI.py
    ├── Entities/Job.py
    └── Widgets/ChatSidebar.py
```

### Design Principles Applied

| Principle | Before | After |
|-----------|--------|-------|
| Single Responsibility | GUI.py handled everything | Each file has one job |
| Encapsulation | Drone logic scattered across GUI.py | Drone.py owns all drone state |
| Testability | Can't test chat without loading the full GUI | ChatSidebar can be instantiated independently |
| Navigability | Search through 1,261 lines to find a bug | Know exactly which file to open |
| Collaboration | Two people editing GUI.py = merge conflicts | Parallel development on separate files |

---

## Slide 6: UX Dead Ends — What We Found

The original GUI had several interaction dead ends where users were **forced to close and reopen the application** to recover from a mistake.

| Dead End | Scenario | User Impact |
|----------|----------|-------------|
| **No polygon undo** | Misclicked a polygon vertex | Must restart the entire app to redraw |
| **GCS locked in** | Placed GCS in wrong location | Cannot change without restart |
| **No mission cancel** | Started a mission, realized setup was wrong | No way back to HomePage without restarting |
| **Modal dialogs block everything** | "Target Found" popup appears | Can't click map, review POIs, or do anything else until choosing |
| **No mission state reset** | Want to start a new mission after finishing one | Must close and reopen the application |
| **Broken "Finish Job" feature** | Right-click → "Finish Job" | `finish_creating_job()` was a stub: just `pass` |

---

## Slide 7: UX Fix — Polygon Editing Controls

### Before:
- Click points on map to draw polygon
- Made a mistake? Close the app and start over

### After:
Added **Undo Last Point** and **Reset** buttons that appear dynamically when polygon editing is active.

**Undo** removes the last vertex and redraws the polygon:
```python
def undo_last_polygon_point(self):
    self.polygon_points.pop()
    self.polygon.delete()
    self.polygon = self.map_widget.set_polygon(self.polygon_points, fill_color=None)
```

**Reset** clears all points and returns to a blank slate:
```python
def reset_polygon(self):
    self.polygon_points = []
    self.polygon.delete()
    self.first_polygon_point = True
```

System chat feedback confirms every action: *"Removed last point. 3 points remaining."*

---

## Slide 8: UX Fix — GCS Placement with Preview & Cancel

### Before:
- Click map → GCS immediately placed, no preview, no cancellation
- Placed in wrong spot? Restart the application

### After:
A three-step workflow with full recoverability:

1. **Click "Place GCS"** — enters placement mode, button changes to "Cancel Placement"
2. **Preview marker follows cursor** — user sees exactly where GCS will land before clicking
3. **Click to confirm** — or press Cancel to abort and try again

Key implementation detail: during placement mode, all existing markers (drones, POIs) have their pointer-events disabled so the user can place the GCS directly on top of a drone's position if needed.

After placement, the button changes to **"Remove GCS"**, allowing users to remove and re-place as needed.

---

## Slide 9: UX Fix — In-Page Navigation (No More Modal Popups)

### Before:
- Clicking "Start Mission" on the HomePage opened a **modal popup** to choose Simulation vs. Real Mission
- The popup blocked all interaction with the main window
- No way to go back once on the MapPage

### After:
- HomePage uses **in-page frame swapping** — no popups
- Initial menu shows "Start Mission" and "Mission Review"
- Clicking "Start Mission" smoothly transitions to mission type selection with a **Back button**
- MapPage includes a "Back to Home" button that **resets all mission state** cleanly

```
HomePage: [Start Mission] [Mission Review]
    ↓ click
Mission Type: [Simulation] [Real Mission] [← Back]
    ↓ click
MapPage: [...controls...] [Back to Home]
    ↓ click (resets state)
HomePage: [Start Mission] [Mission Review]
```

---

## Slide 10: UX Fix — Non-Blocking Target Found Dialog

### Before (modal, blocks everything):
```python
# tkinter: grab_set() makes the dialog modal — no map interaction
self.target_found_popup = CTkToplevel(...)
self.target_found_popup.grab_set()  # BLOCKS ALL INTERACTION
```
User **cannot** click the POI to view detection images or zoom the map to verify the location before making a critical decision.

### After (non-modal, allows investigation):
```python
# PyQt6: show() instead of exec() — user can still interact with map
self._target_dialog = TargetFoundDialog(poi_name, gui_ref)
self._target_dialog.accepted.connect(lambda: missionState.end_mission())
self._target_dialog.rejected.connect(lambda: missionState.remove_poi_investigate_job(poi_id))
self._target_dialog.show()  # NON-BLOCKING
```

User **can now**:
- Click the POI marker to view captured images
- Zoom and pan the map to verify the detection location
- Review other POIs before deciding to end or continue the mission

---

## Slide 11: Why Switch Frameworks? tkinter Limitations

After refactoring and fixing UX dead ends, we hit fundamental limitations of the tkinter/customtkinter stack:

| Limitation | Impact |
|------------|--------|
| **tkintermapview has limited map features** | No custom marker icons beyond colored circles, no marker layering control, no tooltip positioning, limited zoom levels |
| **No built-in thread safety** | MAVLink updates from background thread required manual `after()` hacks to avoid crashes |
| **Dated visual style** | customtkinter improves on raw tkinter but still looks like a desktop app from 2010 |
| **Canvas-based chat scrolling** | Had to manually manage canvas scroll regions, redraws, and `yview_moveto()` |
| **No CSS-like styling** | Colors hardcoded per-widget; changing the theme means editing dozens of lines |
| **Limited layout system** | `grid()` and `pack()` geometry managers are fragile; resizing often breaks layouts |
| **No web engine** | Can't embed modern web technologies (Leaflet.js, D3, etc.) |

---

## Slide 12: PyQt6 — The New Stack

We migrated the entire GUI to **PyQt6** — Python bindings for the Qt framework (C++ backend).

### New Architecture: 10 files, 2,503 lines

```
GUI/
├── GUI.py                   (367 lines)  Controller + _Invoker thread safety
├── theme.py                 (205 lines)  Global dark theme stylesheet (CSS-like)
├── Entities/
│   ├── Drone.py             (142 lines)  Drone state
│   ├── POI.py               (177 lines)  POI entity + non-modal dialog
│   └── Job.py               ( 16 lines)  Data classes
├── Pages/
│   ├── HomePage.py          (126 lines)  Mission launcher
│   └── MapPage.py           (548 lines)  Map interface
└── Widgets/
    ├── LeafletMap.py         (471 lines)  Leaflet.js map via QWebEngineView
    ├── ChatSidebar.py        (170 lines)  LLM chat with thread-safe bubbles
    └── DroneWidgets.py       (281 lines)  Drone info cards + settings
```

---

## Slide 13: Code Growth Across Versions

| Version | Files | Total Lines | Framework |
|---------|-------|-------------|-----------|
| Original (monolithic) | 2 | 1,393 | customtkinter + tkintermapview |
| Refactored (modular) | 8 | 1,542 | customtkinter + tkintermapview |
| PyQt6 (current) | 10 | 2,503 | PyQt6 + Leaflet.js |

The PyQt6 version is larger because it includes:
- **LeafletMap.py** (471 lines) — a full JavaScript bridge that replaces tkintermapview's limited functionality
- **theme.py** (205 lines) — a centralized dark theme that replaces dozens of scattered hardcoded colors
- Enhanced features: non-modal dialogs, thread-safe invoker, interactive marker toggling, offline tile support

---

## Slide 14: Leaflet.js Map — A Major Upgrade

### Before (tkintermapview):
- Colored circle markers with basic hover tooltips
- Single-layer: all markers at same depth
- No custom icons
- Limited zoom levels
- No communication bridge to Python for marker clicks

### After (Leaflet.js via QWebEngineView):

**Custom marker icons** for drones, POIs, GCS, and detection points — loaded from PNG assets.

**Intelligent layering** via zIndexOffset:
```
Drone markers:     zIndexOffset = 1000  (always on top)
POI markers:       zIndexOffset =  500  (middle layer)
GCS marker:        zIndexOffset = -1000 (bottom layer)
```

**Per-type tooltip positioning:**
- Drone labels appear **above** the icon (close to image)
- GCS labels appear **below** the icon (prevents overlap when co-located)

**Permanent tooltips** — labels always visible, not just on hover.

**Python ↔ JavaScript bridge** via QWebChannel:
```
User clicks marker on map
  → JavaScript: marker.on('click', () => bridge.onMarkerClick(id))
  → QWebChannel: _MapBridge.onMarkerClick() fires pyqtSignal
  → Python: POI._on_marker_click() opens detail popup
```

---

## Slide 15: The _Invoker Pattern — Thread Safety

### The Problem:
MAVLink runs in a background thread, sending drone position updates at 10–30 Hz. Directly modifying PyQt6 widgets from a background thread causes **crashes and race conditions**.

### The Solution:
A 12-line thread-safe invoker that marshals all GUI updates to the main thread:

```python
class _Invoker(QObject):
    _sig = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self._sig.connect(self._call, Qt.ConnectionType.QueuedConnection)

    def _call(self, fn):
        fn()

    def invoke(self, fn):
        self._sig.emit(fn)
```

### How it works:
```
MAVLink Thread                    Main Thread (GUI)
     |                                 |
     |-- invoker.invoke(update_fn) --> |
     |      ↓                          |
     |   signal emitted (queued)       |
     |                                 |<-- Qt event loop dequeues
     |                                 |<-- update_fn() runs safely
```

### Used everywhere:
- `updateDronePosition()` — 10–30 Hz telemetry updates
- `addDetectedPOI()` — POI creation from CV detection thread (uses `threading.Event()` for blocking wait)
- `create_system_chat_message()` — chat messages from LLM thread
- `_invoke_bubble()` — LLM response display from ThreadPoolExecutor callback

---

## Slide 16: Dark Theme — Centralized Styling

### Before (tkinter):
Colors hardcoded per widget, scattered across 1,261 lines:
```python
# 30+ lines like this throughout GUI.py:
bubble.configure(fg_color="#3b82f6")
self.chat_canvas = CTkCanvas(..., bg="#2B2B2B")
container.configure(fg_color="#337ab7")
```

### After (PyQt6):
A single `theme.py` file (205 lines) with CSS-like Qt Stylesheets:

```css
/* Applied globally — every widget inherits automatically */
QMainWindow, QWidget {
    background-color: #1a1a2e;
    color: #e0e0e0;
    font-family: "Segoe UI", Arial;
}

/* Button variants via CSS properties */
QPushButton[cssClass="primary"]:hover {
    background-color: #533483;     /* Purple accent */
}
QPushButton[cssClass="danger"] {
    background-color: #6b1d1d;     /* Red for destructive actions */
}

/* Status-driven coloring */
QLabel[cssClass="status-active"]   { color: #00e676; }  /* Green */
QLabel[cssClass="status-standby"]  { color: #ffab00; }  /* Orange */
QLabel[cssClass="status-critical"] { color: #ff1744; }  /* Red */
```

**Color palette:**

| Element | Color | Hex |
|---------|-------|-----|
| Background | Deep Navy | #1a1a2e |
| Cards/Frames | Navy | #16213e |
| Accent (hover/active) | Purple | #533483 |
| Primary Text | Light Gray | #e0e0e0 |
| Active Status | Green | #00e676 |
| Warning | Orange | #ffab00 |
| Critical | Red | #ff1744 |

---

## Slide 17: LLM Chat Integration

The chat sidebar allows natural language control of the mission. Users can type commands like "Send drone 1 to POI 1" or "Start mission" and the LLM translates them to system actions.

### End-to-End Flow:

```
1. User types: "Send drone 1 to POI 1"
       ↓
2. ThreadPoolExecutor submits to Ollama (non-blocking)
       ↓
3. System prompt provides context:
   - Available drones, POIs, mission area
   - Rules: "Send drone X to POI Y" → create_poi_investigate_job
       ↓
4. Ollama returns tool_call:
   { name: "create_poi_investigate_job", args: { poi_id: 1, drone_id: 1 } }
       ↓
5. Python dispatches to missionState:
   missionState.create_poi_investigate_job(1, 1, 5)
       ↓
6. Thread-safe chat bubble confirms:
   "LLM: Sending drone 1 to investigate POI 1"
```

### Available Tools:
| Tool | Trigger Phrases | Action |
|------|----------------|--------|
| `call_start_mission` | "Start mission", "Begin", "Launch" | Deploys all drones to search |
| `create_poi_investigate_job` | "Send drone X to POI Y", "Investigate POI" | Navigates a specific drone to a POI |
| `call_return_to_launch` | "Bring drone home", "Return to launch" | Recalls a drone to GCS |
| `call_end_mission` | "End mission", "Stop everything" | Recalls all drones |

---

## Slide 18: Signals & Slots vs. Callbacks

### tkinter (before): Manual callbacks
```python
# Emitter hardcoded to a single callback
button.configure(command=self.on_click)

# Threading: manual after() calls to avoid crashes
self.map_widget.after(100, clear_widgets)
```

### PyQt6 (after): Decoupled signals & slots
```python
# One signal, many listeners — fully decoupled
self.map_widget.marker_clicked.connect(poi._on_marker_click)
self.map_widget.marker_clicked.connect(drone._on_marker_click)

# Thread safety built in via QueuedConnection
self._sig.connect(self._call, Qt.ConnectionType.QueuedConnection)
```

| Aspect | tkinter Callbacks | PyQt6 Signals/Slots |
|--------|-------------------|---------------------|
| Coupling | Emitter knows the receiver | Emitter is decoupled |
| Multiple listeners | One callback per event | Many slots per signal |
| Thread safety | Manual (fragile) | Built-in (QueuedConnection) |
| Type safety | Runtime errors | Signal args validated |
| Debugging | Opaque callback stack | Signal chain visible |
| Performance | Python function calls | Optimized C++ backend |

---

## Slide 19: Feature Comparison — All Three Versions

| Feature | Original | Refactored tkinter | PyQt6 |
|---------|----------|-------------------|-------|
| File structure | 2 files (1,393 lines) | 8 files (1,542 lines) | 10 files (2,503 lines) |
| Polygon undo/reset | No | Yes | Yes |
| GCS preview marker | No | Yes (cursor-follow) | Yes (cursor-follow) |
| GCS cancellation | No | Yes | Yes |
| GCS removal & re-placement | No | Yes | Yes |
| Non-blocking dialogs | No | No | Yes |
| In-page navigation | No (modal popup) | Yes | Yes |
| Back to Home button | No | Yes | Yes |
| Mission state reset | No (restart required) | Yes | Yes |
| Custom map icons | No (colored circles) | No (colored circles) | Yes (PNG assets) |
| Marker layering (z-index) | No | No | Yes |
| Tooltip positioning | Hover only, fixed | Hover only, fixed | Permanent, per-type |
| Thread-safe GUI updates | Manual after() | Manual after() | _Invoker pattern |
| Global theme system | No (hardcoded colors) | No (hardcoded colors) | Yes (theme.py, 205 lines) |
| LLM tool calling | Basic | Basic | Full (4 tools, type-safe) |
| Offline map tiles | Localhost fallback | Localhost fallback | Localhost fallback |
| Auto-center on drone | No | Yes | Yes |
| Map framework | tkintermapview | tkintermapview | Leaflet.js (QWebEngineView) |
| Interactive marker toggling | No | No | Yes |

---

## Slide 20: Summary

### Phase 1 — Refactoring
Broke a monolithic 1,261-line file into 8 focused modules. Each class now has a single responsibility and lives in its own file. The import dependency graph is clean and navigable.

### Phase 2 — UX Improvements
Eliminated every dead end where users would have to close and reopen the application:
- Polygon undo/reset
- GCS preview, cancel, remove, and re-place
- In-page navigation with Back buttons
- Mission state reset on return to Home

### Phase 3 — Framework Migration
Moved from customtkinter to PyQt6 for:
- **Leaflet.js maps** with custom icons, layering, and permanent tooltips
- **Thread-safe architecture** via the _Invoker pattern (12 lines that prevent all race conditions)
- **Centralized dark theme** in a single CSS-like stylesheet
- **Non-modal dialogs** that let users investigate before making critical decisions
- **Signals & slots** for decoupled, type-safe event handling

The GUI evolved from a fragile prototype into a professional, maintainable application ready for field use.
