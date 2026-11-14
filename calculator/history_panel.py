"""The history side panel: past calculations, newest first."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QModelIndex, QObject, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
)

from .history import HistoryEntry
from .theme import DARK_THEME, Theme, ui_font

HISTORY_PANEL_WIDTH = 280


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
