"""Rules for the caretaker sign-in PIN.

Six digits, because the PIN is the whole credential once a phone is registered.
Obvious choices are refused: they are the first thing anyone who has picked up
the phone would try.
"""

import re

PIN_LENGTH = 6
PIN_RULE_MESSAGE = "Choose a 6-digit PIN that is not an obvious one such as 123456 or 000000."

_PIN_PATTERN = re.compile(rf"\d{{{PIN_LENGTH}}}")


def is_acceptable_pin(pin: str) -> bool:
    if not _PIN_PATTERN.fullmatch(pin):
        return False
    digits = [int(ch) for ch in pin]
    if len(set(digits)) < 3:  # 000000, 111111, 121212, 112211
        return False
    steps = {b - a for a, b in zip(digits, digits[1:], strict=False)}
    if steps in ({1}, {-1}):  # 123456, 654321
        return False
    half = PIN_LENGTH // 2
    if pin[:half] == pin[half:]:  # 123123
        return False
    return True
