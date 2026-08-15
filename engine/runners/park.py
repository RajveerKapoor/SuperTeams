#!/usr/bin/env python3
"""park.py — graceful stop. Parking is a state transition, not a crash.

When the weekly cap looms or the human says stop: write a park-state with the
reason, the frontier, and the resume condition; then sleep. No session spins, no
window is wasted, no work is lost — the registry and checkpoints hold everything
(doctrine/07 section 7).

This is why a multi-day rate-limit reset is a non-event.

  park.py "weekly cap hit; resume after reset"

After running this, disarm the babysit loop's Cron job — park.py cannot do it
for you because the loop lives in the harness, not on disk. The printed
instructions say exactly what to disarm.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _core import (  # noqa: E402
    EXIT_OK,
    append_audit,
    append_line,
    find_workspace,
    hr,
    load_registry,
    now_iso,
    orch_dir,
    read_json,
    run_cli,
)
from roadmap import frontier  # noqa: E402
from window import load_state, save_state  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(prog="park.py")
    parser.add_argument("reason")
    parser.add_argument("--workspace")
    parser.add_argument(
        "--resume-when",
        default="the weekly cap resets, or the human says go",
        help="the condition that should end the park",
    )
    args = parser.parse_args()

    workspace = find_workspace(Path(args.workspace) if args.workspace else None)
    registry = load_registry(workspace)
    ready = [entry["id"] for entry in frontier(registry)]

    in_flight = None
    status_dir = workspace / "handoffs" / "status"
    if status_dir.exists():
        for status_file in sorted(status_dir.glob("WAVE_*_STATUS.json")):
            status = read_json(status_file, {})
            if status.get("state") in (
                "RUNNING",
                "AUDITING",
                "AWAITING_BACKGROUND_COMPUTE",
                "HALTED",
                "INTERRUPTED",
            ):
                in_flight = status.get("wave_id")
                break

    state = load_state(workspace)
    state["park_state"] = {
        "reason": args.reason,
        "parked_at": now_iso(),
        "resume_condition": args.resume_when,
        "frontier": ready,
        "in_flight_wave": in_flight,
    }
    save_state(workspace, state)

    append_audit(
        workspace, entry_id="MISSION", action="park", patch=state["park_state"]
    )
    append_line(
        orch_dir(workspace) / "OUTBOX.md",
        f"\n## {now_iso()} — PARKED\n{args.reason}\n"
        f"Frontier held: {', '.join(ready) or '(empty)'}\n"
        f"In-flight wave: {in_flight or '(none)'}\n"
        f"Resumes when: {args.resume_when}\n",
    )

    print("PARKED")
    print(hr())
    print(f"  reason:      {args.reason}")
    print(f"  resume when: {args.resume_when}")
    print(f"  frontier held ({len(ready)}): {', '.join(ready) or '(empty)'}")
    print(f"  in-flight wave: {in_flight or '(none)'}")
    print(hr())
    print("  Now disarm the babysit loop so nothing spins during the park:")
    print("    - Claude Code: CronDelete the babysit job for this mission")
    print("  Nothing is lost. resume.py re-derives everything from disk.")
    return EXIT_OK


if __name__ == "__main__":
    run_cli(main)
