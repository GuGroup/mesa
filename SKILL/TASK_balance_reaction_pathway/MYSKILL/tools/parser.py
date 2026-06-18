# YTK
# YTK

from .species import SpeciesRef
import re

_TERM_RE = re.compile(
    r"""
    ^\s*
    (?:(?P<coefficient>[+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*)?
    (?P<label>\*[A-Za-z][A-Za-z0-9_]*|[A-Za-z][A-Za-z0-9_]*\(g\))
    \s*$
    """,
    re.VERBOSE,
)

def parse_component_term(term: str) -> SpeciesRef:
    match = _TERM_RE.match(term)

    if not match:
        raise ValueError(
            f"invalid component term: {term!r}."
            "Expected forms like 'HNO3(g)', or '4*H'."
        )

    coefficient = float(match.group("coefficient") or 1.0)
    label = match.group("label")

    if label.startswith("*"):
        return SpeciesRef(
            species=label[1:],
            phase="ADS",
            coefficient=coefficient,
        )

    if label.endswith("(g)"):
        return SpeciesRef(
            species=label[:-3],
            phase="GAS",
            coefficient=coefficient,
        )

    raise ValueError(f"component term must include phase or site: {term!r}")

def parse_state_expr(state_expr: str) -> list[SpeciesRef]:
    terms = [term.strip() for term in state_expr.split("+")]
    terms = [term for term in terms if term]

    if not terms:
        raise ValueError("state expression is empty")

    return [parse_component_term(term) for term in terms]

