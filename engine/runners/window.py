#!/usr/bin/env python3
"""window.py — the rate-limit window and weekly-cap tracker.

Two limits shape the whole architecture (doctrine/07 section 1):
  - the 5-hour usage window: work proceeds until spent, then the session pauses
    and does NOT auto-resume;
  - the weekly cap: a hard ceiling; when hit the system must park until reset,
    which can be days away.

One Wave General session is one window is one wave. The babysit loop fires
window-aligned so the tick that closes one wave launches the next into a fresh
window.

  window.py show
  window.py roll                       # a fresh window opened
  window.py spend --frac 0.3
  window.py set --weekly-used 0.71 --weekly-reset 2026-07-06T00:00:00Z
"""

from __future__ import annotations

import argparse
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _core import (  # noqa: E402
    EXIT_OK,
    atomic_write_json,
    find_workspace,
    hr,
    kv,
    now_iso,
    parse_iso,
    read_json,
    run_cli,
    validate_against,
    window_state_path,
)


def load_state(workspace: Path) -> dict:
    return read_json(
        window_state_path(workspace),
        {
            "window_started_at": now_iso(),
            "window_length_h": 5.0,
            "window_budget_remaining_frac": 1.0,
            "weekly_cap_reset_at": None,
            "weekly_used_frac": 0.0,
            "weekly_park_ceiling": 0.9,
            "cadence_cron": None,
            "last_tick_at": None,
            "park_state": None,
        },
    )


def save_state(workspace: Path, state: dict) -> None:
    validate_against(state, "window_state", "WINDOW_STATE.json")
    atomic_write_json(window_state_path(workspace), state)


def window_remaining_h(state: dict) -> float:
    started = parse_iso(state.get("window_started_at", ""))
    length = float(state.get("window_length_h", 5.0))
    if started is None:
        return length
    from datetime import datetime, timezone

    elapsed = (datetime.now(timezone.utc) - started).total_seconds() / 3600.0
    return max(0.0, length - elapsed)


def should_park(state: dict) -> tuple[bool, str]:
    ceiling = float(state.get("weekly_park_ceiling", 0.9))
    used = float(state.get("weekly_used_frac", 0.0))
    if used < ceiling:
        return False, ""
    reset = parse_iso(state.get("weekly_cap_reset_at") or "")
    if reset is None:
        return True, f"weekly usage {used:.0%} >= ceiling {ceiling:.0%}, reset time unknown"
    from datetime import datetime, timezone

    hours = (reset - datetime.now(timezone.utc)).total_seconds() / 3600.0
    if hours > 1.0:
        return True, (
            f"weekly usage {used:.0%} >= ceiling {ceiling:.0%} with {hours:.1f}h until "
            "reset — parking rather than starting a wave it cannot finish"
        )
    return False, ""


def cmd_show(workspace: Path) -> int:
    state = load_state(workspace)
    remaining = window_remaining_h(state)
    park, reason = should_park(state)

    print("window state")
    print(hr())
    print(kv("window started", state.get("window_started_at")))
    print(kv("window length", f"{state.get('window_length_h')}h"))
    print(kv("window remaining", f"~{remaining:.2f}h (wall clock)"))
    print(kv("budget remaining", f"{float(state.get('window_budget_remaining_frac') or 0):.0%}"))
    print(kv("weekly used", f"{float(state.get('weekly_used_frac', 0)):.0%}"))
    print(kv("weekly ceiling", f"{float(state.get('weekly_park_ceiling', 0.9)):.0%}"))
    print(kv("weekly reset", state.get("weekly_cap_reset_at") or "(unknown)"))
    print(kv("cadence", state.get("cadence_cron") or "(no cron armed)"))
    print(kv("last tick", state.get("last_tick_at") or "(never)"))
    if state.get("park_state"):
        print(kv("PARKED", state["park_state"].get("reason")))
        print(kv("  resume when", state["park_state"].get("resume_condition")))
    print(hr())
    if park:
        print(f"  RECOMMENDATION: park.  {reason}")
    elif remaining < 1.0:
        print(
            f"  RECOMMENDATION: do not launch a new wave — only ~{remaining:.1f}h left in "
            "this window. Wait for the roll."
        )
    else:
        print(f"  RECOMMENDATION: a wave of up to ~{max(0.0, remaining - 0.5):.1f}h fits.")
    return EXIT_OK


def main() -> int:
    parser = argparse.ArgumentParser(prog="window.py")
    parser.add_argument("--workspace")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("show")

    p_roll = sub.add_parser("roll", help="record that a fresh window opened")
    p_roll.add_argument("--length", type=float, default=5.0)

    p_spend = sub.add_parser("spend")
    p_spend.add_argument("--frac", type=float, required=True, help="fraction of the window used")

    p_set = sub.add_parser("set")
    p_set.add_argument("--weekly-used", type=float)
    p_set.add_argument("--weekly-reset")
    p_set.add_argument("--ceiling", type=float)
    p_set.add_argument("--cadence")

    sub.add_parser("tick", help="stamp last_tick_at")

    args = parser.parse_args()
    workspace = find_workspace(Path(args.workspace) if args.workspace else None)

    if args.command == "show":
        return cmd_show(workspace)

    state = load_state(workspace)
    if args.command == "roll":
        state["window_started_at"] = now_iso()
        state["window_length_h"] = args.length
        state["window_budget_remaining_frac"] = 1.0
        print(f"window rolled: {args.length}h from {state['window_started_at']}")
    elif args.command == "spend":
        current = float(state.get("window_budget_remaining_frac") or 1.0)
        state["window_budget_remaining_frac"] = max(0.0, current - args.frac)
        print(f"window budget: {current:.0%} -> {state['window_budget_remaining_frac']:.0%}")
    elif args.command == "set":
        if args.weekly_used is not None:
            state["weekly_used_frac"] = args.weekly_used
        if args.weekly_reset:
            state["weekly_cap_reset_at"] = args.weekly_reset
        if args.ceiling is not None:
            state["weekly_park_ceiling"] = args.ceiling
        if args.cadence:
            state["cadence_cron"] = args.cadence
        print("window state updated")
    elif args.command == "tick":
        state["last_tick_at"] = now_iso()
        print(f"tick {state['last_tick_at']}")

    save_state(workspace, state)
    return EXIT_OK


if __name__ == "__main__":
    run_cli(main)
