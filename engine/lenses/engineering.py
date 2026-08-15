#!/usr/bin/env python3
"""engineering.py — every surprising behavior is a candidate.

A performance cliff, a flaky test, a dependency smell, a TODO hiding a real gap,
a coupling that shouldn't exist, an error path never exercised.

"Record all" has teeth here: the refactor task that happens to notice a latent
perf regression logs it *even though nobody asked it to*. That artifact is the
whole reason the protocol exists — the finding nobody was looking for is the one
that never gets found any other way.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List

from .base import Candidate, Lens, register

# Keyword families. Crude by design: a keyword sweep that misses is cheap, and a
# keyword sweep that over-fires just adds a FLAGGED row for the harvest to weigh.
SIGNALS = [
    (
        "flaky",
        r"\b(flak|intermittent|nondeterministic|non-deterministic|passes on retry|"
        r"random(ly)? fail|heisenbug|race)\b",
        "a test that is not a test if it only sometimes passes",
    ),
    (
        "perf-cliff",
        r"\b(cliff|regress\w*|slowdown|latency spike|timeout|O\(n\^?2\)|quadratic|"
        r"thrash\w*|gc pause|p99)\b",
        "a discontinuity in cost, which usually means an algorithmic surprise",
    ),
    (
        "dependency-smell",
        r"\b(pinned to|unpinned|transitive|vendored|deprecat\w+|end.of.life|eol|"
        r"cve-\d{4}|unmaintained|forked upstream)\b",
        "a dependency that will become someone's incident",
    ),
    (
        "hidden-gap",
        r"\b(todo|fixme|hack|xxx|workaround|for now|temporar\w+|revisit)\b",
        "a marker where a real gap was deferred and then forgotten",
    ),
    (
        "coupling",
        r"\b(circular|cyclic|import cycle|god (object|class)|reaches into|"
        r"private api|monkey.?patch|global state)\b",
        "a coupling that will make the next change harder than it should be",
    ),
    (
        "unexercised-path",
        r"\b(never (called|hit|exercised)|no coverage|uncovered|dead code|"
        r"unreachable|except:\s*pass|swallow\w* (the )?(error|exception))\b",
        "an error path that has never run is an error path that does not work",
    ),
]

_COMPILED = [(name, re.compile(pattern, re.I), why) for name, pattern, why in SIGNALS]


@register("engineering")
class EngineeringLens(Lens):
    name = "engineering"
    looks_for = (
        "a perf cliff, a flaky test, a dependency smell, a coupling that shouldn't "
        "exist, an error path never exercised, a TODO hiding a real gap"
    )

    #: a measurement this many times off the group median is a cliff, not noise
    OUTLIER_RATIO = 8.0

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
                            kind="smell" if name != "perf-cliff" else "regression",
                            detail={"signal": name, "matched": found.group(0)},
                        )
                    )

        # ---- numeric outliers: the perf cliff you can see in the numbers ----
        numeric = [
            (r["artifact_id"], self.numeric(r))
            for r in records
            if self.numeric(r) is not None
        ]
        positive = [(aid, v) for aid, v in numeric if v > 0]
        if len(positive) >= 5:
            values = sorted(v for _, v in positive)
            median = values[len(values) // 2]
            if median > 0:
                for artifact_id, value in positive:
                    ratio = value / median
                    if ratio >= self.OUTLIER_RATIO or ratio <= 1 / self.OUTLIER_RATIO:
                        candidates.append(
                            Candidate(
                                artifact_id=artifact_id,
                                reason=(
                                    f"{ratio:.1f}× the group median ({value:.6g} vs "
                                    f"{median:.6g}) across {len(positive)} comparable "
                                    "measurements — a cliff, not a slope"
                                ),
                                kind="regression",
                                # Rank-based and deliberately rough: with n
                                # comparable values, being this far out is roughly
                                # a 1-in-n event before any correction.
                                p_value=min(1.0, 2.0 / len(positive)),
                                detail={"ratio": ratio, "median": median},
                            )
                        )

        # ---- bimodality: the signature of a flaky measurement ---------------
        if len(positive) >= 8:
            values = sorted(v for _, v in positive)
            mid = len(values) // 2
            low, high = values[:mid], values[mid:]
            mean_low = sum(low) / len(low)
            mean_high = sum(high) / len(high)
            spread_low = _stdev(low)
            spread_high = _stdev(high)
            gap = mean_high - mean_low
            pooled = math.sqrt(spread_low**2 + spread_high**2) or 1e-12
            if gap / pooled > 4.0:
                candidates.append(
                    Candidate(
                        artifact_id=positive[0][0],
                        reason=(
                            f"the {len(positive)} measurements split into two tight "
                            f"clusters ({mean_low:.4g} and {mean_high:.4g}, gap "
                            f"{gap / pooled:.1f}σ). Two clusters usually means two "
                            "code paths, not one noisy one — find the switch."
                        ),
                        kind="anomaly",
                        detail={"low": mean_low, "high": mean_high},
                    )
                )

        return candidates


def _stdev(values: List[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return math.sqrt(sum((v - mean) ** 2 for v in values) / (len(values) - 1))
