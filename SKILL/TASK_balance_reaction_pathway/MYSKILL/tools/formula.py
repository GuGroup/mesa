import re

_FORMULA_RE = re.compile(r"([CHON])(\d*)")

def parse_formula_CHON(formula: str) -> dict[str, float]:
    count = {"C": 0.0, "H": 0.0, "O": 0.0, "N": 0.0}

    pos = 0
    for match in _FORMULA_RE.finditer(formula):
        if match.start() != pos:
            raise ValueError(f"invalid CHON formula: {formula!r}")

        elem = match.group(1)
        num = match.group(2)
        count[elem] += float(num) if num else 1.0
        pos = match.end()

    if pos != len(formula):
        raise ValueError(f"invlaid CHON formula: {formula!r}")

    return count

