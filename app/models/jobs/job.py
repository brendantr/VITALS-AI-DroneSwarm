from __future__ import annotations

from typing import Any, Iterable, Optional


class JobWaypoint:
    def __init__(self, lat: float, lon: float, waypoint_num: int, map_widget: Any | None = None) -> None:
        self.lat = lat
        self.lon = lon
        self.waypoint_num = waypoint_num
        self.marker = None
        if map_widget is not None:
            self.marker = map_widget.set_marker(lat, lon, text=str(waypoint_num))


class Job:
    INITIAL_SEARCH = "Initial Search"
    AUTOMATED_PATH = "Automated Path"
    USER_PATH = "User Path"
    INVESTIGATE_POI = "Investigate POI"
    CRITICAL = 1
    NORMAL = 5

    _local_id_counter = 1

    def __init__(
        self,
        job_type: str,
        job_status: str,
        waypoints: Iterable[Any] | None,
        mission_state: Any | None = None,
        job_priority: int = NORMAL,
        path_obj: Any | None = None,
        job_id: Optional[int] = None,
    ) -> None:
        self.job_type = job_type
        self.job_status = job_status
        self.waypoints = list(waypoints) if waypoints is not None else []
        self.mission_state = mission_state
        self.job_priority = int(job_priority)
        self.path_obj = path_obj
        self.last_waypoint = 1
        self.upload_try_count = 0
        self.job_id = job_id if job_id is not None else self._next_job_id()
        self.start = self.waypoints[0] if self.waypoints else None
        self.end = self.waypoints[-1] if self.waypoints else None

    def _next_job_id(self) -> int:
        if self.mission_state is not None and hasattr(self.mission_state, "jobIDCounter"):
            job_id = self.mission_state.jobIDCounter
            self.mission_state.jobIDCounter += 1
            return job_id
        job_id = Job._local_id_counter
        Job._local_id_counter += 1
        return job_id

    @property
    def status(self) -> str:
        return self.job_status

    @status.setter
    def status(self, value: str) -> None:
        self.job_status = value

    def __lt__(self, other: "Job") -> bool:
        # Compare jobs based on their priority sorting from high to low since using minheap
        return self.job_priority > other.job_priority
