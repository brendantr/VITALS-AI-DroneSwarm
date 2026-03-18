# Job Refactoring Documentation

## Overview

This document summarizes the refactor of the Job model, JobWaypoint, and JobQueue system. The refactor unified job data into a dedicated `models/jobs` package, cleaned up the `Job` API, and updated call sites in `missionState`, GUI modules, and LangGraph integration.

---

## Original Structure (Before Refactoring)

**Primary Files:**
- `app/models/jobs/job.py` (contained overlapping `Job` + `JobWaypoint` definitions, two `__init__` methods in one class)
- `app/models/jobs/job_queue.py` (thin wrapper around `queue.PriorityQueue`)
- Multiple call sites constructing `Job` with inconsistent argument order and missing imports

**Key Issues:**
- `Job` had two `__init__` methods, so only the last one (waypoint marker) actually worked.
- Job queue exposed the raw queue structure, which leaked implementation details into GUI code.
- Job status was set using `job.status`, but the real field was `job.job_status`.

---

## New Modular Structure (After Refactoring)

```
models/jobs/
├── job.py        - Job + JobWaypoint classes with consistent API
└── job_queue.py  - Heap-backed JobQueue with list_jobs() API
```

---

## Detailed Changes

### 1. `models/jobs/job.py`

**Before:**
- Two `__init__` methods in `Job` (one for job data, one for waypoint marker).
- Job ID, status, and priority handling was inconsistent across call sites.

**After:**
- Separate `JobWaypoint` class.
- Single `Job` constructor with consistent fields:
  - `job_type`, `job_status`, `job_priority`
  - `waypoints`, `path_obj`
  - `job_id` sourced from `missionState.jobIDCounter` if available
  - `last_waypoint`, `upload_try_count`
- Added `status` property as a compatibility layer for old code.

---

### 2. `models/jobs/job_queue.py`

**Before:**
- Used `queue.PriorityQueue` directly.
- Call sites accessed `.queue` to display jobs.

**After:**
- Replaced with heap-based queue (`heapq`) for predictable ordering.
- New methods:
  - `add_job(job)`
  - `get_next_job()`
  - `peek_next_job()`
  - `list_jobs()` (safe for GUI display)

---

### 3. `missionState.py`

**Updates:**
- Imports `Job` from `models/jobs/job.py`.
- Uses `job.job_status` consistently.
- GUI updates now pass `jobQueue.list_jobs()` instead of raw queue internals.

---

### 4. GUI + LangGraph Call Sites

**Updated:**
- `GUI.py` imports `JobWaypoint` from `models/jobs/job`.
- `MapPage.py` creates jobs with the new signature.
- `LangGraph/langChainMain.py` now imports `Job` and uses the new constructor shape.
- Safety fix in `Drone.update_jobs()` to avoid deleting a `None` path.

---

## Summary of Benefits

1. **Single Source of Truth:** Job state now lives in a single, clean class.
2. **Consistent Constructor:** All `Job` creation calls align on the same API.
3. **Cleaner Queue API:** GUI no longer depends on internal queue structure.
4. **Waypoint Separation:** `JobWaypoint` is now a distinct type for map markers.
5. **Compatibility Preserved:** `status` property maps to `job_status`.

---

## File Locations

- **Models:** `app/models/jobs/job.py`, `app/models/jobs/job_queue.py`
- **Call Site Updates:**
  - `app/missionState.py`
  - `app/GUI/GUI.py`
  - `app/GUI/Pages/MapPage.py`
  - `app/GUI/Entities/Drone.py`
  - `app/LangGraph/langChainMain.py`
