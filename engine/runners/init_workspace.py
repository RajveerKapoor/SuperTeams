#!/usr/bin/env python3
"""init_workspace.py — scaffold a mission workspace.

Creates the predecessor's `verification/` tree, generalized (doctrine/03 s.1):
every directory, a seeded REGISTRY.json, the handoffs tree, the charters copied
from the engine, and the human-facing surface (STEERING / INBOX / OUTBOX).

  init_workspace.py <path> --mission "clarity-refactor" --mode finite
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import Dict

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _core import (  # noqa: E402
    EXIT_GENERIC,
    EXIT_OK,
    atomic_write_json,
    atomic_write_text,
    die,
    engine_root,
    now_iso,
    run_cli,
)

DIRECTORIES = [
    "runners",
    "reports",
    "datasets",
    "handoffs/waves",
    "handoffs/briefs",
    "handoffs/summaries",
    "handoffs/status",
    "handoffs/checkpoints",
    "handoffs/full_records",
    "handoffs/halt_requests",
    "handoffs/orchestrator",
    "handoffs/orchestrator/intake",
    ".claude/agents",
    ".claude/commands",
]

# Charters copied from the engine into the mission on init, so a mission is
# self-contained and its doctrine cannot drift out from under it mid-flight.
CHARTERS = [
    ("ORCHESTRATOR_RUNBOOK.md", "handoffs/waves/ORCHESTRATOR_RUNBOOK.md"),
    ("WAVE_GENERAL_OPERATING_MANUAL.md", "handoffs/waves/WAVE_GENERAL_OPERATING_MANUAL.md"),
    ("AUDITOR_CHARTER.md", "handoffs/waves/AUDITOR_CHARTER.md"),
    ("SUBAGENT_CHARTER.md", "handoffs/waves/SUBAGENT_CHARTER.md"),
    ("WAVE_INDEX.md", "handoffs/waves/WAVE_INDEX.md"),
    ("AUTO_ADVANCE_POLICY.md", "handoffs/orchestrator/AUTO_ADVANCE_POLICY.md"),
    ("ORCHESTRATOR_HANDOFF.md", "handoffs/orchestrator/ORCHESTRATOR_HANDOFF.md"),
]

GITIGNORE = """\
REGISTRY.lock
.*.tmp.*
__pycache__/
*.pyc
.DS_Store
"""


def render(text: str, context: Dict[str, str]) -> str:
    for key, value in context.items():
        text = text.replace("{{" + key + "}}", value)
    return text


def main() -> int:
    parser = argparse.ArgumentParser(prog="init_workspace.py")
    parser.add_argument("path", help="workspace directory to create or adopt")
    parser.add_argument("--mission", required=True, help="mission slug, e.g. clarity-refactor")
    parser.add_argument("--mode", choices=["finite", "persistent"], default="finite")
    parser.add_argument("--goal", default="(to be written by the Orchestrator)")
    parser.add_argument("--force", action="store_true", help="adopt a non-empty directory")
    args = parser.parse_args()

    workspace = Path(args.path).expanduser().resolve()
    registry_file = workspace / "REGISTRY.json"
    if registry_file.exists() and not args.force:
        raise die(
            EXIT_GENERIC,
            f"{registry_file} already exists. This workspace is already initialised; "
            "pass --force only if you intend to adopt it.",
        )

    for directory in DIRECTORIES:
        (workspace / directory).mkdir(parents=True, exist_ok=True)

    context = {
        "MISSION": args.mission,
        "MODE": args.mode,
        "GOAL": args.goal,
        "CREATED_AT": now_iso(),
        "WORKSPACE": str(workspace),
    }

    # ---- REGISTRY.json -----------------------------------------------------
    atomic_write_json(
        registry_file,
        {
            "schema_version": 2,
            "mission": args.mission,
            "mode": args.mode,
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "pre_registered_frozen_at": None,
            "n_entries": 0,
            "entries": {},
        },
    )

    # ---- append-only files -------------------------------------------------
    for name in ("artifacts.jsonl", "REGISTRY.audit.log"):
        target = workspace / name
        if not target.exists():
            target.touch()

    # ---- charters ----------------------------------------------------------
    templates = engine_root() / "templates"
    for source_name, dest_rel in CHARTERS:
        source = templates / source_name
        dest = workspace / dest_rel
        if not source.exists():
            print(f"  warning: missing template {source}", file=sys.stderr)
            continue
        atomic_write_text(dest, render(source.read_text(encoding="utf-8"), context))

    # ---- MISSION.md --------------------------------------------------------
    mission_template = templates / "MISSION.md"
    if mission_template.exists() and not (workspace / "MISSION.md").exists():
        atomic_write_text(
            workspace / "MISSION.md",
            render(mission_template.read_text(encoding="utf-8"), context),
        )

    # ---- the human-facing surface -----------------------------------------
    orch = workspace / "handoffs" / "orchestrator"
    seed_files = {
        "STEERING.md": (
            "# STEERING — you write here, the Orchestrator reads at every wave boundary\n\n"
            "Drop a directive at any instant. It is read at the NEXT wave boundary (never\n"
            "mid-wave, so it cannot corrupt an in-flight wave's frozen scope). Every\n"
            "directive becomes a Decision record; if it authorizes something, an\n"
            "Authorization record too.\n\n"
            "Format: one directive per block, newest at the bottom. Head a new\n"
            "block with the word unread in square brackets; the Orchestrator\n"
            "rewrites it to read once the directive has become a Decision.\n\n"
            "Example:\n\n"
            "    ## [read] 2026-08-15T09:00:00Z — stop work on the parser branch\n\n"
            "---\n\n"
            # This file is seeded WITHOUT the unread marker anywhere in it —
            # not in a placeholder block and not in the instructions above, which
            # is why they spell the word out instead of showing the token. The
            # babysit loop greps for that literal token, so any example of it
            # here would make the first tick of every new mission announce a
            # human directive that does not exist.
            "## [read] " + now_iso() + " — workspace initialised\n"
            "(no directives yet)\n"
        ),
        "INBOX.md": (
            "# INBOX — freeform human notes\n\n"
            "For thoughts that are not crisp directives. The Orchestrator triages these\n"
            "into tasks or Decisions. Use STEERING.md when you want something done.\n"
        ),
        "OUTBOX.md": (
            "# OUTBOX — the batched digest (the one file to read)\n\n"
            "Wave closures, verdicts, findings, decisions. Reading it is optional;\n"
            "nothing waits on it. Genuine decisions arrive as a notification instead.\n"
        ),
        "CAMPAIGN_LOG.md": f"# CAMPAIGN LOG — {args.mission}\n\nAppend-only narrative.\n\n## {now_iso()} — workspace initialised\nmode: {args.mode}\n",
        "WAVE_LAUNCH_QUEUE.md": (
            "# WAVE LAUNCH QUEUE\n\n"
            "| wave | tasks | depends on | status |\n"
            "|------|-------|-----------|--------|\n"
            "| (none yet) | | | |\n"
        ),
        "ROADMAP.md": "# ROADMAP\n\nRendered by `roadmap.py render`. Do not hand-edit.\n",
        "ADVERSARIAL_LOG.md": (
            "# ADVERSARIAL LOG\n\n"
            "Every devil's-advocate round run against this mission's plan, what it found,\n"
            "and what changed as a result. Written when the Orchestrator first commits the\n"
            "plan (MISSION.md) and on every re-plan thereafter.\n"
        ),
    }
    for name, body in seed_files.items():
        target = orch / name
        if not target.exists():
            atomic_write_text(target, body)

    # ---- WINDOW_STATE.json -------------------------------------------------
    window_state = orch / "WINDOW_STATE.json"
    if not window_state.exists():
        atomic_write_json(
            window_state,
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

    # ---- a pinned copy of the engine, so the mission cannot shift ----------
    # The workspace MIRRORS the engine layout (runners/ schemas/ templates/
    # lenses/ bin/), because `_core.engine_root()` is "the parent of the directory
    # holding _core.py". Inside a mission that resolves to the workspace root, so
    # every sibling directory has to sit where the engine's does — otherwise the
    # runners look for their schemas somewhere nothing ever wrote.
    #
    # Pinning is the point: a campaign that runs for weeks must not have its
    # schemas, templates, or lenses change shape underneath it because someone
    # edited the shared engine on day four.
    # The engine's own test battery is not part of a mission: it tests the
    # engine, and shipping it into every workspace invites someone to run it
    # there and read the result as a statement about the mission.
    for source in (engine_root() / "runners").glob("*.py"):
        if source.name.startswith("test_"):
            continue
        shutil.copy2(source, workspace / "runners" / source.name)

    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store", "test_*.py")
    for name in ("schemas", "templates", "lenses", "curiosity", "stats", "repro"):
        dest = workspace / name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(engine_root() / name, dest, ignore=ignore)

    # The launchers live in handoffs/orchestrator/ (doctrine/03 section 1), beside
    # the Orchestrator's own files, because the Orchestrator is the only role that
    # ever runs them.
    for source in (engine_root() / "bin").glob("*.sh"):
        dest = orch / source.name
        shutil.copy2(source, dest)
        dest.chmod(0o755)

    # /revive and /audit — the two slash commands the roles invoke by name.
    for source in (engine_root() / "commands").glob("*.md"):
        shutil.copy2(source, workspace / ".claude" / "commands" / source.name)

    gitignore = workspace / ".gitignore"
    if not gitignore.exists():
        atomic_write_text(gitignore, GITIGNORE)

    print(f"workspace initialised: {workspace}")
    print(f"  mission: {args.mission}   mode: {args.mode}")
    print("  next: roadmap.py add-task ... ; pre_register.py --set ... ; pre_register.py --freeze")
    return EXIT_OK


if __name__ == "__main__":
    run_cli(main)
