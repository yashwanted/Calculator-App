"""Custom-painted widgets: keypad buttons, toolbar buttons and the display."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QObject,
    QPointF,
    QRectF,
    QSize,
    Qt,
    QTimer,
    QVariantAnimation,
)
from PySide6.QtGui import (
    QColor,
    QGuiApplication,
    QFont,
    QFontMetricsF,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
)
from PySide6.QtWidgets import QAbstractButton, QSizePolicy, QWidget

from .theme import (
    DARK_THEME,
    MODE_DARK,
    MODE_LIGHT,
    MODE_SYSTEM,
    Theme,
    blend,
    ui_font,
)

KEY_FLASH_MS = 110  # How long a button lights up for a keyboard press.


def reduced_motion() -> bool:
    """True when macOS's Reduce Motion setting is on."""
    hints = QGuiApplication.styleHints()
    return (
        hints is not None
        and hints.accessibility().motionPreference() == Qt.MotionPreference.ReducedMotion
    )



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
        if reduced_motion():
            self._step(target)  # Jump straight to the end state.
            return
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
        self._border = QColor(0, 0, 0, 0)
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
        self._border = QColor(theme.button_border)
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

        # The whole button shrinks slightly while pressed, unless Reduce Motion
        # is on, in which case only its colour changes.
        scale = 1.0 if reduced_motion() else 1.0 - 0.05 * self._press.value
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

        background = blend(
            blend(
                QColor(self._colors.background),
                QColor(self._colors.hover),
                self._hover.value,
            ),
            QColor(self._colors.pressed),
            self._press.value,
        )
        if self._border.alpha() and self.role != "memory":
            painter.setPen(QPen(self._border, 1.2))
        else:
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
        background = blend(idle, QColor(self._theme.row_hover), self._hover.value)
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
