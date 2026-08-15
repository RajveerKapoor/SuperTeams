#!/usr/bin/env python3
"""checkpoint.py — the resumability contract.

Run after EVERY task banks, never batched (doctrine/07 section 3). The
checkpoint is derived from REGISTRY truth, not from what the caller believes,
so a checkpoint can never record a completion the kernel did not accept.

Because banking is serial, at most one task is ever un-checkpointed: a rate
limit, a laptop sleep, or a kill costs at most that one task, never a window.

  checkpoint.py 2k
  checkpoint.py 2k --defer TASK_0033 --manifest datasets/matrix.manifest.json --shell bg-9f3
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _core import (  # noqa: E402
    EXIT_OK,
    atomic_write_text,
    count_artifacts,
    find_workspace,
    load_registry,
    now_iso,
    read_json,
    run_cli,
    validate_against,
    wave_paths,
)

BODY = """\
# WAVE {wave_id} CHECKPOINT

Written {ts} by `checkpoint.py`, derived from REGISTRY truth.

**On resume:** read this, cross-check against the REGISTRY (**registry wins on any
conflict**), revert any orphan `IN_PROGRESS` to `PENDING` with a note, and resume
from the first pending task. Because banking is serial, at most one task is re-done.

```json
{payload}
```

## Resume classification hint
{hint}
"""


def main() -> int:
    parser = argparse.ArgumentParser(prog="checkpoint.py")
    parser.add_argument("wave_id")
    parser.add_argument("--workspace")
    parser.add_argument("--defer", help="task id handed to background compute")
    parser.add_argument("--manifest", help="the deferred task's manifest path")
    parser.add_argument("--shell", help="the background shell id")
    args = parser.parse_args()

    workspace = find_workspace(Path(args.workspace) if args.workspace else None)
    paths = wave_paths(workspace, args.wave_id)
    registry = load_registry(workspace)

    wave_tasks = [
        e
        for e in registry.get("entries", {}).values()
        if e.get("type") == "task" and e.get("wave") == args.wave_id
    ]
    completed = sorted(e["id"] for e in wave_tasks if e.get("status") == "COMPLETED")
    in_progress = next(
        (e["id"] for e in wave_tasks if e.get("status") == "IN_PROGRESS"), None
    )
    pending = sorted(
        e["id"] for e in wave_tasks if e.get("status") in ("PENDING", "BLOCKED_ON_DEPS")
    )

    baseline_file = paths["baseline"]
    baseline = read_json(baseline_file, {}).get("artifacts_at_start", 0)

    deferred: List[Dict[str, Any]] = []
    if paths["checkpoint"].exists():
        text = paths["checkpoint"].read_text(encoding="utf-8")
        if "```json" in text:
            block = text.split("```json", 1)[1].split("```", 1)[0]
            try:
                deferred = json.loads(block).get("deferred", []) or []
            except json.JSONDecodeError:
                deferred = []
    if args.defer:
        deferred = [d for d in deferred if d.get("task") != args.defer]
        deferred.append(
            {"task": args.defer, "manifest": args.manifest, "shell_id": args.shell}
        )

    payload = {
        "wave_id": args.wave_id,
        "completed": completed,
        "in_progress": in_progress,
        "pending": pending,
        "deferred": deferred,
        "artifacts_baseline": baseline,
        "artifacts_at_checkpoint": count_artifacts(workspace),
        "last_checkpoint_at": now_iso(),
        "reconcile_rule": "registry wins on any conflict",
    }
    validate_against(payload, "checkpoint", str(paths["checkpoint"]))

    if not completed and not deferred:
        hint = (
            "**stalled-nothing-banked** if this wave is found dead here: nothing is "
            "banked, so there is nothing to recompute. That is a *clean restart*, not "
            "a partial resume (doctrine/06 A5)."
        )
    elif deferred:
        hint = (
            "**awaiting-bg**: a producer is running under the OS and outlives this "
            "session. Do NOT relaunch the compute. Arm one Monitor on the manifest, "
            "validate the hash, then consume (doctrine/07 section 4)."
        )
    else:
        hint = (
            f"**stalled-partial / interrupted**: {len(completed)} task(s) banked. "
            "Checkpoint-resume. Do NOT recompute the persisted artifacts (A4) — for "
            "each pending item decide recompute-vs-synthesize."
        )

    atomic_write_text(
        paths["checkpoint"],
        BODY.format(
            wave_id=args.wave_id,
            ts=now_iso(),
            payload=json.dumps(payload, indent=2),
            hint=hint,
        ),
    )

    if paths["status"].exists():
        status = read_json(paths["status"])
        status["last_checkpoint_at"] = payload["last_checkpoint_at"]
        status["artifacts_now"] = payload["artifacts_at_checkpoint"]
        status["tasks_done"] = len(completed)
        status["tasks_pending"] = pending
        status["task_in_progress"] = in_progress
        status["updated_at"] = now_iso()
        validate_against(status, "status", str(paths["status"]))
        from _core import atomic_write_json

        atomic_write_json(paths["status"], status)

    print(
        f"checkpoint {args.wave_id}: {len(completed)} banked, "
        f"{len(pending)} pending, in_progress={in_progress or '—'}, "
        f"{len(deferred)} deferred"
    )
    return EXIT_OK


if __name__ == "__main__":
    run_cli(main)
