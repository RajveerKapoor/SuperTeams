#!/usr/bin/env python3
"""research.py — the predecessor's Curiosity Protocol, kept in spirit, as one lens.

Known-constant match, pairwise ratios, continued-fraction expansion, small
integer-relation search, near-coincidence thresholds. This was the whole protocol
in the predecessor system; here it is the specialized case of a general machinery.

**The honest caveat, stated in the code because it governs how the output must be
read:** the p-values below come from a deliberately crude null — "a value drawn
log-uniformly from a comparable range". They exist to *rank* candidates for the
BH pass, not to certify any one of them. A constant match with p≈1e-4 out of a
pool of 20,000 artifacts is not a discovery; it is the arithmetic of a large pool.
That is exactly why promotion happens later, across the whole pool, under FDR.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

from .base import Candidate, Lens, register

# The matchers live in curiosity/ (doctrine/03 section 1) so anything can use
# them; this lens is the adapter that decides what counts as a candidate.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from curiosity.constants import (  # noqa: E402
    CONSTANTS,
    DEFAULT_TAU,
    SMALL_RATIONAL_MAX_DEN,
    continued_fraction,
    integer_relation,
    match_constant,
    match_small_rational,
    p_constant_match,
    p_rational_match,
)


@register("research")
class ResearchLens(Lens):
    name = "research"
    looks_for = (
        "a constant match, a small-rational match, a striking continued fraction, "
        "a pairwise ratio that lands on something, a near-coincidence between two "
        "independent measurements"
    )

    def __init__(self, tau: float = DEFAULT_TAU, max_pairs: int = 4000):
        self.tau = tau
        # Pairwise sweeps are O(n²). The cap is a *stated* bound, not a silent
        # truncation: sweep() reports when it stops so the pool never looks
        # more thoroughly examined than it was.
        self.max_pairs = max_pairs

    def sweep(self, records: List[Dict[str, Any]]) -> List[Candidate]:
        candidates: List[Candidate] = []
        numeric: List[tuple] = []

        for record in records:
            value = self.numeric(record)
            if value is None:
                continue
            numeric.append((record.get("artifact_id"), value, record))

            hit = match_constant(value, self.tau)
            if hit:
                name, target, err = hit
                candidates.append(
                    Candidate(
                        artifact_id=record["artifact_id"],
                        reason=f"within {err:.2e} of {name} ({target:.9g})",
                        kind="relationship",
                        p_value=p_constant_match(max(err, 1e-12), len(CONSTANTS)),
                        detail={"constant": name, "target": target, "rel_error": err},
                    )
                )

            rational = match_small_rational(value, self.tau)
            if rational:
                frac, err = rational
                candidates.append(
                    Candidate(
                        artifact_id=record["artifact_id"],
                        reason=f"within {err:.2e} of {frac.numerator}/{frac.denominator}",
                        kind="relationship",
                        p_value=p_rational_match(
                            max(err, 1e-12), SMALL_RATIONAL_MAX_DEN, magnitude=value
                        ),
                        detail={"rational": str(frac), "rel_error": err},
                    )
                )

            cf = continued_fraction(value)
            # A partial quotient this large means the preceding convergent is an
            # extraordinarily good rational approximation.
            big = [q for q in cf[1:] if abs(q) >= 100]
            if big:
                candidates.append(
                    Candidate(
                        artifact_id=record["artifact_id"],
                        reason=f"continued fraction {cf} has a large partial quotient "
                        f"({max(big, key=abs)}) — near a simple rational",
                        kind="novel-form",
                        p_value=None,
                        detail={"cf": cf},
                    )
                )

        # ---- pairwise: ratios and two-term integer relations ------------------
        pairs_examined = 0
        truncated = False
        for i in range(len(numeric)):
            for j in range(i + 1, len(numeric)):
                if pairs_examined >= self.max_pairs:
                    truncated = True
                    break
                pairs_examined += 1
                id_a, a, _ = numeric[i]
                id_b, b, _ = numeric[j]
                if b == 0:
                    continue

                ratio = a / b
                hit = match_constant(ratio, self.tau)
                if hit:
                    name, target, err = hit
                    candidates.append(
                        Candidate(
                            artifact_id=id_a,
                            reason=f"ratio to {id_b} is within {err:.2e} of {name}",
                            kind="relationship",
                            p_value=p_constant_match(max(err, 1e-12), len(CONSTANTS)),
                            detail={"with": id_b, "ratio": ratio, "constant": name},
                        )
                    )

                relation = integer_relation(a, b)
                if relation:
                    m, n, k = relation
                    candidates.append(
                        Candidate(
                            artifact_id=id_a,
                            reason=f"integer relation with {id_b}: "
                            f"{m}·a + {n}·b ≈ {k}",
                            kind="relationship",
                            p_value=None,
                            detail={"with": id_b, "m": m, "n": n, "k": k},
                        )
                    )
            if truncated:
                break

        if truncated:
            # Law: no silent caps. A bounded sweep says so, in the pool.
            candidates.append(
                Candidate(
                    artifact_id=numeric[0][0] if numeric else "—",
                    reason=(
                        f"PAIRWISE SWEEP TRUNCATED at {self.max_pairs} pairs "
                        f"({len(numeric)} numeric artifacts). Coverage is partial — "
                        "re-run with a higher max_pairs to complete it."
                    ),
                    kind="infeasibility",
                    p_value=None,
                    detail={"examined": pairs_examined, "numeric_artifacts": len(numeric)},
                )
            )

        return candidates
