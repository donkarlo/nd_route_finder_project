from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from nd_route_finder.domain.activity_type import ActivityType
from nd_route_finder.domain.route_request import RouteRequest
from nd_route_finder.domain.track import Track
from nd_route_finder.ui.map_bridge import MapBridge
from nd_route_finder.ui.map_document_store import MapDocumentStore
from nd_route_finder.ui.map_html_builder import MapHtmlBuilder
from nd_route_finder.ui.route_worker import RouteWorker


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._worker: RouteWorker | None = None
        self._map_builder = MapHtmlBuilder()
        self._map_store = MapDocumentStore()
        self.setWindowTitle("nd_route_finder")
        self.resize(1280, 820)

        self._gpx_root = QLineEdit(str(Path.home()))
        self._dem_path = QLineEdit("")
        self._output_path = QLineEdit(str(Path.home() / "generated_round_trip.gpx"))

        self._activity = QComboBox()
        self._activity.addItem("Cycling", ActivityType.CYCLING.value)
        self._activity.addItem("Hiking", ActivityType.HIKING.value)

        self._latitude = QDoubleSpinBox()
        self._latitude.setRange(-90.0, 90.0)
        self._latitude.setDecimals(7)
        self._latitude.setValue(47.0707)

        self._longitude = QDoubleSpinBox()
        self._longitude.setRange(-180.0, 180.0)
        self._longitude.setDecimals(7)
        self._longitude.setValue(15.4395)

        self._distance = QDoubleSpinBox()
        self._distance.setRange(1.0, 120.0)
        self._distance.setDecimals(1)
        self._distance.setSuffix(" km")
        self._distance.setValue(20.0)

        self._max_grade = QDoubleSpinBox()
        self._max_grade.setRange(1.0, 40.0)
        self._max_grade.setDecimals(1)
        self._max_grade.setSuffix(" %")
        self._max_grade.setValue(12.0)

        self._slope_note = QLabel(
            "Slope is always checked. If no local DEM is selected, Copernicus GLO-30 tiles are downloaded once and cached automatically."
        )
        self._slope_note.setWordWrap(True)

        self._generate = QPushButton("Generate route")
        self._status = QLabel("Click the map to choose the start point.")
        self._status.setWordWrap(True)

        # OSM tile servers require native applications to identify themselves
        # with a non-generic HTTP User-Agent. QWebEngineView uses the default
        # profile unless another profile is explicitly supplied.
        web_profile = QWebEngineProfile.defaultProfile()
        web_profile.setHttpUserAgent(
            "nd_route_finder/0.8 (PySide6 QtWebEngine desktop route planner)"
        )
        self._web = QWebEngineView()
        self._web.settings().setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls,
            True,
        )

        self._map_bridge = MapBridge(self._map_start_selected, self)
        self._web_channel = QWebChannel(self._web.page())
        self._web_channel.registerObject("bridge", self._map_bridge)
        self._web.page().setWebChannel(self._web_channel)
        self._show_selector_map()

        self._controls = QWidget()
        form = QFormLayout(self._controls)
        form.addRow(
            "GPX root folder",
            self._path_row(self._gpx_root, self._choose_gpx_root, "Browse"),
        )
        form.addRow("Activity", self._activity)
        form.addRow("Start latitude", self._latitude)
        form.addRow("Start longitude", self._longitude)
        form.addRow("Target distance", self._distance)
        form.addRow("Maximum slope", self._max_grade)
        form.addRow(
            "DEM / GeoTIFF (optional override)",
            self._path_row(self._dem_path, self._choose_dem, "Browse"),
        )
        form.addRow(
            "Output GPX",
            self._path_row(self._output_path, self._choose_output, "Save as"),
        )

        left_layout = QVBoxLayout()
        left_layout.addWidget(self._controls)
        left_layout.addWidget(self._slope_note)
        left_layout.addWidget(self._generate)
        left_layout.addWidget(self._status)
        left_layout.addStretch(1)
        left = QWidget()
        left.setLayout(left_layout)
        left.setMinimumWidth(340)
        left.setMaximumWidth(460)

        splitter = QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(self._web)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([360, 920])
        self.setCentralWidget(splitter)

        self._generate.clicked.connect(self._start_generation)

    def _path_row(
        self,
        line_edit: QLineEdit,
        callback: Callable[[], None],
        label: str,
    ) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        button = QPushButton(label)
        button.clicked.connect(callback)
        layout.addWidget(line_edit, 1)
        layout.addWidget(button)
        return widget

    def _show_selector_map(self) -> None:
        html = self._map_builder.build_selector(
            self._latitude.value(),
            self._longitude.value(),
        )
        self._load_map_html(html)

    def _load_map_html(self, html: str) -> None:
        map_path = self._map_store.write(html)
        self._web.load(QUrl.fromLocalFile(str(map_path)))

    def _map_start_selected(self, latitude: float, longitude: float) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        self._latitude.setValue(latitude)
        self._longitude.setValue(longitude)
        self._status.setText(f"Start selected: {latitude:.6f}, {longitude:.6f}")

    def _choose_gpx_root(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "Select GPX root folder",
            self._gpx_root.text(),
        )
        if selected:
            self._gpx_root.setText(selected)
            self._output_path.setText(str(Path(selected) / "generated_round_trip.gpx"))

    def _choose_dem(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Select elevation raster",
            self._dem_path.text() or str(Path.home()),
            "Raster (*.tif *.tiff);;All files (*)",
        )
        if selected:
            self._dem_path.setText(selected)

    def _choose_output(self) -> None:
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "Save generated GPX",
            self._output_path.text(),
            "GPX (*.gpx)",
        )
        if selected:
            self._output_path.setText(
                selected if selected.lower().endswith(".gpx") else selected + ".gpx"
            )

    def _start_generation(self) -> None:
        gpx_root = Path(self._gpx_root.text()).expanduser().resolve()
        output = Path(self._output_path.text()).expanduser().resolve()
        if output.suffix.lower() != ".gpx":
            output = output.with_suffix(".gpx")
        self._output_path.setText(str(output))
        dem_text = self._dem_path.text().strip()
        dem = Path(dem_text).expanduser().resolve() if dem_text else None

        if not gpx_root.is_dir():
            QMessageBox.warning(self, "Invalid input", "Choose an existing GPX root folder.")
            return
        if dem is not None and not dem.is_file():
            QMessageBox.warning(self, "Invalid input", "The selected DEM file does not exist.")
            return

        activity_data = str(self._activity.currentData())
        request = RouteRequest(
            gpx_root=gpx_root,
            activity=ActivityType(activity_data),
            start_latitude=self._latitude.value(),
            start_longitude=self._longitude.value(),
            target_distance_km=self._distance.value(),
            max_grade_percent=self._max_grade.value(),
            output_gpx=output,
            dem_path=dem,
        )

        self._controls.setEnabled(False)
        self._web.setEnabled(False)
        self._generate.setEnabled(False)
        self._status.setText(f"Starting … Output is fixed to: {output}")
        self._worker = RouteWorker(request)
        self._worker.status_changed.connect(self._status.setText)
        self._worker.succeeded.connect(self._generation_succeeded)
        self._worker.failed.connect(self._generation_failed)
        self._worker.finished.connect(self._generation_finished)
        self._worker.start()

    def _generation_succeeded(self, result: object) -> None:
        if not isinstance(result, tuple) or len(result) != 4:
            self._generation_failed("Unexpected route generation result.")
            return
        previous_tracks, generated, output, html = result
        if not isinstance(previous_tracks, list) or not isinstance(generated, Track):
            self._generation_failed("Unexpected route generation result types.")
            return
        if not isinstance(output, Path):
            self._generation_failed("Unexpected output path type.")
            return
        if not output.is_file() or output.stat().st_size <= 0:
            self._generation_failed(f"GPX was not found on disk after saving: {output}")
            return

        self._output_path.setText(str(output))
        self._load_map_html(str(html))
        if generated.max_grade_percent is None:
            self._generation_failed("Internal error: slope was not evaluated.")
            return
        slope_text = f"max slope {generated.max_grade_percent:.1f}%"
        size_kib = output.stat().st_size / 1024.0
        self._status.setText(
            f"Done — {generated.distance_m / 1000.0:.2f} km, {slope_text}, "
            f"{len(previous_tracks)} previous track(s). GPX verified: {output} "
            f"({size_kib:.1f} KiB)"
        )

    def _generation_failed(self, message: str) -> None:
        self._status.setText("Failed")
        QMessageBox.critical(self, "Route generation failed", message)

    def _generation_finished(self) -> None:
        self._controls.setEnabled(True)
        self._web.setEnabled(True)
        self._generate.setEnabled(True)
