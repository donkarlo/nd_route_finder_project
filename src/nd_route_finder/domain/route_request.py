from dataclasses import dataclass
from pathlib import Path

from nd_route_finder.domain.activity_type import ActivityType


@dataclass(slots=True, frozen=True)
class RouteRequest:
    gpx_root: Path
    activity: ActivityType
    start_latitude: float
    start_longitude: float
    target_distance_km: float
    max_grade_percent: float
    output_gpx: Path
    dem_path: Path | None = None

    @property
    def target_distance_m(self) -> float:
        return self.target_distance_km * 1000.0

    @property
    def graph_radius_m(self) -> float:
        return max(1500.0, min(12000.0, self.target_distance_m * 0.36))
