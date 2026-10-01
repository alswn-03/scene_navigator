# 메인 타임라인 UI
# - 씬 마커 (클릭 시 씬 시작점으로 이동, hover 시 name tooltip)
# - 현재 재생 위치 / 재생 진행 색상
# - 줌, 좌우 이동 (드래그 / 트랙패드 가로 스크롤 / 하단 바)
# - 항상 보이는 하단 회색 바

import html
import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QToolTip, QWidget

from scene_data import Scene

GREEN = QColor("#36684f")
TRACK = QColor("#dfe5e1")
ORANGE = QColor("#e59d38")
LABEL = QColor("#87928d")
TICK = QColor("#c9d1cd")
MARKER_BORDER = QColor("#cdd6d1")
OVERVIEW_TRACK = QColor("#e6ebe8")
OVERVIEW_HANDLE = QColor("#a3ada8")

MIN_ZOOM = 1.0
MAX_ZOOM = 10.0

MARGIN = 22  # 좌우 여백 (끝 마커/라벨이 잘리지 않도록)
LABEL_Y = 12
BAR_Y = 48
OVERVIEW_Y = 90

BAR_WIDTH = 6
MARKER_RADIUS = 7
MARKER_HIT = 10  # 마커 클릭/hover 판정 반경(px)
DRAG_THRESHOLD = 4  # 이보다 적게 움직이면 클릭으로 간주

# 눈금 간격 후보(초)
TICK_STEPS = (
    1, 2, 5, 10, 15, 30,
    60, 120, 300, 600, 900, 1800,
    3600, 7200, 14400,
)


def format_clock(seconds: float, with_hours: bool) -> str:
    seconds = max(0, int(seconds))

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    if with_hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    return f"{minutes:02d}:{secs:02d}"


class TimelineWidget(QWidget):
    seek_requested = Signal(float)

    def __init__(self):
        super().__init__()

        self.duration = 0.0
        self.current_time = 0.0
        self.scenes: list[Scene] = []

        self.zoom = 1.0
        self.view_start = 0.0

        self._press: dict | None = None
        self._hover: int | None = None

        self.setMouseTracking(True)
        self.setMinimumHeight(104)

    # ------------------------------------------------------------
    # 좌표 변환
    # ------------------------------------------------------------

    @property
    def visible_duration(self) -> float:
        if self.duration <= 0:
            return 0.0

        return self.duration / self.zoom

    @property
    def view_end(self) -> float:
        return self.view_start + self.visible_duration

    def _track_width(self) -> float:
        return max(1.0, self.width() - MARGIN * 2)

    def _time_to_x(self, seconds: float) -> float | None:
        visible = self.visible_duration

        if visible <= 0:
            return None

        ratio = (seconds - self.view_start) / visible

        if ratio < -0.001 or ratio > 1.001:
            return None

        return MARGIN + ratio * self._track_width()

    def _x_to_time(self, x: float) -> float:
        ratio = (x - MARGIN) / self._track_width()
        ratio = max(0.0, min(1.0, ratio))

        return self.view_start + ratio * self.visible_duration

    # ------------------------------------------------------------
    # 상태 변경
    # ------------------------------------------------------------

    def set_duration(self, duration: float):
        duration = max(0.0, duration)

        if duration == self.duration:
            return

        self.duration = duration
        self._clamp_view()
        self.update()

    def set_current_time(self, seconds: float):
        previous = self.current_time
        self.current_time = max(0.0, seconds)

        # 재생(또는 외부 이동)으로 재생 위치가 화면 밖으로 나가면 화면을 따라 이동.
        # 사용자가 다른 구간을 둘러보는 중이면(이미 화면 밖이었다면) 건드리지 않는다.
        if (
            self.zoom > 1
            and self._press is None
            and self._in_view(previous)
            and not self._in_view(self.current_time)
        ):
            self.reveal(self.current_time)

        self.update()

    def set_scenes(self, scenes: list[Scene]):
        self.scenes = scenes
        self._hover = None
        self.update()

    def set_zoom(self, zoom: float):
        zoom = max(MIN_ZOOM, min(MAX_ZOOM, zoom))

        if self.duration <= 0:
            self.zoom = zoom
            return

        # 재생 위치가 보이면 그 위치를 고정점으로, 아니면 화면 중앙을 기준으로 확대
        if self._in_view(self.current_time):
            anchor = self.current_time
        else:
            anchor = self.view_start + self.visible_duration / 2

        ratio = (anchor - self.view_start) / self.visible_duration

        self.zoom = zoom
        self.view_start = anchor - ratio * self.visible_duration

        self._clamp_view()
        self.update()

    def reveal(self, seconds: float):
        """해당 시각이 화면 밖이면 화면을 옮겨서 보이게 한다."""

        if self.duration <= 0 or self._in_view(seconds):
            return

        if seconds > self.view_end:
            self.view_start = seconds - self.visible_duration * 0.1
        else:
            self.view_start = seconds - self.visible_duration * 0.9

        self._clamp_view()
        self.update()

    def _in_view(self, seconds: float) -> bool:
        return self.view_start <= seconds <= self.view_end

    def _clamp_view(self):
        if self.duration <= 0:
            self.view_start = 0.0
            return

        max_start = max(0.0, self.duration - self.visible_duration)
        self.view_start = min(max(0.0, self.view_start), max_start)

    # ------------------------------------------------------------
    # 그리기
    # ------------------------------------------------------------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self.duration > 0:
            self._paint_ticks(painter)

        self._paint_bar(painter)
        self._paint_markers(painter)
        self._paint_playhead(painter)
        self._paint_overview(painter)

    def _tick_step(self) -> float:
        # 라벨 사이가 최소 90px 이상 되는 가장 작은 간격
        per_second = self._track_width() / self.visible_duration

        for step in TICK_STEPS:
            if step * per_second >= 90:
                return step

        return TICK_STEPS[-1]

    def _paint_ticks(self, painter: QPainter):
        step = self._tick_step()
        with_hours = self.duration >= 3600

        painter.setFont(QFont(self.font().family(), 9))

        t = math.ceil(self.view_start / step) * step

        while t <= self.view_end + 1e-6:
            x = self._time_to_x(t)

            if x is not None:
                painter.setPen(LABEL)
                painter.drawText(
                    QRectF(x - 32, LABEL_Y - 8, 64, 16),
                    Qt.AlignmentFlag.AlignCenter,
                    format_clock(t, with_hours),
                )

                painter.setPen(QPen(TICK, 1))
                painter.drawLine(
                    QPointF(x, LABEL_Y + 11),
                    QPointF(x, LABEL_Y + 16),
                )

            t += step

    def _paint_bar(self, painter: QPainter):
        right = MARGIN + self._track_width()

        painter.setPen(
            QPen(TRACK, BAR_WIDTH, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        )
        painter.drawLine(QPointF(MARGIN, BAR_Y), QPointF(right, BAR_Y))

        if self.duration <= 0:
            return

        # 이미 재생된 구간
        progress = (self.current_time - self.view_start) / self.visible_duration
        progress = min(1.0, progress)

        if progress <= 0:
            return

        painter.setPen(
            QPen(GREEN, BAR_WIDTH, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        )
        painter.drawLine(
            QPointF(MARGIN, BAR_Y),
            QPointF(MARGIN + self._track_width() * progress, BAR_Y),
        )

    def _paint_markers(self, painter: QPainter):
        for index, scene in enumerate(self.scenes):
            x = self._time_to_x(scene.start_seconds)

            if x is None:
                continue

            radius = MARKER_RADIUS + (2 if index == self._hover else 0)

            # 그림자
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(0, 0, 0, 28))
            painter.drawEllipse(QPointF(x, BAR_Y + 1.5), radius + 0.5, radius + 0.5)

            painter.setBrush(QColor("#ffffff"))
            painter.setPen(
                QPen(GREEN if index == self._hover else MARKER_BORDER, 1)
            )
            painter.drawEllipse(QPointF(x, BAR_Y), radius, radius)

    def _paint_playhead(self, painter: QPainter):
        x = self._time_to_x(self.current_time)

        if x is None:
            return

        painter.setPen(
            QPen(ORANGE, 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        )
        painter.drawLine(QPointF(x, BAR_Y - 17), QPointF(x, BAR_Y + 17))

    def _overview_handle(self) -> tuple[float, float]:
        """하단 바에서 현재 보고 있는 범위의 (왼쪽 x, 너비)."""

        width = self._track_width()

        if self.duration <= 0:
            return MARGIN, width

        return (
            MARGIN + width * self.view_start / self.duration,
            width * self.visible_duration / self.duration,
        )

    def _paint_overview(self, painter: QPainter):
        width = self._track_width()

        # 전체 영상 범위 (항상 표시)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(OVERVIEW_TRACK)
        painter.drawRoundedRect(
            QRectF(MARGIN, OVERVIEW_Y - 2, width, 4), 2, 2
        )

        # 현재 보고 있는 범위
        left, handle_width = self._overview_handle()

        painter.setBrush(OVERVIEW_HANDLE)
        painter.drawRoundedRect(
            QRectF(left, OVERVIEW_Y - 3.5, handle_width, 7), 3.5, 3.5
        )

        # 전체 대비 재생 위치
        if self.duration > 0:
            x = MARGIN + width * min(1.0, self.current_time / self.duration)

            painter.setPen(
                QPen(ORANGE, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            )
            painter.drawLine(QPointF(x, OVERVIEW_Y - 7), QPointF(x, OVERVIEW_Y + 7))

    # ------------------------------------------------------------
    # 입력
    # ------------------------------------------------------------

    def _marker_at(self, x: float, y: float) -> int | None:
        if abs(y - BAR_Y) > 14:
            return None

        best = None
        best_distance = MARKER_HIT + 1

        for index, scene in enumerate(self.scenes):
            marker_x = self._time_to_x(scene.start_seconds)

            if marker_x is None:
                continue

            distance = abs(marker_x - x)

            if distance < best_distance:
                best = index
                best_distance = distance

        return best

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or self.duration <= 0:
            return

        x = event.position().x()
        y = event.position().y()

        if abs(y - OVERVIEW_Y) <= 12:
            self._begin_overview_drag(x)

        elif abs(y - BAR_Y) <= 26:
            self._press = {
                "kind": "bar",
                "x": x,
                "view": self.view_start,
                "moved": False,
            }

    def _begin_overview_drag(self, x: float):
        left, handle_width = self._overview_handle()

        # 핸들 밖을 누르면 그 위치가 화면 중앙이 되도록 이동
        if not left <= x <= left + handle_width:
            center = (x - MARGIN) / self._track_width() * self.duration
            self.view_start = center - self.visible_duration / 2
            self._clamp_view()
            left, _ = self._overview_handle()
            self.update()

        self._press = {"kind": "overview", "grab": x - left}
        self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        x = event.position().x()
        y = event.position().y()

        if self._press is None:
            self._update_hover(x, y, event.globalPosition().toPoint())
            return

        if self._press["kind"] == "overview":
            ratio = (x - self._press["grab"] - MARGIN) / self._track_width()
            self.view_start = ratio * self.duration
            self._clamp_view()
            self.update()
            return

        delta = x - self._press["x"]

        if not self._press["moved"]:
            # 확대 상태에서만 드래그 이동. 1x에서는 클릭으로만 동작.
            if abs(delta) < DRAG_THRESHOLD or self.zoom <= 1:
                return

            self._press["moved"] = True
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

        self.view_start = (
            self._press["view"]
            - delta / self._track_width() * self.visible_duration
        )
        self._clamp_view()
        self.update()

    def mouseReleaseEvent(self, event):
        press = self._press
        self._press = None

        if press is None or event.button() != Qt.MouseButton.LeftButton:
            return

        self.unsetCursor()

        # 드래그 없이 놓았으면 클릭 → 이동
        if press["kind"] == "bar" and not press["moved"]:
            x = event.position().x()
            marker = self._marker_at(x, event.position().y())

            if marker is not None:
                target = self.scenes[marker].start_seconds
            else:
                target = self._x_to_time(x)

            self.seek_requested.emit(max(0.0, min(self.duration, target)))

        self._update_hover(
            event.position().x(),
            event.position().y(),
            event.globalPosition().toPoint(),
        )

    def _update_hover(self, x: float, y: float, global_pos):
        marker = self._marker_at(x, y)

        if marker != self._hover:
            self._hover = marker
            self.update()

            if marker is None:
                QToolTip.hideText()

            else:
                scene = self.scenes[marker]
                text = html.escape(scene.start)

                if scene.name:
                    text = f"<b>{html.escape(scene.name)}</b><br>{text}"

                QToolTip.showText(global_pos, text, self)

        if abs(y - BAR_Y) <= 26 and self.duration > 0:
            self.setCursor(Qt.CursorShape.PointingHandCursor)

        elif abs(y - OVERVIEW_Y) <= 12 and self.zoom > 1:
            self.setCursor(Qt.CursorShape.OpenHandCursor)

        else:
            self.unsetCursor()

    def wheelEvent(self, event):
        # 트랙패드 가로 스크롤 (마우스 휠 세로 스크롤도 같은 방향으로 처리)
        pixel = event.pixelDelta()
        angle = event.angleDelta()

        dx = pixel.x() or angle.x() / 3
        dy = pixel.y() or angle.y() / 3
        delta = dx if abs(dx) >= abs(dy) else dy

        event.accept()

        if self.zoom <= 1 or delta == 0:
            return

        self.view_start -= delta / self._track_width() * self.visible_duration
        self._clamp_view()
        self.update()

    def leaveEvent(self, event):
        if self._hover is not None:
            self._hover = None
            self.update()

        if self._press is None:
            self.unsetCursor()
