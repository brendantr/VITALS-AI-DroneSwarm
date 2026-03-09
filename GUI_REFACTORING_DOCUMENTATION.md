# GUI Refactoring Documentation

## Overview

This document details the refactoring process that transformed the original monolithic 1,262-line `GUI.py` file into a modular architecture consisting of a 255-line main `GUI.py` file with supporting modules organized into three directories: `Entities/`, `Pages/`, and `Widgets/`.

---

## Original Structure (Before Refactoring)

**File:** `Backup/Original/GUI/GUI.py`
**Total Lines:** 1,262

### Classes in Original Monolithic File:

| Class | Lines | Description |
|-------|-------|-------------|
| `Drone` | 15-177 | Drone entity with position, telemetry, job management |
| `Job` | 181-186 | Simple job data class |
| `POI` | 188-290 | Point of Interest entity with popup handling |
| `POIInfoBox` | 291-306 | Widget displaying POI info in sidebar |
| `ChatSidebar` | 308-475 | Chat interface with LLM integration |
| `jobInfoContainer` | 477-489 | Container widget for drone job lists |
| `jobInfoItem` | 491-522 | Individual job display widget |
| `DroneInfoBox` | 526-661 | Drone info widget with settings dialog |
| `MapPage` | 664-967 | Main map page with all map functionality |
| `HomePage` | 969-986 | Simple home/welcome page |
| `JobWaypoint` | 988-992 | Waypoint marker for job creation |
| `GUI` | 995-1257 | Main application controller |

---

## New Modular Structure (After Refactoring)

```
GUI/
├── GUI.py                     (255 lines) - Main application controller
├── Entities/
│   ├── __init__.py
│   ├── Drone.py              (169 lines) - Drone entity class
│   ├── POI.py                (123 lines) - POI entity + POIInfoBox widget
│   └── Job.py                (15 lines)  - Job and JobWaypoint classes
├── Pages/
│   ├── __init__.py
│   ├── HomePage.py           (81 lines)  - Welcome/home page
│   └── MapPage.py            (469 lines) - Main map interface
└── Widgets/
    ├── __init__.py
    ├── ChatSidebar.py        (173 lines) - Chat interface with LLM
    └── DroneWidgets.py       (187 lines) - DroneInfoBox, jobInfoContainer, jobInfoItem
```

**Total Lines After Refactoring:** ~1,472 lines (includes new features added during refactoring)

---

## Detailed Changes by Module

### 1. Main GUI.py (995-1257 → 255 lines)

**Moved Out:**
- All class definitions except `GUI`
- Inline widget creation logic

**Retained:**
- Application initialization
- Page navigation (`show_home_page`, `show_map_page`)
- Mission state linking
- Drone update methods (`updateDronePosition`, `updateDroneTelemetry`, etc.)
- Detection point handling
- Debugging function calls
- GCS location setting

**New Imports Added:**
```python
from GUI.Entities.Job import JobWaypoint
from GUI.Pages.HomePage import HomePage
from GUI.Pages.MapPage import MapPage
```

**Improvements Made:**
- Added `has_centered_on_drone` flag for auto-centering map on first drone position
- Added coordinate conversion check in `updateDronePosition` (MAVLink 1e-7 scaling)
- Added debug logging statements
- Initialized `gcs_location` and `gcs_marker` as `None` in constructor

---

### 2. Entities/Drone.py (Lines 15-177 → 169 lines)

**Extracted:** The `Drone` class in its entirety

**Import Changes:**
```python
# Original inline import
import math
import PIL.Image
import PIL.ImageTk

# New modular import
from GUI.Widgets.DroneWidgets import DroneInfoBox, jobInfoContainer, jobInfoItem
```

**Modifications:**
- `setPosition()` method simplified - coordinate conversion now handled by `GUI.py`
- Original converted lat/lon from 7-decimal int format internally; now expects pre-converted coordinates

---

### 3. Entities/POI.py (Lines 188-306 → 123 lines)

**Extracted:**
- `POI` class (lines 188-290)
- `POIInfoBox` class (lines 291-306)

**No functional changes** - Direct extraction with proper imports added.

---

### 4. Entities/Job.py (Lines 181-186, 988-992 → 15 lines)

**Extracted:**
- `Job` class (lines 181-186)
- `JobWaypoint` class (lines 988-992)

**Bug Fix Applied:**
```python
# Original (line 186) - Bug: path_obj not assigned to self
path_obj = path_obj

# Fixed
self.path_obj = path_obj  # Comment: "changed it to self. on 10/27/25"
```

---

### 5. Pages/HomePage.py (Lines 969-986 → 81 lines)

**Extracted:** `HomePage` class

**Major UX Enhancement:**
The original HomePage was minimal (18 lines) with just a button that opened a popup:

```python
# Original
class HomePage(customtkinter.CTkFrame):
    def __init__(self, parent, switch_to_map, gui_ref, **kwargs):
        super().__init__(parent, **kwargs)
        self.switch_to_map = switch_to_map
        label = customtkinter.CTkLabel(self, text="Welcome to VITALS!", ...)
        switch_button = customtkinter.CTkButton(self, text="Start Mission", command=self.switch_to_map)
        mission_review_button = customtkinter.CTkButton(self, text="Mission Review")
```

**Refactored version includes:**
- Two-screen flow: Initial menu → Mission type selection
- Back button to return to initial menu
- Simulation vs Real Mission selection integrated into the page (no popup)
- `show_mission_type_selection()` and `show_initial_menu()` methods for navigation
- Cleaner separation of concerns

---

### 6. Pages/MapPage.py (Lines 664-967 → 469 lines)

**Extracted:** `MapPage` class

**New Imports:**
```python
from GUI.Entities.Drone import Drone
from GUI.Entities.Job import Job
from GUI.Entities.POI import POI
from GUI.Widgets.ChatSidebar import ChatSidebar
```

**New Features Added:**

1. **GCS Placement Preview System:**
   - `gcs_preview_marker` - Shows marker preview while hovering
   - `gcs_motion_binding` - Mouse motion event binding
   - `_load_gcs_icon()` - Pre-loads GCS icon
   - `toggle_gcs_placement()` - Toggle between place/remove modes
   - `update_gcs_preview()` - Updates preview marker on mouse move
   - `cancel_gcs_placement()` - Cancels placement mode
   - `finalize_gcs_placement()` - Cleans up after placement

2. **Polygon Editing Controls:**
   - `polygon_edit_frame` - Frame containing undo/reset buttons
   - `undo_polygon_button` - Removes last polygon point
   - `reset_polygon_button` - Clears all polygon points
   - `undo_last_polygon_point()` - Implementation of undo
   - `reset_polygon()` - Implementation of reset

3. **Separate "Place GCS" Button:**
   - Original: GCS placement started automatically after Mavlink connection
   - New: Dedicated button for explicit GCS placement

4. **Improved Polygon Handling:**
   - Original: `self.polygon.add_position()` used for adding points
   - New: Polygon deleted and recreated on each point add for consistency with undo

---

### 7. Widgets/ChatSidebar.py (Lines 308-475 → 173 lines)

**Extracted:** `ChatSidebar` class

**No functional changes** - Direct extraction with proper imports:
```python
import PIL.Image
import customtkinter
from concurrent.futures import ThreadPoolExecutor
from LangGraph import langChainMain
```

---

### 8. Widgets/DroneWidgets.py (Lines 477-661 → 187 lines)

**Extracted:**
- `jobInfoContainer` class (lines 477-489)
- `jobInfoItem` class (lines 491-522)
- `DroneInfoBox` class (lines 526-661)

**No functional changes** - Direct extraction with proper imports.

---

## Import Dependency Graph

```
GUI.py
├── GUI.Entities.Job (JobWaypoint)
├── GUI.Pages.HomePage
└── GUI.Pages.MapPage
    ├── GUI.Entities.Drone
    │   └── GUI.Widgets.DroneWidgets (DroneInfoBox, jobInfoContainer, jobInfoItem)
    ├── GUI.Entities.Job (Job)
    ├── GUI.Entities.POI (POI)
    └── GUI.Widgets.ChatSidebar
```

---

## Summary of Changes

### Code Organization Benefits:

1. **Separation of Concerns:** Each file now has a single responsibility
2. **Maintainability:** Changes to drone widgets don't require touching the main GUI file
3. **Testability:** Individual components can be tested in isolation
4. **Readability:** Smaller files are easier to navigate and understand
5. **Reusability:** Entities and widgets can be imported independently

### New Features Added During Refactoring:

1. **GCS Preview Placement** - Visual feedback when placing Ground Control Station
2. **Polygon Undo/Reset** - Ability to correct polygon drawing mistakes
3. **Auto-Center on Drone** - Map automatically centers on first drone position
4. **Improved HomePage Flow** - In-page navigation instead of popup dialogs
5. **Enhanced Coordinate Handling** - Robust MAVLink coordinate conversion

### Line Count Comparison:

| Component | Original | Refactored |
|-----------|----------|------------|
| Main GUI.py | 1,262 | 255 |
| Entities/ | (inline) | 307 |
| Pages/ | (inline) | 550 |
| Widgets/ | (inline) | 360 |
| **Total** | **1,262** | **1,472** |

*Note: Total increased due to new features added during refactoring*

---

## File Locations

- **Original File:** `Backup/Original/GUI/GUI.py`
- **Refactored Files:** `app/GUI/` directory structure shown above
