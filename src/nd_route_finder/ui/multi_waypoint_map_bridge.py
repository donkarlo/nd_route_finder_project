from collections.abc import Callable

from PySide6.QtCore import QObject, Slot


class MultiWaypointMapBridge(QObject):
    def __init__(
        self,
        start_selected: Callable[[float, float], None],
        point_selected: Callable[[float, float, str], None],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._start_selected = start_selected
        self._point_selected = point_selected

    @Slot(float, float)
    def setStart(self, latitude: float, longitude: float) -> None:
        self._start_selected(latitude, longitude)

    @Slot(float, float, str)
    def addPoint(self, latitude: float, longitude: float, label: str) -> None:
        self._point_selected(latitude, longitude, label)
