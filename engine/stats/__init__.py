"""stats — multiple-comparison discipline, shared across lenses and the harvest.

Kept here rather than inside a lens because the FDR gate must be the SAME
procedure for every domain. A lens that shipped its own significance rule could
quietly grade itself on an easier curve than the pool it competes with.
"""

from .multiple_comparisons import (  # noqa: F401
    benjamini_hochberg,
    bh_q_values,
    bonferroni,
    summarize,
)

__all__ = ["benjamini_hochberg", "bh_q_values", "bonferroni", "summarize"]
