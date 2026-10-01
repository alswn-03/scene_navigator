# Files 모달 (영상 / 씬 데이터 선택)
# - 영상과 씬 데이터를 각각 독립적으로 선택
# - 경로는 화면 표시에만 쓰고 어디에도 저장하지 않는다

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

VIDEO_KINDS = {
    ".mov": "QuickTime Movie",
    ".mp4": "MPEG-4 Movie",
    ".m4v": "MPEG-4 Video",
}


class ElidedLabel(QLabel):
    """너비를 넘으면 가운데를 줄여서(…) 표시하는 한 줄 라벨."""

    def __init__(self):
        super().__init__()

        self._full = ""
        self.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )

    def set_full_text(self, text: str):
        self._full = text
        self._elide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._elide()

    def _elide(self):
        super().setText(
            self.fontMetrics().elidedText(
                self._full,
                Qt.TextElideMode.ElideMiddle,
                max(0, self.width()),
            )
        )


class IconBadge(QWidget):
    """파일 종류 아이콘 (video / document)."""

    def __init__(self, kind: str):
        super().__init__()

        self.kind = kind
        self.setFixedSize(44, 44)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self.kind == "video":
            background, stroke = QColor("#e1efe8"), QColor("#36684f")
        else:
            background, stroke = QColor("#f3ead8"), QColor("#7a5c2e")

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(background)
        painter.drawRoundedRect(self.rect(), 10, 10)

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(
            QPen(stroke, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                 Qt.PenJoinStyle.RoundJoin)
        )

        if self.kind == "video":
            painter.drawRoundedRect(QRectF(11, 13, 22, 18), 3, 3)
            painter.drawLine(QPointF(17, 13), QPointF(17, 31))
            painter.drawLine(QPointF(27, 13), QPointF(27, 31))

            painter.setBrush(stroke)
            painter.drawPolygon(
                QPolygonF([QPointF(20, 18), QPointF(20, 26), QPointF(25, 22)])
            )

        else:
            painter.drawRoundedRect(QRectF(14, 11, 16, 22), 3, 3)

            for y in (18, 22, 26):
                painter.drawLine(QPointF(18, y), QPointF(26, y))


class FileCard(QPushButton):
    """아이콘 + 파일명 + 설명 + chevron 형태의 선택 카드."""

    def __init__(self, icon_kind: str):
        super().__init__()

        self.setObjectName("card")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedHeight(66)

        row = QHBoxLayout(self)
        row.setContentsMargins(11, 0, 16, 0)
        row.setSpacing(14)

        self.title = ElidedLabel()
        self.title.setObjectName("cardTitle")

        self.subtitle = QLabel()
        self.subtitle.setObjectName("cardSub")

        texts = QVBoxLayout()
        texts.setSpacing(3)
        texts.addStretch()
        texts.addWidget(self.title)
        texts.addWidget(self.subtitle)
        texts.addStretch()

        chevron = QLabel("›")
        chevron.setObjectName("chevron")

        row.addWidget(IconBadge(icon_kind))
        row.addLayout(texts, 1)
        row.addWidget(chevron)

        for child in (self.title, self.subtitle, chevron):
            child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def set_content(self, title: str, subtitle: str, tooltip: str = ""):
        self.title.set_full_text(title)
        self.subtitle.setText(subtitle)
        self.setToolTip(tooltip)


class FilesDialog(QDialog):
    video_requested = Signal()
    scenes_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Files")
        self.setModal(True)
        self.setFixedWidth(440)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 24)
        layout.setSpacing(0)

        eyebrow = QLabel("LOCAL WORKSPACE")
        eyebrow.setObjectName("eyebrow")

        title = QLabel("Video & scene data")
        title.setObjectName("dialogTitle")

        description = QLabel(
            "Choose files independently. Nothing is uploaded "
            "or saved after this session."
        )
        description.setObjectName("description")
        description.setWordWrap(True)

        layout.addWidget(eyebrow)
        layout.addSpacing(6)
        layout.addWidget(title)
        layout.addSpacing(10)
        layout.addWidget(description)
        layout.addSpacing(22)

        self.video_status = QLabel()
        self.video_card = FileCard("video")
        self.scene_status = QLabel()
        self.scene_card = FileCard("document")

        layout.addLayout(self._section("VIDEO", self.video_status))
        layout.addSpacing(8)
        layout.addWidget(self.video_card)
        layout.addSpacing(20)
        layout.addLayout(self._section("SCENE DATA", self.scene_status))
        layout.addSpacing(8)
        layout.addWidget(self.scene_card)
        layout.addSpacing(22)

        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setObjectName("divider")

        layout.addWidget(divider)
        layout.addSpacing(16)

        done = QPushButton("Done")
        done.setObjectName("done")
        done.setCursor(Qt.CursorShape.PointingHandCursor)
        done.setDefault(True)
        done.clicked.connect(self.accept)

        footer = QHBoxLayout()
        footer.addStretch()
        footer.addWidget(done)

        layout.addLayout(footer)

        self.video_card.clicked.connect(self.video_requested)
        self.scene_card.clicked.connect(self.scenes_requested)

        self.setStyleSheet(
            """
            QDialog { background: #fafaf8; }

            QLabel#eyebrow {
                color: #7f8a85; font-size: 11px; font-weight: 700;
                letter-spacing: 2px;
            }
            QLabel#dialogTitle {
                color: #15201c; font-size: 26px; font-weight: 700;
            }
            QLabel#description { color: #44504a; font-size: 13px; }

            QLabel#sectionName {
                color: #7f8a85; font-size: 11px; font-weight: 700;
                letter-spacing: 2px;
            }
            QLabel#statusOn { color: #36684f; font-size: 12px; font-weight: 600; }
            QLabel#statusOff { color: #9aa49f; font-size: 12px; }

            QPushButton#card {
                background: #ffffff; border: 1px solid #dfe5e1;
                border-radius: 14px; text-align: left;
            }
            QPushButton#card:hover { border-color: #36684f; background: #fcfdfc; }

            QLabel#cardTitle { color: #15201c; font-size: 14px; font-weight: 600; }
            QLabel#cardSub { color: #7f8a85; font-size: 12px; }
            QLabel#chevron { color: #44504a; font-size: 22px; }

            QFrame#divider { background: #e3e8e5; border: none; }

            QPushButton#done {
                background: #36684f; color: #ffffff; border: none;
                border-radius: 10px; padding: 8px 26px;
                font-size: 13px; font-weight: 600;
            }
            QPushButton#done:hover { background: #2d5942; }
            """
        )

        self.refresh(None, None, 0)

    def _section(self, name: str, status: QLabel) -> QHBoxLayout:
        label = QLabel(name)
        label.setObjectName("sectionName")

        row = QHBoxLayout()
        row.setContentsMargins(4, 0, 2, 0)
        row.addWidget(label)
        row.addStretch()
        row.addWidget(status)

        return row

    @staticmethod
    def _set_status(label: QLabel, text: str | None):
        if text:
            label.setObjectName("statusOn")
            label.setText(f"✓  {text}")

        else:
            label.setObjectName("statusOff")
            label.setText("Not selected")

        # objectName 변경을 스타일에 반영
        label.style().unpolish(label)
        label.style().polish(label)

    def refresh(
        self,
        video_path: str | None,
        scene_path: str | None,
        scene_count: int,
    ):
        if video_path:
            path = Path(video_path)

            self.video_card.set_content(
                path.name,
                VIDEO_KINDS.get(path.suffix.lower(), "Video"),
                str(path),
            )
            self._set_status(self.video_status, "Selected")

        else:
            self.video_card.set_content(
                "Choose a video…", ".mov · .mp4 · .m4v"
            )
            self._set_status(self.video_status, None)

        if scene_path:
            self.scene_card.set_content(
                Path(scene_path).name,
                "JSON scene data",
                str(scene_path),
            )
            self._set_status(
                self.scene_status,
                f"{scene_count} scene{'s' if scene_count != 1 else ''}",
            )

        else:
            self.scene_card.set_content(
                "Choose scene data…", ".json"
            )
            self._set_status(self.scene_status, None)
