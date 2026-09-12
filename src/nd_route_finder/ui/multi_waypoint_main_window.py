import json
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from nd_route_finder.domain.activity_type import ActivityType
from nd_route_finder.domain.geo_point import GeoPoint
from nd_route_finder.domain.multi_waypoint_route_request import MultiWaypointRouteRequest
from nd_route_finder.domain.track import Track
from nd_route_finder.ui.main_window import MainWindow
from nd_route_finder.ui.multi_waypoint_map_bridge import MultiWaypointMapBridge
from nd_route_finder.ui.multi_waypoint_map_html_builder import MultiWaypointMapHtmlBuilder
from nd_route_finder.ui.multi_waypoint_route_worker import MultiWaypointRouteWorker


class MultiWaypointMainWindow(MainWindow):
    """Adds optional ordered intermediate points while retaining MainWindow behavior."""

    _WAYPOINT_DATA_ROLE = int(Qt.ItemDataRole.UserRole)

    def __init__(self) -> None:
        super().__init__()

        self._map_builder = MultiWaypointMapHtmlBuilder()

        self._map_action = QComboBox()
        self._map_action.addItem("Set start point", "start")
        self._map_action.addItem("Add intermediate point", "waypoint")

        self._waypoint_list = QListWidget()
        self._waypoint_list.setMinimumHeight(120)
        self._waypoint_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self._waypoint_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self._waypoint_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

        self._remove_waypoint = QPushButton("Remove selected")
        self._clear_waypoints = QPushButton("Clear")
        buttons = QWidget()
        buttons_layout = QHBoxLayout(buttons)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        buttons_layout.addWidget(self._remove_waypoint)
        buttons_layout.addWidget(self._clear_waypoints)

        waypoint_widget = QWidget()
        waypoint_layout = QVBoxLayout(waypoint_widget)
        waypoint_layout.setContentsMargins(0, 0, 0, 0)
        hint = QLabel(
            "Optional. Add points by map click or search, then drag them here to change route order."
        )
        hint.setWordWrap(True)
        waypoint_layout.addWidget(hint)
        waypoint_layout.addWidget(self._waypoint_list)
        waypoint_layout.addWidget(buttons)

        form = self._controls.layout()
        if not isinstance(form, QFormLayout):
            raise RuntimeError("Unexpected controls layout; expected QFormLayout.")
        form.addRow("Map / search action", self._map_action)
        form.addRow("Intermediate points", waypoint_widget)

        # Replace the original two-method bridge with an extended bridge while
        # keeping the original setStart method contract intact.
        self._web_channel.deregisterObject(self._map_bridge)
        self._map_bridge = MultiWaypointMapBridge(
            self._map_start_selected,
            self._map_point_selected,
            self,
        )
        self._web_channel.registerObject("bridge", self._map_bridge)
        self._web.page().setWebChannel(self._web_channel)

        self._map_action.currentIndexChanged.connect(self._selection_mode_changed)
        self._web.loadFinished.connect(self._map_loaded)
        self._remove_waypoint.clicked.connect(self._remove_selected_waypoint)
        self._clear_waypoints.clicked.connect(self._clear_all_waypoints)
        self._waypoint_list.model().rowsMoved.connect(self._waypoint_rows_moved)

        self._show_selector_map()
        self._selection_mode_changed()

    def _show_selector_map(self) -> None:
        self._prepare_map_builder()
        html = self._map_builder.build_selector(
            self._latitude.value(),
            self._longitude.value(),
        )
        self._load_map_html(html)

    def _prepare_map_builder(self) -> None:
        if isinstance(self._map_builder, MultiWaypointMapHtmlBuilder):
            self._map_builder.set_waypoints(self._waypoints())

    def _apply_selection_mode_to_map(self) -> None:
        mode = str(self._map_action.currentData() or "start")
        self._web.page().runJavaScript(
            f"window.ndSetSelectionMode && window.ndSetSelectionMode({json.dumps(mode)});"
        )

    def _selection_mode_changed(self, *_: object) -> None:
        mode = str(self._map_action.currentData() or "start")
        self._apply_selection_mode_to_map()
        if mode == "waypoint":
            self._status.setText(
                "Add intermediate points by clicking the map or choosing a search result."
            )
        else:
            self._status.setText("Map/search selection now sets the start point.")

    def _map_loaded(self, ok: bool) -> None:
        if not ok:
            return
        self._apply_selection_mode_to_map()
        self._sync_waypoint_markers()

    def _map_point_selected(self, latitude: float, longitude: float, label: str) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        item = QListWidgetItem()
        clean_label = " ".join(label.split())
        item.setData(
            self._WAYPOINT_DATA_ROLE,
            (float(latitude), float(longitude), clean_label),
        )
        self._waypoint_list.addItem(item)
        self._refresh_waypoint_texts()
        self._sync_waypoint_markers()
        self._status.setText(
            f"Intermediate point added: {latitude:.6f}, {longitude:.6f}. "
            "Drag items in the left panel to change their order."
        )

    def _remove_selected_waypoint(self) -> None:
        row = self._waypoint_list.currentRow()
        if row < 0:
            return
        self._waypoint_list.takeItem(row)
        self._refresh_waypoint_texts()
        self._sync_waypoint_markers()

    def _clear_all_waypoints(self) -> None:
        self._waypoint_list.clear()
        self._sync_waypoint_markers()
        self._status.setText("Intermediate points cleared; original one-start-point mode is active.")

    def _waypoint_rows_moved(self, *_: object) -> None:
        QTimer.singleShot(0, self._after_waypoint_reorder)

    def _after_waypoint_reorder(self) -> None:
        self._refresh_waypoint_texts()
        self._sync_waypoint_markers()
        self._status.setText("Intermediate point order updated.")

    def _waypoints(self) -> tuple[GeoPoint, ...]:
        points: list[GeoPoint] = []
        for index in range(self._waypoint_list.count()):
            value = self._waypoint_list.item(index).data(self._WAYPOINT_DATA_ROLE)
            if not isinstance(value, (tuple, list)) or len(value) < 2:
                continue
            points.append(GeoPoint(float(value[0]), float(value[1])))
        return tuple(points)

    def _refresh_waypoint_texts(self) -> None:
        for index in range(self._waypoint_list.count()):
            item = self._waypoint_list.item(index)
            value = item.data(self._WAYPOINT_DATA_ROLE)
            if not isinstance(value, (tuple, list)) or len(value) < 2:
                continue
            latitude = float(value[0])
            longitude = float(value[1])
            label = str(value[2]) if len(value) >= 3 else ""
            suffix = f" — {label}" if label else ""
            item.setText(
                f"{index + 1}. {latitude:.6f}, {longitude:.6f}{suffix}"
            )

    def _sync_waypoint_markers(self) -> None:
        points = [[point.latitude, point.longitude] for point in self._waypoints()]
        payload = json.dumps(points, separators=(",", ":"))
        self._web.page().runJavaScript(
            f"window.ndSyncWaypoints && window.ndSyncWaypoints({payload});"
        )

    def _start_generation(self) -> None:
        gpx_root = Path(self._gpx_root.text()).expanduser().resolve()
        output = Path(self._output_path.text()).expanduser().resolve()
        if output.suffix.lower() != ".gpx":
            output = output.with_suffix(".gpx")
        self._output_path.setText(str(output))
        dem_text = self._dem_path.text().strip()
        dem: Path | None = None
        if dem_text:
            dem = Path(dem_text).expanduser().resolve()

        if not gpx_root.is_dir():
            QMessageBox.warning(self, "Invalid input", "Choose an existing GPX root folder.")
            return
        if dem is not None and not dem.is_file():
            QMessageBox.warning(self, "Invalid input", "The selected DEM file does not exist.")
            return

        activity_data = str(self._activity.currentData())
        request = MultiWaypointRouteRequest(
            gpx_root=gpx_root,
            activity=ActivityType(activity_data),
            start_latitude=self._latitude.value(),
            start_longitude=self._longitude.value(),
            target_distance_km=self._distance.value(),
            max_grade_percent=self._max_grade.value(),
            output_gpx=output,
            dem_path=dem,
            waypoints=self._waypoints(),
        )

        self._elevation_profile.clear()
        self._slope_profile.clear()
        self._profile_splitter.hide()
        self._profile_hover_left()

        self._controls.setEnabled(False)
        self._web.setEnabled(False)
        self._load_gpx.setEnabled(False)
        self._generate.setEnabled(False)
        point_text = (
            f" with {len(request.waypoints)} ordered intermediate point(s)"
            if request.waypoints
            else ""
        )
        self._status.setText(f"Starting circular route{point_text} … Output: {output}")
        self._worker = MultiWaypointRouteWorker(request)
        self._worker.status_changed.connect(self._status.setText)
        self._worker.succeeded.connect(self._generation_succeeded)
        self._worker.failed.connect(self._generation_failed)
        self._worker.finished.connect(self._generation_finished)
        self._worker.start()

    def _generation_succeeded(self, result: object) -> None:
        if isinstance(result, tuple) and len(result) == 4:
            previous_tracks, generated, output, _html = result
            if isinstance(previous_tracks, list) and isinstance(generated, Track):
                self._prepare_map_builder()
                enhanced_html = self._map_builder.build_routes(previous_tracks, generated)
                result = (previous_tracks, generated, output, enhanced_html)
        super()._generation_succeeded(result)
        if isinstance(result, tuple) and len(result) == 4:
            generated = result[1]
            if (
                isinstance(generated, Track)
                and generated.metadata.get("constraint_fallback") == "true"
                and generated.max_grade_percent is not None
            ):
                self._status.setText(
                    f"Done — closest available GPX: {generated.distance_m / 1000.0:.2f} km, "
                    f"max slope {generated.max_grade_percent:.1f}%. "
                    f"Exact distance/slope combination was not available."
                )
