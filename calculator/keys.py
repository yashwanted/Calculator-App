"""The keypad layout, keyboard shortcuts and key-event translation."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent


# Each entry: (label, engine key, colour role, tooltip).
BUTTON_ROWS: tuple[tuple[tuple[str, str, str, str], ...], ...] = (
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
TEXT_KEYS = {
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
LETTER_KEYS = {
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

SPECIAL_KEYS = {
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
    if key in SPECIAL_KEYS:
        return SPECIAL_KEYS[key]
    if key == Qt.Key.Key_M and modifiers & Qt.KeyboardModifier.ShiftModifier:
        return "M-"
    if event.text() in TEXT_KEYS:
        return TEXT_KEYS[event.text()]
    return LETTER_KEYS.get(key)


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
