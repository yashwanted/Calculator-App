"""PySide6 user interface: themes, custom-painted widgets and the main window.

All arithmetic lives in ``calculator.engine``. This module only forwards key
presses to it and renders whatever it reports.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from typing import Callable, Optional

from PySide6.QtCore import (
    QByteArray,
    QEasingCurve,
    QEvent,
    QModelIndex,
    QObject,
    QPointF,
    QRectF,
    QSettings,
    QSize,
    Qt,
    QTimer,
    QUrl,
    QVariantAnimation,
)
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QDesktopServices,
    QFont,
    QFontDatabase,
    QFontMetricsF,
    QGuiApplication,
    QIcon,
    QKeyEvent,
    QKeySequence,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .engine import Calculator, INVALID_INPUT_MESSAGE
from .history import HistoryEntry, HistoryStore

logger = logging.getLogger(__name__)

HISTORY_PANEL_WIDTH = 280
DEFAULT_WINDOW_SIZE = QSize(380, 640)
TRANSIENT_MESSAGE_MS = 1400
KEY_FLASH_MS = 110
VALUE_TEXT_PIXELS = 76
ERROR_TEXT_PIXELS = 32  # Errors should be readable, not shouted.

PROJECT_URL = "https://github.com/yashwanted/Calculator-App"
LATEST_RELEASE_URL = f"{PROJECT_URL}/releases/latest"

# Shown by Help > Keyboard Shortcuts. Keep in step with the README.
KEYBOARD_SHORTCUTS = (
    ("Digits, decimal point", "0–9, ."),
    ("Add, subtract", "+, -"),
    ("Multiply, divide", "* or X, /"),
    ("Equals", "Enter or ="),
    ("Parentheses", "(, )"),
    ("Percent", "%"),
    ("Delete last character", "Backspace"),
    ("Clear entry", "Esc or C"),
    ("All clear", "A"),
    ("Change sign", "N"),
    ("Square root", "R"),
    ("Square", "Q"),
    ("Reciprocal (1/x)", "I"),
    ("Memory add, subtract", "M, Shift+M"),
    ("Memory recall, clear", "K, L"),
    ("Copy result", "Cmd+C"),
    ("Paste number or expression", "Cmd+V"),
    ("Show or hide history", "H or Cmd+Y"),
    ("Change appearance", "T"),
    ("Minimize window", "Cmd+M"),
    ("Close window", "Cmd+W"),
)

# --- Themes -----------------------------------------------------------------


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


def _blend(start: QColor, end: QColor, amount: float) -> QColor:
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


# --- Animation helper -------------------------------------------------------


class _Tween(QObject):
    """Animates one 0..1 float, restarting smoothly from wherever it is now."""

    def __init__(self, owner: QWidget, on_change: Callable[[], None]):
        super().__init__(owner)
        self.value = 0.0
        self._on_change = on_change
        self._animation = QVariantAnimation(self)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.valueChanged.connect(self._step)

    def _step(self, value: float) -> None:
        self.value = float(value)
        self._on_change()

    def to(self, target: float, duration_ms: int) -> None:
        self._animation.stop()
        self._animation.setDuration(duration_ms)
        self._animation.setStartValue(self.value)
        self._animation.setEndValue(float(target))
        self._animation.start()


# --- Calculator button ------------------------------------------------------


class CalcButton(QAbstractButton):
    """A rounded button with animated hover and press states."""

    def __init__(self, label: str, role: str, tooltip: str = ""):
        super().__init__()
        self.label = label
        self.role = role
        self._colors = DARK_THEME.digit
        self._edge = QColor(0, 0, 0, 0)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(44, 28 if role == "memory" else 44)
        self.setAccessibleName(label)
        if tooltip:
            self.setToolTip(tooltip)

        self._hover = _Tween(self, self.update)
        self._press = _Tween(self, self.update)
        self.pressed.connect(lambda: self._press.to(1.0, 70))
        self.released.connect(lambda: self._press.to(0.0, 220))

    def apply_theme(self, theme: Theme) -> None:
        self._colors = getattr(theme, self.role)
        self._edge = QColor(theme.button_edge)
        self.update()

    def flash(self) -> None:
        """Show a press, for when the matching keyboard key is used."""
        self._press.to(1.0, 50)
        QTimer.singleShot(KEY_FLASH_MS, self._end_flash)

    def _end_flash(self) -> None:
        if not self.isDown():
            self._press.to(0.0, 220)

    def enterEvent(self, event: QEvent) -> None:
        self._hover.to(1.0, 120)
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        self._hover.to(0.0, 200)
        super().leaveEvent(event)

    def sizeHint(self) -> QSize:
        return QSize(68, 40 if self.role == "memory" else 68)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # The whole button shrinks slightly while pressed.
        scale = 1.0 - 0.05 * self._press.value
        center = QRectF(self.rect()).center()
        painter.translate(center)
        painter.scale(scale, scale)
        painter.translate(-center)

        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -1.5)
        radius = min(rect.width(), rect.height()) * 0.3
        if self._edge.alpha() and self.role == "digit":
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self._edge)
            painter.drawRoundedRect(rect.translated(0, 1), radius, radius)

        background = _blend(
            _blend(
                QColor(self._colors.background),
                QColor(self._colors.hover),
                self._hover.value,
            ),
            QColor(self._colors.pressed),
            self._press.value,
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(background)
        painter.drawRoundedRect(rect, radius, radius)

        text_color = QColor(self._colors.text)
        if not self.isEnabled():
            text_color.setAlphaF(0.35)
        if self.label == "⌫":
            self._draw_backspace(painter, rect, text_color)
        else:
            painter.setPen(text_color)
            painter.setFont(self._label_font(rect))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.label)

    def _label_font(self, rect: QRectF) -> QFont:
        base = min(rect.height(), rect.width())
        if self.role == "memory":
            return ui_font(min(base * 0.42, 14), QFont.Weight.Medium)
        if self.role == "function":
            return ui_font(min(base * 0.32, 21), QFont.Weight.Medium)
        if self.role == "digit":
            return ui_font(min(base * 0.40, 30), QFont.Weight.Normal, tabular=True)
        return ui_font(min(base * 0.46, 32), QFont.Weight.Medium)

    @staticmethod
    def _draw_backspace(painter: QPainter, rect: QRectF, color: QColor) -> None:
        height = min(min(rect.height(), rect.width()) * 0.40, 18)
        width = height * 1.4
        left = rect.center().x() - width / 2
        top = rect.center().y() - height / 2
        notch = height * 0.45

        outline = QPainterPath()
        outline.moveTo(left + notch, top)
        outline.lineTo(left + width, top)
        outline.lineTo(left + width, top + height)
        outline.lineTo(left + notch, top + height)
        outline.lineTo(left, top + height / 2)
        outline.closeSubpath()

        pen = QPen(color, max(1.4, height * 0.09))
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(outline)

        cross_x = left + notch + (width - notch) / 2
        cross_y = top + height / 2
        arm = height * 0.2
        painter.drawLine(
            QPointF(cross_x - arm, cross_y - arm), QPointF(cross_x + arm, cross_y + arm)
        )
        painter.drawLine(
            QPointF(cross_x - arm, cross_y + arm), QPointF(cross_x + arm, cross_y - arm)
        )


class IconButton(QAbstractButton):
    """A small toolbar button with a glyph drawn in code."""

    def __init__(self, glyph: str):
        super().__init__()
        self.glyph = glyph
        self._theme = DARK_THEME
        self._hover = _Tween(self, self.update)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedSize(30, 30)

    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.update()

    def set_glyph(self, glyph: str) -> None:
        self.glyph = glyph
        self.update()

    def enterEvent(self, event: QEvent) -> None:
        self._hover.to(1.0, 120)
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        self._hover.to(0.0, 200)
        super().leaveEvent(event)

    def sizeHint(self) -> QSize:
        return QSize(30, 30)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect())

        idle = QColor(self._theme.row_hover)
        idle.setAlpha(0)
        background = _blend(idle, QColor(self._theme.row_hover), self._hover.value)
        if self.isChecked():
            background = QColor(self._theme.accent_soft)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(background)
        painter.drawRoundedRect(rect, 8, 8)

        color = QColor(self._theme.accent if self.isChecked() else self._theme.muted)
        {
            "history": self._draw_history,
            MODE_SYSTEM: self._draw_system,
            MODE_LIGHT: self._draw_sun,
            MODE_DARK: self._draw_moon,
        }[self.glyph](painter, rect.center(), color)

    @staticmethod
    def _stroke(painter: QPainter, color: QColor) -> None:
        pen = QPen(color, 1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

    def _draw_history(self, painter: QPainter, center: QPointF, color: QColor) -> None:
        """A clock face."""
        self._stroke(painter, color)
        painter.drawEllipse(center, 7.5, 7.5)
        painter.drawLine(center, center + QPointF(0, -4.5))
        painter.drawLine(center, center + QPointF(3.2, 1.8))

    def _draw_system(self, painter: QPainter, center: QPointF, color: QColor) -> None:
        """A half-filled circle: both themes, chosen by the system."""
        self._stroke(painter, color)
        painter.drawEllipse(center, 7.5, 7.5)
        half = QPainterPath()
        half.moveTo(center + QPointF(0, -7.5))
        half.arcTo(QRectF(center.x() - 7.5, center.y() - 7.5, 15, 15), 90, -180)
        half.closeSubpath()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawPath(half)

    def _draw_sun(self, painter: QPainter, center: QPointF, color: QColor) -> None:
        self._stroke(painter, color)
        painter.drawEllipse(center, 3.6, 3.6)
        painter.translate(center)
        for _ in range(8):
            painter.drawLine(QPointF(0, -6.2), QPointF(0, -8.2))
            painter.rotate(45)
        painter.translate(-center)

    def _draw_moon(self, painter: QPainter, center: QPointF, color: QColor) -> None:
        disc = QPainterPath()
        disc.addEllipse(center, 7.5, 7.5)
        bite = QPainterPath()
        bite.addEllipse(center + QPointF(3.8, -3.2), 6.4, 6.4)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawPath(disc.subtracted(bite))


# --- Display ----------------------------------------------------------------


class FitLabel(QWidget):
    """Right-aligned single-line text that shrinks to fit its width.

    Below ``min_pixels`` the start of the text is elided instead, keeping the
    most recent part visible. Text is measured at paint time, so it adapts to
    any window size.
    """

    def __init__(
        self,
        max_pixels: float,
        min_pixels: float,
        weight: QFont.Weight,
        height_ratio: float = 0.82,
    ):
        super().__init__()
        self._text = ""
        self._color = QColor("#000000")
        self._max_pixels = max_pixels
        self._min_pixels = min_pixels
        self._weight = weight
        self._height_ratio = height_ratio
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_text(self, text: str) -> None:
        if text != self._text:
            self._text = text
            self.update()

    def text(self) -> str:
        return self._text

    def set_color(self, color: str) -> None:
        self._color = QColor(color)
        self.update()

    def set_max_pixels(self, max_pixels: float) -> None:
        if max_pixels != self._max_pixels:
            self._max_pixels = max_pixels
            self.update()

    def fitted_font(self) -> QFont:
        """The largest font at which the text fits, within the size limits."""
        size = min(self._max_pixels, self.height() * self._height_ratio)
        size = max(size, self._min_pixels)
        font = ui_font(size, self._weight, tabular=True)
        if self._text:
            width = QFontMetricsF(font).horizontalAdvance(self._text)
            if width > self.width():
                # Measuring can be slightly non-linear, hence the small margin.
                shrunk = size * self.width() / width * 0.985
                font = ui_font(max(shrunk, self._min_pixels), self._weight, tabular=True)
        return font

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        font = self.fitted_font()
        metrics = QFontMetricsF(font)
        text = self._text
        if metrics.horizontalAdvance(text) > self.width():
            text = metrics.elidedText(text, Qt.TextElideMode.ElideLeft, self.width())
        painter.setFont(font)
        painter.setPen(self._color)
        painter.drawText(
            QRectF(self.rect()),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            text,
        )


# --- History panel ----------------------------------------------------------

_ENTRY_ROLE = Qt.ItemDataRole.UserRole + 1


class _HistoryDelegate(QStyledItemDelegate):
    """Paints a history row: expression above, result below."""

    ROW_HEIGHT = 62

    def __init__(self, parent: QObject):
        super().__init__(parent)
        self.theme = DARK_THEME

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        return QSize(option.rect.width(), self.ROW_HEIGHT)

    def paint(
        self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex
    ) -> None:
        entry: HistoryEntry = index.data(_ENTRY_ROLE)
        if entry is None:
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(option.rect).adjusted(8, 2, -8, -2)
        if option.state & QStyle.StateFlag.State_MouseOver:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(self.theme.row_hover))
            painter.drawRoundedRect(rect, 10, 10)

        content = rect.adjusted(12, 7, -12, -7)
        align = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        top = QRectF(content.left(), content.top(), content.width(), 18)
        font = ui_font(12, tabular=True)
        painter.setFont(font)
        painter.setPen(QColor(self.theme.muted))
        painter.drawText(
            top,
            align,
            QFontMetricsF(font).elidedText(
                entry.expression, Qt.TextElideMode.ElideLeft, top.width()
            ),
        )

        bottom = QRectF(content.left(), top.bottom() + 1, content.width(), 24)
        font = ui_font(18, QFont.Weight.Medium, tabular=True)
        painter.setFont(font)
        painter.setPen(QColor(self.theme.text))
        painter.drawText(
            bottom,
            align,
            QFontMetricsF(font).elidedText(
                entry.result.replace("-", "−"),
                Qt.TextElideMode.ElideRight,
                bottom.width(),
            ),
        )
        painter.restore()


class HistoryPanel(QFrame):
    """Side panel listing past calculations."""

    def __init__(self, on_select: Callable[[HistoryEntry], None], on_clear: Callable):
        super().__init__()
        self.setObjectName("historyPanel")
        self.setFixedWidth(HISTORY_PANEL_WIDTH)

        self._title = QLabel("History")
        self._title.setObjectName("historyTitle")
        self._title.setFont(ui_font(15, QFont.Weight.DemiBold))

        self._empty = QLabel("No calculations yet")
        self._empty.setObjectName("historyEmpty")
        self._empty.setFont(ui_font(13))
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._delegate = _HistoryDelegate(self)
        self.list = QListWidget()
        self.list.setObjectName("historyList")
        self.list.setItemDelegate(self._delegate)
        self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setFrameShape(QFrame.Shape.NoFrame)
        self.list.setMouseTracking(True)
        self.list.setCursor(Qt.CursorShape.PointingHandCursor)
        self.list.itemClicked.connect(lambda item: on_select(item.data(_ENTRY_ROLE)))

        self.clear_button = QPushButton("Clear history")
        self.clear_button.setObjectName("clearHistory")
        self.clear_button.setFont(ui_font(13, QFont.Weight.Medium))
        self.clear_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.clear_button.setFixedHeight(34)
        self.clear_button.clicked.connect(lambda: on_clear())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 16, 8, 14)
        layout.setSpacing(8)
        title_row = QHBoxLayout()
        title_row.setContentsMargins(12, 0, 12, 4)
        title_row.addWidget(self._title)
        layout.addLayout(title_row)
        layout.addWidget(self.list, 1)
        layout.addWidget(self._empty, 1)
        button_row = QHBoxLayout()
        button_row.setContentsMargins(8, 0, 8, 0)
        button_row.addWidget(self.clear_button)
        layout.addLayout(button_row)

    def apply_theme(self, theme: Theme) -> None:
        self._delegate.theme = theme
        self.list.viewport().update()

    def set_entries(self, entries: list[HistoryEntry]) -> None:
        self.list.clear()
        for entry in entries:
            self._add_item(entry, self.list.count())
        self._update_empty_state()

    def prepend(self, entry: HistoryEntry) -> None:
        self._add_item(entry, 0)
        self._update_empty_state()
        self.list.scrollToTop()

    def _add_item(self, entry: HistoryEntry, row: int) -> None:
        item = QListWidgetItem()
        item.setData(_ENTRY_ROLE, entry)
        item.setToolTip(f"{entry.expression} {entry.result}\nClick to use this result")
        self.list.insertItem(row, item)

    def _update_empty_state(self) -> None:
        has_entries = self.list.count() > 0
        self.list.setVisible(has_entries)
        self._empty.setVisible(not has_entries)
        self.clear_button.setEnabled(has_entries)


# --- App icon ---------------------------------------------------------------


def make_app_icon() -> QIcon:
    """Draw the app icon: a coral tile with the four essential symbols."""
    size = 1024
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # macOS icons sit inside a margin and have generously rounded corners.
    tile = QRectF(100, 100, 824, 824)
    gradient = QLinearGradient(tile.topLeft(), tile.bottomRight())
    gradient.setColorAt(0.0, QColor("#FF9472"))
    gradient.setColorAt(1.0, QColor("#E2502E"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(gradient)
    painter.drawRoundedRect(tile, 186, 186)

    pen = QPen(QColor("#FFFFFF"), 62)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    arm = 82
    left, right, top, bottom = 340, 684, 340, 684
    # Plus.
    painter.drawLine(left - arm, top, left + arm, top)
    painter.drawLine(left, top - arm, left, top + arm)
    # Minus.
    painter.drawLine(right - arm, top, right + arm, top)
    # Times.
    diagonal = round(arm * 0.76)
    painter.drawLine(
        left - diagonal, bottom - diagonal, left + diagonal, bottom + diagonal
    )
    painter.drawLine(
        left - diagonal, bottom + diagonal, left + diagonal, bottom - diagonal
    )
    # Equals.
    painter.drawLine(right - arm, bottom - 50, right + arm, bottom - 50)
    painter.drawLine(right - arm, bottom + 50, right + arm, bottom + 50)
    painter.end()

    icon = QIcon()
    for edge in (16, 32, 64, 128, 256, 512, 1024):
        icon.addPixmap(
            pixmap.scaled(
                edge,
                edge,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
    return icon


# --- Key layout -------------------------------------------------------------

# Each entry: (label, engine key, colour role, tooltip).
_BUTTON_ROWS: tuple[tuple[tuple[str, str, str, str], ...], ...] = (
    (
        ("MC", "MC", "memory", "Clear memory  (L)"),
        ("MR", "MR", "memory", "Recall memory  (K)"),
        ("M+", "M+", "memory", "Add to memory  (M)"),
        ("M−", "M-", "memory", "Subtract from memory  (Shift+M)"),
        ("⌫", "backspace", "memory", "Delete  (Backspace)"),
    ),
    (
        ("AC", "AC", "function", "All clear  (A)"),
        ("C", "C", "function", "Clear entry  (Esc or C)"),
        ("(", "(", "function", "Open parenthesis, key: ("),
        (")", ")", "function", "Close parenthesis, key: )"),
        ("÷", "/", "operator", "Divide  (/)"),
    ),
    (
        ("√", "sqrt", "function", "Square root  (R)"),
        ("7", "7", "digit", ""),
        ("8", "8", "digit", ""),
        ("9", "9", "digit", ""),
        ("×", "*", "operator", "Multiply  (* or X)"),
    ),
    (
        ("x²", "square", "function", "Square  (Q)"),
        ("4", "4", "digit", ""),
        ("5", "5", "digit", ""),
        ("6", "6", "digit", ""),
        ("−", "-", "operator", "Subtract  (-)"),
    ),
    (
        ("¹⁄ₓ", "reciprocal", "function", "Reciprocal, 1/x  (I)"),
        ("1", "1", "digit", ""),
        ("2", "2", "digit", ""),
        ("3", "3", "digit", ""),
        ("+", "+", "operator", "Add  (+)"),
    ),
    (
        ("%", "%", "function", "Percent  (%)"),
        ("±", "negate", "function", "Change sign  (N)"),
        ("0", "0", "digit", ""),
        (".", ".", "digit", ""),
        ("=", "=", "equals", "Equals  (Enter or =)"),
    ),
)

# Keys identified by the text they type.
_TEXT_KEYS = {
    **{digit: digit for digit in "0123456789"},
    ".": ".",
    ",": ".",
    "+": "+",
    "-": "-",
    "−": "-",
    "*": "*",
    "×": "*",
    "x": "*",
    "X": "*",
    "/": "/",
    "÷": "/",
    "=": "=",
    "%": "%",
    "(": "(",
    ")": ")",
}

# Letter shortcuts. The Shift state is checked first, for M- versus M+.
_LETTER_KEYS = {
    Qt.Key.Key_A: "AC",
    Qt.Key.Key_C: "C",
    Qt.Key.Key_N: "negate",
    Qt.Key.Key_R: "sqrt",
    Qt.Key.Key_Q: "square",
    Qt.Key.Key_I: "reciprocal",
    Qt.Key.Key_M: "M+",
    Qt.Key.Key_K: "MR",
    Qt.Key.Key_L: "MC",
}

_SPECIAL_KEYS = {
    Qt.Key.Key_Return: "=",
    Qt.Key.Key_Enter: "=",
    Qt.Key.Key_Backspace: "backspace",
    Qt.Key.Key_Delete: "backspace",
    Qt.Key.Key_Escape: "C",
}


def engine_key_for_event(event: QKeyEvent) -> Optional[str]:
    """Translate a key event to an engine key, or None if it isn't one."""
    modifiers = event.modifiers()
    # On macOS, Qt's ControlModifier is Cmd. Those belong to the menu bar.
    command_like = (
        Qt.KeyboardModifier.ControlModifier
        | Qt.KeyboardModifier.MetaModifier
        | Qt.KeyboardModifier.AltModifier
    )
    if modifiers & command_like:
        return None
    key = Qt.Key(event.key())
    if key in _SPECIAL_KEYS:
        return _SPECIAL_KEYS[key]
    if key == Qt.Key.Key_M and modifiers & Qt.KeyboardModifier.ShiftModifier:
        return "M-"
    if event.text() in _TEXT_KEYS:
        return _TEXT_KEYS[event.text()]
    return _LETTER_KEYS.get(key)


# --- Main window ------------------------------------------------------------


class MainWindow(QMainWindow):
    def __init__(
        self,
        settings: Optional[QSettings] = None,
        history: Optional[HistoryStore] = None,
    ):
        super().__init__()
        self.setWindowTitle("Calculator")
        self.setObjectName("mainWindow")

        self.engine = Calculator()
        self.settings = settings if settings is not None else QSettings()
        self.history = history if history is not None else HistoryStore()
        self.theme = DARK_THEME
        self.buttons: dict[str, CalcButton] = {}
        self._applying_mode = False

        # Short-lived messages shown in place of the normal display text.
        self._value_message: Optional[str] = None
        self._expression_message: Optional[str] = None
        self._message_timer = QTimer(self)
        self._message_timer.setSingleShot(True)
        self._message_timer.timeout.connect(self._clear_messages)

        self._build_ui()
        self._build_menus()
        self.history_panel.set_entries(self.history.entries)

        # Everything is restored from settings before the window first appears.
        mode = str(self.settings.value("theme", MODE_SYSTEM))
        self._theme_mode = mode if mode in THEME_MODES else MODE_SYSTEM
        self._apply_theme_mode()
        QGuiApplication.styleHints().colorSchemeChanged.connect(
            lambda _scheme: self._refresh_theme()
        )
        self.history_panel.setVisible(
            self.settings.value("historyOpen", False, type=bool)
        )
        self._sync_history_controls()
        self._restore_geometry()
        self._refresh()

    # --- Construction -------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        pane = QVBoxLayout()
        pane.setContentsMargins(14, 10, 14, 14)
        pane.setSpacing(4)
        pane.addLayout(self._build_toolbar())

        self.expression_label = FitLabel(
            max_pixels=17, min_pixels=11, weight=QFont.Weight.Normal
        )
        self.expression_label.setMinimumHeight(24)
        self.expression_label.setMaximumHeight(30)
        self.value_label = FitLabel(
            max_pixels=VALUE_TEXT_PIXELS, min_pixels=13, weight=QFont.Weight.Light
        )
        self.value_label.setMinimumHeight(56)
        pane.addSpacing(2)
        pane.addWidget(self.expression_label)
        pane.addWidget(self.value_label, 2)
        pane.addSpacing(8)
        pane.addLayout(self._build_keypad(), 8)
        root.addLayout(pane, 1)

        self.history_panel = HistoryPanel(self._load_history_entry, self._clear_history)
        root.addWidget(self.history_panel)

    def _build_toolbar(self) -> QHBoxLayout:
        self.theme_button = IconButton(MODE_SYSTEM)
        self.theme_button.clicked.connect(self._cycle_theme_mode)

        self.memory_indicator = QLabel("M")
        self.memory_indicator.setObjectName("memoryIndicator")
        self.memory_indicator.setFont(ui_font(11, QFont.Weight.Bold))
        self.memory_indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.memory_indicator.setFixedSize(24, 18)
        # Reserve its space, so that nothing shifts when it appears.
        policy = self.memory_indicator.sizePolicy()
        policy.setRetainSizeWhenHidden(True)
        self.memory_indicator.setSizePolicy(policy)

        self.history_button = IconButton("history")
        self.history_button.setCheckable(True)
        self.history_button.setToolTip("Show or hide history  (H)")
        self.history_button.clicked.connect(self._set_history_open)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        toolbar.addWidget(self.theme_button)
        toolbar.addWidget(self.memory_indicator)
        toolbar.addStretch(1)
        toolbar.addWidget(self.history_button)
        return toolbar

    def _build_keypad(self) -> QGridLayout:
        grid = QGridLayout()
        grid.setSpacing(8)
        for row, buttons in enumerate(_BUTTON_ROWS):
            # The memory row is deliberately shorter than the others.
            grid.setRowStretch(row, 3 if row == 0 else 5)
            for column, (label, key, role, tooltip) in enumerate(buttons):
                button = CalcButton(label, role, tooltip)
                button.clicked.connect(lambda _=False, k=key: self.press(k))
                if key == "backspace":
                    button.setAutoRepeat(True)
                    button.setAutoRepeatDelay(400)
                    button.setAutoRepeatInterval(70)
                self.buttons[key] = button
                grid.addWidget(button, row, column)
        for column in range(5):
            grid.setColumnStretch(column, 1)
        return grid

    def _build_menus(self) -> None:
        """Native menu bar, which also owns the Cmd shortcuts."""
        bar = self.menuBar()

        edit = bar.addMenu("Edit")
        copy_action = QAction("Copy Result", self)
        copy_action.setShortcut(QKeySequence.StandardKey.Copy)
        copy_action.triggered.connect(self.copy_result)
        edit.addAction(copy_action)
        paste_action = QAction("Paste", self)
        paste_action.setShortcut(QKeySequence.StandardKey.Paste)
        paste_action.triggered.connect(self.paste_clipboard)
        edit.addAction(paste_action)
        edit.addSeparator()
        clear_action = QAction("Clear History", self)
        clear_action.triggered.connect(self._clear_history)
        edit.addAction(clear_action)

        view = bar.addMenu("View")
        self.history_action = QAction("Show History", self)
        self.history_action.setCheckable(True)
        self.history_action.setShortcut(QKeySequence("Ctrl+Y"))
        self.history_action.triggered.connect(self._set_history_open)
        view.addAction(self.history_action)

        appearance = view.addMenu("Appearance")
        group = QActionGroup(self)
        self.mode_actions: dict[str, QAction] = {}
        for mode in THEME_MODES:
            action = QAction(MODE_LABELS[mode], self)
            action.setCheckable(True)
            action.triggered.connect(lambda _=False, m=mode: self.set_theme_mode(m))
            group.addAction(action)
            appearance.addAction(action)
            self.mode_actions[mode] = action

        window_menu = bar.addMenu("Window")
        minimize_action = QAction("Minimize", self)
        minimize_action.setShortcut(QKeySequence("Ctrl+M"))
        minimize_action.triggered.connect(self.showMinimized)
        window_menu.addAction(minimize_action)
        close_action = QAction("Close", self)
        close_action.setShortcut(QKeySequence.StandardKey.Close)
        close_action.triggered.connect(self.close)
        window_menu.addAction(close_action)

        help_menu = bar.addMenu("Help")
        # On macOS, Qt moves this into the app menu, where About belongs.
        about_action = QAction("About Calculator", self)
        about_action.setMenuRole(QAction.MenuRole.AboutRole)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
        shortcuts_action = QAction("Keyboard Shortcuts", self)
        shortcuts_action.triggered.connect(lambda: self.shortcuts_box().exec())
        help_menu.addAction(shortcuts_action)
        help_menu.addSeparator()
        github_action = QAction("Calculator on GitHub", self)
        github_action.triggered.connect(lambda: open_url(PROJECT_URL))
        help_menu.addAction(github_action)
        updates_action = QAction("Check for Updates…", self)
        updates_action.triggered.connect(lambda: open_url(LATEST_RELEASE_URL))
        help_menu.addAction(updates_action)

    # --- Help ---------------------------------------------------------------

    def about_box(self) -> tuple[QMessageBox, QPushButton]:
        """The About window and its "View on GitHub" button, not yet shown."""
        box = QMessageBox(self)
        box.setWindowTitle("About Calculator")
        box.setIconPixmap(make_app_icon().pixmap(96, 96))
        box.setText("Calculator")
        box.setInformativeText(f"Version {__version__}")
        github = box.addButton("View on GitHub", QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Ok)
        return box, github

    def show_about(self) -> None:
        box, github = self.about_box()
        box.exec()
        if box.clickedButton() is github:
            open_url(PROJECT_URL)

    def shortcuts_box(self) -> QMessageBox:
        """The Keyboard Shortcuts window, not yet shown."""
        rows = "".join(
            f"<tr><td>{action}</td><td style='padding-left:16px'><b>{keys}</b></td></tr>"
            for action, keys in KEYBOARD_SHORTCUTS
        )
        box = QMessageBox(self)
        box.setWindowTitle("Keyboard Shortcuts")
        box.setText("Keyboard Shortcuts")
        box.setInformativeText(f"<table>{rows}</table>")
        box.addButton(QMessageBox.StandardButton.Ok)
        return box

    def _restore_geometry(self) -> None:
        geometry = self.settings.value("geometry")
        restored = isinstance(geometry, QByteArray) and self.restoreGeometry(geometry)
        if not restored:
            width = DEFAULT_WINDOW_SIZE.width()
            if self.history_panel.isVisibleTo(self):
                width += HISTORY_PANEL_WIDTH
            self.resize(width, DEFAULT_WINDOW_SIZE.height())

    # --- Key handling -------------------------------------------------------

    def press(self, key: str) -> None:
        """Forward a key to the engine, then update the screen."""
        try:
            self.engine.press(key)
            completed = self.engine.take_completed()
            if completed is not None:
                entry = self.history.add(
                    completed.expression, completed.result, completed.value
                )
                self.history_panel.prepend(entry)
        except Exception:  # A bug must never take down the whole app.
            logger.exception("Unexpected error handling key %r", key)
            self.engine.all_clear()
        self._clear_messages(refresh=False)
        self._refresh()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = engine_key_for_event(event)
        if key is not None:
            self.press(key)
            self.buttons[key].flash()
            return
        modifiers = event.modifiers() & ~Qt.KeyboardModifier.KeypadModifier
        if modifiers == Qt.KeyboardModifier.NoModifier:
            if event.key() == Qt.Key.Key_H:
                self._set_history_open(not self.history_panel.isVisible())
                return
            if event.key() == Qt.Key.Key_T:
                self._cycle_theme_mode()
                return
        super().keyPressEvent(event)

    # --- Copy and paste -----------------------------------------------------

    def copy_result(self) -> None:
        text = self.engine.copy_text
        if text:
            QGuiApplication.clipboard().setText(text)
            self._show_expression_message("Copied")

    def paste_clipboard(self) -> None:
        text = QGuiApplication.clipboard().text()
        try:
            accepted = self.engine.paste(text)
        except Exception:
            logger.exception("Unexpected error pasting")
            accepted = False
        if accepted:
            self._clear_messages(refresh=False)
            self._refresh()
        else:
            self._show_value_message(INVALID_INPUT_MESSAGE)

    # --- Rendering ----------------------------------------------------------

    def _refresh(self) -> None:
        """Copy the engine's state to the screen."""
        engine = self.engine
        value = self._value_message or engine.display.replace("-", "−")
        is_error = self._value_message is not None or engine.error is not None
        self.value_label.set_text(value)
        self.value_label.set_color(self.theme.error if is_error else self.theme.text)
        self.value_label.set_max_pixels(
            ERROR_TEXT_PIXELS if is_error else VALUE_TEXT_PIXELS
        )
        self.value_label.setAccessibleName(value)

        expression = self._expression_message or engine.expression
        self.expression_label.set_text(expression)
        self.expression_label.setToolTip(engine.expression)
        self.expression_label.set_color(
            self.theme.accent if self._expression_message else self.theme.muted
        )

        self.memory_indicator.setVisible(engine.has_memory)
        self.memory_indicator.setToolTip(
            f"Memory: {engine.memory_display.replace('-', '−')}"
        )
        self.buttons["MC"].setEnabled(engine.has_memory)
        self.buttons["MR"].setEnabled(engine.has_memory)

    def _show_value_message(self, message: str) -> None:
        self._value_message = message
        self._message_timer.start(TRANSIENT_MESSAGE_MS)
        self._refresh()

    def _show_expression_message(self, message: str) -> None:
        self._expression_message = message
        self._message_timer.start(TRANSIENT_MESSAGE_MS)
        self._refresh()

    def _clear_messages(self, refresh: bool = True) -> None:
        self._message_timer.stop()
        self._value_message = None
        self._expression_message = None
        if refresh:
            self._refresh()

    # --- History ------------------------------------------------------------

    def _load_history_entry(self, entry: HistoryEntry) -> None:
        self.engine.load_value(entry.value)
        self._clear_messages(refresh=False)
        self._refresh()

    def _clear_history(self) -> None:
        self.history.clear()
        self.history_panel.set_entries([])

    def _set_history_open(self, is_open: bool) -> None:
        """Show or hide the panel, widening the window rather than the keypad."""
        if is_open == self.history_panel.isVisible():
            self._sync_history_controls()
            return
        can_resize = not (self.isMaximized() or self.isFullScreen())
        # Measure first: showing the panel can itself grow the window to fit.
        delta = HISTORY_PANEL_WIDTH if is_open else -HISTORY_PANEL_WIDTH
        target_width = self.width() + delta
        self.history_panel.setVisible(is_open)
        if can_resize:
            # Both layouts must recalculate, or the old minimum width still holds.
            self.centralWidget().layout().activate()
            self.layout().activate()
            self.resize(target_width, self.height())
        self._sync_history_controls()

    def _sync_history_controls(self) -> None:
        is_open = self.history_panel.isVisibleTo(self)
        self.history_button.setChecked(is_open)
        self.history_action.setChecked(is_open)

    # --- Themes -------------------------------------------------------------

    def set_theme_mode(self, mode: str) -> None:
        self._theme_mode = mode
        self.settings.setValue("theme", mode)
        self._apply_theme_mode()

    def _cycle_theme_mode(self) -> None:
        index = THEME_MODES.index(self._theme_mode)
        self.set_theme_mode(THEME_MODES[(index + 1) % len(THEME_MODES)])

    def _apply_theme_mode(self) -> None:
        # Telling Qt about the mode also switches the native title bar to match.
        scheme = {
            MODE_SYSTEM: Qt.ColorScheme.Unknown,
            MODE_LIGHT: Qt.ColorScheme.Light,
            MODE_DARK: Qt.ColorScheme.Dark,
        }[self._theme_mode]
        self._applying_mode = True
        try:
            QGuiApplication.styleHints().setColorScheme(scheme)
        finally:
            self._applying_mode = False
        self._refresh_theme()

    def _resolved_theme(self) -> Theme:
        if self._theme_mode == MODE_LIGHT:
            return LIGHT_THEME
        if self._theme_mode == MODE_DARK:
            return DARK_THEME
        scheme = QGuiApplication.styleHints().colorScheme()
        return DARK_THEME if scheme == Qt.ColorScheme.Dark else LIGHT_THEME

    def _refresh_theme(self) -> None:
        if self._applying_mode:
            return  # Called straight afterwards, by _apply_theme_mode.
        self.theme = self._resolved_theme()
        theme = self.theme
        self.setStyleSheet(
            f"""
            #mainWindow, #central {{ background: {theme.window}; }}
            #historyPanel {{
                background: {theme.panel};
                border-left: 1px solid {theme.divider};
            }}
            #historyTitle {{ color: {theme.text}; background: transparent; }}
            #historyEmpty {{ color: {theme.muted}; background: transparent; }}
            #historyList {{ background: transparent; outline: none; }}
            #historyList QScrollBar:vertical {{
                background: transparent; width: 8px; margin: 2px;
            }}
            #historyList QScrollBar::handle:vertical {{
                background: {theme.divider}; border-radius: 2px; min-height: 28px;
            }}
            #historyList QScrollBar::add-line:vertical,
            #historyList QScrollBar::sub-line:vertical {{ height: 0; }}
            #historyList QScrollBar::add-page:vertical,
            #historyList QScrollBar::sub-page:vertical {{ background: transparent; }}
            #clearHistory {{
                color: {theme.text};
                background: {theme.row_hover};
                border: none;
                border-radius: 10px;
            }}
            #clearHistory:hover {{ background: {theme.divider}; }}
            #clearHistory:pressed {{ background: {theme.accent_soft}; }}
            #clearHistory:disabled {{ color: {theme.muted}; background: transparent; }}
            #memoryIndicator {{
                color: {theme.accent};
                background: {theme.accent_soft};
                border-radius: 6px;
            }}
            """
        )
        for button in self.buttons.values():
            button.apply_theme(theme)
        self.theme_button.apply_theme(theme)
        self.history_button.apply_theme(theme)
        self.history_panel.apply_theme(theme)

        self.theme_button.set_glyph(self._theme_mode)
        self.theme_button.setToolTip(
            f"Appearance: {MODE_LABELS[self._theme_mode]}  (T to change)"
        )
        self.mode_actions[self._theme_mode].setChecked(True)
        self._refresh()

    # --- Persistence --------------------------------------------------------

    def _save_settings(self) -> None:
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("historyOpen", self.history_panel.isVisibleTo(self))
        self.settings.setValue("theme", self._theme_mode)
        self.settings.sync()

    def closeEvent(self, event: QEvent) -> None:
        self._save_settings()
        super().closeEvent(event)


def open_url(url: str) -> None:
    """Open a web page in the default browser."""
    if not QDesktopServices.openUrl(QUrl(url)):
        logger.warning("Could not open %s", url)


def set_macos_app_name(name: str) -> None:
    """Make the macOS menu bar say ``name`` rather than "Python".

    macOS reads the name from the running bundle's info dictionary, so it is
    updated here using the Objective-C runtime. Purely cosmetic: failure is fine.
    The packaged app doesn't need this, as its Info.plist already has the name.
    """
    if sys.platform != "darwin" or hasattr(sys, "frozen"):
        return
    try:
        import ctypes
        import ctypes.util

        ctypes.cdll.LoadLibrary(ctypes.util.find_library("Foundation"))
        objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
        objc.objc_getClass.restype = ctypes.c_void_p
        objc.objc_getClass.argtypes = [ctypes.c_char_p]
        objc.sel_registerName.restype = ctypes.c_void_p
        objc.sel_registerName.argtypes = [ctypes.c_char_p]
        send_address = ctypes.cast(objc.objc_msgSend, ctypes.c_void_p).value
        pointer = ctypes.c_void_p
        send = ctypes.CFUNCTYPE(pointer, pointer, pointer)(send_address)
        send_string = ctypes.CFUNCTYPE(pointer, pointer, pointer, ctypes.c_char_p)(
            send_address
        )
        send_pair = ctypes.CFUNCTYPE(pointer, pointer, pointer, pointer, pointer)(
            send_address
        )

        select = objc.sel_registerName
        ns_string = objc.objc_getClass(b"NSString")
        make_string = select(b"stringWithUTF8String:")
        bundle = send(objc.objc_getClass(b"NSBundle"), select(b"mainBundle"))
        info = send(bundle, select(b"infoDictionary"))
        send_pair(
            info,
            select(b"setObject:forKey:"),
            send_string(ns_string, make_string, name.encode()),
            send_string(ns_string, make_string, b"CFBundleName"),
        )
    except Exception:
        logger.debug("Could not set the macOS app name", exc_info=True)


def create_application(arguments: list[str]) -> QApplication:
    """Create the QApplication with the identity that QSettings relies on."""
    set_macos_app_name("Calculator")
    app = QApplication(arguments)
    app.setApplicationName("Calculator")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("Calculator")
    app.setOrganizationDomain("calculator.local")
    app.setWindowIcon(make_app_icon())
    return app


def run() -> int:
    """Create the application and run it until the window closes."""
    app = create_application(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()
