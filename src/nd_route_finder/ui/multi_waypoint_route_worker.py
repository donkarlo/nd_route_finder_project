from PySide6.QtCore import QThread, Signal

from nd_route_finder.application.multi_waypoint_route_finder_application import (
    MultiWaypointRouteFinderApplication,
)
from nd_route_finder.domain.route_request import RouteRequest


class MultiWaypointRouteWorker(QThread):
    status_changed = Signal(str)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, request: RouteRequest) -> None:
        super().__init__()
        self._request = request

    def run(self) -> None:
        try:
            result = MultiWaypointRouteFinderApplication().run(
                self._request,
                status=self.status_changed.emit,
            )
            self.succeeded.emit(result)
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")
