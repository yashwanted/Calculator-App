"""Tests for the menus and Help windows, using an invisible Qt platform."""

import os
import re
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtGui import QAction, QKeySequence  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from calculator import __version__, ui  # noqa: E402
from calculator.history import HistoryStore  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app, tmp_path):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    window = ui.MainWindow(settings, HistoryStore(tmp_path / "history.json"))
    yield window
    window.close()


def menu_actions(window, title):
    for menu_action in window.menuBar().actions():
        if menu_action.text() == title:
            return {action.text(): action for action in menu_action.menu().actions()}
    raise AssertionError(f"No {title} menu")


def test_window_menu_has_minimize(window):
    actions = menu_actions(window, "Window")
    assert list(actions)[:2] == ["Minimize", "Close"]
    assert actions["Minimize"].shortcut() == QKeySequence("Ctrl+M")


def test_help_menu_items(window):
    actions = menu_actions(window, "Help")
    for title in (
        "About Calculator",
        "Keyboard Shortcuts",
        "Calculator on GitHub",
        "Check for Updates…",
    ):
        assert title in actions
    assert actions["About Calculator"].menuRole() == QAction.MenuRole.AboutRole


@pytest.mark.parametrize(
    "title, url",
    [
        ("Calculator on GitHub", ui.PROJECT_URL),
        ("Check for Updates…", ui.LATEST_RELEASE_URL),
    ],
)
def test_help_links_open_the_right_page(window, monkeypatch, title, url):
    opened = []
    monkeypatch.setattr(ui, "open_url", opened.append)
    menu_actions(window, "Help")[title].trigger()
    assert opened == [url]


def test_about_window_shows_version_without_personal_name(window):
    box, github = window.about_box()
    assert box.text() == "Calculator"
    assert __version__ in box.informativeText()
    assert github.text() == "View on GitHub"
    shown = " ".join([box.windowTitle(), box.text(), box.informativeText()])
    assert "yashwant" not in shown.lower()


def test_shortcuts_window_lists_every_letter_key(window):
    listed = set()
    for _action, keys in ui.KEYBOARD_SHORTCUTS:
        listed.update(re.split(r", | or ", keys))
    letters = {chr(key.value) for key in ui._LETTER_KEYS} | {"H", "T"}
    assert letters <= listed
    text = window.shortcuts_box().informativeText()
    for action, keys in ui.KEYBOARD_SHORTCUTS:
        assert action in text and keys in text
