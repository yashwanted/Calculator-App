"""Checks that a built app really works, run by build_app.sh after each build.

``Calculator --self-test result.json`` starts the real UI from inside the
bundle, types a calculation with real key events, and checks saving and
restoring. It uses a temporary folder, so your own history and settings are
never read or changed. The window is on screen only for a moment.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import (
    QElapsedTimer,
    QEvent,
    QSettings,
    Qt,
    qInstallMessageHandler,
)
from PySide6.QtGui import QKeyEvent

from . import __version__
from .history import HistoryStore, default_history_path
from .ui import MainWindow, create_application

_KEYS = {
    "2": Qt.Key.Key_2,
    "3": Qt.Key.Key_3,
    "4": Qt.Key.Key_4,
    "+": Qt.Key.Key_Plus,
    "*": Qt.Key.Key_Asterisk,
    "=": Qt.Key.Key_Equal,
}


def _wait(app, milliseconds: int) -> None:
    timer = QElapsedTimer()
    timer.start()
    while timer.elapsed() < milliseconds:
        app.processEvents()


def _type(app, window: MainWindow, text: str) -> None:
    for char in text:
        event = QKeyEvent(
            QEvent.Type.KeyPress, _KEYS[char], Qt.KeyboardModifier.NoModifier, char
        )
        app.sendEvent(window, event)


def _check_saved_state(app, folder: Path) -> list[str]:
    """Use the window, close it, and confirm that a new window restores it all."""
    problems: list[str] = []
    settings = QSettings(str(folder / "settings.ini"), QSettings.Format.IniFormat)
    history_path = folder / "history.json"

    window = MainWindow(settings, HistoryStore(history_path))
    window.show()
    _wait(app, 200)
    _type(app, window, "2+3*4=")
    if window.value_label.text() != "14":
        problems.append(f"2+3*4 displayed {window.value_label.text()!r}")
    for mode in ("light", "dark"):
        window.set_theme_mode(mode)
        _wait(app, 50)
        if window.grab().isNull():
            problems.append(f"could not render the {mode} theme")
    window._set_history_open(True)
    _wait(app, 50)
    window.close()

    restored = MainWindow(settings, HistoryStore(history_path))
    restored.show()
    _wait(app, 100)
    if [entry.result for entry in restored.history.entries] != ["14"]:
        problems.append("history was not restored")
    if not restored.history_panel.isVisible():
        problems.append("history panel state was not restored")
    if restored._theme_mode != "dark":
        problems.append("theme was not restored")
    restored.close()
    return problems


def run_self_test(output_path: str) -> int:
    """Write a JSON report to ``output_path``; return 0 if everything passed."""
    report: dict = {"version": __version__, "frozen": hasattr(sys, "frozen")}
    problems: list[str] = []
    qt_messages: list[str] = []
    try:
        qInstallMessageHandler(lambda _type, _context, text: qt_messages.append(text))
        app = create_application(["Calculator"])
        report["platform"] = app.platformName()
        report["settings_file"] = QSettings().fileName()
        report["history_file"] = str(default_history_path())

        if app.platformName() != "cocoa":
            problems.append(f"unexpected platform {app.platformName()}")
        if report["frozen"]:
            bundle = Path(sys.executable).resolve().parents[2]
            report["bundle"] = str(bundle)
            for key in ("settings_file", "history_file"):
                if Path(report[key]).resolve().is_relative_to(bundle):
                    problems.append(f"{key} is inside the app bundle")
        with tempfile.TemporaryDirectory() as folder:
            problems += _check_saved_state(app, Path(folder))
        problems += [f"Qt: {message}" for message in qt_messages]
    except Exception as error:  # The report must be written whatever goes wrong.
        problems.append(f"{type(error).__name__}: {error}")

    report["problems"] = problems
    report["passed"] = not problems
    Path(output_path).write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0 if not problems else 1
