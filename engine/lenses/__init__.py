"""SuperTeam lenses — the pluggable half of the Curiosity Protocol.

The discipline is constant across every mission: **record all, provenance-tag,
promote later, FDR-gate.** Only the question "what counts as a candidate here?"
is domain-specific, and that is what a lens answers.

    from lenses import get_lens, sweep_pool

    sweep_pool(records)              # groups by each record's own lens
    get_lens("engineering").sweep(records)
"""

from .base import (  # noqa: F401
    LENS_STATUS,
    Candidate,
    Lens,
    available,
    benjamini_hochberg,
    bh_q_values,
    get_lens,
    register,
    sweep_pool,
)
from .engineering import EngineeringLens  # noqa: F401
from .generic import GenericLens  # noqa: F401
from .ops import OpsLens  # noqa: F401
from .research import ResearchLens  # noqa: F401
from .writing import WritingLens  # noqa: F401

__all__ = [
    "Candidate",
    "Lens",
    "LENS_STATUS",
    "available",
    "benjamini_hochberg",
    "bh_q_values",
    "get_lens",
    "register",
    "sweep_pool",
    "EngineeringLens",
    "GenericLens",
    "OpsLens",
    "ResearchLens",
    "WritingLens",
]
