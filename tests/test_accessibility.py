"""Tests for VoiceOver names, announcements, Reduce Motion and Increase Contrast."""

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtGui import QAccessible, QColor  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from calculator import ui, widgets  # noqa: E402
from calculator.history import HistoryStore  # noqa: E402
from calculator.keys import BUTTON_ROWS  # noqa: E402
from calculator.theme import DARK_THEME, LIGHT_THEME, high_contrast  # noqa: E402

NAME = QAccessible.Text.Name


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app, tmp_path):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    window = ui.MainWindow(settings, HistoryStore(tmp_path / "history.json"))
    window.show()
    yield window
    window.close()


def spoken(widget):
    return QAccessible.queryAccessibleInterface(widget).text(NAME)


def contrast(foreground, background):
    def luminance(colour):
        channels = []
        for value in QColor(colour).getRgbF()[:3]:
            channels.append(
                value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4
            )
        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]

    light, dark = sorted([luminance(foreground), luminance(background)], reverse=True)
    return (light + 0.05) / (dark + 0.05)


# --- Spoken names -------------------------------------------------------------


def test_every_button_has_a_spoken_name_made_of_words_or_digits(window):
    for row in BUTTON_ROWS:
        for _label, key, _role, _tooltip in row:
            name = spoken(window.buttons[key])
            assert name, key
            assert name.replace(" ", "").isalnum(), (key, name)


def test_toolbar_buttons_and_memory_badge_are_named(window):
    assert spoken(window.theme_button) == "Appearance"
    assert spoken(window.history_button) == "History"
    assert spoken(window.memory_indicator) == "Memory in use"


def test_result_and_expression_are_readable(window):
    for key in "12+3=":
        window.press(key)
    assert spoken(window.value_label) == "Result 15"
    assert spoken(window.expression_label) == "12 + 3 ="


def test_errors_are_read_without_the_result_prefix(window):
    for key in "1/0=":
        window.press(key)
    assert spoken(window.value_label) == "Can't divide by zero"


def test_history_rows_are_readable(window):
    for key in "4-9=":
        window.press(key)
    panel = window.history_panel
    assert spoken(panel.list) == "Past calculations"
    row = QAccessible.queryAccessibleInterface(panel.list).child(0)
    assert row.text(NAME) == "4 − 9 = −5"


# --- Announcements ------------------------------------------------------------


def test_results_errors_and_copies_are_announced(window, monkeypatch):
    said = []
    monkeypatch.setattr(window, "announce", said.append)
    for key in "6*7=":
        window.press(key)
    window.copy_result()
    for key in "1/0=":
        window.press(key)
    assert said == ["42", "Copied", "Can't divide by zero"]


def test_announcing_is_safe_without_voiceover(window):
    window.announce("42")  # Must not raise whether or not VoiceOver is on.


# --- Reduce Motion ------------------------------------------------------------


def test_reduce_motion_makes_animations_instant(window, monkeypatch):
    monkeypatch.setattr(widgets, "reduced_motion", lambda: True)
    button = window.buttons["7"]
    button._press.to(1.0, 500)
    assert button._press.value == 1.0
    assert not button.grab().isNull()


# --- Increase Contrast --------------------------------------------------------


@pytest.mark.parametrize("theme", [LIGHT_THEME, DARK_THEME])
def test_high_contrast_strengthens_secondary_text_and_outlines_buttons(theme):
    strong = high_contrast(theme)
    assert contrast(strong.muted, strong.window) > contrast(theme.muted, theme.window)
    assert QColor(strong.button_border).alpha() == 255
    assert QColor(theme.button_border).alpha() == 0
    assert contrast(strong.button_border, strong.window) >= 3


@pytest.mark.parametrize("theme", [LIGHT_THEME, DARK_THEME])
def test_normal_text_meets_wcag_aa(theme):
    pairs = [
        (theme.text, theme.window),
        (theme.muted, theme.window),
        (theme.muted, theme.panel),
        (theme.error, theme.window),
        (theme.accent, theme.accent_soft),
    ]
    for role in ("digit", "function", "operator", "equals"):
        colours = getattr(theme, role)
        pairs.append((colours.text, colours.background))
    for foreground, background in pairs:
        assert contrast(foreground, background) >= 4.5, (foreground, background)


def test_buttons_draw_with_an_outline_in_high_contrast(window):
    for button in window.buttons.values():
        button.apply_theme(high_contrast(LIGHT_THEME))
    assert window.buttons["7"]._border.alpha() == 255
    assert not window.grab().isNull()
