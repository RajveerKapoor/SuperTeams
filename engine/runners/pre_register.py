#!/usr/bin/env python3
"""pre_register.py — freeze the definition of done.

The anti-goalpost-moving line (doctrine/04 section 3, doctrine/08 section 2).
Before any Subagent starts, each task's acceptance criterion is frozen. After
that, dispatch.py refuses (exit 6) any patch that alters a frozen field unless
the caller passes --unfreeze with a cited Authorization.

  pre_register.py --set --disc TASK_0031 \\
      --dod "config.load() has no module-level state; all 41 call sites updated" \\
      --check "pytest tests/config -q && ! grep -rn '_GLOBAL_CFG' src/" \\
      --precision deterministic
  pre_register.py --freeze                 # freeze EVERY task with a complete criterion
  pre_register.py --status                 # what is frozen, what is not
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _core import (  # noqa: E402
    EXIT_GENERIC,
    EXIT_OK,
    EXIT_SCHEMA,
    append_audit,
    die,
    find_workspace,
    get_entry,
    hr,
    load_registry,
    now_iso,
    registry_lock,
    run_cli,
    save_registry,
    truncate,
)

REQUIRED_FOR_FREEZE = ("falsification_criterion", "acceptance_check")


def cmd_set(args: argparse.Namespace, workspace: Path) -> int:
    with registry_lock(workspace):
        registry = load_registry(workspace)
        entry = get_entry(registry, args.disc)
        if entry.get("type") != "task":
            raise die(EXIT_SCHEMA, f"{args.disc} is not a task")
        if entry.get("frozen"):
            raise die(
                EXIT_GENERIC,
                f"{args.disc} is already frozen. Moving a frozen goalpost requires "
                "dispatch.py update --unfreeze <field> --authz <AUTHZ_id>.",
            )

        pre = entry.setdefault("pre_registered", {})
        if args.dod is not None:
            pre["falsification_criterion"] = args.dod
        if args.check is not None:
            pre["acceptance_check"] = args.check
        if args.precision is not None:
            pre["required_precision_se"] = args.precision
        if args.stumped_width is not None:
            pre["stumped_ci_width"] = args.stumped_width
        if args.target_n is not None:
            pre["target_n"] = args.target_n
        pre.setdefault("required_precision_se", "deterministic")
        pre.setdefault("stumped_ci_width", None)
        pre.setdefault("target_n", 1)

        entry["version"] = entry.get("version", 1) + 1
        save_registry(workspace, registry)
        append_audit(
            workspace,
            entry_id=args.disc,
            action="pre_register.set",
            patch={"pre_registered": pre},
            new_version=entry["version"],
        )
    print(f"{args.disc}: criterion drafted (not yet frozen)")
    return EXIT_OK


def cmd_freeze(args: argparse.Namespace, workspace: Path) -> int:
    frozen: List[str] = []
    skipped: List[str] = []

    with registry_lock(workspace):
        registry = load_registry(workspace)
        targets = (
            [args.disc]
            if args.disc
            else [
                eid
                for eid, e in registry.get("entries", {}).items()
                if e.get("type") == "task" and not e.get("frozen")
            ]
        )
        stamp = now_iso()
        for entry_id in targets:
            entry = get_entry(registry, entry_id)
            if entry.get("type") != "task":
                continue
            if entry.get("frozen"):
                continue
            if entry.get("status") == "SUPERSEDED":
                continue
            pre = entry.get("pre_registered", {})
            missing = [f for f in REQUIRED_FOR_FREEZE if not pre.get(f)]
            if missing:
                skipped.append(f"{entry_id} (missing {', '.join(missing)})")
                continue
            entry["frozen"] = True
            entry["frozen_at"] = stamp
            entry["version"] = entry.get("version", 1) + 1
            frozen.append(entry_id)
            append_audit(
                workspace,
                entry_id=entry_id,
                action="FREEZE",
                patch={"frozen": True, "frozen_at": stamp},
                new_version=entry["version"],
            )

        if frozen and not registry.get("pre_registered_frozen_at"):
            registry["pre_registered_frozen_at"] = stamp
        save_registry(workspace, registry)

    print(f"froze {len(frozen)} task criterion(s)")
    for entry_id in frozen:
        print(f"  frozen  {entry_id}")
    if skipped:
        print(f"\nskipped {len(skipped)} — incomplete criteria, nothing to freeze:")
        for item in skipped:
            print(f"  skip    {item}")
        print(
            "\nA task cannot start until its criterion is frozen. Draft the missing "
            "fields with --set, then re-run --freeze."
        )
    return EXIT_OK


def cmd_status(workspace: Path) -> int:
    registry = load_registry(workspace)
    tasks = {
        eid: e for eid, e in registry.get("entries", {}).items() if e.get("type") == "task"
    }
    print(f"pre-registration status  ({len(tasks)} tasks)")
    print(f"registry frozen_at: {registry.get('pre_registered_frozen_at') or '(never)'}")
    print(hr())
    for entry_id, entry in sorted(tasks.items()):
        mark = "FROZEN" if entry.get("frozen") else "draft "
        pre = entry.get("pre_registered", {})
        dod = pre.get("falsification_criterion") or "(no definition of done)"
        print(f"  {mark}  {entry_id}  {truncate(entry.get('title', ''), 40)}")
        print(f"          dod:   {truncate(dod, 66)}")
        print(f"          check: {truncate(pre.get('acceptance_check') or '(none)', 66)}")
    return EXIT_OK


def main() -> int:
    parser = argparse.ArgumentParser(prog="pre_register.py")
    parser.add_argument("--workspace")
    parser.add_argument("--set", action="store_true", help="draft a criterion")
    parser.add_argument("--freeze", action="store_true", help="freeze criteria (default action)")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--disc", help="entry id; omit with --freeze to freeze all")
    parser.add_argument("--dod", help="falsification_criterion: what 'done' means, in prose")
    parser.add_argument("--check", help="acceptance_check: the mechanical check that decides it")
    parser.add_argument("--precision", help="required_precision_se, or the string 'deterministic'")
    parser.add_argument("--stumped-width", help="stumped_ci_width: how uncertain before honest STUMP")
    parser.add_argument("--target-n", type=int, help="target_n; 1 for a deterministic task")
    args = parser.parse_args()

    workspace = find_workspace(Path(args.workspace) if args.workspace else None)

    if args.status:
        return cmd_status(workspace)
    if args.set:
        if not args.disc:
            raise die(EXIT_GENERIC, "--set requires --disc <ID>")
        return cmd_set(args, workspace)
    return cmd_freeze(args, workspace)


if __name__ == "__main__":
    run_cli(main)
