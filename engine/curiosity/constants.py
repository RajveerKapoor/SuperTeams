#!/usr/bin/env python3
"""constants.py — the research lens's matcher library (doctrine/03 section 1).

The predecessor's Curiosity Protocol built on a known-constants table, pairwise
ratios, continued fractions and integer-relation search. That machinery lives
here as a reusable lib so the `research` lens is a thin adapter over it and any
other lens (or a Subagent doing a one-off sweep) can call the same matchers.

**The library is deliberately SMALL.** A constants table large enough to match
anything matches nothing: every entry widens the union-bound null in
`p_constant_match`, so adding constants makes each individual match *less*
surprising, not more. Growing this table is a real decision with a statistical
cost, not a freebie.
"""

from __future__ import annotations

import math
from fractions import Fraction
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# The table
# ---------------------------------------------------------------------------

CONSTANTS: Dict[str, float] = {
    "π": math.pi,
    "e": math.e,
    "φ (golden ratio)": (1 + math.sqrt(5)) / 2,
    "√2": math.sqrt(2),
    "√3": math.sqrt(3),
    "√5": math.sqrt(5),
    "ln 2": math.log(2),
    "ln 10": math.log(10),
    "γ (Euler–Mascheroni)": 0.5772156649015329,
    "ζ(3) (Apéry)": 1.2020569031595943,
    "Catalan G": 0.9159655941772190,
    "π²": math.pi**2,
    "π²/6": math.pi**2 / 6,
    "π/2": math.pi / 2,
    "π/4": math.pi / 4,
    "2π": 2 * math.pi,
    "√π": math.sqrt(math.pi),
    "e^π": math.e**math.pi,
    "1/π": 1 / math.pi,
    "Feigenbaum δ": 4.669201609102990,
    "Feigenbaum α": 2.502907875095892,
}

#: rationals up to this denominator are their own match family
SMALL_RATIONAL_MAX_DEN = 12

#: relative tolerance for "this is a match"
DEFAULT_TAU = 1e-4


def relative_error(value: float, target: float) -> float:
    if target == 0:
        return abs(value)
    return abs(value - target) / abs(target)


# ---------------------------------------------------------------------------
# Matchers
# ---------------------------------------------------------------------------


def match_constant(
    value: float, tau: float = DEFAULT_TAU
) -> Optional[Tuple[str, float, float]]:
    """Closest library constant within `tau`. Returns (name, target, rel_error)."""
    best: Optional[Tuple[str, float, float]] = None
    for name, target in CONSTANTS.items():
        err = relative_error(value, target)
        if err <= tau and (best is None or err < best[2]):
            best = (name, target, err)
    return best


def match_small_rational(
    value: float, tau: float = DEFAULT_TAU, max_den: int = SMALL_RATIONAL_MAX_DEN
) -> Optional[Tuple[Fraction, float]]:
    """Closest rational with denominator ≤ `max_den`, if within `tau`."""
    if not math.isfinite(value) or value == 0:
        return None
    approx = Fraction(value).limit_denominator(max_den)
    if approx == 0:
        return None
    err = relative_error(value, float(approx))
    return (approx, err) if err <= tau else None


def continued_fraction(value: float, terms: int = 8) -> List[int]:
    """The first `terms` partial quotients.

    A large partial quotient early means the convergent before it is an
    unusually good rational approximation — the classic signal that a measured
    number "wants" to be a simple ratio.
    """
    out: List[int] = []
    x = value
    for _ in range(terms):
        if not math.isfinite(x):
            break
        whole = math.floor(x)
        out.append(int(whole))
        frac = x - whole
        if frac < 1e-12:
            break
        x = 1 / frac
    return out


def integer_relation(
    a: float, b: float, max_coeff: int = 8, tau: float = 1e-6
) -> Optional[Tuple[int, int, int]]:
    """Small integers (m, n, k) with m·a + n·b ≈ k, or None.

    A brute-force two-term stand-in for PSLQ: enough to catch the relations that
    actually appear between two measured quantities, small enough that the null
    stays computable.
    """
    best: Optional[Tuple[int, int, int]] = None
    best_err = tau
    for m in range(-max_coeff, max_coeff + 1):
        for n in range(-max_coeff, max_coeff + 1):
            # BOTH coefficients must be non-zero. With m=0 the "relation" says
            # nothing about `a` — it is just the statement that `b` is near a
            # rational, which match_small_rational already reports. Allowing it
            # floods the pool with one junk candidate per pair.
            if m == 0 or n == 0:
                continue
            combo = m * a + n * b
            k = round(combo)
            scale = max(abs(m * a), abs(n * b), 1.0)
            err = abs(combo - k) / scale
            if err < best_err:
                best_err = err
                best = (m, n, int(k))
    return best


# ---------------------------------------------------------------------------
# Nulls — crude on purpose, and only ever used to RANK for the FDR pass
# ---------------------------------------------------------------------------


def p_constant_match(tau: float, n_constants: int = len(CONSTANTS)) -> float:
    """Union bound: P(a log-uniform value lands within relative τ of ANY of N).

    This is not a certification. Out of a pool of 20,000 artifacts, a match at
    p≈1e-4 is the arithmetic of a large pool, not a discovery — which is exactly
    why promotion happens later, across the whole pool, under Benjamini–Hochberg.
    """
    return min(1.0, 2.0 * tau * n_constants)


def p_rational_match(
    tau: float, max_den: int = SMALL_RATIONAL_MAX_DEN, magnitude: float = 1.0
) -> float:
    """P(a value of this magnitude lands within relative τ of SOME rational p/q, q ≤ D).

    `magnitude` is load-bearing and easy to leave out, which makes this null
    wrong in a way that flatters the finding. A relative tolerance τ on a value
    v spans an ABSOLUTE window of 2τ|v|. Rationals with denominator exactly q sit
    1/q apart, so the count of candidates inside that window grows with |v|:

        matches ≈ 2τ|v| · Σ_{q≤D} q  ≈  2τ|v| · 3D²/π²

    Concretely: 41.902 is within 5.7e-5 of 419/10, which looks striking at
    relative precision and is nearly certain to happen for ANY number near 42
    (p ≈ 0.2). The same relative closeness at 0.75 is genuinely rare. Dropping
    the magnitude term reports both as p ≈ 5e-3 and floods the pool with the
    former.
    """
    density = 3.0 * max_den**2 / math.pi**2
    return min(1.0, 2.0 * tau * max(abs(magnitude), 1e-12) * density)
