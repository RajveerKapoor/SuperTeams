#!/usr/bin/env python3
"""generic.py — for a mixed or novel domain. Pre-judges NOTHING.

This lens exists because of the deepest point in the predecessor's protocol:
**gravity and calculus were not matches against an existing library.** A system
that filters findings through "does this match something I already know?" will
systematically miss anything genuinely new — it can only ever rediscover.

So this lens has no keyword table and no constants library. It surfaces things by
*structure of the pool itself*: what is unusual relative to its own neighbours,
what is unique, what the work itself flagged. Those signals do not require anyone
to have anticipated the finding's shape in advance.

It is also the fallback for an unknown lens name, which is why it must be the
conservative one.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Any, Dict, List

from .base import Candidate, Lens, register


@register("generic")
class GenericLens(Lens):
    name = "generic"
    looks_for = (
        "anything surprising, judged only against the pool itself — no keyword "
        "table, no constants library, no prior about what a finding looks like"
    )

    #: |z| beyond this against the pool's own distribution
    Z_THRESHOLD = 3.0

    def sweep(self, records: List[Dict[str, Any]]) -> List[Candidate]:
        candidates: List[Candidate] = []

        # 1. The work's own flag. The Subagent that produced the artifact had
        #    context nobody downstream has; if it wrote a note, that is a signal
        #    on its own and it does not need to justify itself to a pattern table.
        for record in records:
            if record.get("candidate_note"):
                candidates.append(
                    Candidate(
                        artifact_id=record["artifact_id"],
                        reason=(
                            "flagged by the work that produced it: "
                            f"{record['candidate_note']}"
                        ),
                        kind=record.get("kind") or "anomaly",
                        detail={"signal": "author-flagged"},
                    )
                )

        # 2. Numeric outliers against the pool's own distribution.
        numeric = [
            (r["artifact_id"], self.numeric(r))
            for r in records
            if self.numeric(r) is not None
        ]
        if len(numeric) >= 6:
            values = [v for _, v in numeric]
            mean = sum(values) / len(values)
            spread = math.sqrt(sum((v - mean) ** 2 for v in values) / (len(values) - 1))
            if spread > 0:
                for artifact_id, value in numeric:
                    z = abs(value - mean) / spread
                    if z >= self.Z_THRESHOLD:
                        candidates.append(
                            Candidate(
                                artifact_id=artifact_id,
                                reason=(
                                    f"{z:.1f}σ from the pool mean — unusual relative "
                                    "to its own neighbours, with no prior about what "
                                    "it should have been"
                                ),
                                kind="anomaly",
                                p_value=max(1e-16, math.erfc(z / math.sqrt(2.0))),
                                detail={"z": z},
                            )
                        )

        # 3. Exact repeats. Independent measurements landing on the identical
        #    value is either a real invariant or a copied result. Both matter,
        #    and neither is visible without checking.
        exact = Counter(
            f"{v!r}" for _, v in numeric if v is not None
        )
        for literal, count in exact.items():
            if count >= 3:
                ids = [aid for aid, v in numeric if f"{v!r}" == literal]
                candidates.append(
                    Candidate(
                        artifact_id=ids[0],
                        reason=(
                            f"{count} artifacts carry the identical value {literal} "
                            f"({', '.join(ids[:5])}{'…' if len(ids) > 5 else ''}). "
                            "Either an invariant worth naming, or one result copied "
                            "into several places — worth knowing which."
                        ),
                        kind="relationship",
                        detail={"count": count, "artifacts": ids[:20]},
                    )
                )

        # 4. Singletons of kind. A pool where exactly one artifact has a given
        #    kind means one task saw something none of its peers did.
        kinds = Counter(r.get("kind") for r in records)
        if len(records) >= 8:
            for record in records:
                if kinds[record.get("kind")] == 1:
                    candidates.append(
                        Candidate(
                            artifact_id=record["artifact_id"],
                            reason=(
                                f"the only {record.get('kind')!r} artifact among "
                                f"{len(records)} — one task saw something none of "
                                "its peers did"
                            ),
                            kind=record.get("kind") or "anomaly",
                            detail={"signal": "kind-singleton"},
                        )
                    )

        return candidates
