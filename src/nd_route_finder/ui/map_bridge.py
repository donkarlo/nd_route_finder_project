from collections.abc import Callable

from PySide6.QtCore import QObject, Slot


class MapBridge(QObject):
    def __init__(
        self,
        start_selected: Callable[[float, float], None],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._start_selected = start_selected

    @Slot(float, float)
    def setStart(self, latitude: float, longitude: float) -> None:
        self._start_selected(latitude, longitude)
