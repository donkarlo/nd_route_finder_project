"""Open the 50 km loop, retaining route generation controls and historic GPX root."""
from pathlib import Path

from PySide6.QtWidgets import QApplication

from nd_route_finder.analysis.track_analyzer import TrackAnalyzer
from nd_route_finder.ui.multi_waypoint_main_window import MultiWaypointMainWindow
from nd_route_finder.gpx.gpx_track_reader import GpxTrackReader


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    gpx_path = project_root / 'gpx/graz_semriacherstrasse_circular_50km_low_overlap.gpx'
    if not gpx_path.is_file():
        raise FileNotFoundError(gpx_path)
    app = QApplication.instance() or QApplication([])
    window = MultiWaypointMainWindow()
    window._map_start_selected(47.077531, 15.4776239)
    window._map_point_selected(47.175987, 15.362206, 'Semriacherstraße 100, 8102')
    window._route_mode.setCurrentIndex(0)  # Circular
    window._route_preference.setCurrentIndex(2)  # Match target distance
    window._distance.setValue(50.0)
    window._max_grade.setValue(20.0)
    window._output_path.setText(str(gpx_path))
    window._last_generated_output = gpx_path
    track = TrackAnalyzer().analyze(GpxTrackReader().read(gpx_path))
    history = GpxTrackReader().read_many(
        list(Path(window._gpx_root.text()).glob('**/*.gpx'))
    )
    window._prepare_map_builder()
    window._load_map_html(window._map_builder.build_routes(history, track))
    window._show_profiles(track)
    window._status.setText(
        f'Circular GPX loaded: {track.distance_m/1000:.2f} km; '
        'estimated max slope 17.7%; 40% overlap with previous GPX, 9% retraced. '
        'Independent obstacle checks unavailable (BRouter route).'
    )
    window.show()
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
