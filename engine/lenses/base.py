#!/usr/bin/env python3
"""base.py — the lens interface and the shared multiple-comparison machinery.

A **lens** answers one domain-specific question: *given the artifacts a task
produced, what here is worth a second look?* Everything else about the Curiosity
Protocol is domain-independent and lives here:

  record ALL  →  provenance-tag  →  sweep with a lens  →  FLAG candidates
                                 →  (later, in a separate pass) FDR-gate  →  PROMOTE

Two rules this module exists to enforce mechanically:

1. **A lens never promotes.** `sweep()` returns Candidates; the only status a lens
   may cause is `FLAGGED`. Promotion happens in `runners/harvest.py`, across the
   whole pool, after the wave is closed. A finding promoted by the same pass that
   found it has been graded by its own author.

2. **A lens never filters the pool.** It reads every record handed to it,
   including the boring ones. "It looked boring" is precisely the case the
   protocol exists for, and uniform examination is also the defense against
   fabrication-by-selection.

Stdlib only, on purpose: the Curiosity Protocol must run in any mission workspace
without a dependency install standing between a Subagent and logging what it saw.
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

# The one status a lens may assign. Kept as a constant so that a lens that tries
# to write PROMOTED trips a grep, a review, and the harvest's own check.
LENS_STATUS = "FLAGGED"


@dataclass
class Candidate:
    """One thing a lens thinks is worth a second look.

    `p_value` is optional and often absent — most lenses are qualitative, and a
    made-up p-value is worse than none because the FDR pass would treat it as
    real. A candidate with `p_value=None` is ranked by the harvest but never
    given a q-value it did not earn.
    """

    artifact_id: str
    reason: str
    kind: str = "anomaly"
    p_value: Optional[float] = None
    detail: Dict[str, Any] = field(default_factory=dict)

    def note(self) -> str:
        """The one-line `candidate_note` written back into the pool."""
        if self.p_value is None:
            return self.reason
        return f"{self.reason} (p≈{self.p_value:.3g}, uncorrected)"


class Lens:
    """The whole interface. Implement `sweep`; inherit everything else."""

    name = "base"
    #: what this lens treats as a candidate, in one line, for the docs and the CLI
    looks_for = "nothing — this is the abstract base"

    def sweep(self, records: List[Dict[str, Any]]) -> List[Candidate]:
        raise NotImplementedError

    # -- helpers every lens gets -------------------------------------------

    @staticmethod
    def numeric(record: Dict[str, Any]) -> Optional[float]:
        """The record's value as a float, or None. Bools are not numbers here."""
        value = record.get("value")
        if isinstance(value, bool) or value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value) if math.isfinite(float(value)) else None
        if isinstance(value, dict):
            inner = value.get("value")
            if isinstance(inner, (int, float)) and not isinstance(inner, bool):
                return float(inner) if math.isfinite(float(inner)) else None
        return None

    @staticmethod
    def text(record: Dict[str, Any]) -> str:
        """Everything textual about a record, lowercased, for keyword sweeps."""
        parts = [
            str(record.get("context") or ""),
            str(record.get("candidate_note") or ""),
            str(record.get("path") or ""),
            str(record.get("kind") or ""),
        ]
        value = record.get("value")
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, dict):
            parts.extend(f"{k} {v}" for k, v in value.items())
        return " ".join(parts).lower()


# ---------------------------------------------------------------------------
# Multiple-comparison discipline
# ---------------------------------------------------------------------------


# The FDR procedure lives in stats/ and is re-exported here, so every lens and
# the harvest share ONE implementation. A lens shipping its own significance rule
# could quietly grade itself on an easier curve than the pool it competes with.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from stats.multiple_comparisons import (  # noqa: E402,F401
    benjamini_hochberg,
    bh_q_values,
)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_REGISTRY: Dict[str, Callable[[], Lens]] = {}


def register(name: str) -> Callable[[type], type]:
    def decorator(cls: type) -> type:
        _REGISTRY[name] = cls  # type: ignore[assignment]
        return cls

    return decorator


def get_lens(name: Optional[str]) -> Lens:
    """Resolve a lens by name. An unknown or missing lens falls back to generic.

    Falling back rather than raising is deliberate: a task with a typo'd lens
    should still get its artifacts swept, because the alternative is a silent
    hole in the pool. The generic lens pre-judges nothing, so the fallback is
    conservative in the right direction.
    """
    from . import engineering, generic, ops, research, writing  # noqa: F401

    key = (name or "generic").strip().lower()
    factory = _REGISTRY.get(key) or _REGISTRY["generic"]
    return factory()  # type: ignore[operator]


def available() -> List[str]:
    from . import engineering, generic, ops, research, writing  # noqa: F401

    return sorted(_REGISTRY)


def sweep_pool(records: Iterable[Dict[str, Any]]) -> List[Candidate]:
    """Group records by their own lens and sweep each group with it.

    Records with no lens go to `generic`, which logs and pre-judges nothing.
    """
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for record in records:
        grouped.setdefault((record.get("lens") or "generic").lower(), []).append(record)

    candidates: List[Candidate] = []
    for lens_name, group in grouped.items():
        candidates.extend(get_lens(lens_name).sweep(group))
    return candidates
