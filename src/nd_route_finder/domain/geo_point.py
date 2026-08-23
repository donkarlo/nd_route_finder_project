from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class GeoPoint:
    latitude: float
    longitude: float
    elevation: float | None = None
