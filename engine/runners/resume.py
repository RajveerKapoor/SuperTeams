#!/usr/bin/env python3
"""resume.py — come back from a park, re-deriving everything from disk.

Never inherits the park-state's numbers: it recomputes the frontier, re-reads
every wave STATUS, and reports what it actually found. A resume that trusted the
park record would be exactly the "inherit a dead session's verdicts" failure the
whole system exists to prevent (doctrine/06 A3).

  resume.py
  resume.py --json
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
    append_audit,
    find_workspace,
    hr,
    load_registry,
    now_iso,
    read_json,
    run_cli,
)
from dispatch import collect_validation_problems  # noqa: E402
from roadmap import frontier  # noqa: E402
from window import load_state, save_state  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(prog="resume.py")
    parser.add_argument("--workspace")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--keep-park", action="store_true", help="report without un-parking")
    args = parser.parse_args()

    workspace = find_workspace(Path(args.workspace) if args.workspace else None)
    state = load_state(workspace)
    park = state.get("park_state")

    registry = load_registry(workspace)
    ready = [entry["id"] for entry in frontier(registry)]
    problems = collect_validation_problems(workspace)

    open_waves: List[Dict[str, Any]] = []
    status_dir = workspace / "handoffs" / "status"
    if status_dir.exists():
        for status_file in sorted(status_dir.glob("WAVE_*_STATUS.json")):
            status = read_json(status_file, {})
            if status.get("state") not in ("COMPLETE", "FAILED"):
                open_waves.append(
                    {
                        "wave_id": status.get("wave_id"),
                        "state": status.get("state"),
                        "tasks_done": status.get("tasks_done"),
                        "tasks_total": status.get("tasks_total"),
                        "last_checkpoint_at": status.get("last_checkpoint_at"),
                    }
                )

    orphans = [
        e["id"]
        for e in registry.get("entries", {}).values()
        if e.get("type") == "task" and e.get("status") == "IN_PROGRESS"
    ]

    result = {
        "was_parked": bool(park),
        "park": park,
        "frontier": ready,
        "open_waves": open_waves,
        "orphan_in_progress": orphans,
        "validate_clean": not problems,
        "validate_problems": problems,
        "resumed_at": now_iso(),
    }

    if not args.keep_park and park:
        state["park_state"] = None
        state["window_started_at"] = now_iso()
        state["window_budget_remaining_frac"] = 1.0
        save_state(workspace, state)
        append_audit(workspace, entry_id="MISSION", action="resume", patch={"from": park})

    if args.json:
        print(json.dumps(result, indent=2))
        return EXIT_OK

    print("RESUME — state re-derived from disk (the park record is not trusted)")
    print(hr())
    if park:
        print(f"  was parked at {park.get('parked_at')}: {park.get('reason')}")
    else:
        print("  was not parked")
    print(f"  frontier now ({len(ready)}): {', '.join(ready) or '(empty)'}")
    if park and set(park.get("frontier") or []) != set(ready):
        print("    note: the frontier CHANGED since the park. Disk wins; re-plan accordingly.")
    print(f"  open waves: {len(open_waves)}")
    for wave in open_waves:
        print(
            f"    WAVE {wave['wave_id']}: {wave['state']} "
            f"({wave['tasks_done']}/{wave['tasks_total']}), "
            f"last checkpoint {wave['last_checkpoint_at'] or 'never'}"
        )
    if orphans:
        print(f"  ORPHAN IN_PROGRESS: {', '.join(orphans)}")
        print("    -> revert these to PENDING before resuming; no session is watching them.")
    print(f"  validate: {'clean' if not problems else str(len(problems)) + ' problem(s)'}")
    for problem in problems[:10]:
        print(f"      - {problem}")
    print(hr())
    if problems:
        print("  Do NOT auto-advance over a dirty registry. HOLD and fix first.")
    else:
        print("  Re-arm the babysit loop window-aligned, then continue from the frontier.")
    return EXIT_OK


if __name__ == "__main__":
    run_cli(main)
