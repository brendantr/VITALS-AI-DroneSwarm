"""Pathing cost map objects for storing per-drone planned paths."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DronePath:
    drone_id: int
    path_points: list[tuple[float, float]] = field(default_factory=list)


@dataclass
class PathingCostMap:
    terrain_tile_id: str | None = None
    source: str = "pathing"
    drone_paths: dict[int, DronePath] = field(default_factory=dict)

    def set_drone_path(self, drone_id: int, path_points: list[tuple[float, float]]) -> None:
        self.drone_paths[int(drone_id)] = DronePath(drone_id=int(drone_id), path_points=list(path_points))

    def clone(self) -> "PathingCostMap":
        copied = PathingCostMap(terrain_tile_id=self.terrain_tile_id, source=self.source)
        for drone_id, drone_path in self.drone_paths.items():
            copied.set_drone_path(drone_id, list(drone_path.path_points))
        return copied

    @classmethod
    def from_assignments(
        cls,
        assignments: dict[int, list],
        terrain_tile_id: str | None = None,
        source: str = "pathing",
    ) -> "PathingCostMap":
        cost_map = cls(terrain_tile_id=terrain_tile_id, source=source)
        for drone_id, points in assignments.items():
            as_tuples = [(float(point.x), float(point.y)) for point in points]
            cost_map.set_drone_path(drone_id, as_tuples)
        return cost_map

    @classmethod
    def from_cell_paths(
        cls,
        cell_paths: dict[int, list[tuple[int, int]]],
        terrain_tile_id: str | None = None,
        source: str = "pathing",
    ) -> "PathingCostMap":
        cost_map = cls(terrain_tile_id=terrain_tile_id, source=source)
        for drone_id, cells in cell_paths.items():
            as_tuples = [(float(c), float(r)) for (r, c) in cells]
            cost_map.set_drone_path(drone_id, as_tuples)
        return cost_map
