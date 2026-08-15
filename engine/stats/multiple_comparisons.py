#!/usr/bin/env python3
"""multiple_comparisons.py — the FDR machinery behind the promotion gate.

The generalization of the predecessor's "Wave 4b BH harvest". Stdlib only.

Why FDR and not Bonferroni, stated once here because every lens depends on it: a
curiosity pool is thousands of comparisons, and Bonferroni at that scale rejects
everything. That *sounds* safe, but a protocol that can never promote anything is
not a cautious discovery system — it is a discovery system that does not work.
Benjamini–Hochberg controls the expected *proportion* of promoted findings that
are false, which is the quantity a human reading the digest actually cares about.
"""

from __future__ import annotations

from typing import Dict, List


def benjamini_hochberg(p_values: List[float], q: float = 0.10) -> List[bool]:
    """BH step-up. Returns a same-order mask: True = reject the null = promote.

    Find the largest rank k with p_(k) ≤ (k/n)·q, then reject every hypothesis at
    rank ≤ k — including ones whose own p-value fails the per-rank threshold.
    That step-up behaviour is the whole procedure; testing each p independently
    against (its own rank/n)·q is a common and subtly wrong reimplementation.
    """
    if not p_values:
        return []
    n = len(p_values)
    order = sorted(range(n), key=lambda i: p_values[i])
    rejected = [False] * n
    max_k = 0
    for rank, idx in enumerate(order, start=1):
        if p_values[idx] <= (rank / n) * q:
            max_k = rank
    for rank, idx in enumerate(order, start=1):
        if rank <= max_k:
            rejected[idx] = True
    return rejected


def bh_q_values(p_values: List[float]) -> List[float]:
    """BH-adjusted q-values, in the input's order.

    Walks from the largest p downward taking a running minimum, which enforces
    the monotonicity the adjustment requires (a smaller p can never end up with
    a larger q than a bigger one).
    """
    if not p_values:
        return []
    n = len(p_values)
    order = sorted(range(n), key=lambda i: p_values[i])
    q = [0.0] * n
    running_min = 1.0
    for rank in range(n, 0, -1):
        idx = order[rank - 1]
        raw = p_values[idx] * n / rank
        running_min = min(running_min, raw)
        q[idx] = min(1.0, running_min)
    return q


def bonferroni(p_values: List[float], alpha: float = 0.05) -> List[bool]:
    """FWER control. Provided for the rare case where a single false promotion
    would be costly enough to justify finding almost nothing."""
    if not p_values:
        return []
    threshold = alpha / len(p_values)
    return [p <= threshold for p in p_values]


def summarize(p_values: List[float], q: float = 0.10) -> Dict[str, float]:
    """A one-glance description of what a harvest is about to do."""
    if not p_values:
        return {"n": 0, "promoted": 0, "q": q, "min_p": float("nan")}
    rejected = benjamini_hochberg(p_values, q)
    return {
        "n": len(p_values),
        "promoted": sum(rejected),
        "q": q,
        "min_p": min(p_values),
        "expected_false_promotions": round(q * max(sum(rejected), 0), 3),
    }
