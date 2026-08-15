"""repro — the reproducibility manifest: seed, environment, commit.

Doctrine/07 section 4 (the Producer/Consumer contract) and doctrine/13 section 3
(`replay.py` as the human-runnable acceptance surface) both stand on this: a
claim is only re-derivable if what produced it is recorded precisely enough to
run again.

The anti-fabrication clause lives here as an API shape, not a rule to remember:
`open_manifest()` writes `status: RUNNING` with `output_sha256: null`, and
`complete_manifest()` refuses to stamp a hash it did not compute from a file that
exists. A hash asserted before the work finishes is not evidence.
"""

from .manifest import (  # noqa: F401
    build_env_hash,
    complete_manifest,
    describe_env,
    git_head,
    make_seed,
    mark_failed,
    mark_infeasible,
    open_manifest,
    verify_manifest,
)

__all__ = [
    "build_env_hash",
    "complete_manifest",
    "describe_env",
    "git_head",
    "make_seed",
    "mark_failed",
    "mark_infeasible",
    "open_manifest",
    "verify_manifest",
]
