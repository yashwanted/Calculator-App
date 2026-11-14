"""Tests for the main window, driven by real clicks and key presses.

Qt draws off screen here, so no window appears while they run.
"""

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QEvent, QSettings, Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication, QKeyEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from calculator import ui  # noqa: E402
from calculator.history import HistoryStore  # noqa: E402
from calculator.history_panel import HISTORY_PANEL_WIDTH  # noqa: E402
from calculator.keys import engine_key_for_event  # noqa: E402
from calculator.theme import DARK_THEME, LIGHT_THEME  # noqa: E402

NO_MODIFIER = Qt.KeyboardModifier.NoModifier


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def folder(tmp_path):
    return tmp_path


def make_window(folder):
    settings = QSettings(str(folder / "settings.ini"), QSettings.Format.IniFormat)
    window = ui.MainWindow(settings, HistoryStore(folder / "history.json"))
    window.show()
    return window


@pytest.fixture
def window(app, folder):
    window = make_window(folder)
    yield window
    window.close()


def click(window, *keys):
    for key in keys:
        QTest.mouseClick(window.buttons[key], Qt.MouseButton.LeftButton)


def type_text(window, text):
    for char in text:
        QTest.keyClick(window, char)


def shown_value(window):
    return window.value_label.text()


# --- Clicking and typing -----------------------------------------------------


def test_clicking_buttons_calculates(window):
    click(window, "2", "+", "3", "*", "4", "=")
    assert shown_value(window) == "14"
    assert window.expression_label.text() == "2 + 3 × 4 ="


def test_typing_calculates(window):
    type_text(window, "12/4=")
    assert shown_value(window) == "3"


def test_enter_and_escape_keys(window):
    type_text(window, "7*6")
    QTest.keyClick(window, Qt.Key.Key_Return)
    assert shown_value(window) == "42"
    type_text(window, "5")
    QTest.keyClick(window, Qt.Key.Key_Escape)
    assert shown_value(window) == "0"


def test_backspace_button_and_key(window):
    type_text(window, "1234")
    click(window, "backspace")
    QTest.keyClick(window, Qt.Key.Key_Backspace)
    assert shown_value(window) == "12"


def test_negative_results_use_a_real_minus_sign(window):
    type_text(window, "3-5=")
    assert shown_value(window) == "−2"


def test_error_is_shown_in_the_error_colour_and_cleared_by_next_key(window):
    type_text(window, "1/0=")
    assert shown_value(window) == "Can't divide by zero"
    assert window.value_label._color.name() == window.theme.error.lower()
    type_text(window, "5")
    assert shown_value(window) == "5"


def test_memory_buttons_and_indicator(window):
    assert not window.memory_indicator.isVisibleTo(window)
    assert not window.buttons["MR"].isEnabled()
    type_text(window, "7")
    click(window, "M+")
    assert window.memory_indicator.isVisibleTo(window)
    assert window.buttons["MR"].isEnabled()
    click(window, "AC", "MR")
    assert shown_value(window) == "7"
    click(window, "MC")
    assert not window.buttons["MR"].isEnabled()


@pytest.mark.parametrize(
    "key, text, modifiers, expected",
    [
        (Qt.Key.Key_5, "5", NO_MODIFIER, "5"),
        (Qt.Key.Key_Asterisk, "*", NO_MODIFIER, "*"),
        (Qt.Key.Key_X, "x", NO_MODIFIER, "*"),
        (Qt.Key.Key_Comma, ",", NO_MODIFIER, "."),
        (Qt.Key.Key_M, "m", NO_MODIFIER, "M+"),
        (Qt.Key.Key_M, "M", Qt.KeyboardModifier.ShiftModifier, "M-"),
        (Qt.Key.Key_Enter, "\r", Qt.KeyboardModifier.KeypadModifier, "="),
        (Qt.Key.Key_C, "c", Qt.KeyboardModifier.ControlModifier, None),
        (Qt.Key.Key_H, "h", NO_MODIFIER, None),
    ],
)
def test_key_translation(app, key, text, modifiers, expected):
    event = QKeyEvent(QEvent.Type.KeyPress, key, modifiers, text)
    assert engine_key_for_event(event) == expected


# --- Copy and paste ----------------------------------------------------------


def test_copy_result(window):
    type_text(window, "6*7=")
    window.copy_result()
    assert QGuiApplication.clipboard().text() == "42"
    assert window.expression_label.text() == "Copied"


def test_paste_expression(window):
    QGuiApplication.clipboard().setText("(2+3)*4")
    window.paste_clipboard()
    type_text(window, "=")
    assert shown_value(window) == "20"


def test_paste_rejects_text(window):
    QGuiApplication.clipboard().setText("hello")
    window.paste_clipboard()
    assert shown_value(window) == ui.INVALID_INPUT_MESSAGE


# --- History -----------------------------------------------------------------


def test_results_are_added_to_history_newest_first(window):
    type_text(window, "1+1=")
    type_text(window, "2*3=")
    assert [entry.result for entry in window.history.entries] == ["6", "2"]
    assert window.history_panel.list.count() == 2


def test_clicking_a_history_entry_reuses_its_result(window):
    type_text(window, "9*9=")
    click(window, "AC")
    panel = window.history_panel
    window._set_history_open(True)
    item = panel.list.item(0)
    QTest.mouseClick(
        panel.list.viewport(),
        Qt.MouseButton.LeftButton,
        pos=panel.list.visualItemRect(item).center(),
    )
    assert shown_value(window) == "81"


def test_clear_history(window):
    type_text(window, "1+1=")
    QTest.mouseClick(window.history_panel.clear_button, Qt.MouseButton.LeftButton)
    assert window.history.entries == []
    assert window.history_panel.list.count() == 0
    assert not window.history_panel.clear_button.isEnabled()


def test_history_panel_widens_the_window_rather_than_squeezing_the_keypad(window):
    window._set_history_open(False)
    width = window.width()
    QTest.keyClick(window, Qt.Key.Key_H)
    assert window.history_panel.isVisible()
    assert window.width() == width + HISTORY_PANEL_WIDTH
    assert window.history_button.isChecked() and window.history_action.isChecked()
    QTest.keyClick(window, Qt.Key.Key_H)
    assert not window.history_panel.isVisible()
    assert window.width() == width


# --- Themes ------------------------------------------------------------------


def test_theme_key_cycles_modes(window):
    window.set_theme_mode("system")
    QTest.keyClick(window, Qt.Key.Key_T)
    assert window._theme_mode == "light" and window.theme is LIGHT_THEME
    QTest.keyClick(window, Qt.Key.Key_T)
    assert window._theme_mode == "dark" and window.theme is DARK_THEME
    QTest.keyClick(window, Qt.Key.Key_T)
    assert window._theme_mode == "system"
    assert window.mode_actions["system"].isChecked()


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_every_part_draws_in_both_themes(window, mode):
    window.set_theme_mode(mode)
    window._set_history_open(True)
    type_text(window, "123.45*6=")
    assert not window.grab().isNull()


# --- Saving and restoring ----------------------------------------------------


def test_settings_and_history_survive_a_restart(app, folder):
    first = make_window(folder)
    type_text(first, "5*5=")
    first.set_theme_mode("dark")
    first._set_history_open(True)
    first.close()

    second = make_window(folder)
    try:
        assert [entry.result for entry in second.history.entries] == ["25"]
        assert second.history_panel.isVisible()
        assert second._theme_mode == "dark"
    finally:
        second.close()


def test_a_crashing_engine_key_is_contained(window, monkeypatch):
    def broken(_key):
        raise RuntimeError("simulated bug")

    type_text(window, "5")
    monkeypatch.setattr(window.engine, "press", broken)
    window.press("+")  # Must not raise.
    assert shown_value(window) == "0"
