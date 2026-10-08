# - 앱 실행 진입점
# - 전체 GUI 조립
# - 영상 선택 / 씬 데이터 선택
# - QuickTime 상태 업데이트
# - 줌 컨트롤 연결

import sys
import time
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QTimer, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPolygonF
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from files_dialog import FilesDialog
from quicktime_controller import QuickTimeController, QuickTimeWorker
from scene_data import load_scenes
import theme
from theme import c
from timeline_widget import MAX_ZOOM, MIN_ZOOM, TimelineWidget

# 타임라인에서 이동한 뒤 QuickTime을 자동 재생할지 여부
PLAY_AFTER_SEEK = True

# 화면 갱신 주기(ms). QuickTime 폴링 사이를 이 주기로 보간해서 부드럽게 표시한다.
UI_INTERVAL_MS = 33

ZOOM_STEP = 0.5

SPEEDS = (0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0)


def format_time(seconds: float) -> str:
    seconds = max(0, int(seconds))

    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


class TransportButton(QPushButton):
    """재생/일시정지(원형)와 이전/다음 씬 버튼."""

    def __init__(self, kind: str, size: int):
        super().__init__()

        self.kind = kind
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def set_kind(self, kind: str):
        self.kind = kind
        self.update()

    def _triangle(self, painter, x, cy, w, h, forward):
        if forward:
            points = [QPointF(x, cy - h / 2), QPointF(x, cy + h / 2), QPointF(x + w, cy)]
        else:
            points = [QPointF(x + w, cy - h / 2), QPointF(x + w, cy + h / 2), QPointF(x, cy)]

        painter.drawPolygon(QPolygonF(points))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)

        d = self.width()
        cx = cy = d / 2

        if self.kind in ("play", "pause"):
            color = c("accent_hover") if self.underMouse() else c("accent")

            if self.isDown():
                color = c("accent_press")

            # 부드러운 그림자
            painter.setBrush(c("accent", 40))
            painter.drawEllipse(QPointF(cx, cy + 3), d / 2 - 2, d / 2 - 2)

            painter.setBrush(color)
            painter.drawEllipse(QPointF(cx, cy), d / 2 - 2, d / 2 - 2)

            painter.setBrush(c("on_accent"))

            if self.kind == "play":
                w, h = d * 0.26, d * 0.32
                self._triangle(painter, cx - w / 2 + 1.5, cy, w, h, True)

            else:
                bar_w, bar_h, gap = d * 0.085, d * 0.30, d * 0.10

                for x in (cx - gap / 2 - bar_w, cx + gap / 2):
                    painter.drawRoundedRect(
                        QRectF(x, cy - bar_h / 2, bar_w, bar_h), 1.5, 1.5
                    )

            return

        painter.setBrush(c("transport_hover") if self.underMouse() else c("transport"))

        w, h = d * 0.2, d * 0.34
        forward = self.kind == "next"

        self._triangle(painter, cx - w, cy, w, h, forward)
        self._triangle(painter, cx, cy, w, h, forward)


class SceneNavigator(QMainWindow):

    def __init__(self):
        super().__init__()

        self.video_path: str | None = None
        self.scene_path: str | None = None
        self.scenes = []

        # QuickTime 상태 (폴링 결과 + 사이 구간 보간용)
        self._status = "no_app"
        self._base_time = 0.0
        self._base_at = time.monotonic()
        self._rate = 0.0
        self._duration = 0.0
        self._playing = False
        self._speed = 1.0  # 재생 배속 (일시정지 중에도 기억)
        self._issued = 0  # UI가 보낸 명령 수 (오래된 폴링 결과 무시용)
        self._last_shown = None

        self.theme_overridden = False

        self.setWindowTitle("Scene Navigator")
        self.resize(720, 240)
        self.setMinimumSize(600, 226)

        self.build_ui()

        self.files_dialog = FilesDialog(self)
        self.files_dialog.video_requested.connect(self.select_video)
        self.files_dialog.scenes_requested.connect(self.select_scene_file)

        self.controller = QuickTimeController()
        self.worker = QuickTimeWorker(self.controller, self)
        self.worker.state_changed.connect(self.on_state)
        self.worker.command_failed.connect(self.show_notice)
        self.worker.start()

        self.ui_timer = QTimer(self)
        self.ui_timer.timeout.connect(self.tick)
        self.ui_timer.start(UI_INTERVAL_MS)

    # ------------------------------------------------------------
    # UI
    # ------------------------------------------------------------

    def build_ui(self):
        root = QWidget()
        root.setObjectName("root")

        self.setCentralWidget(root)

        layout = QVBoxLayout(root)
        layout.setContentsMargins(24, 10, 24, 10)
        layout.setSpacing(0)

        # 상단: 파일 정보 + Files
        self.info_label = QLabel()
        self.info_label.setObjectName("info")

        files_button = QPushButton("Files")
        files_button.setObjectName("files")
        files_button.setCursor(Qt.CursorShape.PointingHandCursor)
        files_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        files_button.clicked.connect(self.open_files)

        # 오류 안내용 한 줄 (평소에는 숨김)
        self.info_label.hide()

        layout.addWidget(self.info_label)

        # 현재 시간 / 전체 길이
        self.time_label = QLabel("00:00:00")
        self.time_label.setObjectName("time")

        self.duration_label = QLabel("/ 00:00:00")
        self.duration_label.setObjectName("duration")

        # 숫자 폭 고정(tabular)으로 시간이 바뀔 때 글자가 흔들리지 않게
        try:
            font = self.time_label.font()
            font.setFeature(QFont.Tag("tnum"), 1)
            self.time_label.setFont(font)
        except Exception:
            pass

        time_row = QHBoxLayout()
        time_row.setSpacing(2)
        time_row.addWidget(self.time_label)
        time_row.addWidget(self.duration_label, 0, Qt.AlignmentFlag.AlignBottom)
        time_row.addStretch()
        time_row.addWidget(files_button, 0, Qt.AlignmentFlag.AlignTop)

        layout.addLayout(time_row)

        # 타임라인
        self.timeline = TimelineWidget()
        self.timeline.seek_requested.connect(self.seek)

        layout.addWidget(self.timeline, 1)

        # 줌
        minus_button = self._zoom_button("−")
        plus_button = self._zoom_button("+")

        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(int(MIN_ZOOM * 100), int(MAX_ZOOM * 100))
        self.zoom_slider.setFixedWidth(150)
        self.zoom_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.zoom_slider.valueChanged.connect(self.change_zoom)

        minus_button.clicked.connect(
            lambda: self.zoom_slider.setValue(self.zoom_slider.value() - int(ZOOM_STEP * 100))
        )
        plus_button.clicked.connect(
            lambda: self.zoom_slider.setValue(self.zoom_slider.value() + int(ZOOM_STEP * 100))
        )

        self.zoom_label = QLabel("1.0×")
        self.zoom_label.setObjectName("zoomLabel")
        self.zoom_label.setFixedWidth(38)
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        zoom_row = QHBoxLayout()
        zoom_row.setSpacing(8)
        zoom_row.addStretch()
        zoom_row.addWidget(minus_button)
        zoom_row.addWidget(self.zoom_slider)
        zoom_row.addWidget(plus_button)
        zoom_row.addWidget(self.zoom_label)

        layout.addLayout(zoom_row)
        layout.addSpacing(6)

        # 재생 컨트롤 + QuickTime 상태
        self.prev_button = TransportButton("prev", 22)
        self.play_button = TransportButton("play", 36)
        self.next_button = TransportButton("next", 22)

        self.prev_button.setToolTip("이전 씬")
        self.next_button.setToolTip("다음 씬")

        self.prev_button.clicked.connect(self.go_previous_scene)
        self.next_button.clicked.connect(self.go_next_scene)
        self.play_button.clicked.connect(self.toggle_play)

        self.status_badge = QLabel("Q")
        self.status_badge.setObjectName("badge")
        self.status_badge.setFixedSize(16, 16)
        self.status_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.status_label = QLabel()
        self.status_label.setObjectName("status")

        status_box = QHBoxLayout()
        status_box.setSpacing(8)
        status_box.addStretch()
        status_box.addWidget(self.status_badge)
        status_box.addWidget(self.status_label)

        transport = QHBoxLayout()
        transport.setSpacing(14)
        transport.addStretch()
        transport.addWidget(self.prev_button)
        transport.addWidget(self.play_button)
        transport.addWidget(self.next_button)
        transport.addStretch()

        bottom = QHBoxLayout()
        self.speed_button = QPushButton("1×")
        self.speed_button.setObjectName("zoomButton")
        self.speed_button.setFixedSize(40, 20)
        self.speed_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.speed_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.speed_button.setToolTip("재생 속도")

        speed_menu = QMenu(self)

        for speed in SPEEDS:
            speed_menu.addAction(
                f"{speed:g}×", lambda checked=False, s=speed: self.set_speed(s)
            )

        self.speed_button.setMenu(speed_menu)

        self.theme_button = QPushButton()
        self.theme_button.setObjectName("zoomButton")
        self.theme_button.setFixedSize(40, 20)
        self.theme_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.theme_button.clicked.connect(self.toggle_theme)

        left_box = QHBoxLayout()
        left_box.setSpacing(6)
        left_box.addWidget(self.speed_button)
        left_box.addWidget(self.theme_button)
        left_box.addStretch()
        bottom.addLayout(left_box, 1)
        bottom.addLayout(transport, 0)
        bottom.addLayout(status_box, 1)

        layout.addLayout(bottom)

        self.apply_theme()

        self._refresh_status()
        self.update_info()

    def apply_theme(self):
        """현재 팔레트를 스타일시트와 직접 그리는 위젯에 반영."""

        self.centralWidget().setStyleSheet(
            """
            QWidget#root { background-color: %(bg)s; }

            QLabel#info { color: %(text_muted)s; font-size: 11px; }
            QLabel#time { color: %(text)s; font-size: 26px; font-weight: 700; }
            QLabel#duration {
                color: %(text_dim)s; font-size: 14px; font-weight: 500;
                padding-bottom: 3px;
            }
            QLabel#zoomLabel { color: %(text_strong)s; font-size: 12px; font-weight: 700; }
            QLabel#status { color: %(text_muted)s; font-size: 11px; }
            QLabel#badge {
                background: #6f8fd0; color: #ffffff; border-radius: 5px;
                font-size: 10px; font-weight: 700;
            }

            QPushButton#files {
                background: %(surface)s; color: %(text_strong)s;
                border: 1px solid %(border)s; border-radius: 9px;
                padding: 5px 14px; font-size: 12px; font-weight: 600;
            }
            QPushButton#files:hover { background: %(hover_bg)s; }

            QPushButton#zoomButton {
                background: %(surface)s; color: %(text_strong)s;
                border: 1px solid %(border)s; border-radius: 8px;
                font-size: 12px; padding: 0;
            }
            QPushButton#zoomButton:hover { background: %(hover_bg)s; }
            QPushButton#zoomButton::menu-indicator { image: none; }

            QSlider::groove:horizontal {
                height: 3px; background: %(track)s; border-radius: 1px;
            }
            QSlider::sub-page:horizontal {
                background: %(accent)s; border-radius: 1px;
            }
            QSlider::handle:horizontal {
                background: %(accent)s; width: 14px; height: 14px;
                margin: -6px 0; border-radius: 7px;
            }
            """ % theme.hexes()
        )
        self.info_label.setStyleSheet(f"color: {theme.hexes()['error']};")

        # 다크일 때는 해(라이트로 전환), 라이트일 때는 달(다크로 전환)
        self.theme_button.setText("☀" if theme.is_dark() else "☾")
        self.theme_button.setToolTip("라이트 모드" if theme.is_dark() else "다크 모드")

        self.timeline.update()

        for button in (self.prev_button, self.play_button, self.next_button):
            button.update()

        self._refresh_status()

        if hasattr(self, "files_dialog"):
            self.files_dialog.apply_theme()

    def toggle_theme(self):
        # 직접 고른 모드는 이후 시스템 설정 변경보다 우선한다
        self.theme_overridden = True
        theme.set_dark(not theme.is_dark())
        self.apply_theme()

    def _zoom_button(self, text: str) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("zoomButton")
        button.setFixedSize(24, 20)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        return button

    # ------------------------------------------------------------
    # 파일 선택
    # ------------------------------------------------------------

    def open_files(self):
        self.files_dialog.refresh(
            self.video_path, self.scene_path, len(self.scenes)
        )
        self.files_dialog.exec()

    def select_video(self):
        path, _ = QFileDialog.getOpenFileName(
            self.files_dialog,
            "영상 선택",
            str(Path(self.video_path).parent) if self.video_path else "",
            "Video Files (*.mov *.mp4 *.m4v)",
        )

        if not path:
            return

        self.video_path = path
        # open 은 즉시 반환되므로 UI 스레드에서 바로 실행해도 된다.
        self.controller.open_video(path)

        self.files_dialog.refresh(
            self.video_path, self.scene_path, len(self.scenes)
        )
        self.update_info()

    def select_scene_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self.files_dialog,
            "씬 데이터 선택",
            str(Path(self.scene_path).parent) if self.scene_path else "",
            "JSON Files (*.json)",
        )

        if not path:
            return

        try:
            scenes = load_scenes(path)

        except Exception as error:
            QMessageBox.critical(self.files_dialog, "씬 데이터 오류", str(error))
            return

        self.scenes = scenes
        self.scene_path = path
        self.timeline.set_scenes(scenes)

        self.files_dialog.refresh(
            self.video_path, self.scene_path, len(self.scenes)
        )
        self.update_info()

    def update_info(self):
        # 파일 정보 줄은 없앴다. 오류 안내만 잠깐 표시하고 숨긴다.
        self.info_label.hide()

    def show_notice(self, message: str):
        self.info_label.setText(message)
        self.info_label.show()

        QTimer.singleShot(4000, self.update_info)

    # ------------------------------------------------------------
    # QuickTime 동기화
    # ------------------------------------------------------------

    def on_state(self, state):
        # 내가 보낸 명령이 아직 반영되기 전의 오래된 상태는 무시
        if state.commands_done < self._issued:
            return

        previous_duration = self._duration
        self._status = state.status

        if state.status == "ok":
            self._base_time = state.current
            self._base_at = state.sampled_at
            self._playing = state.playing
            self._duration = state.duration

            if state.rate:
                # QuickTime에서 직접 바꾼 배속도 따라간다
                self._rate = state.rate
                self._set_speed_label(state.rate)
            else:
                self._rate = self._speed

        elif state.status in ("no_app", "no_document"):
            self._base_time = 0.0
            self._playing = False
            self._duration = 0.0

        # "error"(일시적 osascript 실패)는 마지막 값을 유지

        if self._duration != previous_duration:
            self.update_info()

        self._refresh_status()

    def position(self) -> float:
        position = self._base_time

        if self._playing:
            position += (time.monotonic() - self._base_at) * self._rate

        if self._duration > 0:
            position = min(position, self._duration)

        return max(0.0, position)

    def tick(self):
        position = self.position()
        shown = (int(position), int(self._duration), self._playing)

        self.timeline.set_duration(self._duration)
        self.timeline.set_current_time(position)

        if shown != self._last_shown:
            self._last_shown = shown

            self.time_label.setText(format_time(position))
            self.duration_label.setText("/ " + format_time(self._duration))
            self.play_button.set_kind("pause" if self._playing else "play")

    def _refresh_status(self):
        connected = self._status in ("ok", "error")

        if self._status == "ok":
            text = "Playing in QuickTime" if self._playing else "Paused in QuickTime"

        elif self._status == "no_document":
            text = "No video in QuickTime"

        elif self._status == "no_app":
            text = "QuickTime not running"

        else:
            text = "Reconnecting…"

        self.status_label.setText(text)
        self.status_badge.setStyleSheet(
            "" if connected and self._status == "ok" else f"background: {theme.hexes()['badge_off']};"
        )

    # ------------------------------------------------------------
    # 명령
    # ------------------------------------------------------------

    def _send(self, name: str, *args):
        self._issued += 1
        self.worker.submit(name, *args)

    def _ensure_video(self) -> bool:
        if self._status != "ok":
            self.show_notice("QuickTime에 열린 영상이 없습니다.")
            return False

        return True

    def seek(self, seconds: float):
        if not self._ensure_video():
            return

        # 응답을 기다리지 않고 화면부터 이동 (QuickTime 반영은 뒤따라온다)
        self._base_time = seconds
        self._base_at = time.monotonic()

        if PLAY_AFTER_SEEK:
            self._playing = True
            self._rate = self._speed

        self._send("seek", seconds, PLAY_AFTER_SEEK, self._speed)

    def toggle_play(self):
        if not self._ensure_video():
            return

        self._base_time = self.position()
        self._base_at = time.monotonic()
        self._playing = not self._playing
        self._rate = self._speed

        if self._playing:
            self._send("play", self._speed)
        else:
            self._send("pause")

    def _set_speed_label(self, speed: float):
        self._speed = speed
        self.speed_button.setText(f"{speed:g}×")

    def set_speed(self, speed: float):
        self._set_speed_label(speed)

        # 재생 중일 때만 즉시 적용, 일시정지 중이면 다음 재생부터 적용
        if self._playing and self._status == "ok":
            self._base_time = self.position()
            self._base_at = time.monotonic()
            self._rate = speed
            self._send("set_rate", speed)

    def go_previous_scene(self):
        position = self.position()

        # 씬 시작 직후(2초 이내)에는 한 씬 앞으로, 아니면 현재 씬의 처음으로
        targets = [s.start_seconds for s in self.scenes if s.start_seconds < position - 2]

        if targets:
            self._jump(targets[-1])

        elif self.scenes:
            self._jump(0.0)

    def go_next_scene(self):
        position = self.position()

        for scene in self.scenes:
            if scene.start_seconds > position + 0.5:
                self._jump(scene.start_seconds)
                return

    def _jump(self, seconds: float):
        self.timeline.reveal(seconds)
        self.seek(seconds)

    def change_zoom(self, value: int):
        zoom = value / 100

        self.timeline.set_zoom(zoom)
        self.zoom_label.setText(f"{zoom:.1f}×")

    def closeEvent(self, event):
        self.worker.stop()
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)

    # 시스템 라이트/다크 설정을 따라간다 (바뀌면 즉시 반영)
    hints = app.styleHints()

    def sync_theme(*_):
        if window.theme_overridden:
            return

        theme.set_dark(hints.colorScheme() == Qt.ColorScheme.Dark)
        window.apply_theme()

    theme.set_dark(hints.colorScheme() == Qt.ColorScheme.Dark)

    window = SceneNavigator()
    hints.colorSchemeChanged.connect(sync_theme)
    window.show()

    sys.exit(app.exec())
