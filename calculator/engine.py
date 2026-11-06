"""Calculator logic: tokenizer, parser, formatting and key-by-key state machine.

This module has no UI dependencies. It is built in three layers:

1. ``tokenize`` turns text into ``Token`` objects.
2. ``evaluate_tokens`` is a recursive-descent parser that computes the value of
   a token list using ``decimal.Decimal``. Python's ``eval``/``exec`` are never
   used, and decimal arithmetic means 0.1 + 0.2 is exactly 0.3.
3. ``Calculator`` models the behaviour of the physical keys: what happens when
   a digit, an operator or "=" is pressed in any given state. The UI only calls
   its methods and renders ``expression``, ``display`` and ``error``.

Grammar (lowest to highest precedence)::

    expression := term (("+" | "-") term)*
    term       := factor (("*" | "/") factor)*
    factor     := ("+" | "-" | "√") factor | postfix
    postfix    := primary ("%" | "²")*
    primary    := NUMBER | "(" expression ")"

Implicit multiplication such as ``2(3+4)`` is made explicit by the tokenizer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import (
    ROUND_HALF_EVEN,
    ROUND_HALF_UP,
    Context,
    Decimal,
    DecimalException,
    DivisionByZero,
    InvalidOperation,
    Overflow,
    localcontext,
)
from functools import wraps
from typing import Callable, Optional

# --- Limits -----------------------------------------------------------------

# Digits accepted while typing, and shown when formatting a value.
MAX_DISPLAY_DIGITS = 16
# Results are kept to this many digits, which removes tiny rounding noise so
# that 1 / 3 × 3 and √2 × √2 come out as exactly 1 and 2.
RESULT_DIGITS = 34
# Working precision while evaluating; extra guard digits for RESULT_DIGITS.
WORKING_DIGITS = 60
# Largest decimal exponent accepted. Beyond it the result is "too large".
MAX_EXPONENT = 9999
# Fixed-point notation is used for values whose exponent falls in this range.
MIN_FIXED_EXPONENT = -8
MAX_FIXED_EXPONENT = MAX_DISPLAY_DIGITS - 1

# These bounds guarantee that no input can exhaust the stack or the display.
MAX_TOKENS = 200
MAX_PAREN_DEPTH = 30
MAX_PARSE_DEPTH = 100
MAX_PASTE_LENGTH = 500
# A function operand larger than this collapses to its value in the expression.
MAX_OPERAND_TOKENS = 24

# --- Errors -----------------------------------------------------------------

DIVIDE_BY_ZERO_MESSAGE = "Can't divide by zero"
INVALID_INPUT_MESSAGE = "Invalid input"
TOO_LARGE_MESSAGE = "Number too large"


class CalcError(Exception):
    """Base class for errors; ``str(error)`` is safe to show to the user."""

    message = INVALID_INPUT_MESSAGE

    def __init__(self, message: Optional[str] = None):
        super().__init__(message or self.message)


class InvalidInputError(CalcError):
    message = INVALID_INPUT_MESSAGE


class DivideByZeroError(CalcError):
    message = DIVIDE_BY_ZERO_MESSAGE


class NumberTooLargeError(CalcError):
    message = TOO_LARGE_MESSAGE


# --- Tokens -----------------------------------------------------------------

NUM, OP, LP, RP, PCT, SQ, SQRT = "num", "op", "(", ")", "%", "²", "√"


@dataclass(frozen=True)
class Token:
    """One unit of an expression. ``value`` is only set for numbers."""

    kind: str
    text: str = ""
    value: Optional[Decimal] = None


def _op(symbol: str) -> Token:
    return Token(OP, symbol)


def _num(value: Decimal) -> Token:
    return Token(NUM, format_number(value), value)


TOKEN_LP = Token(LP, "(")
TOKEN_RP = Token(RP, ")")
TOKEN_PCT = Token(PCT, "%")
TOKEN_SQ = Token(SQ, "²")
TOKEN_SQRT = Token(SQRT, "√")

# Maps every accepted spelling of an operator to its canonical symbol.
_OPERATOR_ALIASES = {
    "+": "+",
    "-": "-",
    "−": "-",
    "–": "-",
    "—": "-",
    "*": "*",
    "×": "*",
    "x": "*",
    "X": "*",
    "·": "*",
    "/": "/",
    "÷": "/",
}
_DISPLAY_OPERATORS = {"+": "+", "-": "−", "*": "×", "/": "÷"}

_NUMBER_RE = re.compile(r"(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?")
_MISPLACED_COMMA_RE = re.compile(r",(?!\d{3}(?!\d))")
_SQRT_WORD_RE = re.compile(r"sqrt", re.IGNORECASE)

# Tokens after which an operand is complete.
_ENDS_OPERAND = {NUM, RP, PCT, SQ}


def _is_binary_position(tokens: list[Token], index: int) -> bool:
    """True if the operator at ``index`` has a left operand."""
    return index > 0 and tokens[index - 1].kind in _ENDS_OPERAND


def tokenize(text: str) -> list[Token]:
    """Convert text such as ``"1,200 × (2 + 3)"`` into tokens.

    Raises ``InvalidInputError`` for anything that is not part of the grammar.
    """
    if _MISPLACED_COMMA_RE.search(text):
        raise InvalidInputError()
    text = _SQRT_WORD_RE.sub("√", text.replace(",", ""))

    tokens: list[Token] = []
    position = 0
    while position < len(text):
        char = text[position]
        if char.isspace():
            position += 1
        elif char.isascii() and char.isdigit() or char == ".":
            match = _NUMBER_RE.match(text, position)
            if not match:
                raise InvalidInputError()
            tokens.append(_number_token(match.group()))
            position = match.end()
        elif char in _OPERATOR_ALIASES:
            tokens.append(_op(_OPERATOR_ALIASES[char]))
            position += 1
        elif char in ("(", ")", "%", "²", "√"):
            tokens.append(
                {
                    "(": TOKEN_LP,
                    ")": TOKEN_RP,
                    "%": TOKEN_PCT,
                    "²": TOKEN_SQ,
                    "√": TOKEN_SQRT,
                }[char]
            )
            position += 1
        else:
            raise InvalidInputError()
    return _insert_implicit_multiplication(tokens)


def _number_token(text: str) -> Token:
    value = Decimal(text)
    # Reject absurd exponents here, before anything tries to format them.
    if abs(value.adjusted()) > MAX_EXPONENT:
        raise NumberTooLargeError()
    return _num(value)


def _insert_implicit_multiplication(tokens: list[Token]) -> list[Token]:
    """Rewrite ``2(3)``, ``(2)(3)``, ``(2)3`` and ``2√9`` with an explicit ×."""
    result: list[Token] = []
    for token in tokens:
        if result:
            previous = result[-1].kind
            if (previous in _ENDS_OPERAND and token.kind in (LP, SQRT)) or (
                previous == RP and token.kind == NUM
            ):
                result.append(_op("*"))
        result.append(token)
    return result


# --- Parser / evaluator -----------------------------------------------------


class _Parser:
    """Recursive-descent evaluator over a token list."""

    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.position = 0
        self.depth = 0

    def parse(self) -> Decimal:
        if not self.tokens:
            raise InvalidInputError()
        value, _ = self._expression()
        if self.position != len(self.tokens):
            raise InvalidInputError()
        return value

    def _peek(self) -> Optional[Token]:
        if self.position < len(self.tokens):
            return self.tokens[self.position]
        return None

    def _peek_operator(self, *symbols: str) -> Optional[str]:
        token = self._peek()
        if token is not None and token.kind == OP and token.text in symbols:
            return token.text
        return None

    # Each level returns (value, is_percent). ``is_percent`` is True when the
    # value is a bare "n%", which addition treats as a share of its left side:
    # 200 + 10% = 220, whereas 200 × 10% = 20.

    def _expression(self) -> tuple[Decimal, bool]:
        self.depth += 1
        if self.depth > MAX_PARSE_DEPTH:
            raise InvalidInputError()
        left, left_is_percent = self._term()
        while symbol := self._peek_operator("+", "-"):
            self.position += 1
            right, right_is_percent = self._term()
            if right_is_percent:
                right = left * right
            left = left + right if symbol == "+" else left - right
            left_is_percent = False
        self.depth -= 1
        return left, left_is_percent

    def _term(self) -> tuple[Decimal, bool]:
        left, is_percent = self._factor()
        while symbol := self._peek_operator("*", "/"):
            self.position += 1
            right, _ = self._factor()
            if symbol == "*":
                left = left * right
            else:
                if right.is_zero():
                    raise DivideByZeroError()
                left = left / right
            is_percent = False
        return left, is_percent

    def _factor(self) -> tuple[Decimal, bool]:
        self.depth += 1
        if self.depth > MAX_PARSE_DEPTH:
            raise InvalidInputError()
        try:
            if symbol := self._peek_operator("+", "-"):
                self.position += 1
                value, is_percent = self._factor()
                return (-value if symbol == "-" else value), is_percent
            token = self._peek()
            if token is not None and token.kind == SQRT:
                self.position += 1
                value, _ = self._factor()
                if value < 0:
                    raise InvalidInputError()
                return value.sqrt(), False
            return self._postfix()
        finally:
            self.depth -= 1

    def _postfix(self) -> tuple[Decimal, bool]:
        value = self._primary()
        is_percent = False
        while (token := self._peek()) is not None and token.kind in (PCT, SQ):
            self.position += 1
            if token.kind == PCT:
                value = value / 100
                is_percent = True
            else:
                value = value * value
                is_percent = False
        return value, is_percent

    def _primary(self) -> Decimal:
        token = self._peek()
        if token is None:
            raise InvalidInputError()
        if token.kind == NUM:
            self.position += 1
            assert token.value is not None
            return token.value
        if token.kind == LP:
            self.position += 1
            value, _ = self._expression()
            closing = self._peek()
            if closing is None or closing.kind != RP:
                raise InvalidInputError()
            self.position += 1
            return value
        raise InvalidInputError()


def _working_context() -> Context:
    return Context(
        prec=WORKING_DIGITS,
        rounding=ROUND_HALF_EVEN,
        Emax=MAX_EXPONENT,
        Emin=-MAX_EXPONENT,
        # Underflow is deliberately untrapped: tiny values simply become 0.
        traps=[InvalidOperation, DivisionByZero, Overflow],
    )


def _round_result(value: Decimal) -> Decimal:
    """Round to RESULT_DIGITS; trailing zeros are dropped, -0 becomes 0."""
    with localcontext(_working_context()) as context:
        context.prec = RESULT_DIGITS
        rounded = (+value).normalize()
        return Decimal(0) if rounded.is_zero() else rounded


def evaluate_tokens(tokens: list[Token]) -> Decimal:
    """Evaluate tokens, raising a ``CalcError`` subclass on any failure."""
    try:
        with localcontext(_working_context()):
            value = _Parser(tokens).parse()
        return _round_result(value)
    except DivisionByZero as error:
        raise DivideByZeroError() from error
    except Overflow as error:
        raise NumberTooLargeError() from error
    except (DecimalException, RecursionError) as error:
        raise InvalidInputError() from error


def evaluate(text: str) -> Decimal:
    """Evaluate an expression string, e.g. ``evaluate("2 + 3 × 4") == 14``."""
    return evaluate_tokens(tokenize(text))


# --- Formatting -------------------------------------------------------------


def format_number(value: Decimal) -> str:
    """Format for display: ``1,234,567.89``, or ``1.5e+20`` when very large/small.

    Uses a plain ASCII minus so that it is easy to compare and copy; the UI may
    swap it for a typographic one.
    """
    if value.is_zero():
        return "0"
    with localcontext() as context:
        context.prec = MAX_DISPLAY_DIGITS
        context.rounding = ROUND_HALF_UP
        rounded = (+value).normalize()
    exponent = rounded.adjusted()
    if MIN_FIXED_EXPONENT <= exponent <= MAX_FIXED_EXPONENT:
        return _group_thousands(format(rounded, "f"))
    sign, digits, _ = rounded.as_tuple()
    text = str(digits[0])
    if len(digits) > 1:
        text += "." + "".join(str(digit) for digit in digits[1:])
    return f"{'-' if sign else ''}{text}e{exponent:+d}"


def _group_thousands(text: str) -> str:
    """Insert separators into a plain number string, preserving what's typed."""
    sign = "-" if text.startswith("-") else ""
    integer, dot, fraction = text.lstrip("-").partition(".")
    return f"{sign}{int(integer or 0):,}{dot}{fraction}"


def plain_number(value: Decimal) -> str:
    """Format without separators, for copying to other applications."""
    return format_number(value).replace(",", "")


def _render_tokens(tokens: list[Token]) -> str:
    """Build the human-readable expression, e.g. ``2 + √(9) × 4``."""
    parts: list[str] = []
    for index, token in enumerate(tokens):
        if token.kind == OP:
            symbol = _DISPLAY_OPERATORS[token.text]
            if _is_binary_position(tokens, index):
                parts.append(f" {symbol} ")
            else:
                parts.append(symbol)
        elif token.kind == NUM:
            parts.append(token.text.replace("-", "−"))
        else:
            parts.append(token.kind)
    return "".join(parts).strip()


# --- Calculator state machine -----------------------------------------------


@dataclass(frozen=True)
class Calculation:
    """A completed calculation, ready to be added to the history."""

    expression: str
    result: str
    value: str  # Full-precision value, so that reloading loses nothing.


def _action(method: Callable) -> Callable:
    """Wrap a key handler: recover from errors first and never let one escape."""

    @wraps(method)
    def wrapper(self: "Calculator", *args, **kwargs):
        if self._error is not None:
            self._reset()
        try:
            return method(self, *args, **kwargs)
        except CalcError as error:
            self._fail(str(error))
        except (DecimalException, ArithmeticError, RecursionError, ValueError):
            self._fail(INVALID_INPUT_MESSAGE)
        return None

    return wrapper


class Calculator:
    """Models the keys of the calculator.

    The current calculation is ``_tokens`` (committed) plus ``_entry`` (the
    number being typed, as text so "1.50" keeps its trailing zero). When no
    number is being typed, ``_shown`` holds the value on the main display.
    """

    def __init__(self) -> None:
        self.memory: Optional[Decimal] = None
        self._completed: Optional[Calculation] = None
        self._reset()

    def _reset(self) -> None:
        """Clear the calculation. Memory is deliberately left untouched."""
        self._tokens: list[Token] = []
        self._entry: Optional[str] = None
        self._entry_locked = False  # A finished entry; next digit replaces it.
        self._shown = Decimal(0)
        self._after_result = False
        self._result_expression = ""
        self._last_operation: Optional[tuple[str, Decimal]] = None
        self._replace_operand = False  # A digit overwrites the last operand.
        self._error: Optional[str] = None

    def _fail(self, message: str) -> None:
        if not self._after_result:
            self._result_expression = self._full_expression()
        self._error = message
        self._after_result = False
        self._tokens = []
        self._entry = None

    # --- What the UI renders ------------------------------------------------

    @property
    def error(self) -> Optional[str]:
        return self._error

    @property
    def display(self) -> str:
        """The large main display: value being typed, a result or an error."""
        if self._error is not None:
            return self._error
        if self._entry is not None:
            return _group_thousands(self._entry)
        return format_number(self._shown)

    @property
    def expression(self) -> str:
        """The smaller line showing the whole expression."""
        if self._after_result or self._error is not None:
            return self._result_expression
        # A lone number would just duplicate the main display.
        if len(self._tokens) == 1 and self._entry is None:
            if self._tokens[0].kind == NUM:
                return ""
        if not self._tokens:
            return ""
        return self._full_expression()

    def _full_expression(self) -> str:
        tokens = list(self._tokens)
        if self._entry is not None:
            tokens.append(_num(Decimal(self._entry)))
        return _render_tokens(tokens)

    @property
    def copy_text(self) -> str:
        """The current value without separators; empty during an error."""
        if self._error is not None:
            return ""
        return plain_number(self.current_value)

    @property
    def current_value(self) -> Decimal:
        return Decimal(self._entry) if self._entry is not None else self._shown

    @property
    def has_memory(self) -> bool:
        return self.memory is not None

    @property
    def memory_display(self) -> str:
        return format_number(self.memory) if self.memory is not None else ""

    def take_completed(self) -> Optional[Calculation]:
        """Return the calculation finished by the last "=", at most once."""
        completed, self._completed = self._completed, None
        return completed

    # --- Internal helpers ---------------------------------------------------

    def _last_kind(self) -> Optional[str]:
        return self._tokens[-1].kind if self._tokens else None

    def _open_paren_count(self) -> int:
        count = 0
        for token in self._tokens:
            count += (token.kind == LP) - (token.kind == RP)
        return count

    def _commit_entry(self) -> None:
        """Move the number being typed into the token list."""
        if self._entry is not None:
            self._shown = Decimal(self._entry)
            self._tokens.append(_num(self._shown))
            self._entry = None
            self._entry_locked = False

    def _continue_from_result(self) -> None:
        """Turn a finished result into the first operand of a new expression."""
        if self._after_result:
            value = self._shown
            self._reset()
            self._shown = value
            self._tokens = [_num(value)]

    def _operand_start(self) -> int:
        """Index of the first token of the operand at the end of the tokens."""
        index = len(self._tokens) - 1
        while index >= 0 and self._tokens[index].kind in (PCT, SQ):
            index -= 1
        if index >= 0 and self._tokens[index].kind == RP:
            depth = 0
            while index >= 0:
                kind = self._tokens[index].kind
                depth += (kind == RP) - (kind == LP)
                if depth == 0:
                    break
                index -= 1
        # Include any prefix attached to the operand, such as √ or a unary −.
        while index > 0:
            previous = self._tokens[index - 1]
            if previous.kind == SQRT or (
                previous.kind == OP and not _is_binary_position(self._tokens, index - 1)
            ):
                index -= 1
            else:
                break
        return max(index, 0)

    def _pop_operand(self) -> list[Token]:
        start = self._operand_start()
        operand = self._tokens[start:]
        del self._tokens[start:]
        return operand

    def _take_operand(self) -> list[Token]:
        """Remove and return what a function key should act on."""
        if self._after_result:
            value = self._shown
            self._reset()
            return [_num(value)]
        if self._entry is not None:
            value = Decimal(self._entry)
            self._entry = None
            self._entry_locked = False
            return [_num(value)]
        if self._last_kind() in _ENDS_OPERAND:
            return self._pop_operand()
        # Nothing typed after an operator: use the value on the display.
        return [_num(self._shown)]

    def _push_function_result(self, operand: list[Token]) -> None:
        """Append a function's operand and show the value it evaluates to."""
        start = len(self._tokens)
        self._tokens.extend(operand)  # Added first, so an error can display it.
        value = evaluate_tokens(operand)
        # Stop nesting from growing without limit, e.g. if √ is pressed forever.
        if len(operand) > MAX_OPERAND_TOKENS:
            self._tokens[start:] = [_num(value)]
        self._shown = value
        self._replace_operand = True

    def _insert_value(self, value: Decimal) -> None:
        """Place a value as the current operand (memory recall, history)."""
        if self._after_result:
            self._reset()
        self._entry = None
        self._entry_locked = False
        if self._last_kind() in _ENDS_OPERAND:
            if self._last_kind() == NUM or self._replace_operand:
                self._pop_operand()
            else:
                self._tokens.append(_op("*"))
        self._tokens.append(_num(value))
        self._shown = value
        self._replace_operand = False

    def _begin_entry(self) -> None:
        """Prepare to start typing a new number."""
        if self._after_result:
            self._reset()
        if self._entry_locked:
            self._entry = None
            self._entry_locked = False
        if self._entry is None and self._last_kind() in _ENDS_OPERAND:
            if self._last_kind() == NUM or self._replace_operand:
                self._pop_operand()
            else:
                self._tokens.append(_op("*"))
        self._replace_operand = False

    def _refresh_shown(self) -> None:
        """After deleting tokens, show the value of whatever is now last."""
        self._shown = Decimal(0)
        if self._last_kind() in _ENDS_OPERAND:
            try:
                self._shown = evaluate_tokens(self._tokens[self._operand_start() :])
            except CalcError:
                pass

    def _has_room(self) -> bool:
        return len(self._tokens) < MAX_TOKENS

    # --- Entering numbers ---------------------------------------------------

    @_action
    def input_digit(self, digit: str) -> None:
        if digit not in tuple("0123456789"):
            return
        self._begin_entry()
        if self._entry is None:
            self._entry = digit
        elif self._entry in ("0", "-0"):
            self._entry = self._entry[:-1] + digit
        elif sum(char.isdigit() for char in self._entry) < MAX_DISPLAY_DIGITS:
            self._entry += digit

    @_action
    def input_decimal(self) -> None:
        self._begin_entry()
        if self._entry is None:
            self._entry = "0."
        elif "." not in self._entry:
            self._entry += "."

    # --- Operators and parentheses ------------------------------------------

    @_action
    def input_operator(self, operator: str) -> None:
        """Apply +, -, * or / (or their ×, ÷, − spellings)."""
        symbol = _OPERATOR_ALIASES.get(operator)
        if symbol is None:
            return
        self._continue_from_result()
        self._commit_entry()
        self._replace_operand = False
        if not self._has_room():
            return
        if not self._tokens:
            self._tokens.append(_num(self._shown))
        last = self._last_kind()
        if last == LP:
            # After "(" only a leading minus makes sense.
            if symbol == "-":
                self._tokens.append(_op("-"))
        elif last == OP:
            if _is_binary_position(self._tokens, len(self._tokens) - 1):
                self._tokens[-1] = _op(symbol)  # Changed their mind: replace.
            elif symbol == "+":
                self._tokens.pop()  # "(−" then "+" cancels the minus.
        elif last in _ENDS_OPERAND:
            self._tokens.append(_op(symbol))

    @_action
    def open_paren(self) -> None:
        if self._after_result:
            self._reset()
        if self._open_paren_count() >= MAX_PAREN_DEPTH or not self._has_room():
            return
        self._commit_entry()
        if self._last_kind() in _ENDS_OPERAND:
            self._tokens.append(_op("*"))
        self._tokens.append(TOKEN_LP)
        self._shown = Decimal(0)
        self._replace_operand = False

    @_action
    def close_paren(self) -> None:
        if self._after_result or self._open_paren_count() == 0:
            return
        if self._entry is None and self._last_kind() not in _ENDS_OPERAND:
            return  # Nothing to close yet: "(" or "2 +" with no right operand.
        self._commit_entry()
        self._tokens.append(TOKEN_RP)
        self._replace_operand = False
        self._shown = evaluate_tokens(self._tokens[self._operand_start() :])

    # --- Equals -------------------------------------------------------------

    @_action
    def equals(self) -> None:
        if self._after_result:
            self._repeat_last_operation()
            return

        self._commit_entry()
        # Drop an unfinished tail such as "2 × (" or "(−".
        dropped_tail = False
        while self._last_kind() in (LP, SQRT) or (
            self._last_kind() == OP
            and not _is_binary_position(self._tokens, len(self._tokens) - 1)
        ):
            self._tokens.pop()
            dropped_tail = True
        # "5 + =" uses the displayed value as the right operand, giving 10.
        if self._last_kind() == OP:
            if dropped_tail:
                operator = self._tokens.pop()
                self._refresh_shown()
                self._tokens.append(operator)
            self._tokens.append(_num(self._shown))
        if not self._tokens:
            self._tokens.append(_num(self._shown))
        self._tokens.extend([TOKEN_RP] * self._open_paren_count())

        tokens = self._tokens
        expression = _render_tokens(tokens) + " ="
        self._result_expression = expression
        self._after_result = True
        value = evaluate_tokens(tokens)
        self._last_operation = self._find_last_operation(tokens, value)
        self._finish(expression, value, tokens)

    def _finish(
        self, expression: str, value: Decimal, tokens: Optional[list[Token]]
    ) -> None:
        """Store a result. Bare numbers ("5 =") do not reach the history."""
        self._shown = value
        self._tokens = []
        self._entry = None
        self._entry_locked = False
        self._replace_operand = False
        self._result_expression = expression
        self._after_result = True
        is_calculation = tokens is None or any(
            token.kind in (OP, PCT, SQ, SQRT) for token in tokens
        )
        if is_calculation:
            self._completed = Calculation(expression, format_number(value), str(value))

    @staticmethod
    def _find_last_operation(
        tokens: list[Token], result: Decimal
    ) -> Optional[tuple[str, Decimal]]:
        """Find the (operator, operand) that "=" repeats: the last top-level one."""
        depth = 0
        for index in range(len(tokens) - 1, 0, -1):
            kind = tokens[index].kind
            depth += (kind == RP) - (kind == LP)
            if depth != 0 or kind != OP or not _is_binary_position(tokens, index):
                continue
            symbol = tokens[index].text
            try:
                if symbol in "+-":
                    # Using the difference gives the right answer for 200 + 10%,
                    # where the effective operand is 20 and not 0.1.
                    left = evaluate_tokens(tokens[:index])
                    operand = result - left if symbol == "+" else left - result
                    return symbol, _round_result(operand)
                return symbol, evaluate_tokens(tokens[index + 1 :])
            except CalcError:
                return None
        return None

    def _repeat_last_operation(self) -> None:
        if self._last_operation is None:
            return
        symbol, operand = self._last_operation
        tokens = [_num(self._shown), _op(symbol), _num(operand)]
        expression = _render_tokens(tokens) + " ="
        self._result_expression = expression
        self._finish(expression, evaluate_tokens(tokens), None)

    # --- Clearing -----------------------------------------------------------

    @_action
    def clear_entry(self) -> None:
        """C: clear the current number; with nothing to clear, clear everything."""
        if self._entry is not None and self._entry not in ("0", "-0"):
            self._entry = "0"
            self._entry_locked = False
        elif self._replace_operand and self._last_kind() in _ENDS_OPERAND:
            self._pop_operand()
            self._replace_operand = False
            self._entry = "0"
        else:
            self._reset()

    @_action
    def all_clear(self) -> None:
        """AC: clear the whole calculation. Memory and history are kept."""
        self._reset()

    @_action
    def backspace(self) -> None:
        if self._after_result:
            self._result_expression = ""  # Keep the value; dismiss the sum.
            return
        if self._entry is not None:
            self._entry = self._entry[:-1]
            self._entry_locked = False
            if self._entry in ("", "-"):
                self._entry = None
                self._shown = Decimal(0)
            return
        last = self._last_kind()
        if last is None:
            return
        if self._replace_operand or last in (PCT, SQ):
            self._pop_operand()
            self._replace_operand = False
        elif last == NUM:
            self._edit_last_number()
            return
        else:
            self._tokens.pop()
        self._refresh_shown()

    def _edit_last_number(self) -> None:
        """Turn the last number back into an entry so it can be edited."""
        value = self._tokens.pop().value
        assert value is not None
        text = format_number(value).replace(",", "")
        if "e" in text or Decimal(text) != value:
            self._refresh_shown()  # Rounded or scientific: remove it entirely.
        else:
            self._entry = text[:-1]
            if self._entry in ("", "-"):
                self._entry = None
                self._shown = Decimal(0)

    # --- Functions ----------------------------------------------------------

    @_action
    def percent(self) -> None:
        """Mark the current number as a percentage.

        ``50 %`` is 0.5, ``200 + 10 %`` is 220 and ``200 × 10 %`` is 20.
        """
        operand = self._take_operand()
        if len(operand) > MAX_OPERAND_TOKENS:
            operand = [_num(evaluate_tokens(operand))]
        fraction = evaluate_tokens([*operand, TOKEN_PCT])
        base = self._percent_base()
        self._tokens.extend([*operand, TOKEN_PCT])
        self._shown = _round_result(base * fraction) if base is not None else fraction
        self._replace_operand = True

    def _percent_base(self) -> Optional[Decimal]:
        """The value a percentage is taken of, when it follows + or −."""
        tokens = self._tokens
        if not tokens or tokens[-1].kind != OP or tokens[-1].text not in "+-":
            return None
        if not _is_binary_position(tokens, len(tokens) - 1):
            return None
        # Only look back as far as the enclosing open parenthesis.
        depth = 0
        start = 0
        for index in range(len(tokens) - 2, -1, -1):
            depth += (tokens[index].kind == RP) - (tokens[index].kind == LP)
            if depth < 0:
                start = index + 1
                break
        return evaluate_tokens(tokens[start:-1])

    @_action
    def toggle_sign(self) -> None:
        if self._after_result:
            value = -self._shown
            self._reset()
            self._tokens = [_num(value)]
            self._shown = value
            self._replace_operand = True
            return
        if self._entry is not None:
            if self._entry.startswith("-"):
                self._entry = self._entry[1:]
            else:
                self._entry = "-" + self._entry
            return
        last = self._last_kind()
        if last in _ENDS_OPERAND:
            operand = self._pop_operand()
            if len(operand) == 2 and operand[0].kind == NUM and last == PCT:
                # Keep it a percentage, so 200 + 10% becomes 200 + −10%.
                self._tokens.extend([_num(-operand[0].value), TOKEN_PCT])
                self._shown = -self._shown
                self._replace_operand = True
                return
            if len(operand) == 1:
                negated = [_num(-operand[0].value)]
            elif operand[0].kind == OP and operand[0].text == "-":
                negated = operand[1:]  # Toggling twice removes the minus.
            else:
                negated = [_op("-"), TOKEN_LP, *operand, TOKEN_RP]
            self._push_function_result(negated)
        elif last == OP and _is_binary_position(self._tokens, len(self._tokens) - 1):
            self._insert_value(-self._shown)
            self._replace_operand = True
        else:
            self._entry = "-0"  # Lets the user type a negative number directly.

    @_action
    def square_root(self) -> None:
        operand = self._take_operand()
        self._push_function_result([TOKEN_SQRT, TOKEN_LP, *operand, TOKEN_RP])

    @_action
    def square(self) -> None:
        operand = self._take_operand()
        is_plain_positive = (
            len(operand) == 1 and operand[0].kind == NUM and operand[0].value >= 0
        )
        if is_plain_positive:
            self._push_function_result([*operand, TOKEN_SQ])
        else:
            self._push_function_result([TOKEN_LP, *operand, TOKEN_RP, TOKEN_SQ])

    @_action
    def reciprocal(self) -> None:
        operand = self._take_operand()
        inner = operand if len(operand) == 1 else [TOKEN_LP, *operand, TOKEN_RP]
        one = _num(Decimal(1))
        self._push_function_result([TOKEN_LP, one, _op("/"), *inner, TOKEN_RP])

    # --- Memory -------------------------------------------------------------

    def _finish_entry_for_memory(self) -> Decimal:
        """Read the current value; the next digit will start a new number."""
        if self._entry is not None:
            self._entry_locked = True
        return self.current_value

    @_action
    def memory_clear(self) -> None:
        self.memory = None

    @_action
    def memory_recall(self) -> None:
        if self.memory is not None:
            self._insert_value(self.memory)

    @_action
    def memory_add(self) -> None:
        self._memory_change(self._finish_entry_for_memory())

    @_action
    def memory_subtract(self) -> None:
        self._memory_change(-self._finish_entry_for_memory())

    def _memory_change(self, amount: Decimal) -> None:
        current = self.memory if self.memory is not None else Decimal(0)
        tokens = [_num(current), _op("+"), _num(amount)]
        self.memory = evaluate_tokens(tokens)

    # --- Loading values from outside ----------------------------------------

    @_action
    def load_value(self, text: str) -> None:
        """Load a value (from the history) as the current operand."""
        self._insert_value(Decimal(text))

    def paste(self, text: str) -> bool:
        """Paste a number or expression. Returns False, changing nothing, if
        the text isn't valid. Text like "1/0" is valid and shows its error.
        """
        if self._error is not None:
            self._reset()
        cleaned = text.strip()
        if not cleaned or len(cleaned) > MAX_PASTE_LENGTH:
            return False
        try:
            tokens = tokenize(cleaned)
        except CalcError:
            return False
        tokens.extend([TOKEN_RP] * self._count_unclosed(tokens))
        if len(self._tokens) + len(tokens) + 2 > MAX_TOKENS:
            return False
        try:
            value = evaluate_tokens(tokens)
        except DivideByZeroError as error:
            self._after_result = False
            self._entry = None
            self._tokens = tokens
            self._fail(str(error))
            return True
        except CalcError:
            return False

        if len(tokens) == 1 and tokens[0].kind == NUM:
            self._insert_value(value)
            return True
        self._insert_value(Decimal(0))
        self._tokens.pop()
        if self._tokens:
            tokens = [TOKEN_LP, *tokens, TOKEN_RP]  # 5 × (pasted expression).
        self._tokens.extend(tokens)
        self._shown = value
        self._replace_operand = self._last_kind() == RP
        return True

    @staticmethod
    def _count_unclosed(tokens: list[Token]) -> int:
        depth = 0
        for token in tokens:
            depth += (token.kind == LP) - (token.kind == RP)
            if depth < 0:
                return 0  # Stray ")": leave it for the parser to reject.
        return depth

    # --- Single entry point used by the UI ----------------------------------

    def press(self, key: str) -> None:
        """Press a key by name: a digit, operator, or an id such as ``sqrt``."""
        handlers: dict[str, Callable[[], None]] = {
            ".": self.input_decimal,
            "(": self.open_paren,
            ")": self.close_paren,
            "=": self.equals,
            "%": self.percent,
            "C": self.clear_entry,
            "AC": self.all_clear,
            "backspace": self.backspace,
            "negate": self.toggle_sign,
            "sqrt": self.square_root,
            "square": self.square,
            "reciprocal": self.reciprocal,
            "MC": self.memory_clear,
            "MR": self.memory_recall,
            "M+": self.memory_add,
            "M-": self.memory_subtract,
        }
        if key in handlers:
            handlers[key]()
        elif key in tuple("0123456789"):
            self.input_digit(key)
        elif key in _OPERATOR_ALIASES:
            self.input_operator(key)
