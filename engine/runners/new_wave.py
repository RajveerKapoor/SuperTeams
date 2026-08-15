#!/usr/bin/env python3
"""new_wave.py — scaffold every file a wave requires.

Templated scaffolding is the structural cure for the predecessor's entire
"bookkeeping convention drift" class (doctrine/06 E1): missing NOTES files,
ad-hoc STATUS strings, inconsistent artifact counts. If new_wave.py creates every
required file and dispatch.py validate makes a missing field an error, state
cannot silently rot.

  new_wave.py 2k --tasks TASK_0031,TASK_0032,TASK_0033
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _core import (  # noqa: E402
    EXIT_GENERIC,
    EXIT_OK,
    append_audit,
    atomic_write_json,
    atomic_write_text,
    count_artifacts,
    die,
    engine_root,
    find_workspace,
    get_entry,
    load_registry,
    now_iso,
    registry_lock,
    run_cli,
    save_registry,
    validate_against,
    wave_paths,
)


def render(text: str, mapping: dict) -> str:
    for key, value in mapping.items():
        text = text.replace("{{" + key + "}}", str(value))
    return text


def main() -> int:
    parser = argparse.ArgumentParser(prog="new_wave.py")
    parser.add_argument("wave_id")
    parser.add_argument("--tasks", required=True, help="comma-separated task ids")
    parser.add_argument("--workspace")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    workspace = find_workspace(Path(args.workspace) if args.workspace else None)
    wave_id = args.wave_id
    task_ids: List[str] = [t.strip() for t in args.tasks.split(",") if t.strip()]
    if not task_ids:
        raise die(EXIT_GENERIC, "--tasks must name at least one task")

    paths = wave_paths(workspace, wave_id)
    if paths["status"].exists() and not args.force:
        raise die(
            EXIT_GENERIC,
            f"wave {wave_id} already scaffolded ({paths['status']}). "
            "One Wave General per wave, ever — pass --force only to repair a scaffold.",
        )

    # Check the templates BEFORE touching the registry. Everything below the
    # lock mutates shared truth; a failure after that point leaves tasks assigned
    # to a wave that has no plan, brief, or status file — a half-scaffolded wave
    # is worse than an unscaffolded one, because it looks ready.
    templates = engine_root() / "templates"
    template_files = ("WAVE_PLAN.md", "WAVE_BRIEF.md", "WAVE_FULL_RECORD.md")
    missing = [name for name in template_files if not (templates / name).exists()]
    if missing:
        raise die(
            EXIT_GENERIC,
            f"missing template(s) in {templates}: {', '.join(missing)}. Nothing was "
            "scaffolded and the registry was not touched. Re-run init_workspace.py "
            "to restore the mission's pinned templates/ directory.",
        )

    with registry_lock(workspace):
        registry = load_registry(workspace)
        for task_id in task_ids:
            entry = get_entry(registry, task_id)
            if entry.get("type") != "task":
                raise die(EXIT_GENERIC, f"{task_id} is not a task")
            if not entry.get("frozen"):
                raise die(
                    EXIT_GENERIC,
                    f"{task_id} has no frozen criterion. Freeze before dispatch — "
                    "a criterion set after the result is seen is not a criterion "
                    "(doctrine/04 section 3).",
                )
            entry["wave"] = wave_id
            entry["version"] = entry.get("version", 1) + 1
        save_registry(workspace, registry)
        append_audit(
            workspace,
            entry_id=f"WAVE_{wave_id}",
            action="new_wave",
            patch={"tasks": task_ids},
        )

    baseline = count_artifacts(workspace)
    mapping = {
        "WAVE_ID": wave_id,
        "MISSION": registry.get("mission", "?"),
        "TASKS": ", ".join(task_ids),
        "TASK_LIST": "\n".join(f"- `{t}`" for t in task_ids),
        "CREATED_AT": now_iso(),
        "BASELINE": baseline,
    }

    for template_name, key in (
        ("WAVE_PLAN.md", "plan"),
        ("WAVE_BRIEF.md", "brief"),
        ("WAVE_FULL_RECORD.md", "full_record"),
    ):
        source = templates / template_name
        atomic_write_text(paths[key], render(source.read_text(encoding="utf-8"), mapping))

    status = {
        "wave_id": wave_id,
        "state": "PLANNED",
        "wavegen_session": None,
        "wavegen_pid_hint": None,
        "tasks_total": len(task_ids),
        "tasks_done": 0,
        "task_in_progress": None,
        "tasks_pending": task_ids,
        "artifacts_at_start": baseline,
        "artifacts_now": baseline,
        "last_checkpoint_at": None,
        "audit_state": "NOT_REQUESTED",
        "deferred_compute": [],
        "summary_path": None,
        "final_audit_at": None,
        "started_at": None,
        "updated_at": now_iso(),
        "next_action": f"launch the Wave General for wave {wave_id}",
    }
    validate_against(status, "status", f"WAVE_{wave_id}_STATUS.json")
    atomic_write_json(paths["status"], status)

    checkpoint = {
        "wave_id": wave_id,
        "completed": [],
        "in_progress": None,
        "pending": task_ids,
        "deferred": [],
        "artifacts_baseline": baseline,
        "artifacts_at_checkpoint": baseline,
        "last_checkpoint_at": now_iso(),
        "reconcile_rule": "registry wins on any conflict",
    }
    validate_against(checkpoint, "checkpoint", f"WAVE_{wave_id}_CHECKPOINT.md")
    atomic_write_text(
        paths["checkpoint"],
        f"# WAVE {wave_id} CHECKPOINT\n\n"
        "Overwritten after EVERY task banks, never batched. On resume: read this,\n"
        "cross-check against the REGISTRY (**registry wins**), revert any orphan\n"
        "IN_PROGRESS to PENDING, resume from the first pending task.\n\n"
        "```json\n"
        + __import__("json").dumps(checkpoint, indent=2)
        + "\n```\n",
    )

    atomic_write_json(
        paths["baseline"],
        {"wave_id": wave_id, "artifacts_at_start": baseline, "recorded_at": now_iso()},
    )

    print(f"wave {wave_id} scaffolded — {len(task_ids)} task(s), artifacts baseline {baseline}")
    for key in ("plan", "brief", "status", "checkpoint", "full_record"):
        print(f"  {paths[key].relative_to(workspace)}")
    print("\n  next: write the PLAN and BRIEF bodies, then launch the Wave General.")
    return EXIT_OK


if __name__ == "__main__":
    run_cli(main)
