#!/usr/bin/env python3
"""writing.py — every unstated assumption is a candidate.

Every claim that outran its support, every structural gap, every reader-question
the draft raises and does not answer.

This lens is the one most likely to fire on the system's *own* prose, which is
the point: a doctrine document that hedges everywhere, or asserts without
evidence, fails the same way a research claim does.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from .base import Candidate, Lens, register

SIGNALS = [
    (
        "unsupported-claim",
        r"\b(obviously|clearly|of course|it is well known|everyone knows|"
        r"needless to say|goes without saying|self.?evident)\b",
        "asserting that something needs no support is not support",
    ),
    (
        "outran-evidence",
        r"\b(proves?|demonstrates? conclusively|guarantees?|always|never fails|"
        r"in all cases|100%|certainly|undoubtedly)\b",
        "a claim stronger than any finite evidence can carry",
    ),
    (
        "hedge-stack",
        r"\b(may(be)? possibly|might potentially|could perhaps|somewhat likely|"
        r"appears to suggest|seems to indicate that it may)\b",
        "stacked hedges usually mean the author does not know and has not said so",
    ),
    (
        "unstated-assumption",
        r"\b(assum\w+|presum\w+|given that|taking for granted|stipulat\w+|"
        r"we take it that|by definition)\b",
        "an assumption named in passing that no section actually establishes",
    ),
    (
        "structural-gap",
        r"\b(tbd|todo|\[fill\]|placeholder|coming soon|to be (written|determined)|"
        r"lorem ipsum|xxx)\b",
        "a hole the draft admits to and the reader will find",
    ),
    (
        "dangling-reference",
        r"(see (section|chapter|figure|table|appendix) [_?]|"
        r"\[citation needed\]|\bibid\.?\s*$|as (discussed|shown) (above|below)\b)",
        "a pointer to something the reader cannot follow",
    ),
    (
        "reader-question",
        r"\b(but why|how does that|what about|unclear (how|why|whether)|"
        r"raises the question|one might ask)\b",
        "a question the draft raises in the reader's head and leaves open",
    ),
]

_COMPILED = [(name, re.compile(pattern, re.I), why) for name, pattern, why in SIGNALS]


@register("writing")
class WritingLens(Lens):
    name = "writing"
    looks_for = (
        "an unstated assumption, a claim outrunning its support, a structural gap, "
        "a dangling reference, a reader-question left unanswered"
    )

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
                            reason=f"{name}: {found.group(0)!r} — {why}",
                            kind="smell",
                            detail={"signal": name, "matched": found.group(0)},
                        )
                    )

            # A prose artifact with no context line is itself a gap: nobody
            # downstream can tell what it was for.
            if record.get("path") and not record.get("context"):
                candidates.append(
                    Candidate(
                        artifact_id=record["artifact_id"],
                        reason=(
                            f"{record['path']} was logged with no context line. An "
                            "artifact nobody can identify later is an artifact that "
                            "will be re-derived from scratch."
                        ),
                        kind="smell",
                        detail={"signal": "no-context"},
                    )
                )

        return candidates
