#!/usr/bin/env python3
"""liveness.py — the pre-launch gate. Four process conditions, three signals.

The predecessor's memory pin #13: *single loop, pre-launch liveness check, no
double-launch*. Two subtleties it paid for in blood, both encoded here:

  alive != progressing   (A5) — a spinning session banks nothing but still shows up
                                in `pgrep`. Killing it is right; launching a rival
                                beside it is not.
  alive-paused != gone   (C1) — a session paused at a rate limit still holds warm
                                context worth a human paste. Guessing "gone"
                                because we could not tell is exactly how the
                                predecessor double-launched.

So `unknown` is its own answer and it REFUSES by default. A gate that guesses is
not a gate.

  liveness.py 2k                 # classify wave 2k's general; exit 0 only if safe to launch
  liveness.py 2k --json
  liveness.py --session orchestrator-main --kind orchestrator
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _core import (  # noqa: E402
    EXIT_GENERIC,
    EXIT_OK,
    count_artifacts,
    find_workspace,
    hr,
    parse_iso,
    read_json,
    run_cli,
    wave_paths,
)

# Exit codes. 0 means "no live owner — launching is safe". Everything else is a
# refusal, and the code says which condition refused, so a caller can branch.
EXIT_SAFE = 0
EXIT_ALIVE_PROGRESSING = 10
EXIT_ALIVE_STALLED = 11
EXIT_ALIVE_PAUSED = 12
EXIT_UNKNOWN = 13

CONDITION_EXIT = {
    "gone": EXIT_SAFE,
    "alive-progressing": EXIT_ALIVE_PROGRESSING,
    "alive-stalled": EXIT_ALIVE_STALLED,
    "alive-paused": EXIT_ALIVE_PAUSED,
    "unknown": EXIT_UNKNOWN,
}

# A checkpoint older than this with no artifact movement is the A5 stall shape.
DEFAULT_STALL_H = 1.5

# How long to watch CPU for the delta. `ps` resolves whole seconds, so anything
# under ~2s cannot distinguish "burning CPU" from "idle" at all.
CPU_SAMPLE_INTERVAL_S = 2.5

# CPU seconds burned over that interval, below which the process is doing nothing.
CPU_IDLE_EPSILON = 0.05


def _pgrep(pattern: str) -> Optional[list]:
    """PIDs whose command line matches `pattern`; None when we cannot tell.

    None is not an empty list. `pgrep` missing, or denied, or timing out means we
    do not know — and not-knowing must never be reported as 'gone'.
    """
    try:
        result = subprocess.run(
            ["pgrep", "-f", pattern], capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode not in (0, 1):
        return None
    return [int(p) for p in result.stdout.split() if p.strip().isdigit()]


def _cpu_seconds(pids: list) -> Optional[float]:
    """Total CPU seconds consumed by these pids. One sample."""
    if not pids:
        return None
    try:
        result = subprocess.run(
            ["ps", "-o", "time=", "-p", ",".join(str(p) for p in pids)],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    total = 0.0
    for line in result.stdout.strip().splitlines():
        parts = line.strip().split(":")
        if not parts or not parts[0]:
            continue
        try:
            seconds = 0.0
            for part in parts:
                seconds = seconds * 60 + float(part)
            total += seconds
        except ValueError:
            return None
    return total


def cpu_delta(pids: list, interval_s: float = CPU_SAMPLE_INTERVAL_S) -> Optional[float]:
    """CPU seconds burned across a short interval — the signal doctrine/07 names.

    It has to be a DELTA, not a total. A session paused at a rate limit after
    four hours of work has a huge cumulative CPU time and is doing nothing; a
    session one minute into real work has a tiny one and is doing everything. The
    absolute number cannot tell those apart, so only the change over an interval
    is informative.

    `ps` reports CPU time at whole-second granularity, so the interval must be
    comfortably longer than a second for the delta to resolve at all.
    """
    first = _cpu_seconds(pids)
    if first is None:
        return None
    time.sleep(interval_s)
    second = _cpu_seconds(pids)
    if second is None:
        return None
    return max(0.0, second - first)


def _hours_since(iso: Optional[str]) -> Optional[float]:
    parsed = parse_iso(iso or "")
    if parsed is None:
        return None
    return (datetime.now(timezone.utc) - parsed).total_seconds() / 3600.0


def classify_wave(
    workspace: Path, wave_id: str, stall_hours: float = DEFAULT_STALL_H
) -> Dict[str, Any]:
    status = read_json(wave_paths(workspace, wave_id)["status"], {})
    session = status.get("wavegen_session")
    state = status.get("state")

    result: Dict[str, Any] = {
        "kind": "wave",
        "wave_id": wave_id,
        "session": session,
        "wave_state": state,
        "signals": {},
        "condition": "unknown",
        "safe_to_launch": False,
        "reason": "",
    }

    # A wave nobody has ever launched has no owner to collide with.
    if not session:
        if state in (None, "PLANNED"):
            result.update(
                condition="gone",
                safe_to_launch=True,
                reason=(
                    f"wave {wave_id} is {state or 'unscaffolded'} and names no "
                    "wavegen_session — no live owner to double-launch."
                ),
            )
            return result
        result["reason"] = (
            f"wave {wave_id} is {state} but WAVE_{wave_id}_STATUS.json names no "
            "wavegen_session, so process liveness cannot be established. Refusing: "
            "an unknown owner is not an absent owner (C1). Set wavegen_session, or "
            "pass --allow-unknown once you have confirmed by hand that nothing is running."
        )
        return result

    pids = _pgrep(session)
    if pids is None:
        result["reason"] = (
            f"could not run pgrep for {session!r}. Unknown != gone (C1) — refusing "
            "to launch. Check by hand, then re-run with --allow-unknown."
        )
        return result

    result["signals"]["pids"] = pids
    if not pids:
        result.update(
            condition="gone",
            safe_to_launch=True,
            reason=(
                f"no process matches {session!r}. The wave is INTERRUPTED, not live: "
                "relaunch it from its checkpoint (the Orchestrator writes the RESUME "
                "directive; the relaunched Wave General executes it)."
            ),
        )
        return result

    # ---- the three progress signals ---------------------------------------
    artifacts_now = count_artifacts(workspace)
    baseline = int(status.get("artifacts_at_start") or 0)
    recorded = int(status.get("artifacts_now") or baseline)
    checkpoint_age = _hours_since(status.get("last_checkpoint_at"))
    burned = cpu_delta(pids)

    stale_checkpoint = checkpoint_age is not None and checkpoint_age > stall_hours
    no_artifact_movement = artifacts_now <= recorded
    looks_idle = burned is not None and burned < CPU_IDLE_EPSILON
    parked = bool(
        read_json(
            workspace / "handoffs" / "orchestrator" / "WINDOW_STATE.json", {}
        ).get("park_state")
    )

    result["signals"].update(
        {
            "artifacts_delta_vs_baseline": artifacts_now - baseline,
            "artifacts_delta_vs_last_status_write": artifacts_now - recorded,
            "checkpoint_age_h": None if checkpoint_age is None else round(checkpoint_age, 3),
            "cpu_seconds_burned": None if burned is None else round(burned, 3),
            "cpu_sample_interval_s": CPU_SAMPLE_INTERVAL_S,
            "tasks_banked": status.get("tasks_done"),
            "tasks_total": status.get("tasks_total"),
            "mission_parked": parked,
        }
    )

    # ORDER MATTERS. Progress is decided by the progress signals — checkpoint
    # advance and artifact movement — BEFORE any CPU reading, because A5's
    # wedged session burns plenty of CPU while banking nothing. Asking "is it
    # busy?" first would call that one healthy.
    if stale_checkpoint and no_artifact_movement:
        banked = int(status.get("tasks_done") or 0)
        result.update(
            condition="alive-stalled",
            reason=(
                f"{session} is alive but NOT progressing: checkpoint is "
                f"{checkpoint_age:.2f}h old and no new artifacts"
                + (
                    f" (it has burned {burned:.2f}s of CPU in the last "
                    f"{CPU_SAMPLE_INTERVAL_S}s, so it is spinning, not idle)"
                    if burned is not None and burned >= CPU_IDLE_EPSILON
                    else ""
                )
                + ". This is A5. "
                + (
                    "Nothing is banked — kill it and clean-restart the wave."
                    if banked == 0
                    else f"{banked} task(s) banked — kill it and checkpoint-resume "
                    "via a RESUME directive."
                )
                + " Killing is the Orchestrator's decision; this gate only refuses to "
                "launch beside it."
            ),
        )
        return result

    # Alive, making progress by the file signals, but burning no CPU right now:
    # the rate-limit pause. The one condition whose right answer is a human paste
    # into the warm session rather than any kind of relaunch.
    if parked or looks_idle:
        result.update(
            condition="alive-paused",
            reason=(
                f"{session} is alive and has burned "
                + ("no measurable" if burned is None else f"{burned:.2f}s of")
                + f" CPU over {CPU_SAMPLE_INTERVAL_S}s"
                + (", and the mission is PARKED" if parked else "")
                + " — the rate-limit pause shape, not a stall and not a death. Do NOT "
                "launch a rival: the paused session holds warm context worth more than "
                "a cold relaunch. Ping the human to paste the RESUME directive into it "
                "(doctrine/07 section 2, C1)."
            ),
        )
        return result

    result.update(
        condition="alive-progressing",
        reason=(
            f"{session} is alive and progressing (checkpoint "
            + (f"{checkpoint_age:.2f}h old" if checkpoint_age is not None else "pending")
            + f", artifacts {baseline}→{artifacts_now}"
            + (f", {burned:.2f}s CPU burned" if burned is not None else "")
            + "). HOLD. Post nothing, launch nothing — the wave is working."
        ),
    )
    return result


def classify_session(session: str, kind: str = "session") -> Dict[str, Any]:
    """Bare process check for a role with no wave STATUS file (the Orchestrator)."""
    result: Dict[str, Any] = {
        "kind": kind,
        "session": session,
        "signals": {},
        "condition": "unknown",
        "safe_to_launch": False,
        "reason": "",
    }
    pids = _pgrep(session)
    if pids is None:
        result["reason"] = (
            f"could not run pgrep for {session!r}. Unknown != gone — refusing."
        )
        return result
    result["signals"]["pids"] = pids
    if not pids:
        result.update(
            condition="gone",
            safe_to_launch=True,
            reason=f"no process matches {session!r}; safe to launch.",
        )
        return result
    result.update(
        condition="alive-progressing",
        reason=(
            f"{len(pids)} live process(es) match {session!r}. Refusing to launch a "
            "second one. Exactly one Orchestrator and exactly one babysit loop exist "
            "at any instant — rotation transfers ownership, it does not duplicate it."
        ),
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(prog="liveness.py")
    parser.add_argument("wave_id", nargs="?", help="wave to check")
    parser.add_argument("--workspace")
    parser.add_argument("--session", help="check a bare session name instead of a wave")
    parser.add_argument("--kind", default="session")
    parser.add_argument("--stall-hours", type=float, default=DEFAULT_STALL_H)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--allow-unknown",
        action="store_true",
        help="treat 'unknown' as safe. Only after checking by hand — this is the "
        "override that re-enables the double-launch bug if used casually.",
    )
    args = parser.parse_args()

    if args.session:
        result = classify_session(args.session, args.kind)
    elif args.wave_id:
        workspace = find_workspace(Path(args.workspace) if args.workspace else None)
        result = classify_wave(workspace, args.wave_id, args.stall_hours)
    else:
        parser.error("give a wave id or --session")
        return EXIT_GENERIC

    if result["condition"] == "unknown" and args.allow_unknown:
        result["safe_to_launch"] = True
        result["reason"] += " [--allow-unknown: overridden by the operator]"

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(hr())
        print(f"  {result['kind']}: {result.get('wave_id') or result.get('session')}")
        print(f"  condition: {result['condition']}")
        print(f"  safe to launch: {'YES' if result['safe_to_launch'] else 'NO'}")
        for key, value in result["signals"].items():
            print(f"    {key}: {value}")
        print(hr())
        print(f"  {result['reason']}")

    if result["safe_to_launch"]:
        return EXIT_SAFE
    return CONDITION_EXIT.get(result["condition"], EXIT_GENERIC)


if __name__ == "__main__":
    run_cli(main)
