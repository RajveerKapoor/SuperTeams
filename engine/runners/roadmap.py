#!/usr/bin/env python3
"""roadmap.py — the DAG: frontier, packing, add-task, supersede, render.

Work is a living dependency graph, not a static queue (doctrine/11 upgrade 5).
The ready frontier is packed into waves each sized to roughly one 5-hour
rate-limit window, because one Wave General session is one window is one wave
(doctrine/07 section 1).

  roadmap.py add-task --title "..." --deps TASK_0028,TASK_0030 --lens engineering
  roadmap.py frontier
  roadmap.py pack --window-budget 4.5
  roadmap.py supersede TASK_0044 --reason "branch died when TASK_0031 returned FAILED"
  roadmap.py render
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Set

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _core import (  # noqa: E402
    EXIT_OK,
    append_audit,
    atomic_write_text,
    die,
    find_workspace,
    get_entry,
    hr,
    load_registry,
    now_iso,
    orch_dir,
    registry_lock,
    run_cli,
    save_registry,
    truncate,
)

DEFAULT_ESTIMATE_H = 1.5


def tasks_of(registry: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {
        eid: e for eid, e in registry.get("entries", {}).items() if e.get("type") == "task"
    }


def frontier(registry: Dict[str, Any]) -> List[Dict[str, Any]]:
    """PENDING or BLOCKED_ON_DEPS tasks whose dependencies are all COMPLETED."""
    tasks = tasks_of(registry)
    ready: List[Dict[str, Any]] = []
    for entry in tasks.values():
        if entry.get("status") not in ("PENDING", "BLOCKED_ON_DEPS"):
            continue
        deps = entry.get("dependencies", []) or []
        if all(
            tasks.get(d, {}).get("status") in ("COMPLETED", "SUPERSEDED") for d in deps
        ):
            ready.append(entry)
    return sorted(ready, key=lambda e: e["id"])


def cmd_add_task(args: argparse.Namespace, workspace: Path) -> int:
    cmd = [
        sys.executable,
        str(Path(__file__).with_name("dispatch.py")),
        "--workspace",
        str(workspace),
        "new",
        "--type",
        "task",
        "--title",
        args.title,
    ]
    if args.deps:
        cmd += ["--deps", args.deps]
    if args.lens:
        cmd += ["--lens", args.lens]
    if args.model:
        cmd += ["--model", args.model]
    fields: Dict[str, Any] = {}
    if args.estimate is not None:
        fields["estimate_h"] = args.estimate
    if args.agent_type:
        fields["agent_type"] = args.agent_type
    if fields:
        import json as _json

        cmd += ["--fields", _json.dumps(fields)]

    result = subprocess.run(cmd, capture_output=True, text=True)
    sys.stderr.write(result.stderr)
    sys.stdout.write(result.stdout)
    return result.returncode


def cmd_frontier(args: argparse.Namespace, workspace: Path) -> int:
    registry = load_registry(workspace)
    ready = frontier(registry)
    if not ready:
        print("frontier: empty — no task has all dependencies COMPLETED")
        blocked = [
            e
            for e in tasks_of(registry).values()
            if e.get("status") in ("PENDING", "BLOCKED_ON_DEPS")
        ]
        if blocked:
            print(f"  ({len(blocked)} task(s) still waiting on dependencies)")
        return EXIT_OK
    print(f"frontier: {len(ready)} ready task(s)")
    print(hr())
    for entry in ready:
        est = entry.get("estimate_h") or DEFAULT_ESTIMATE_H
        frozen = "frozen" if entry.get("frozen") else "DRAFT "
        print(
            f"  {entry['id']}  [{frozen}] ~{est:>4.1f}h  "
            f"{truncate(entry.get('title', ''), 46)}"
        )
    return EXIT_OK


def cmd_pack(args: argparse.Namespace, workspace: Path) -> int:
    registry = load_registry(workspace)
    ready = frontier(registry)
    budget = args.window_budget
    chosen: List[Dict[str, Any]] = []
    spent = 0.0
    deferred: List[str] = []

    for entry in ready:
        est = entry.get("estimate_h") or DEFAULT_ESTIMATE_H
        if not entry.get("frozen"):
            deferred.append(f"{entry['id']} (criterion not frozen — run pre_register.py)")
            continue
        if spent + est > budget and chosen:
            deferred.append(f"{entry['id']} (would exceed the window budget)")
            continue
        if est > budget:
            # A single task larger than a whole window is legitimate; it must use
            # the background-compute contract rather than be shortened (B1).
            print(
                f"  note: {entry['id']} estimates {est:.1f}h > budget {budget:.1f}h. "
                "It must use the Producer/Consumer background-compute contract "
                "(doctrine/07 section 4). Never shorten a run to fit a window."
            )
        chosen.append(entry)
        spent += est

    if not chosen:
        print("pack: nothing packable.")
        for item in deferred:
            print(f"  deferred: {item}")
        return EXIT_OK

    print(f"pack: {len(chosen)} task(s), est {spent:.1f}h of a {budget:.1f}h window")
    print(hr())
    for entry in chosen:
        est = entry.get("estimate_h") or DEFAULT_ESTIMATE_H
        print(f"  {entry['id']}  ~{est:>4.1f}h  {truncate(entry.get('title', ''), 50)}")
    if deferred:
        print("\n  deferred to a later wave:")
        for item in deferred:
            print(f"    {item}")
    print("\n  --tasks " + ",".join(e["id"] for e in chosen))
    return EXIT_OK


def cmd_supersede(args: argparse.Namespace, workspace: Path) -> int:
    with registry_lock(workspace):
        registry = load_registry(workspace)
        entry = get_entry(registry, args.task)
        if entry.get("status") == "COMPLETED":
            raise die(
                1,
                f"{args.task} is COMPLETED. Completed work is never superseded — "
                "its record stands for the audit trail.",
            )
        entry["status"] = "SUPERSEDED"
        entry["notes"] = args.reason
        entry["superseded_by"] = args.by
        entry["version"] = entry.get("version", 1) + 1
        save_registry(workspace, registry)
        append_audit(
            workspace,
            entry_id=args.task,
            action="supersede",
            patch={"reason": args.reason, "superseded_by": args.by},
            new_version=entry["version"],
        )
    print(f"{args.task} -> SUPERSEDED (kept for audit, not executed)")
    return EXIT_OK


def cmd_render(args: argparse.Namespace, workspace: Path) -> int:
    registry = load_registry(workspace)
    tasks = tasks_of(registry)
    ready_ids = {e["id"] for e in frontier(registry)}

    lines = [
        f"# ROADMAP — {registry.get('mission')}",
        "",
        f"Rendered {now_iso()} by `roadmap.py render`. Do not hand-edit.",
        f"Mode: **{registry.get('mode')}**  ·  {len(tasks)} tasks",
        "",
        "| task | status | verdict | deps | wave | title |",
        "|------|--------|---------|------|------|-------|",
    ]
    for entry_id, entry in sorted(tasks.items()):
        marker = " ←ready" if entry_id in ready_ids else ""
        deps = ", ".join(entry.get("dependencies", []) or []) or "—"
        lines.append(
            f"| `{entry_id}`{marker} | {entry.get('status')} | "
            f"{entry.get('verdict') or '—'} | {deps} | {entry.get('wave') or '—'} | "
            f"{truncate(entry.get('title', ''), 60)} |"
        )

    counts: Dict[str, int] = {}
    for entry in tasks.values():
        counts[entry.get("status", "?")] = counts.get(entry.get("status", "?"), 0) + 1
    lines += ["", "## Status counts", ""]
    for status, count in sorted(counts.items()):
        lines.append(f"- **{status}**: {count}")

    target = orch_dir(workspace) / "ROADMAP.md"
    atomic_write_text(target, "\n".join(lines) + "\n")
    print(f"wrote {target}")
    return EXIT_OK


def main() -> int:
    parser = argparse.ArgumentParser(prog="roadmap.py")
    parser.add_argument("--workspace")
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add-task")
    p_add.add_argument("--title", required=True)
    p_add.add_argument("--deps")
    p_add.add_argument("--lens")
    p_add.add_argument("--model")
    p_add.add_argument("--estimate", type=float, help="planning estimate in hours")
    p_add.add_argument("--agent-type", help="the generated agent that should execute this")
    p_add.set_defaults(func=cmd_add_task)

    p_frontier = sub.add_parser("frontier")
    p_frontier.set_defaults(func=cmd_frontier)

    p_pack = sub.add_parser("pack")
    p_pack.add_argument("--window-budget", type=float, default=4.5, help="hours (default 4.5)")
    p_pack.set_defaults(func=cmd_pack)

    p_sup = sub.add_parser("supersede")
    p_sup.add_argument("task")
    p_sup.add_argument("--reason", required=True)
    p_sup.add_argument("--by", help="the task or decision that superseded it")
    p_sup.set_defaults(func=cmd_supersede)

    p_render = sub.add_parser("render")
    p_render.set_defaults(func=cmd_render)

    args = parser.parse_args()
    workspace = find_workspace(Path(args.workspace) if args.workspace else None)
    return args.func(args, workspace)


if __name__ == "__main__":
    run_cli(main)
