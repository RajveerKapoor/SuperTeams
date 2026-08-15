#!/usr/bin/env python3
"""status.py — "where are we", in one command.

The human drops in after days away. They should not have to reconstruct state
from a transcript — the transcript is not the truth, the registry is
(doctrine/09 section 5). This prints, from disk: mission state, the frontier,
the in-flight wave and its progress, recent OUTBOX digests, pending escalations,
the window budget, and any unread steering.

  status.py
  status.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _core import (  # noqa: E402
    EXIT_OK,
    count_artifacts,
    find_workspace,
    hr,
    kv,
    load_registry,
    orch_dir,
    read_json,
    run_cli,
    truncate,
)
from dispatch import collect_validation_problems  # noqa: E402
from roadmap import frontier  # noqa: E402
from window import load_state, should_park, window_remaining_h  # noqa: E402

ACTIVE_WAVE_STATES = (
    "PLANNED",
    "RUNNING",
    "AUDITING",
    "HALTED",
    "INTERRUPTED",
    "AWAITING_BACKGROUND_COMPUTE",
)


def tail(path: Path, n: int) -> List[str]:
    if not path.exists():
        return []
    lines = [ln.rstrip() for ln in path.read_text(encoding="utf-8").splitlines()]
    return [ln for ln in lines if ln.strip()][-n:]


def unread_steering(path: Path) -> List[str]:
    if not path.exists():
        return []
    return [
        ln.strip()
        for ln in path.read_text(encoding="utf-8").splitlines()
        if "[unread]" in ln.lower()
    ]


def gather(workspace: Path) -> Dict[str, Any]:
    registry = load_registry(workspace)
    entries = registry.get("entries", {})
    tasks = {k: v for k, v in entries.items() if v.get("type") == "task"}
    orch = orch_dir(workspace)

    waves: List[Dict[str, Any]] = []
    status_dir = workspace / "handoffs" / "status"
    if status_dir.exists():
        for status_file in sorted(status_dir.glob("WAVE_*_STATUS.json")):
            waves.append(read_json(status_file, {}))

    stumped = [
        {"id": t["id"], "unblock": t.get("unblock_criterion"), "title": t.get("title")}
        for t in tasks.values()
        if t.get("verdict") == "STUMPED"
    ]
    unaudited = [
        e["id"]
        for e in entries.values()
        if e.get("type") == "claim"
        and e.get("load_bearing")
        and e.get("audit_state") != "PASS"
    ]
    halts = sorted((workspace / "handoffs" / "halt_requests").glob("*_HALT.md")) if (
        workspace / "handoffs" / "halt_requests"
    ).exists() else []

    return {
        "mission": registry.get("mission"),
        "mode": registry.get("mode"),
        "frozen_at": registry.get("pre_registered_frozen_at"),
        "entries": len(entries),
        "task_status": dict(Counter(t.get("status") for t in tasks.values())),
        "task_verdicts": dict(
            Counter(t.get("verdict") for t in tasks.values() if t.get("verdict"))
        ),
        "frontier": [e["id"] for e in frontier(registry)],
        "waves": waves,
        "active_waves": [w for w in waves if w.get("state") in ACTIVE_WAVE_STATES],
        "artifacts": count_artifacts(workspace),
        "stumped": stumped,
        "unaudited_claims": unaudited,
        "halt_files": [str(p.name) for p in halts],
        "window": load_state(workspace),
        "validate_problems": collect_validation_problems(workspace),
        "outbox_tail": tail(orch / "OUTBOX.md", 12),
        "unread_steering": unread_steering(orch / "STEERING.md"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(prog="status.py")
    parser.add_argument("--workspace")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    workspace = find_workspace(Path(args.workspace) if args.workspace else None)
    data = gather(workspace)

    if args.json:
        print(json.dumps(data, indent=2, default=str))
        return EXIT_OK

    window = data["window"]
    park = window.get("park_state")
    remaining = window_remaining_h(window)
    park_now, park_reason = should_park(window)

    print(hr("═"))
    print(f"  MISSION  {data['mission']}   ({data['mode']} mode)")
    print(hr("═"))

    if park:
        print(f"  ▸ PARKED since {park.get('parked_at')}: {park.get('reason')}")
        print(f"    resumes when: {park.get('resume_condition')}")
        print()

    print("  WORK")
    for status, count in sorted(data["task_status"].items()):
        print(kv(f"  {status}", count))
    if data["task_verdicts"]:
        print("  verdicts: " + ", ".join(f"{k}×{v}" for k, v in sorted(data["task_verdicts"].items())))
    print(kv("  artifacts logged", data["artifacts"]))
    print(kv("  criteria frozen at", data["frozen_at"] or "NOT FROZEN — nothing may start"))
    print()

    print("  FRONTIER (ready to run)")
    if data["frontier"]:
        for task_id in data["frontier"]:
            print(f"    {task_id}")
    else:
        print("    (empty — nothing has all dependencies COMPLETED)")
    print()

    print("  WAVES")
    if data["active_waves"]:
        for wave in data["active_waves"]:
            print(
                f"    WAVE {wave.get('wave_id')}: {wave.get('state')}  "
                f"{wave.get('tasks_done')}/{wave.get('tasks_total')} tasks  "
                f"artifacts {wave.get('artifacts_at_start')}→{wave.get('artifacts_now')}  "
                f"audit={wave.get('audit_state')}"
            )
            print(f"      last checkpoint: {wave.get('last_checkpoint_at') or 'never'}")
            print(f"      next: {wave.get('next_action') or '—'}")
    else:
        done = [w for w in data["waves"] if w.get("state") == "COMPLETE"]
        print(f"    no wave in flight ({len(done)} complete)")
    print()

    escalations = []
    if data["halt_files"]:
        escalations.append(f"{len(data['halt_files'])} HALT request(s): {', '.join(data['halt_files'])}")
    if data["unread_steering"]:
        escalations.append(f"{len(data['unread_steering'])} unread steering directive(s)")
    if data["validate_problems"]:
        escalations.append(f"registry validate is DIRTY ({len(data['validate_problems'])} problems)")
    failed_audits = [w for w in data["waves"] if w.get("audit_state") == "FAIL"]
    if failed_audits:
        escalations.append(f"{len(failed_audits)} wave(s) with a FAILED audit")
    if data["stumped"]:
        escalations.append(f"{len(data['stumped'])} STUMPED task(s) awaiting an unblock")

    print("  NEEDS YOU" if escalations else "  NEEDS YOU — nothing")
    for item in escalations:
        print(f"    ! {item}")
    if data["stumped"]:
        for item in data["stumped"][:6]:
            print(f"      {item['id']}: needs {truncate(item['unblock'] or '(unspecified)', 52)}")
    if data["validate_problems"]:
        for problem in data["validate_problems"][:6]:
            print(f"      {truncate(problem, 70)}")
    print()

    print("  BUDGET")
    print(kv("  window remaining", f"~{remaining:.1f}h of {window.get('window_length_h')}h"))
    print(kv("  weekly used", f"{float(window.get('weekly_used_frac', 0)):.0%} "
                              f"(park at {float(window.get('weekly_park_ceiling', 0.9)):.0%})"))
    if park_now:
        print(f"    ! {park_reason}")
    print()

    if data["outbox_tail"]:
        print("  RECENT (OUTBOX)")
        for line in data["outbox_tail"]:
            print(f"    {truncate(line, 74)}")
        print()

    print(hr())
    print("  steer:   handoffs/orchestrator/STEERING.md   (read at the next wave boundary)")
    print("  read:    handoffs/orchestrator/OUTBOX.md")
    print("  verify:  runners/replay.py <CLAIM_ID>        (reproduce any claim yourself)")
    return EXIT_OK


if __name__ == "__main__":
    run_cli(main)
