import bisect
import math

from PySide6.QtCore import QPointF, QRectF, Signal, Qt
from PySide6.QtGui import QMouseEvent, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from nd_route_finder.domain.geo_point import GeoPoint
from nd_route_finder.domain.track import Track


class ProfileChartWidget(QWidget):
    point_hovered = Signal(float, float, str)
    hover_left = Signal()

    _EARTH_RADIUS_M = 6_371_008.8
    _SLOPE_HALF_WINDOW_M = 50.0

    def __init__(self, title: str, value_kind: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        if value_kind not in {"elevation", "slope"}:
            raise ValueError(f"Unsupported profile value kind: {value_kind}")
        self._title = title
        self._value_kind = value_kind
        self._points: list[GeoPoint] = []
        self._distances_m: list[float] = []
        self._values: list[float] = []
        self._hover_index: int | None = None
        self.setMouseTracking(True)
        self.setMinimumHeight(150)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def clear(self) -> None:
        self._points = []
        self._distances_m = []
        self._values = []
        self._hover_index = None
        self.update()

    def set_track(self, track: Track) -> None:
        points = [point for segment in track.segments for point in segment]
        if len(points) < 2:
            self.clear()
            return

        distances_m = [0.0]
        for first, second in zip(points, points[1:]):
            distances_m.append(distances_m[-1] + self._distance(first, second))

        if distances_m[-1] <= 0.0:
            self.clear()
            return

        elevations: list[float] = []
        for point in points:
            if point.elevation is None or not math.isfinite(point.elevation):
                self.clear()
                return
            elevations.append(float(point.elevation))

        self._points = points
        self._distances_m = distances_m
        if self._value_kind == "elevation":
            self._values = elevations
        else:
            self._values = self._centered_slopes(distances_m, elevations)
        self._hover_index = None
        self.update()

    def paintEvent(self, event: object) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        palette = self.palette()
        painter.fillRect(self.rect(), palette.base())

        painter.setPen(palette.text().color())
        title_font = painter.font()
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.drawText(12, 20, self._title)
        title_font.setBold(False)
        painter.setFont(title_font)

        plot = self._plot_rect()
        if not self._values or len(self._values) != len(self._distances_m):
            painter.setPen(palette.mid().color())
            painter.drawText(plot, Qt.AlignmentFlag.AlignCenter, "Generate a route to see this profile.")
            return

        y_min, y_max = self._y_range()
        x_max = self._distances_m[-1]
        if x_max <= 0.0 or y_max <= y_min:
            return

        grid_pen = QPen(palette.midlight().color())
        grid_pen.setWidthF(1.0)
        axis_pen = QPen(palette.mid().color())
        axis_pen.setWidthF(1.0)
        text_color = palette.text().color()

        painter.setPen(grid_pen)
        x_ticks = 6
        for tick in range(x_ticks + 1):
            ratio = tick / x_ticks
            x = plot.left() + ratio * plot.width()
            painter.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
            painter.setPen(text_color)
            km = x_max * ratio / 1000.0
            label = f"{km:.0f}" if km >= 10.0 else f"{km:.1f}"
            painter.drawText(
                QRectF(x - 28.0, plot.bottom() + 3.0, 56.0, 18.0),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                label,
            )
            painter.setPen(grid_pen)

        y_ticks = 5
        for tick in range(y_ticks + 1):
            ratio = tick / y_ticks
            y = plot.bottom() - ratio * plot.height()
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            value = y_min + ratio * (y_max - y_min)
            painter.setPen(text_color)
            painter.drawText(
                QRectF(2.0, y - 9.0, plot.left() - 7.0, 18.0),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                self._axis_value(value),
            )
            painter.setPen(grid_pen)

        if self._value_kind == "slope" and y_min < 0.0 < y_max:
            zero_y = self._value_to_y(0.0, plot, y_min, y_max)
            zero_pen = QPen(palette.mid().color())
            zero_pen.setWidthF(1.5)
            painter.setPen(zero_pen)
            painter.drawLine(QPointF(plot.left(), zero_y), QPointF(plot.right(), zero_y))

        painter.setPen(axis_pen)
        painter.drawRect(plot)
        painter.setPen(text_color)
        painter.drawText(
            QRectF(plot.left(), plot.bottom() + 20.0, plot.width(), 18.0),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            "Distance (km)",
        )

        path = QPainterPath()
        for index, (distance_m, value) in enumerate(zip(self._distances_m, self._values)):
            x = plot.left() + (distance_m / x_max) * plot.width()
            y = self._value_to_y(value, plot, y_min, y_max)
            point = QPointF(x, y)
            if index == 0:
                path.moveTo(point)
            else:
                path.lineTo(point)

        route_pen = QPen(palette.highlight().color())
        route_pen.setWidthF(1.8)
        painter.setPen(route_pen)
        painter.drawPath(path)

        if self._hover_index is not None:
            index = min(self._hover_index, len(self._values) - 1)
            distance_m = self._distances_m[index]
            value = self._values[index]
            x = plot.left() + (distance_m / x_max) * plot.width()
            y = self._value_to_y(value, plot, y_min, y_max)

            cross_pen = QPen(palette.text().color())
            cross_pen.setWidthF(1.0)
            cross_pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(cross_pen)
            painter.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))

            painter.setPen(QPen(palette.text().color(), 2.0))
            painter.setBrush(palette.base())
            painter.drawEllipse(QPointF(x, y), 4.0, 4.0)

            info = self._hover_text(index)
            painter.setPen(text_color)
            painter.drawText(
                QRectF(plot.left() + 8.0, plot.top() + 6.0, plot.width() - 16.0, 20.0),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                info,
            )

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self._values:
            return
        plot = self._plot_rect()
        position = event.position()
        if not plot.contains(position):
            if self._hover_index is not None:
                self._hover_index = None
                self.update()
                self.hover_left.emit()
            return

        ratio = min(1.0, max(0.0, (position.x() - plot.left()) / max(1.0, plot.width())))
        target_distance = ratio * self._distances_m[-1]
        index = self._nearest_index(target_distance)
        if index == self._hover_index:
            return

        self._hover_index = index
        self.update()
        point = self._points[index]
        self.point_hovered.emit(
            point.latitude,
            point.longitude,
            self._hover_text(index),
        )

    def leaveEvent(self, event: object) -> None:
        del event
        if self._hover_index is not None:
            self._hover_index = None
            self.update()
        self.hover_left.emit()

    def _plot_rect(self) -> QRectF:
        return QRectF(
            58.0,
            30.0,
            max(1.0, self.width() - 72.0),
            max(1.0, self.height() - 75.0),
        )

    def _y_range(self) -> tuple[float, float]:
        low = min(self._values)
        high = max(self._values)
        if self._value_kind == "slope":
            bound = max(1.0, abs(low), abs(high)) * 1.08
            return -bound, bound
        span = high - low
        padding = max(3.0, span * 0.08)
        return low - padding, high + padding

    def _axis_value(self, value: float) -> str:
        if self._value_kind == "elevation":
            return f"{value:.0f} m"
        return f"{value:.0f}%"

    def _hover_text(self, index: int) -> str:
        distance_km = self._distances_m[index] / 1000.0
        value = self._values[index]
        if self._value_kind == "elevation":
            return f"{distance_km:.2f} km · {value:.1f} m"
        return f"{distance_km:.2f} km · {value:+.1f}% slope"

    def _value_to_y(self, value: float, plot: QRectF, y_min: float, y_max: float) -> float:
        ratio = (value - y_min) / (y_max - y_min)
        return plot.bottom() - ratio * plot.height()

    def _nearest_index(self, target_distance_m: float) -> int:
        index = bisect.bisect_left(self._distances_m, target_distance_m)
        if index <= 0:
            return 0
        if index >= len(self._distances_m):
            return len(self._distances_m) - 1
        before = self._distances_m[index - 1]
        after = self._distances_m[index]
        return index - 1 if target_distance_m - before <= after - target_distance_m else index

    def _centered_slopes(
        self,
        distances_m: list[float],
        elevations_m: list[float],
    ) -> list[float]:
        total = distances_m[-1]
        result: list[float] = []
        for index, center in enumerate(distances_m):
            left_target = max(0.0, center - self._SLOPE_HALF_WINDOW_M)
            right_target = min(total, center + self._SLOPE_HALF_WINDOW_M)
            left = self._nearest_distance_index(distances_m, left_target)
            right = self._nearest_distance_index(distances_m, right_target)

            if right <= left:
                left = max(0, index - 1)
                right = min(len(distances_m) - 1, index + 1)
            horizontal = distances_m[right] - distances_m[left]
            if horizontal <= 0.0:
                result.append(0.0)
                continue
            result.append((elevations_m[right] - elevations_m[left]) / horizontal * 100.0)
        return result

    def _nearest_distance_index(self, distances_m: list[float], target: float) -> int:
        index = bisect.bisect_left(distances_m, target)
        if index <= 0:
            return 0
        if index >= len(distances_m):
            return len(distances_m) - 1
        before = distances_m[index - 1]
        after = distances_m[index]
        return index - 1 if target - before <= after - target else index

    def _distance(self, first: GeoPoint, second: GeoPoint) -> float:
        lat1 = math.radians(first.latitude)
        lat2 = math.radians(second.latitude)
        dlat = lat2 - lat1
        dlon = math.radians(second.longitude - first.longitude)
        a = (
            math.sin(dlat / 2.0) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2.0) ** 2
        )
        a = min(1.0, max(0.0, a))
        return self._EARTH_RADIUS_M * 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
