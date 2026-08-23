from enum import Enum


class ActivityType(str, Enum):
    CYCLING = "cycling"
    HIKING = "hiking"

    @property
    def osmnx_network_type(self) -> str:
        return "bike" if self is ActivityType.CYCLING else "walk"
