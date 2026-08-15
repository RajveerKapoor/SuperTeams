#!/usr/bin/env python3
"""wave_status.py — the ONLY writer of WAVE_<id>_STATUS.json.

The most-polled file in the system and the babysit loop's primary signal. It is
schema-validated on every write so the predecessor's "STATUS.json missing several
conventional fields" drift becomes a validation error rather than silent rot
(doctrine/03 section 4, doctrine/06 E1).

  wave_status.py 2k --set state=RUNNING --task-in-progress TASK_0031
  wave_status.py 2k --show
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _core import (  # noqa: E402
    EXIT_GENERIC,
    EXIT_OK,
    atomic_write_json,
    count_artifacts,
    die,
    find_workspace,
    hr,
    load_registry,
    now_iso,
    read_json,
    run_cli,
    validate_against,
    wave_paths,
)

INT_FIELDS = {"tasks_total", "tasks_done", "artifacts_at_start", "artifacts_now", "wavegen_pid_hint"}


def main() -> int:
    parser = argparse.ArgumentParser(prog="wave_status.py")
    parser.add_argument("wave_id")
    parser.add_argument("--workspace")
    parser.add_argument("--set", action="append", default=[], help="field=value (repeatable)")
    parser.add_argument("--task-in-progress", dest="in_progress")
    parser.add_argument("--clear-in-progress", action="store_true")
    parser.add_argument("--next-action")
    parser.add_argument("--show", action="store_true")
    parser.add_argument(
        "--recount",
        action="store_true",
        help="refresh artifacts_now and tasks_done from disk truth",
    )
    args = parser.parse_args()

    workspace = find_workspace(Path(args.workspace) if args.workspace else None)
    path = wave_paths(workspace, args.wave_id)["status"]
    status = read_json(path)

    if args.show:
        print(json.dumps(status, indent=2))
        return EXIT_OK

    for assignment in args.set:
        if "=" not in assignment:
            raise die(EXIT_GENERIC, f"--set expects field=value, got {assignment!r}")
        field, _, raw = assignment.partition("=")
        field = field.strip()
        raw = raw.strip()
        if field in INT_FIELDS:
            status[field] = int(raw)
        elif raw.lower() in ("null", "none", ""):
            status[field] = None
        else:
            status[field] = raw

    if args.in_progress:
        status["task_in_progress"] = args.in_progress
    if args.clear_in_progress:
        status["task_in_progress"] = None
    if args.next_action:
        status["next_action"] = args.next_action

    if args.recount or True:
        # artifacts_now is always re-derived from disk: it is a liveness signal,
        # and a liveness signal an agent can assert is not a signal (Law 1).
        status["artifacts_now"] = count_artifacts(workspace)

    registry = load_registry(workspace)
    wave_tasks = [
        e
        for e in registry.get("entries", {}).values()
        if e.get("type") == "task" and e.get("wave") == args.wave_id
    ]
    if wave_tasks:
        status["tasks_total"] = len(wave_tasks)
        status["tasks_done"] = sum(1 for e in wave_tasks if e.get("status") == "COMPLETED")
        status["tasks_pending"] = sorted(
            e["id"] for e in wave_tasks if e.get("status") in ("PENDING", "BLOCKED_ON_DEPS")
        )

    if status.get("state") == "RUNNING" and not status.get("started_at"):
        status["started_at"] = now_iso()
    status["updated_at"] = now_iso()

    validate_against(status, "status", str(path))
    atomic_write_json(path, status)

    print(f"wave {args.wave_id}: state={status['state']} "
          f"tasks {status['tasks_done']}/{status['tasks_total']} "
          f"artifacts {status['artifacts_at_start']}→{status['artifacts_now']} "
          f"audit={status['audit_state']}")
    return EXIT_OK


if __name__ == "__main__":
    run_cli(main)
