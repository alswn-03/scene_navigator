# 라이트 / 다크 팔레트
# - 시스템 설정을 따라 main.py가 set_dark()로 전환한다
# - 위젯은 그릴 때마다 c()/hexes()로 현재 팔레트를 읽는다

from PySide6.QtGui import QColor

LIGHT = {
    "bg": "#fafaf8",
    "surface": "#ffffff",
    "surface_hover": "#fcfdfc",
    "hover_bg": "#f3f6f4",
    "border": "#dfe5e1",
    "divider": "#e3e8e5",
    "text": "#15201c",
    "text_strong": "#34413b",
    "text_desc": "#44504a",
    "text_muted": "#7f8a85",
    "text_dim": "#8a9590",
    "text_off": "#9aa49f",
    "accent": "#36684f",
    "accent_hover": "#2d5942",
    "accent_press": "#244a37",
    "on_accent": "#ffffff",
    "orange": "#e59d38",
    "error": "#c0563f",
    "badge_off": "#b9c2bd",
    "transport": "#4a5750",
    "transport_hover": "#15201c",
    "track": "#dfe5e1",
    "tick": "#c9d1cd",
    "label": "#87928d",
    "marker_fill": "#ffffff",
    "marker_border": "#cdd6d1",
    "overview_track": "#e6ebe8",
    "overview_handle": "#a3ada8",
    "video_bg": "#e1efe8",
    "video_fg": "#36684f",
    "doc_bg": "#f3ead8",
    "doc_fg": "#7a5c2e",
}

DARK = {
    "bg": "#121715",
    "surface": "#1b2320",
    "surface_hover": "#202a26",
    "hover_bg": "#232e2a",
    "border": "#2c3732",
    "divider": "#2a3531",
    "text": "#e9efec",
    "text_strong": "#cfd9d4",
    "text_desc": "#aab6b0",
    "text_muted": "#8d9a94",
    "text_dim": "#7f8b85",
    "text_off": "#66726c",
    "accent": "#5ecce0",
    "accent_hover": "#7ad8e9",
    "accent_press": "#48b8cc",
    "on_accent": "#0a1518",
    "orange": "#f0b253",
    "error": "#e8806b",
    "badge_off": "#46524c",
    "transport": "#9aa8a1",
    "transport_hover": "#ffffff",
    "track": "#2a3531",
    "tick": "#3a4741",
    "label": "#7f8b85",
    "marker_fill": "#e9efec",
    "marker_border": "#43524b",
    "overview_track": "#232d29",
    "overview_handle": "#5d6b64",
    "video_bg": "#1a3a42",
    "video_fg": "#5ecce0",
    "doc_bg": "#3a3020",
    "doc_fg": "#e0b872",
}

_dark = False


def set_dark(dark: bool):
    global _dark
    _dark = dark


def is_dark() -> bool:
    return _dark


def hexes() -> dict[str, str]:
    """스타일시트용 (%(name)s 치환) 현재 팔레트."""

    return DARK if _dark else LIGHT


def c(name: str, alpha: int | None = None) -> QColor:
    color = QColor(hexes()[name])

    if alpha is not None:
        color.setAlpha(alpha)

    return color
