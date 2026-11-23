"""Small arithmetic evaluator and layout rules for the camera chip tray."""
from fractions import Fraction
import re


_DIGITS = re.compile(r"[0-9]{1,8}\Z")
_PRECEDENCE = {"+": 1, "-": 1, "*": 2, "/": 2}
_LABELS = {
    "plus": "+", "add": "+", "minus": "-", "subtract": "-", "−": "-",
    "times": "*", "multiply": "*", "x": "*", "×": "*", "asterisk": "*",
    "divide": "/", "division": "/", "÷": "/", "slash": "/",
    "equals": "=", "equal": "=", "question": "?", "question mark": "?",
}
_DISPLAY = {"*": "×", "/": "÷", "-": "−"}


def token(label):
    key = label.strip().casefold()
    value = _LABELS.get(key, key)
    return value if value in (*_PRECEDENCE, "=", "?") or _DIGITS.fullmatch(value) else None


def evaluate(labels):
    """Evaluate only numbers and the four arithmetic operators."""
    tokens = [token(label) for label in labels]
    if tokens and tokens[-1] == "?":
        tokens.pop()
    if tokens and tokens[-1] == "=":
        tokens.pop()
    if not 0 < len(tokens) <= 24 or any(value is None or value in ("=", "?") for value in tokens):
        raise ValueError("Show a complete row of numbers and +, −, × or ÷. Put = or = ? at the end.")
    # Adjacent digit chips form one number.
    merged = []
    for value in tokens:
        if merged and value.isdecimal() and merged[-1].isdecimal():
            merged[-1] += value
        else:
            merged.append(value)
    numbers, ops = [], []
    expect_number = True
    sign = 1

    def combine():
        right, left, operator = numbers.pop(), numbers.pop(), ops.pop()
        if operator == "/" and right == 0:
            raise ValueError("Division by zero is undefined.")
        numbers.append({"+": lambda: left + right, "-": lambda: left - right,
                        "*": lambda: left * right, "/": lambda: left / right}[operator]())

    for value in merged:
        if value.isdecimal():
            if not expect_number or len(value) > 8:
                raise ValueError("Use whole-number terms of up to eight digits.")
            numbers.append(Fraction(sign * int(value)))
            sign, expect_number = 1, False
        elif expect_number and value in ("+", "-"):
            sign *= -1 if value == "-" else 1
        elif expect_number:
            raise ValueError("Place a number before or after each operator.")
        else:
            while ops and _PRECEDENCE[ops[-1]] >= _PRECEDENCE[value]:
                combine()
            ops.append(value)
            expect_number = True
    if expect_number:
        raise ValueError("The equation ends with an operator.")
    while ops:
        combine()
    if not any(value in _PRECEDENCE for value in merged):
        raise ValueError("Use at least one arithmetic operator.")
    return " ".join(_DISPLAY.get(value, value) for value in merged), numbers[0]


def split_chips(chips, divider):
    """Read lines above the divider and keep the bank below it."""
    rows = []
    bank = []
    for chip in sorted(chips, key=lambda item: item.centre[1]):
        x, y, width, height = chip.bounds
        if y < divider < y + height:
            raise ValueError("Move chips away from the equation/bank divider.")
        if chip.centre[1] >= divider:
            bank.append(chip)
            continue
        line = next((row for row in rows if abs(row[0].centre[1] - chip.centre[1])
                     <= max(10, min(row[0].bounds[3], height) * 0.42)), None)
        if line is None:
            rows.append([chip])
        else:
            line.append(chip)
    return [tuple(sorted(row, key=lambda item: item.centre[0])) for row in rows], bank
