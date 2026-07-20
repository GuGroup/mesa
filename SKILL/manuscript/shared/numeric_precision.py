"""Normalize decimal precision in public manuscript text."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


DECIMAL_LITERAL = re.compile(
    r"(?<![\w.])(?P<mantissa>[+\-−]?\d+\.\d{3,})(?P<exponent>[eE][+\-]?\d+)?(?!\w|\.\d)"
)
TWO_DECIMAL_PLACES = Decimal("0.01")


def format_numeric_precision(text: str) -> str:
    """Round decimal literals beyond two places while preserving other text."""

    def replace(match: re.Match[str]) -> str:
        mantissa = match.group("mantissa")
        unicode_minus = mantissa.startswith("−")
        try:
            value = Decimal(mantissa.replace("−", "-"))
        except InvalidOperation:
            return match.group(0)
        rounded = value.quantize(TWO_DECIMAL_PLACES, rounding=ROUND_HALF_UP)
        rendered = format(rounded, "f").rstrip("0").rstrip(".")
        if rendered == "-0":
            rendered = "0"
        elif unicode_minus and rendered.startswith("-"):
            rendered = "−" + rendered[1:]
        return rendered + (match.group("exponent") or "")

    return DECIMAL_LITERAL.sub(replace, str(text))


def overprecise_decimal_literals(text: str) -> list[str]:
    """Return decimal literals that exceed two places."""

    return [match.group(0) for match in DECIMAL_LITERAL.finditer(str(text))]
