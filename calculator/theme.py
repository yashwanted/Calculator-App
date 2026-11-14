"""Colour themes, theme modes and fonts shared by the whole interface."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Optional

from PySide6.QtGui import QColor, QFont, QFontDatabase



@dataclass(frozen=True)
class ButtonColors:
    background: str
    hover: str
    pressed: str
    text: str


@dataclass(frozen=True)
class Theme:
    window: str
    panel: str
    divider: str
    text: str
    muted: str
    error: str
    accent: str
    accent_soft: str
    row_hover: str
    button_edge: str  # Faint lower edge that lifts light-theme buttons.
    digit: ButtonColors
    function: ButtonColors
    operator: ButtonColors
    equals: ButtonColors
    memory: ButtonColors


DARK_THEME = Theme(
    window="#15161A",
    panel="#1B1C21",
    divider="#2A2C33",
    text="#F5F5F7",
    muted="#9EA3AE",
    error="#FF8F7A",
    accent="#FF8A6B",
    accent_soft="#3A2620",
    row_hover="#26282E",
    button_edge="#00000000",
    digit=ButtonColors("#2B2D34", "#363841", "#454852", "#F5F5F7"),
    function=ButtonColors("#1F2026", "#2A2C33", "#383A43", "#BFC3CC"),
    operator=ButtonColors("#3A2620", "#4A2F27", "#5C392E", "#FF9E85"),
    equals=ButtonColors("#FF7A59", "#FF8D70", "#E5674A", "#231008"),
    memory=ButtonColors("#00000000", "#24262C", "#30323A", "#9EA3AE"),
)

LIGHT_THEME = Theme(
    window="#F4F3F0",
    panel="#ECEBE7",
    divider="#DBD9D3",
    text="#1B1C20",
    muted="#62656E",
    error="#B3321A",
    accent="#B8391C",
    accent_soft="#FBE4DC",
    row_hover="#E2E0DB",
    button_edge="#1F000000",
    digit=ButtonColors("#FFFFFF", "#FAF9F7", "#E9E7E2", "#1B1C20"),
    function=ButtonColors("#E6E4DF", "#DEDCD6", "#D1CFC8", "#3F424A"),
    operator=ButtonColors("#FBE4DC", "#F8D8CC", "#F3C7B7", "#A32F15"),
    equals=ButtonColors("#C8401F", "#D34B2A", "#AE3518", "#FFFFFF"),
    memory=ButtonColors("#00000000", "#E6E4DF", "#DAD8D2", "#62656E"),
)

# Theme modes as stored in the settings.
MODE_SYSTEM, MODE_LIGHT, MODE_DARK = "system", "light", "dark"
THEME_MODES = (MODE_SYSTEM, MODE_LIGHT, MODE_DARK)
MODE_LABELS = {MODE_SYSTEM: "Match System", MODE_LIGHT: "Light", MODE_DARK: "Dark"}


def blend(start: QColor, end: QColor, amount: float) -> QColor:
    """Interpolate between two colours, including alpha."""
    return QColor(
        round(start.red() + (end.red() - start.red()) * amount),
        round(start.green() + (end.green() - start.green()) * amount),
        round(start.blue() + (end.blue() - start.blue()) * amount),
        round(start.alpha() + (end.alpha() - start.alpha()) * amount),
    )


# --- Fonts ------------------------------------------------------------------

_FONT_PREFERENCES = ("Inter", "Helvetica Neue", "Segoe UI", "Roboto", "Arial")
_cached_family: Optional[str] = None


def _font_family() -> str:
    """The macOS system font (SF), or else the first available fallback."""
    global _cached_family
    if _cached_family is None:
        if sys.platform == "darwin":
            _cached_family = QFontDatabase.systemFont(
                QFontDatabase.SystemFont.GeneralFont
            ).family()
        else:
            available = set(QFontDatabase.families())
            _cached_family = next(
                (name for name in _FONT_PREFERENCES if name in available),
                QFont().family(),
            )
    return _cached_family


def ui_font(
    pixel_size: float,
    weight: QFont.Weight = QFont.Weight.Normal,
    tabular: bool = False,
) -> QFont:
    font = QFont(_font_family())
    font.setPixelSize(max(1, round(pixel_size)))
    font.setWeight(weight)
    if tabular:
        # Fixed-width digits, so numbers don't jiggle as they change.
        font.setFeature(QFont.Tag("tnum"), 1)
    return font
