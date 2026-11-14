"""The main window, its menus, and app start-up.

All arithmetic lives in ``calculator.engine``. This module only forwards key
presses to it and renders whatever it reports. The pieces it is built from live
in ``theme``, ``widgets``, ``history_panel``, ``keys`` and ``icon``.
"""

from __future__ import annotations

import logging
import sys
from typing import Optional

from PySide6.QtCore import QByteArray, QEvent, QSettings, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QDesktopServices,
    QFont,
    QGuiApplication,
    QKeyEvent,
    QKeySequence,
)
from PySide6.QtWidgets import (
    QApplication,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .engine import Calculator, INVALID_INPUT_MESSAGE
from .history import HistoryEntry, HistoryStore
from .history_panel import HISTORY_PANEL_WIDTH, HistoryPanel
from .icon import make_app_icon
from .keys import BUTTON_ROWS, KEYBOARD_SHORTCUTS, engine_key_for_event
from .theme import (
    DARK_THEME,
    LIGHT_THEME,
    MODE_DARK,
    MODE_LABELS,
    MODE_LIGHT,
    MODE_SYSTEM,
    THEME_MODES,
    Theme,
    ui_font,
)
from .widgets import CalcButton, FitLabel, IconButton

logger = logging.getLogger(__name__)

DEFAULT_WINDOW_SIZE = QSize(380, 640)
TRANSIENT_MESSAGE_MS = 1400
VALUE_TEXT_PIXELS = 76
ERROR_TEXT_PIXELS = 32  # Errors should be readable, not shouted.

PROJECT_URL = "https://github.com/yashwanted/Calculator-App"
LATEST_RELEASE_URL = f"{PROJECT_URL}/releases/latest"


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
        for row, buttons in enumerate(BUTTON_ROWS):
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
