"""curiosity — reusable Curiosity-Protocol libs (doctrine/03 section 1).

`constants.py` is the research lens's matcher library. It is a *lib*, not a lens:
the lens decides what counts as a candidate, this decides whether a number is
close to something nameable.
"""

from .constants import (  # noqa: F401
    CONSTANTS,
    DEFAULT_TAU,
    SMALL_RATIONAL_MAX_DEN,
    continued_fraction,
    integer_relation,
    match_constant,
    match_small_rational,
    p_constant_match,
    p_rational_match,
    relative_error,
)
