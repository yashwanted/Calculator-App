"""Tests for the calculator engine, driven the way a user drives the keys."""

import random
import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from calculator.engine import (  # noqa: E402
    DIVIDE_BY_ZERO_MESSAGE,
    INVALID_INPUT_MESSAGE,
    TOO_LARGE_MESSAGE,
    Calculator,
    CalcError,
    DivideByZeroError,
    InvalidInputError,
    evaluate,
    format_number,
)
from calculator.history import HistoryStore  # noqa: E402


def press(calculator: Calculator, keys: str) -> Calculator:
    """Press space-separated keys; digit groups like "12.5" are typed in order."""
    for key in keys.split():
        if key[0].isdigit() or (key[0] == "." and len(key) > 1):
            for char in key:
                calculator.press(char)
        else:
            calculator.press(key)
    return calculator


def run(keys: str) -> str:
    return press(Calculator(), keys).display


# --- Expression evaluation --------------------------------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("2 + 3 * 4", "14"),
        ("2 * 3 + 4", "10"),
        ("10 - 4 - 3", "3"),
        ("100 / 10 / 5", "2"),
        ("(2 + 3) * 4", "20"),
        ("2 * (3 + (4 - 1))", "12"),
        ("-3 + 5", "2"),
        ("2 * -3", "-6"),
        ("--3", "3"),
        ("0.1 + 0.2", "0.3"),
        ("1.1 * 1.1", "1.21"),
        ("1 / 3 * 3", "1"),
        ("2(3 + 4)", "14"),
        ("(2)(3)", "6"),
        ("(2)3", "6"),
        ("2√9", "6"),
        ("sqrt(16)", "4"),
        ("√16 + 1", "5"),
        ("3²", "9"),
        ("-3²", "-9"),
        ("(-3)²", "9"),
        ("1,234 + 1", "1235"),
        ("3 × 4 ÷ 2 − 1", "5"),
        ("1e3 + 1", "1001"),
        ("50%", "0.5"),
        ("200 + 10%", "220"),
        ("200 - 10%", "180"),
        ("200 * 10%", "20"),
    ],
)
def test_evaluate(text, expected):
    assert evaluate(text) == Decimal(expected)


def test_decimals_are_exact():
    assert str(evaluate("0.1 + 0.2")) == "0.3"


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "abc",
        "2 +",
        "* 2",
        "2 3",
        "(2",
        "2)",
        "()",
        "1..2",
        "1.2.3",
        "1,23",
        "2 ** 3",
        "__import__('os')",
        "1 + nan",
        "Infinity",
        "٣",
    ],
)
def test_evaluate_rejects_invalid_input(text):
    with pytest.raises(InvalidInputError):
        evaluate(text)


def test_evaluate_division_by_zero():
    with pytest.raises(DivideByZeroError):
        evaluate("1 / 0")
    with pytest.raises(DivideByZeroError):
        evaluate("0 / 0")


def test_evaluate_square_root_of_negative():
    with pytest.raises(InvalidInputError):
        evaluate("√(-4)")


def test_deep_nesting_raises_instead_of_crashing():
    with pytest.raises(CalcError):
        evaluate("(" * 5000 + "1" + ")" * 5000)
    with pytest.raises(CalcError):
        evaluate("-" * 5000 + "1")


# --- Formatting -------------------------------------------------------------


@pytest.mark.parametrize(
    "value, expected",
    [
        ("0", "0"),
        ("-0", "0"),
        ("1234567.89", "1,234,567.89"),
        ("-1234567.89", "-1,234,567.89"),
        ("1000", "1,000"),
        ("1E+3", "1,000"),
        ("0.5", "0.5"),
        ("0.00000001", "0.00000001"),
        ("0.000000001", "1e-9"),
        ("9999999999999999", "9,999,999,999,999,999"),
        ("1E+16", "1e+16"),
        ("1.5E+20", "1.5e+20"),
        ("-1.5E-20", "-1.5e-20"),
        ("0.33333333333333333333", "0.3333333333333333"),
        ("0.66666666666666666667", "0.6666666666666667"),
    ],
)
def test_format_number(value, expected):
    assert format_number(Decimal(value)) == expected


# --- Precedence, chaining ---------------------------------------------------


def test_precedence_via_keys():
    assert run("2 + 3 * 4 =") == "14"


def test_parentheses_via_keys():
    assert run("( 2 + 3 ) * 4 =") == "20"


def test_missing_closing_parentheses_are_added():
    calculator = press(Calculator(), "( 2 + 3 =")
    assert calculator.display == "5"
    assert calculator.expression == "(2 + 3) ="


def test_nothing_to_close_is_ignored():
    assert run(") 2 + 3 ) =") == "5"
    assert run("( ) 2 ) =") == "2"


def test_implicit_multiplication_via_keys():
    assert run("2 ( 3 + 4 ) =") == "14"
    assert run("( 2 + 3 ) 4 =") == "20"


def test_decimals_via_keys():
    assert run("0.1 + 0.2 =") == "0.3"
    assert run(". 5 + .25 =") == "0.75"
    assert run("1 . . 5 =") == "1.5"


def test_operator_after_result_continues_from_result():
    calculator = press(Calculator(), "2 + 3 = * 4")
    assert calculator.expression == "5 × 4"
    assert press(calculator, "=").display == "20"


def test_digit_after_result_starts_fresh():
    calculator = press(Calculator(), "2 + 3 = 7")
    assert calculator.display == "7"
    assert calculator.expression == ""
    assert press(calculator, "+ 1 =").display == "8"


def test_decimal_after_result_starts_fresh():
    assert run("2 + 3 = . 5") == "0.5"


def test_changing_operator_replaces_it():
    calculator = press(Calculator(), "5 + * - * 2")
    assert calculator.expression == "5 × 2"
    assert press(calculator, "=").display == "10"


def test_equals_with_missing_right_operand_uses_display():
    assert run("5 + =") == "10"
    assert run("5 * =") == "25"


def test_operator_on_empty_starts_from_zero():
    assert run("+ 5 =") == "5"


def test_leading_minus_inside_parentheses():
    assert run("2 * ( - 3 ) =") == "-6"


def test_unfinished_tail_is_dropped():
    assert run("2 * ( =") == "4"


def test_expression_and_display_lines():
    calculator = Calculator()
    assert (calculator.display, calculator.expression) == ("0", "")
    press(calculator, "1234567.89")
    assert calculator.display == "1,234,567.89"
    assert calculator.expression == ""
    press(calculator, "+ 1")
    assert calculator.expression == "1,234,567.89 + 1"
    press(calculator, "=")
    assert calculator.expression == "1,234,567.89 + 1 ="
    assert calculator.display == "1,234,568.89"


def test_typing_preserves_trailing_zeros_and_point():
    assert run("1.50") == "1.50"
    assert run("1.") == "1."
    assert run("0.00") == "0.00"


def test_leading_zeros_collapse():
    assert run("007") == "7"


def test_entry_digit_limit():
    assert run("12345678901234567890") == "1,234,567,890,123,456"


# --- Repeat equals ----------------------------------------------------------


def test_repeat_equals():
    calculator = press(Calculator(), "2 + 3 =")
    assert press(calculator, "=").display == "8"
    assert press(calculator, "=").display == "11"
    assert calculator.expression == "8 + 3 ="


def test_repeat_equals_with_multiply_and_divide():
    assert run("2 * 3 = = =") == "54"
    assert run("100 / 2 = =") == "25"


def test_repeat_equals_uses_last_top_level_operation():
    assert run("2 + 3 * 4 = =") == "56"
    assert run("( 1 + 2 ) * ( 3 + 1 ) = =") == "48"


def test_repeat_equals_with_nothing_to_repeat():
    assert run("5 = =") == "5"
    assert run("9 sqrt = =") == "3"


def test_repeat_equals_percent_uses_effective_amount():
    assert run("200 + 10 % =") == "220"
    assert run("200 + 10 % = =") == "240"


def test_repeat_stops_after_new_number():
    assert run("2 + 3 = 7 = =") == "7"


# --- Division by zero and error recovery ------------------------------------


def test_division_by_zero_message():
    calculator = press(Calculator(), "5 / 0 =")
    assert calculator.error == DIVIDE_BY_ZERO_MESSAGE
    assert calculator.display == DIVIDE_BY_ZERO_MESSAGE
    assert calculator.expression == "5 ÷ 0 ="


def test_zero_divided_by_zero():
    assert run("0 / 0 =") == DIVIDE_BY_ZERO_MESSAGE


@pytest.mark.parametrize(
    "keys, expected",
    [
        ("7", "7"),
        (".", "0."),
        ("+", "0"),
        ("=", "0"),
        ("C", "0"),
        ("AC", "0"),
        ("backspace", "0"),
        ("%", "0"),
        ("negate", "0"),
        ("sqrt", "0"),
        ("square", "0"),
        ("(", "0"),
        (")", "0"),
    ],
)
def test_any_key_recovers_from_error(keys, expected):
    calculator = press(Calculator(), "5 / 0 =")
    press(calculator, keys)
    assert calculator.error is None
    assert calculator.display.replace("-", "") == expected


def test_calculator_works_normally_after_error():
    calculator = press(Calculator(), "5 / 0 = 2 + 2 =")
    assert calculator.display == "4"


def test_memory_survives_an_error():
    calculator = press(Calculator(), "5 M+ 1 / 0 = MR")
    assert calculator.display == "5"


def test_reciprocal_of_zero():
    assert run("0 reciprocal") == DIVIDE_BY_ZERO_MESSAGE


def test_division_by_zero_inside_parentheses_reports_on_close():
    assert run("( 1 / 0 )") == DIVIDE_BY_ZERO_MESSAGE


# --- Percent ----------------------------------------------------------------


def test_standalone_percent():
    assert run("50 %") == "0.5"
    assert run("50 % =") == "0.5"


def test_percent_shows_effective_amount_while_adding():
    calculator = press(Calculator(), "200 + 10 %")
    assert calculator.display == "20"
    assert calculator.expression == "200 + 10%"
    assert press(calculator, "=").display == "220"


def test_percent_subtract_and_multiply():
    assert run("200 - 10 % =") == "180"
    assert run("200 * 10 % =") == "20"
    assert run("200 / 10 % =") == "2,000"


def test_percent_base_stops_at_open_parenthesis():
    assert run("5 * ( 200 + 10 %") == "20"
    assert run("5 * ( 200 + 10 % ) =") == "1,100"


def test_percent_of_a_result():
    assert run("100 + 100 = %") == "2"


def test_sign_toggle_keeps_a_percentage():
    calculator = press(Calculator(), "200 + 10 % negate")
    assert calculator.display == "-20"
    assert press(calculator, "=").display == "180"


def test_repeated_percent_cannot_grow_without_limit():
    calculator = press(Calculator(), "5")
    for _ in range(5000):
        calculator.press("%")
    assert calculator.error is None
    assert len(calculator.expression) < 500


def test_digit_after_percent_replaces_operand():
    assert run("200 + 10 % 5 =") == "205"


# --- Sign toggle ------------------------------------------------------------


def test_sign_toggle_on_entry():
    assert run("5 negate") == "-5"
    assert run("5 negate negate") == "5"
    assert run("5 negate + 8 =") == "3"


def test_sign_toggle_before_typing():
    calculator = press(Calculator(), "negate 5")
    assert calculator.display == "-5"
    assert press(calculator, "+ 8 =").display == "3"


def test_sign_toggle_on_result():
    calculator = press(Calculator(), "2 + 3 = negate")
    assert calculator.display == "-5"
    assert press(calculator, "+ 1 =").display == "-4"


def test_sign_toggle_on_function_result():
    calculator = press(Calculator(), "9 sqrt negate")
    assert calculator.display == "-3"
    assert press(calculator, "negate").display == "3"
    assert press(calculator, "=").display == "3"


def test_sign_toggle_after_operator_uses_display():
    assert run("5 + negate =") == "0"


def test_sign_toggle_on_decimal_entry():
    assert run("1.5 negate") == "-1.5"


# --- Square root, square, reciprocal ----------------------------------------


def test_square_root():
    assert run("9 sqrt") == "3"
    assert run("2 sqrt square =") == "2"


def test_square_root_of_negative_is_an_error():
    calculator = press(Calculator(), "4 negate sqrt")
    assert calculator.error == INVALID_INPUT_MESSAGE
    assert press(calculator, "9 sqrt").display == "3"


def test_failed_function_stays_visible_in_expression():
    calculator = press(Calculator(), "2 + 4 negate sqrt")
    assert calculator.expression == "2 + √(−4)"


def test_square():
    assert run("5 square") == "25"
    assert run("5 negate square") == "25"


def test_reciprocal():
    assert run("4 reciprocal") == "0.25"
    assert run("3 reciprocal * 3 =") == "1"


def test_functions_respect_precedence_in_expression():
    calculator = press(Calculator(), "2 + 9 sqrt")
    assert calculator.expression == "2 + √(9)"
    assert calculator.display == "3"
    assert press(calculator, "* 4 =").display == "14"


def test_function_after_operator_uses_display():
    assert run("9 + sqrt =") == "12"


def test_function_on_result_continues_from_result():
    assert run("5 + 4 = sqrt") == "3"


def test_digit_after_function_replaces_operand():
    assert run("2 + 9 sqrt 5 =") == "7"


def test_function_on_parenthesised_group():
    assert run("( 3 + 6 ) sqrt") == "3"


def test_repeated_functions_cannot_grow_without_limit():
    calculator = press(Calculator(), "16")
    for _ in range(5000):
        calculator.press("sqrt")
    assert calculator.error is None
    assert len(calculator.expression) < 500
    assert Decimal(calculator.display) == 1


# --- Clear and backspace ----------------------------------------------------


def test_clear_entry_keeps_pending_expression():
    calculator = press(Calculator(), "2 + 3 C")
    assert calculator.display == "0"
    assert press(calculator, "5 =").display == "7"


def test_clear_twice_clears_everything():
    calculator = press(Calculator(), "2 + 3 C C")
    assert calculator.expression == ""
    assert calculator.display == "0"


def test_clear_removes_function_operand():
    assert run("2 + 9 sqrt C 5 =") == "7"


def test_all_clear_keeps_memory():
    calculator = press(Calculator(), "5 M+ 2 + 3 AC")
    assert calculator.display == "0"
    assert calculator.expression == ""
    assert calculator.memory == 5


def test_all_clear_stops_repeat():
    assert run("2 + 3 = AC =") == "0"


def test_backspace_on_entry():
    assert run("123 backspace") == "12"
    assert run("1 backspace") == "0"
    assert run("1.5 backspace") == "1."
    assert run("5 negate backspace") == "0"


def test_backspace_walks_back_through_expression():
    calculator = press(Calculator(), "12 + 34")
    press(calculator, "backspace backspace")
    assert calculator.expression == "12 +"
    press(calculator, "backspace")
    assert calculator.expression == ""
    assert calculator.display == "12"
    press(calculator, "backspace")
    assert calculator.display == "1"
    press(calculator, "backspace backspace backspace")
    assert calculator.display == "0"


def test_backspace_after_result_keeps_value():
    calculator = press(Calculator(), "2 + 3 = backspace")
    assert calculator.display == "5"
    assert calculator.expression == ""
    assert press(calculator, "+ 1 =").display == "6"


def test_backspace_removes_function_operand_whole():
    calculator = press(Calculator(), "2 + 9 sqrt backspace")
    assert calculator.expression == "2 +"


def test_backspace_removes_parentheses():
    calculator = press(Calculator(), "( 2 ) backspace")
    assert calculator.expression == "(2"
    press(calculator, "backspace backspace backspace")
    assert calculator.expression == ""
    assert calculator.display == "0"


# --- Memory -----------------------------------------------------------------


def test_memory_starts_empty():
    calculator = Calculator()
    assert not calculator.has_memory
    assert calculator.memory_display == ""
    press(calculator, "MR")
    assert calculator.display == "0"


def test_memory_add_subtract_recall_clear():
    calculator = press(Calculator(), "10 M+")
    assert calculator.has_memory
    assert calculator.memory == 10
    press(calculator, "3 M-")
    assert calculator.memory == 7
    assert calculator.memory_display == "7"
    press(calculator, "AC MR")
    assert calculator.display == "7"
    press(calculator, "MC")
    assert not calculator.has_memory


def test_memory_holding_zero_still_counts_as_holding_a_value():
    calculator = press(Calculator(), "5 M+ 5 M-")
    assert calculator.has_memory
    assert calculator.memory == 0


def test_memory_uses_result():
    calculator = press(Calculator(), "2 + 3 = M+")
    assert calculator.memory == 5
    assert calculator.display == "5"


def test_digit_after_memory_add_starts_a_new_number():
    assert run("5 M+ 6") == "6"


def test_memory_recall_in_expression():
    assert run("5 M+ AC 2 + MR =") == "7"
    assert run("5 M+ AC 3 MR =") == "5"


def test_memory_is_exact():
    calculator = press(Calculator(), "0.1 M+ 0.2 M+")
    assert calculator.memory == Decimal("0.3")


# --- Very large and very small numbers --------------------------------------


def test_large_multiplication_uses_scientific_notation():
    assert run("9999999999999999 * 9999999999999999 =") == "9.999999999999998e+31"


def test_large_number_is_shown_with_separators_when_it_fits():
    assert run("99999999 * 10000000 =") == "999,999,990,000,000"


def test_very_small_uses_scientific_notation():
    assert run("1 / 1000000000000 =") == "1e-12"


def test_overflow_reports_error_and_never_hangs():
    calculator = press(Calculator(), "9999999999999999")
    for _ in range(40):
        calculator.press("square")
        if calculator.error:
            break
    assert calculator.error == TOO_LARGE_MESSAGE
    assert press(calculator, "2 + 2 =").display == "4"


def test_repeated_squares_of_tiny_values_underflow_to_zero():
    calculator = press(Calculator(), "0.0000000000000001")
    for _ in range(40):
        calculator.press("square")
    assert calculator.error is None
    assert calculator.display == "0"


def test_repeat_equals_overflow_is_an_error():
    calculator = press(Calculator(), "9999999999999999 * 9999999999999999 =")
    for _ in range(1000):
        calculator.press("=")
        if calculator.error:
            break
    assert calculator.error == TOO_LARGE_MESSAGE


def test_chained_results_keep_precision():
    assert run("1 / 3 = * 3 =") == "1"
    assert run("2 sqrt = square =") == "2"


# --- Paste ------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, expected_display",
    [
        ("42", "42"),
        ("  1,234.5 \n", "1,234.5"),
        ("-7", "-7"),
        ("2 + 3 × 4", "14"),
        ("(2 + 3", "5"),
        ("1e20", "1e+20"),
    ],
)
def test_paste_valid(text, expected_display):
    calculator = Calculator()
    assert calculator.paste(text) is True
    assert calculator.display == expected_display


@pytest.mark.parametrize(
    "text",
    ["", "hello", "2 +", "1,2", ")", "2 ** 2", "1" * 501, "√(-1)", "1e99999"],
)
def test_paste_invalid_changes_nothing(text):
    calculator = press(Calculator(), "2 + 3")
    assert calculator.paste(text) is False
    assert calculator.expression == "2 + 3"
    assert press(calculator, "=").display == "5"


def test_paste_expression_groups_into_pending_expression():
    calculator = press(Calculator(), "5 *")
    assert calculator.paste("2 + 3") is True
    assert calculator.expression == "5 × (2 + 3)"
    assert press(calculator, "=").display == "25"


def test_paste_number_then_continue():
    calculator = press(Calculator(), "2 +")
    calculator.paste("3")
    assert press(calculator, "=").display == "5"


def test_paste_replaces_result():
    calculator = press(Calculator(), "2 + 3 =")
    calculator.paste("9")
    assert calculator.display == "9"
    assert press(calculator, "+ 1 =").display == "10"


def test_paste_division_by_zero_shows_error():
    calculator = Calculator()
    assert calculator.paste("1/0") is True
    assert calculator.error == DIVIDE_BY_ZERO_MESSAGE


def test_copy_text_has_no_separators():
    calculator = press(Calculator(), "1234567.5")
    assert calculator.copy_text == "1234567.5"
    assert press(calculator, "/ 0 =").copy_text == ""


# --- History records --------------------------------------------------------


def test_equals_reports_completed_calculation_once():
    calculator = press(Calculator(), "1000 + 234.5 =")
    completed = calculator.take_completed()
    assert completed.expression == "1,000 + 234.5 ="
    assert completed.result == "1,234.5"
    assert completed.value == "1234.5"
    assert calculator.take_completed() is None


def test_bare_number_and_errors_are_not_recorded():
    calculator = press(Calculator(), "5 =")
    assert calculator.take_completed() is None
    press(calculator, "1 / 0 =")
    assert calculator.take_completed() is None


def test_repeat_equals_is_recorded():
    calculator = press(Calculator(), "2 + 3 =")
    calculator.take_completed()
    press(calculator, "=")
    assert calculator.take_completed().result == "8"


def test_load_value_restores_full_precision():
    calculator = press(Calculator(), "1 / 3 =")
    value = calculator.take_completed().value
    calculator = Calculator()
    calculator.load_value(value)
    assert press(calculator, "* 3 =").display == "1"


def test_load_value_into_pending_expression():
    calculator = press(Calculator(), "2 +")
    calculator.load_value("5")
    assert press(calculator, "=").display == "7"


def test_history_store_round_trip(tmp_path):
    path = tmp_path / "nested" / "history.json"
    store = HistoryStore(path)
    store.add("1 + 1 =", "2", "2")
    store.add("2 + 2 =", "4", "4")
    reloaded = HistoryStore(path)
    assert [entry.result for entry in reloaded.entries] == ["4", "2"]
    reloaded.clear()
    assert HistoryStore(path).entries == []


@pytest.mark.parametrize("content", ["{not json", '{"a": 1}', '[1, {"result": 3}]'])
def test_history_store_tolerates_corrupt_file(tmp_path, content):
    path = tmp_path / "history.json"
    path.write_text(content)
    assert HistoryStore(path).entries == []


# --- Robustness -------------------------------------------------------------


ALL_KEYS = list("0123456789.+-*/()=%") + [
    "C",
    "AC",
    "backspace",
    "negate",
    "sqrt",
    "square",
    "reciprocal",
    "MC",
    "MR",
    "M+",
    "M-",
]


@pytest.mark.parametrize("seed", range(20))
def test_random_key_mashing_never_raises(seed):
    generator = random.Random(seed)
    calculator = Calculator()
    for _ in range(3000):
        calculator.press(generator.choice(ALL_KEYS))
        # Everything the UI reads must always work too.
        assert isinstance(calculator.display, str) and calculator.display
        assert isinstance(calculator.expression, str)
        assert isinstance(calculator.copy_text, str)
        calculator.take_completed()


def test_unknown_key_is_ignored():
    calculator = press(Calculator(), "5")
    calculator.press("banana")
    assert calculator.display == "5"
