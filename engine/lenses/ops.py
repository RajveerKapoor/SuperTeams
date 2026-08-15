#!/usr/bin/env python3
"""ops.py — every anomaly is a candidate.

A metric out of band, a log pattern that is new, config drift, a resource
creeping. Serendipity here is catching the incident *before* it is an incident:
the value of this lens is measured in pages that never fire.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List

from .base import Candidate, Lens, register

SIGNALS = [
    (
        "saturation",
        r"\b(oom|out of memory|disk full|no space left|throttl\w+|rate.?limit\w*|"
        r"429|503|backpressure|queue depth|connection pool exhaust\w*)\b",
        "a resource at its ceiling",
    ),
    (
        "new-log-pattern",
        r"\b(first (seen|occurrence)|new error|unrecognized|unknown (error|code)|"
        r"unexpected|stack ?trace|panic|segfault|core dump)\b",
        "a message the system has not emitted before",
    ),
    (
        "config-drift",
        r"\b(drift\w*|out of sync|differs from|manual (change|edit)|"
        r"not in (git|source control)|hotfix\w*|hand.?edited)\b",
        "running state that no longer matches declared state",
    ),
    (
        "creep",
        r"\b(creep\w*|growing|leak\w*|unbounded|monotonic\w* increas\w*|"
        r"never (freed|released|reclaimed))\b",
        "a resource that goes up and never comes down",
    ),
    (
        "silent-degradation",
        r"\b(retry|retries|fallback|degraded|partial (failure|outage)|"
        r"circuit.?break\w*|stale (cache|read))\b",
        "the system absorbing a fault instead of reporting it",
    ),
]

_COMPILED = [(name, re.compile(pattern, re.I), why) for name, pattern, why in SIGNALS]


@register("ops")
class OpsLens(Lens):
    name = "ops"
    looks_for = (
        "a metric out of band, a new log pattern, config drift, a resource "
        "creeping, a fault the system is silently absorbing"
    )

    #: |z| beyond this against the group is out of band
    Z_THRESHOLD = 3.0

    def sweep(self, records: List[Dict[str, Any]]) -> List[Candidate]:
        candidates: List[Candidate] = []

        for record in records:
            haystack = self.text(record)
            for name, pattern, why in _COMPILED:
                found = pattern.search(haystack)
                if found:
                    candidates.append(
                        Candidate(
                            artifact_id=record["artifact_id"],
                            reason=f"{name}: matched {found.group(0)!r} — {why}",
                            kind="anomaly",
                            detail={"signal": name, "matched": found.group(0)},
                        )
                    )

        # ---- out-of-band metrics --------------------------------------------
        numeric = [
            (r["artifact_id"], self.numeric(r))
            for r in records
            if self.numeric(r) is not None
        ]
        if len(numeric) >= 6:
            values = [v for _, v in numeric]
            mean = sum(values) / len(values)
            spread = math.sqrt(
                sum((v - mean) ** 2 for v in values) / (len(values) - 1)
            )
            if spread > 0:
                for artifact_id, value in numeric:
                    z = abs(value - mean) / spread
                    if z >= self.Z_THRESHOLD:
                        candidates.append(
                            Candidate(
                                artifact_id=artifact_id,
                                reason=(
                                    f"{z:.1f}σ from the group mean ({value:.6g} vs "
                                    f"{mean:.6g}±{spread:.3g}, n={len(values)}) — "
                                    "out of band"
                                ),
                                kind="anomaly",
                                p_value=_two_sided_normal_p(z),
                                detail={"z": z, "mean": mean, "sd": spread},
                            )
                        )

        # ---- monotone creep --------------------------------------------------
        # Records arrive in log order, so a strictly rising numeric series is a
        # resource going one way. Six points is enough to be worth a look and
        # short enough to catch it early.
        series = [v for _, v in numeric]
        if len(series) >= 6 and all(b > a for a, b in zip(series, series[1:])):
            growth = series[-1] / series[0] if series[0] else float("inf")
            candidates.append(
                Candidate(
                    artifact_id=numeric[-1][0],
                    reason=(
                        f"strictly monotonic increase across all {len(series)} "
                        f"samples ({series[0]:.4g} → {series[-1]:.4g}, {growth:.1f}×). "
                        "Something that only goes up is a leak until proven otherwise."
                    ),
                    kind="scaling",
                    # P(a random permutation is sorted) = 1/n!
                    p_value=min(1.0, 1.0 / math.factorial(min(len(series), 12))),
                    detail={"first": series[0], "last": series[-1], "n": len(series)},
                )
            )

        return candidates


def _two_sided_normal_p(z: float) -> float:
    """2·(1 − Φ(|z|)) via erfc. Normality is an assumption, and a shaky one for
    most ops metrics — this ranks candidates, it does not certify them."""
    return max(1e-16, math.erfc(abs(z) / math.sqrt(2.0)))
