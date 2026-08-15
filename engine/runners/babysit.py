#!/usr/bin/env python3
"""babysit.py — the continuity daemon's classifier.

On every tick this answers one question from ON-DISK TRUTH ALONE: what should
happen next? It never reasons from a transcript. It reads files, applies the
decision table in doctrine/07 section 2, and prints exactly one action for the
calling agent to carry out.

The two subtleties the predecessor paid for in blood are both here:

  alive != progressing   A session can spin for 5.5 hours and bank nothing
                         (Wave 2j). Liveness is a THREE-signal judgment:
                         process, artifacts-count delta, checkpoint advance.

  alive-paused != gone   A session paused at a rate limit still holds warm
                         context worth a human paste. Never spawn a rival (C1).

Actions this can emit (every name below is actually returned by classify):
  HOLD  LAUNCH_NEXT  REVIVE_CHECKPOINT  RESTART_CLEAN  PING_HUMAN  PING_HUMAN_PASTE
  CONSUME_BG  HANDLE_HALT  PARK  FIX_INTEGRITY  READ_STEERING  MISSION_DONE

  babysit.py                # human-readable
  babysit.py --json         # for a scripted loop
  babysit.py --stall-hours 1.5
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _core import (  # noqa: E402
    EXIT_OK,
    count_artifacts,
    find_workspace,
    hr,
    load_registry,
    now_iso,
    orch_dir,
    parse_iso,
    read_json,
    run_cli,
)
from dispatch import collect_validation_problems  # noqa: E402
from roadmap import frontier  # noqa: E402
from window import load_state, save_state, should_park, window_remaining_h  # noqa: E402

ACTIVE_STATES = (
    "PLANNED",
    "RUNNING",
    "AUDITING",
    "HALTED",
    "INTERRUPTED",
    "AWAITING_BACKGROUND_COMPUTE",
)


def process_alive(session_name: Optional[str]) -> Optional[bool]:
    """Is a process whose command line mentions this session name alive?

    Returns None when we cannot tell, which the classifier treats as 'unknown'
    rather than 'gone' — guessing 'gone' is how you double-launch (C1).
    """
    if not session_name:
        return None
    try:
        result = subprocess.run(
            ["pgrep", "-f", session_name], capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.returncode == 0 and bool(result.stdout.strip())


def hours_since(iso: Optional[str]) -> Optional[float]:
    parsed = parse_iso(iso or "")
    if parsed is None:
        return None
    return (datetime.now(timezone.utc) - parsed).total_seconds() / 3600.0


def classify(workspace: Path, stall_hours: float) -> Dict[str, Any]:
    registry = load_registry(workspace)
    window = load_state(workspace)
    orch = orch_dir(workspace)
    artifacts_now = count_artifacts(workspace)

    signals: List[str] = []
    action: str
    detail: str

    # ---- 0. parked --------------------------------------------------------
    if window.get("park_state"):
        return {
            "action": "HOLD",
            "detail": (
                "the mission is PARKED: "
                f"{window['park_state'].get('reason')}. Resume with resume.py when "
                f"{window['park_state'].get('resume_condition')}."
            ),
            "signals": ["park_state is set"],
            "artifacts_now": artifacts_now,
        }

    # ---- 1. integrity first — never auto-advance over a dirty registry ----
    problems = collect_validation_problems(workspace)
    if problems:
        return {
            "action": "FIX_INTEGRITY",
            "detail": (
                f"dispatch.py validate reports {len(problems)} problem(s). A validation "
                "failure is a HOLD-and-flag, never an auto-advance."
            ),
            "signals": problems[:8],
            "artifacts_now": artifacts_now,
        }

    # ---- 2. the in-flight wave -------------------------------------------
    waves: List[Dict[str, Any]] = []
    status_dir = workspace / "handoffs" / "status"
    if status_dir.exists():
        for status_file in sorted(status_dir.glob("WAVE_*_STATUS.json")):
            waves.append(read_json(status_file, {}))
    in_flight = next((w for w in waves if w.get("state") in ACTIVE_STATES), None)

    if in_flight is not None:
        wave_id = in_flight.get("wave_id")
        state = in_flight.get("state")
        alive = process_alive(in_flight.get("wavegen_session"))
        banked = int(in_flight.get("tasks_done") or 0)
        baseline = int(in_flight.get("artifacts_at_start") or 0)
        artifacts_delta = artifacts_now - baseline
        checkpoint_age = hours_since(in_flight.get("last_checkpoint_at"))

        signals = [
            f"process: {'alive' if alive else ('gone' if alive is False else 'unknown')}",
            f"artifacts delta vs baseline: {artifacts_delta}",
            f"checkpoint age: "
            + (f"{checkpoint_age:.2f}h" if checkpoint_age is not None else "never"),
            f"tasks banked: {banked}/{in_flight.get('tasks_total')}",
        ]

        if state == "HALTED":
            return {
                "action": "HANDLE_HALT",
                "detail": (
                    f"wave {wave_id} is HALTED. Read "
                    f"handoffs/halt_requests/WAVE_{wave_id}_HALT.md, classify the reason, "
                    "and either write a RESUME directive (/revive) or escalate per the "
                    "touchpoint policy. Do NOT improvise a workaround."
                ),
                "signals": signals,
                "wave_id": wave_id,
                "artifacts_now": artifacts_now,
            }

        if state == "AWAITING_BACKGROUND_COMPUTE":
            deferred = in_flight.get("deferred_compute") or []
            ready, waiting = [], []
            for item in deferred:
                manifest_path = workspace / (item.get("manifest") or "")
                manifest = read_json(manifest_path, {}) if manifest_path.exists() else {}
                if manifest.get("status") == "COMPLETE" and manifest.get("output_sha256"):
                    ready.append(item)
                elif manifest.get("status") == "INFEASIBLE":
                    return {
                        "action": "HANDLE_HALT",
                        "detail": (
                            f"producer for {item.get('task')} reported INFEASIBLE. The "
                            "hardware cannot do the full spec in available time. HALT to "
                            "the Orchestrator — never silently substitute a smaller job."
                        ),
                        "signals": signals,
                        "wave_id": wave_id,
                        "artifacts_now": artifacts_now,
                    }
                else:
                    waiting.append(item)
            if ready:
                return {
                    "action": "CONSUME_BG",
                    "detail": (
                        f"background output ready for {[i.get('task') for i in ready]}. "
                        "Relaunch the Wave General to run the five-check validation "
                        "(status COMPLETE, file exists, size matches, SHA matches, "
                        "completed_at sane) and consume."
                    ),
                    "signals": signals,
                    "wave_id": wave_id,
                    "artifacts_now": artifacts_now,
                }
            return {
                "action": "HOLD",
                "detail": (
                    f"wave {wave_id} awaits background compute ({len(waiting)} producer(s) "
                    "still running under the OS). Arm ONE Monitor on the manifest; do not "
                    "tight-poll (C2)."
                ),
                "signals": signals,
                "wave_id": wave_id,
                "artifacts_now": artifacts_now,
            }

        # ---- the four-condition liveness gate --------------------------------
        # Delegate to liveness.classify_wave rather than re-deriving a weaker
        # copy here. The predecessor's decision table has FOUR process
        # conditions, and the one this tick used to miss is `alive-paused`: a
        # session paused at a rate limit is alive, holds warm context, and must
        # NOT be killed or double-launched — it needs a human paste. The old
        # 2-signal logic (no CPU delta) classified that as `stalled → kill +
        # clean restart`, the exact C1 hazard. One classifier, sampled the same
        # way the pre-launch gate samples it, closes that gap.
        from liveness import classify_wave  # local import keeps CLI startup fast

        verdict = classify_wave(workspace, wave_id, stall_hours)
        condition = verdict["condition"]
        signals = signals + [f"liveness: {condition}"] + [
            f"{k}={v}" for k, v in verdict.get("signals", {}).items()
        ]

        if condition == "gone":
            return {
                "action": "REVIVE_CHECKPOINT" if banked else "RESTART_CLEAN",
                "detail": (
                    f"wave {wave_id} is INTERRUPTED — its Wave General process is gone. "
                    + (
                        f"{banked} task(s) are banked, so this is a checkpoint-resume: "
                        "write a RESUME directive (/revive) and relaunch from "
                        f"handoffs/checkpoints/WAVE_{wave_id}_CHECKPOINT.md, reverting any "
                        "orphan IN_PROGRESS to PENDING. Do NOT recompute persisted "
                        "artifacts (A4)."
                        if banked
                        else "NOTHING is banked, so there is nothing to recompute: this is a "
                        "CLEAN RESTART, not a partial resume (A5)."
                    )
                    + " Run a pre-launch liveness check first (C1)."
                ),
                "signals": signals,
                "wave_id": wave_id,
                "artifacts_now": artifacts_now,
            }

        if condition == "alive-paused":
            return {
                "action": "PING_HUMAN_PASTE",
                "detail": (
                    f"wave {wave_id} is ALIVE BUT PAUSED at a rate limit — burning no CPU "
                    "with a recent checkpoint. Do NOT kill it and do NOT launch a rival: "
                    "the paused session holds warm context worth more than a cold "
                    "relaunch. Ping the human to paste the RESUME directive into the "
                    "paused session (C1)."
                ),
                "signals": signals,
                "wave_id": wave_id,
                "artifacts_now": artifacts_now,
            }

        if condition == "alive-stalled":
            return {
                "action": "RESTART_CLEAN" if banked == 0 else "REVIVE_CHECKPOINT",
                "detail": (
                    f"wave {wave_id} is ALIVE BUT SPINNING (Wave-2j signature): "
                    + verdict["reason"]
                ),
                "signals": signals,
                "wave_id": wave_id,
                "artifacts_now": artifacts_now,
            }

        if condition == "unknown":
            return {
                "action": "HOLD",
                "detail": (
                    f"wave {wave_id}: liveness is UNKNOWN (could not read the process "
                    "table). Unknown is not gone (C1) — HOLD and do not launch anything. "
                    + verdict["reason"]
                ),
                "signals": signals,
                "wave_id": wave_id,
                "artifacts_now": artifacts_now,
            }

        # ---- invariant #3: no role session exceeds its age budget (A2) -------
        # A Wave General is bounded by ONE window: it does not rotate mid-wave,
        # it IS the wave, and at the window boundary it checkpoints and exits so
        # the next session resumes (07 §5). A wave still RUNNING well past a full
        # window is a session that should have rotated — the five-day-bloat
        # shape (A2). The tick FLAGS it (never kills a progressing wave); the
        # doctrine's invariant #3 is "rotation, or flag", and this is the flag.
        window_length = float(window.get("window_length_h") or 5.0)
        wave_age = hours_since(in_flight.get("started_at"))
        rotation_overdue = wave_age is not None and wave_age > 1.2 * window_length
        if rotation_overdue:
            signals = signals + [
                f"wave age {wave_age:.1f}h > {1.2 * window_length:.1f}h — ROTATION OVERDUE"
            ]

        return {
            "action": "HOLD",
            "detail": (
                f"wave {wave_id} is {state} and progressing. Post nothing. The wave is "
                "working."
                + (
                    f" NOTE: this Wave General session has run {wave_age:.1f}h, past a "
                    f"full {window_length:.0f}h window — it should checkpoint and rotate "
                    "at the boundary (invariant #3 / A2). If it is genuinely still "
                    "progressing, let it finish the task and rotate; if the clock and the "
                    "checkpoint disagree, investigate a stuck session."
                    if rotation_overdue
                    else ""
                )
            ),
            "signals": signals,
            "wave_id": wave_id,
            "artifacts_now": artifacts_now,
        }

    # ---- 3. no wave in flight --------------------------------------------
    steering = orch / "STEERING.md"
    if steering.exists() and "[unread]" in steering.read_text(encoding="utf-8").lower():
        # An unread directive is checked here — at a wave boundary, never mid-wave.
        unread = [
            ln.strip()
            for ln in steering.read_text(encoding="utf-8").splitlines()
            if "[unread]" in ln.lower()
        ]
        if unread and not all("(nothing yet)" in u for u in unread):
            return {
                "action": "READ_STEERING",
                "detail": (
                    "an unread human directive is waiting in STEERING.md and we are at a "
                    "wave boundary. Read it, turn it into a Decision (and an Authorization "
                    "if it grants anything), re-plan if needed, then mark it read."
                ),
                "signals": unread[:5],
                "artifacts_now": artifacts_now,
            }

    last_complete = [w for w in waves if w.get("state") == "COMPLETE"]
    for wave in last_complete:
        if wave.get("audit_state") == "FAIL":
            return {
                "action": "PING_HUMAN",
                "detail": (
                    f"wave {wave.get('wave_id')} closed with a FAILED audit. This is a "
                    "genuine decision: the doer may not grade its own redo. Escalate with "
                    "options (commission a corrective task / re-run the wave / accept with "
                    "a note) and a recommendation."
                ),
                "signals": [f"WAVE_{wave.get('wave_id')} audit_state=FAIL"],
                "artifacts_now": artifacts_now,
            }

    park_now, park_reason = should_park(window)
    if park_now:
        return {
            "action": "PARK",
            "detail": f"{park_reason}. Run park.py and disarm this loop.",
            "signals": [f"weekly_used_frac={window.get('weekly_used_frac')}"],
            "artifacts_now": artifacts_now,
        }

    ready = frontier(registry)
    tasks = [e for e in registry.get("entries", {}).values() if e.get("type") == "task"]
    open_tasks = [t for t in tasks if t.get("status") not in ("COMPLETED", "SUPERSEDED")]

    if not open_tasks:
        if registry.get("mode") == "persistent":
            return {
                "action": "HOLD",
                "detail": (
                    "persistent mode with an empty frontier: the team is idle and healthy. "
                    "Check the intake channel (handoffs/orchestrator/intake/) and STEERING "
                    "at the next boundary. There is no terminal state here."
                ),
                "signals": ["no open tasks", "mode=persistent"],
                "artifacts_now": artifacts_now,
            }
        return {
            "action": "MISSION_DONE",
            "detail": (
                "every task is terminal and the mode is finite. Run the SYNTHESIS wave "
                "(Orchestrator-only) to produce the deliverable, then notify the human — "
                "this is one of the few genuine interrupts."
            ),
            "signals": [f"{len(tasks)} tasks, all terminal"],
            "artifacts_now": artifacts_now,
        }

    if not ready:
        blocked = [t for t in open_tasks if t.get("verdict") == "STUMPED"]
        if blocked and len(blocked) == len(open_tasks):
            return {
                "action": "PING_HUMAN",
                "detail": (
                    f"hard block: all {len(blocked)} remaining task(s) are STUMPED and "
                    "nothing else is ready. Escalate with the single thing that would "
                    "unblock the most work."
                ),
                "signals": [f"{t['id']}: {t.get('unblock_criterion')}" for t in blocked[:5]],
                "artifacts_now": artifacts_now,
            }
        return {
            "action": "HOLD",
            "detail": (
                "no task has all dependencies COMPLETED and no wave is in flight. "
                "Something is inconsistent — inspect the DAG with roadmap.py frontier."
            ),
            "signals": [f"{len(open_tasks)} open tasks, 0 ready"],
            "artifacts_now": artifacts_now,
        }

    remaining = window_remaining_h(window)
    if remaining < 1.0:
        return {
            "action": "HOLD",
            "detail": (
                f"~{remaining:.1f}h left in this window — too little to launch a wave that "
                "would finish. Wait for the window to roll; the next tick is "
                "window-aligned."
            ),
            "signals": [f"window remaining {remaining:.2f}h", f"{len(ready)} ready tasks"],
            "artifacts_now": artifacts_now,
        }

    unfrozen = [e["id"] for e in ready if not e.get("frozen")]
    if unfrozen:
        return {
            "action": "HOLD",
            "detail": (
                f"{len(unfrozen)} ready task(s) have no frozen criterion: {unfrozen[:5]}. "
                "Freeze before dispatch — a criterion set after the result is seen is not "
                "a criterion. Run pre_register.py."
            ),
            "signals": unfrozen[:8],
            "artifacts_now": artifacts_now,
        }

    return {
        "action": "LAUNCH_NEXT",
        "detail": (
            f"{len(ready)} task(s) ready, ~{remaining:.1f}h of window left, registry clean, "
            "no wave in flight. Auto-advance: pack a wave (roadmap.py pack), scaffold it "
            "(new_wave.py), write PLAN + BRIEF, launch the Wave General, and digest one "
            "line to OUTBOX. This is not a decision — do not wake the human."
        ),
        "signals": [f"ready: {', '.join(e['id'] for e in ready[:8])}"],
        "artifacts_now": artifacts_now,
    }


def main() -> int:
    parser = argparse.ArgumentParser(prog="babysit.py")
    parser.add_argument("--workspace")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--stall-hours",
        type=float,
        default=1.5,
        help="no artifacts and no checkpoint advance for this long = stalled",
    )
    parser.add_argument("--no-tick", action="store_true", help="do not stamp last_tick_at")
    args = parser.parse_args()

    workspace = find_workspace(Path(args.workspace) if args.workspace else None)
    result = classify(workspace, args.stall_hours)
    result["ts"] = now_iso()

    if not args.no_tick:
        window = load_state(workspace)
        window["last_tick_at"] = result["ts"]
        save_state(workspace, window)

    if args.json:
        print(json.dumps(result, indent=2))
        return EXIT_OK

    print(hr("═"))
    print(f"  BABYSIT TICK  {result['ts']}")
    print(hr("═"))
    print(f"  ACTION: {result['action']}")
    if result.get("wave_id"):
        print(f"  wave:   {result['wave_id']}")
    print()
    for line in result["detail"].split(". "):
        if line.strip():
            print(f"  {line.strip().rstrip('.')}.")
    print()
    print("  signals (all read from disk):")
    for signal in result.get("signals", []):
        print(f"    - {signal}")
    return EXIT_OK


if __name__ == "__main__":
    run_cli(main)
