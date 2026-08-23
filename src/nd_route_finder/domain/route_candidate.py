from dataclasses import dataclass, field

from nd_route_finder.domain.geo_point import GeoPoint


@dataclass(slots=True)
class RouteCandidate:
    nodes: list[int]
    distance_m: float
    overlap_ratio: float
    base_score: float
    max_grade_percent: float | None = None
    points: list[GeoPoint] = field(default_factory=list)
