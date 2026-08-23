from dataclasses import dataclass, field
from pathlib import Path

from nd_route_finder.domain.geo_point import GeoPoint


@dataclass(slots=True)
class Track:
    name: str
    segments: list[list[GeoPoint]]
    source: Path | None = None
    distance_m: float = 0.0
    max_grade_percent: float | None = None
    metadata: dict[str, str] = field(default_factory=dict)
