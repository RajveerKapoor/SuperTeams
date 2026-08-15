#!/usr/bin/env python3
"""dispatch.py — the atomic REGISTRY merger, and the only thing allowed to write it.

This is the one file the whole system reconciles against. Its contract
(doctrine/04_REGISTRY_AND_DISPATCH.md):

  Layer 1  fcntl.flock(LOCK_EX | LOCK_NB) on REGISTRY.lock, polled, 30s soft timeout
  Layer 2  optimistic version check — a patch asserts the version it read
  Write    open(tmp) -> flush -> fsync -> rename           (atomic on POSIX)
  Audit    one JSON line per applied mutation to REGISTRY.audit.log

Four gates, each converting a rule the predecessor had to REMEMBER into a rule
the kernel CHECKS:

  exit 3  VERSION_CONFLICT     someone else wrote between your read and your lock
  exit 6  FROZEN               a patch tried to move a frozen goalpost   (Law 3)
  exit 7  ARTIFACT_MISSING     a completion with no persisted, hashed artifact (Law 1)
  exit 8  DEPENDENCY_NOT_MET   a start/complete that jumped its dependencies

Usage:
  dispatch.py update   --disc TASK_0031 --patch done.json [--unfreeze F --authz AUTHZ_0003]
  dispatch.py new      --type task --title "..." [--deps A,B] [--lens engineering]
  dispatch.py show     --disc TASK_0031
  dispatch.py validate [--json]
  dispatch.py audit-tail [N]
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _core import (  # noqa: E402
    EXIT_ARTIFACT_MISSING,
    EXIT_DEPENDENCY_NOT_MET,
    EXIT_FROZEN,
    EXIT_GENERIC,
    EXIT_NOT_FOUND,
    EXIT_OK,
    EXIT_SCHEMA,
    EXIT_VERSION_CONFLICT,
    FROZEN_FIELDS,
    ID_PREFIXES,
    ID_RE,
    append_audit,
    die,
    find_workspace,
    get_entry,
    hr,
    load_registry,
    next_id,
    normalize_frozen_field,
    normalize_verdict,
    now_iso,
    read_json,
    registry_lock,
    run_cli,
    save_registry,
    sha256_file,
    validate_against,
    verify_artifact_ref,
    verify_entry_artifacts,
)

SCHEMA_FOR_TYPE = {
    "task": "task",
    "claim": "claim",
    "artifact_ref": "artifact_ref",
    "decision": "decision",
    "authorization": "authorization",
}

# A status that means "this task is finished, one way or another".
TERMINAL_STATUS = "COMPLETED"

# Verdicts that assert the work produced something. These demand artifacts.
PRODUCTIVE_VERDICTS = {"DONE", "REVISED", "FAILED", "TRIVIAL"}


# ---------------------------------------------------------------------------
# Entry templates
# ---------------------------------------------------------------------------


def blank_task(entry_id: str, title: str) -> Dict[str, Any]:
    return {
        "id": entry_id,
        "type": "task",
        "title": title,
        "wave": None,
        "status": "PENDING",
        "verdict": None,
        "verdict_value": None,
        "verdict_ci_95": None,
        "dependencies": [],
        "pre_registered": {
            "falsification_criterion": None,
            "acceptance_check": None,
            "required_precision_se": None,
            "stumped_ci_width": None,
            "target_n": 1,
        },
        "frozen": False,
        "frozen_at": None,
        "model_hint": None,
        "lens": None,
        "agent_id": None,
        "agent_type": None,
        "estimate_h": None,
        "started_at": None,
        "finished_at": None,
        "methods_used": [],
        "numerics_config": {},
        "code_commit": None,
        "env_hash": None,
        "input_data_hashes": {},
        "report_path": None,
        "report_sha256": None,
        "artifacts": [],
        "side_findings": [],
        "unblock_criterion": None,
        "criterion_mismatch_flag": False,
        "theoretical_conflict": False,
        "superseded_by": None,
        "notes": None,
        "version": 1,
    }


def blank_entry(entry_type: str, entry_id: str, fields: Dict[str, Any]) -> Dict[str, Any]:
    if entry_type == "task":
        entry = blank_task(entry_id, fields.get("title", "(untitled)"))
    elif entry_type == "claim":
        entry = {
            "id": entry_id,
            "type": "claim",
            "statement": fields.get("statement", ""),
            "source_task": fields.get("source_task", ""),
            "load_bearing": bool(fields.get("load_bearing", True)),
            "evidence": [],
            "rederive": None,
            "audit_state": "UNAUDITED",
            "audited_by": None,
            "audited_at": None,
            "audit_note": None,
            "conflict": False,
            "conflict_note": None,
            "version": 1,
        }
    elif entry_type == "artifact_ref":
        entry = {
            "id": entry_id,
            "type": "artifact_ref",
            "path": fields.get("path", ""),
            "sha256": fields.get("sha256", ""),
            "bytes": fields.get("bytes"),
            "manifest": None,
            "produced_by": fields.get("produced_by", ""),
            "logged_at": now_iso(),
            "version": 1,
        }
    elif entry_type == "decision":
        entry = {
            "id": entry_id,
            "type": "decision",
            "decision": fields.get("decision", ""),
            "rationale": fields.get("rationale", ""),
            "kind": fields.get("kind"),
            "touches": [],
            "cites_authz": fields.get("cites_authz"),
            "decided_by": fields.get("decided_by", "orchestrator"),
            "decided_at": now_iso(),
            "version": 1,
        }
    elif entry_type == "authorization":
        entry = {
            "id": entry_id,
            "type": "authorization",
            "granted_by": fields.get("granted_by", "human"),
            "grants": fields.get("grants", ""),
            "scope": fields.get("scope", ""),
            "granted_at": now_iso(),
            "channel": fields.get("channel", "unspecified"),
            "expires_at": None,
            "revoked": False,
            "version": 1,
        }
    else:
        raise die(EXIT_SCHEMA, f"unknown entry type: {entry_type}")

    for key, value in fields.items():
        if key in entry and value is not None:
            entry[key] = value
    return entry


# ---------------------------------------------------------------------------
# Patch application
# ---------------------------------------------------------------------------


def deep_merge(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    """Merge patch into a copy of base. Nested dicts merge; lists replace."""
    out = copy.deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def check_frozen(
    before: Dict[str, Any],
    patch: Dict[str, Any],
    unfreeze: List[str],
    entry_id: str,
) -> List[str]:
    """Return the frozen fields this patch would move, minus those unfrozen.

    Gate for exit 6 (Law 3: never relax a frozen criterion to make work pass).
    """
    if not before.get("frozen"):
        return []
    proposed = patch.get("pre_registered")
    if not isinstance(proposed, dict):
        return []

    allowed = {normalize_frozen_field(f.split(".")[-1]) for f in unfreeze}
    current = before.get("pre_registered", {})
    violations: List[str] = []
    for raw_field, new_value in proposed.items():
        field = normalize_frozen_field(raw_field)
        if field not in FROZEN_FIELDS:
            continue
        if current.get(field) == new_value:
            continue  # a no-op write is not a goalpost move
        if field in allowed:
            continue
        violations.append(f"{entry_id}.pre_registered.{field}")
    return violations


def check_dependencies(
    registry: Dict[str, Any], after: Dict[str, Any], before: Dict[str, Any]
) -> List[str]:
    """Gate for exit 8: no start or complete before dependencies are COMPLETED."""
    if after.get("type") != "task":
        return []
    new_status = after.get("status")
    if new_status not in ("IN_PROGRESS", "COMPLETED"):
        return []
    if before.get("status") == new_status:
        return []  # not a transition; do not re-litigate history

    entries = registry.get("entries", {})
    unmet: List[str] = []
    for dep_id in after.get("dependencies", []) or []:
        dep = entries.get(dep_id)
        if dep is None:
            unmet.append(f"{dep_id} (does not exist)")
        elif dep.get("status") == "SUPERSEDED":
            continue  # a superseded dependency is intentionally dead
        elif dep.get("status") != "COMPLETED":
            unmet.append(f"{dep_id} (status={dep.get('status')})")
    return unmet


def check_banking_gate(
    workspace: Path, registry: Dict[str, Any], after: Dict[str, Any], before: Dict[str, Any]
) -> List[str]:
    """Gate for exit 7 (Law 1: truth lives on disk).

    On a transition to COMPLETED, re-hash every artifact the entry references
    and the task report. An agent that 'completed' but wrote nothing gets a hard
    error, not a silent success.
    """
    if after.get("type") != "task":
        return []
    if after.get("status") != TERMINAL_STATUS:
        return []
    if before.get("status") == TERMINAL_STATUS:
        return []

    problems = verify_entry_artifacts(workspace, registry, after)

    verdict = normalize_verdict(after.get("verdict"))
    if verdict is None:
        problems.append(f"{after['id']} cannot be COMPLETED with a null verdict")

    if verdict in PRODUCTIVE_VERDICTS:
        if not after.get("report_path"):
            problems.append(
                f"{after['id']} verdict {verdict} requires a report_path — "
                "a claim without a persisted artifact is a rumor (Law 1)"
            )
        if not (after.get("artifacts") or []):
            problems.append(
                f"{after['id']} verdict {verdict} requires at least one logged artifact "
                "(use log_artifact.py)"
            )
    return problems


def check_verdict_invariants(after: Dict[str, Any]) -> List[str]:
    """Honest-verdict invariants from doctrine/05 section 3."""
    if after.get("type") != "task":
        return []
    verdict = normalize_verdict(after.get("verdict"))
    problems: List[str] = []
    if verdict == "STUMPED" and not after.get("unblock_criterion"):
        problems.append(
            f"{after['id']}: a STUMPED verdict requires a non-null unblock_criterion "
            "('here is exactly what would let me' — Law 5)"
        )
    if verdict == "REVISED" and not after.get("criterion_mismatch_flag"):
        problems.append(
            f"{after['id']}: a REVISED verdict requires criterion_mismatch_flag=true "
            "so the mismatch is surfaced rather than self-fixed (D3)"
        )
    return problems


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_update(args: argparse.Namespace) -> int:
    workspace = find_workspace(Path(args.workspace) if args.workspace else None)
    entry_id = args.disc

    if args.patch:
        patch = read_json(Path(args.patch))
    elif args.set:
        patch = json.loads(args.set)
    else:
        raise die(EXIT_GENERIC, "update needs --patch <file.json> or --set '<json>'")
    if not isinstance(patch, dict):
        raise die(EXIT_SCHEMA, "patch must be a JSON object")

    unfreeze = list(args.unfreeze or [])
    if unfreeze and not args.authz:
        raise die(
            EXIT_FROZEN,
            "--unfreeze requires --authz <AUTHZ_id>: only the human, through a "
            "recorded Authorization, can move a goalpost (Law 3 / Law 9)",
        )

    # The asserted version: --expect-version wins, else a `version` key in the patch.
    asserted = args.expect_version
    if asserted is None and "version" in patch:
        asserted = patch["version"]

    with registry_lock(workspace):
        registry = load_registry(workspace)
        before = get_entry(registry, entry_id)
        prior_version = before.get("version", 1)

        # ---- Layer 2: optimistic version check (04 §1) -----------------------
        # "A patch must assert the version it read." This is what catches the
        # read-modify-write race that flock alone cannot: two agents both read
        # v3, both write, and last-writer silently wins. The assertion is
        # MANDATORY on an existing-entry update, not opt-in — an opt-in race
        # guard guards nothing, because the racing writers are exactly the ones
        # who won't remember to opt in. The version to assert is the one the
        # caller saw in `dispatch.py show`.
        if asserted is None:
            raise die(
                EXIT_VERSION_CONFLICT,
                f"{entry_id} is at version {prior_version} and your patch asserts no "
                "version. Every update must assert the version it read (04 §1): pass "
                f"--expect-version {prior_version} (or include \"version\": {prior_version} "
                "in the patch) after reading the entry with `dispatch.py show`. This is "
                "the guard against the read-modify-write race, so it cannot be skipped.",
            )
        if int(asserted) != int(prior_version):
            raise die(
                EXIT_VERSION_CONFLICT,
                f"{entry_id} is at version {prior_version}, patch asserted "
                f"{asserted}. Another writer moved it between your read and this "
                "write. Re-read the entry and rebuild your patch.",
            )

        if args.authz:
            authz = registry.get("entries", {}).get(args.authz)
            if authz is None:
                raise die(EXIT_NOT_FOUND, f"cited authorization does not exist: {args.authz}")
            if authz.get("type") != "authorization":
                raise die(EXIT_SCHEMA, f"{args.authz} is not an authorization entry")
            if authz.get("revoked"):
                raise die(EXIT_FROZEN, f"{args.authz} has been revoked")

        # ---- Gate: frozen criteria (exit 6) ----------------------------------
        violations = check_frozen(before, patch, unfreeze, entry_id)
        if violations:
            raise die(
                EXIT_FROZEN,
                "refusing to move a frozen goalpost: "
                + ", ".join(violations)
                + "\n  A criterion that looks wrong is flagged (verdict REVISED + "
                "criterion_mismatch_flag), never self-unfrozen. To move it, record an "
                "Authorization and pass --unfreeze <field> --authz <AUTHZ_id>.",
            )

        working = copy.deepcopy(patch)
        working.pop("version", None)  # version is kernel-owned, never patch-owned
        after = deep_merge(before, working)
        after["id"] = entry_id
        after["version"] = prior_version + 1

        if after.get("type") == "task" and after.get("verdict") is not None:
            after["verdict"] = normalize_verdict(after["verdict"])

        # ---- Schema (exit 5) -------------------------------------------------
        schema_name = SCHEMA_FOR_TYPE.get(after.get("type", ""))
        if schema_name:
            validate_against(after, schema_name, entry_id)

        # ---- Gate: dependencies (exit 8) -------------------------------------
        unmet = check_dependencies(registry, after, before)
        if unmet:
            raise die(
                EXIT_DEPENDENCY_NOT_MET,
                f"{entry_id} -> {after.get('status')} but dependencies are not COMPLETED: "
                + ", ".join(unmet),
            )

        # ---- Gate: banking / anti-fabrication (exit 7) -----------------------
        problems = check_banking_gate(workspace, registry, after, before)
        if problems:
            raise die(
                EXIT_ARTIFACT_MISSING,
                "banking gate refused this completion:\n  - " + "\n  - ".join(problems),
            )

        # ---- Honest-verdict invariants (exit 5) ------------------------------
        problems = check_verdict_invariants(after)
        if problems:
            raise die(EXIT_SCHEMA, "verdict invariant violated:\n  - " + "\n  - ".join(problems))

        # ---- Timestamps the kernel owns --------------------------------------
        if after.get("type") == "task":
            if before.get("status") != "IN_PROGRESS" and after.get("status") == "IN_PROGRESS":
                after["started_at"] = after.get("started_at") or now_iso()
            if before.get("status") != TERMINAL_STATUS and after.get("status") == TERMINAL_STATUS:
                after["finished_at"] = after.get("finished_at") or now_iso()

        registry["entries"][entry_id] = after
        save_registry(workspace, registry)

        append_audit(
            workspace,
            entry_id=entry_id,
            action="update",
            patch=patch,
            prior_version=prior_version,
            new_version=after["version"],
            extra=(
                {"unfreeze": unfreeze, "authz": args.authz}
                if unfreeze
                else None
            ),
        )
        if unfreeze:
            # A double record: the mutation above, and an explicit unfreeze marker,
            # so a goalpost move is never a single easily-missed line.
            append_audit(
                workspace,
                entry_id=entry_id,
                action="UNFREEZE",
                patch={"fields": unfreeze},
                prior_version=prior_version,
                new_version=after["version"],
                extra={"authz": args.authz, "unfreeze": True},
            )

    print(f"{entry_id} updated: version {prior_version} -> {after['version']}")
    if after.get("type") == "task":
        print(f"  status={after.get('status')} verdict={after.get('verdict')}")
    return EXIT_OK


def cmd_new(args: argparse.Namespace) -> int:
    workspace = find_workspace(Path(args.workspace) if args.workspace else None)
    entry_type = args.type
    prefix = {v: k for k, v in ID_PREFIXES.items() if k in ("TASK", "CLAIM", "ART", "DEC", "AUTHZ")}
    prefix_for = {
        "task": "TASK",
        "claim": "CLAIM",
        "artifact_ref": "ART",
        "decision": "DEC",
        "authorization": "AUTHZ",
    }
    if entry_type not in prefix_for:
        raise die(EXIT_SCHEMA, f"unknown --type {entry_type}")

    fields: Dict[str, Any] = json.loads(args.fields) if args.fields else {}
    if args.title:
        fields["title"] = args.title
    if args.deps:
        fields["dependencies"] = [d.strip() for d in args.deps.split(",") if d.strip()]
    if args.lens:
        fields["lens"] = args.lens
    if args.model:
        fields["model_hint"] = args.model

    with registry_lock(workspace):
        registry = load_registry(workspace)
        entry_id = args.id or next_id(registry, prefix_for[entry_type])
        if entry_id in registry.get("entries", {}):
            raise die(EXIT_GENERIC, f"{entry_id} already exists")
        entry = blank_entry(entry_type, entry_id, fields)
        validate_against(entry, SCHEMA_FOR_TYPE[entry_type], entry_id)

        # A task whose dependencies are not all COMPLETED starts BLOCKED_ON_DEPS.
        if entry_type == "task" and entry.get("dependencies"):
            entries = registry.get("entries", {})
            if any(entries.get(d, {}).get("status") != "COMPLETED" for d in entry["dependencies"]):
                entry["status"] = "BLOCKED_ON_DEPS"

        registry.setdefault("entries", {})[entry_id] = entry
        save_registry(workspace, registry)
        append_audit(workspace, entry_id=entry_id, action="create", patch=fields, new_version=1)

    print(entry_id)
    return EXIT_OK


def cmd_show(args: argparse.Namespace) -> int:
    """Read-only: takes no lock, per doctrine/04 section 5."""
    workspace = find_workspace(Path(args.workspace) if args.workspace else None)
    registry = load_registry(workspace)
    entry = get_entry(registry, args.disc)
    print(json.dumps(entry, indent=2))
    return EXIT_OK


def cmd_audit_tail(args: argparse.Namespace) -> int:
    workspace = find_workspace(Path(args.workspace) if args.workspace else None)
    log = workspace / "REGISTRY.audit.log"
    if not log.exists():
        print("(no audit log yet)")
        return EXIT_OK
    lines = [ln for ln in log.read_text(encoding="utf-8").splitlines() if ln.strip()]
    for line in lines[-args.n :]:
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            print(line)
            continue
        marker = "  UNFREEZE!" if record.get("unfreeze") else ""
        print(
            f"{record.get('ts')}  {record.get('entry_id'):<12} {record.get('action'):<8} "
            f"v{record.get('prior_version')}->{record.get('new_version')}{marker}"
        )
    return EXIT_OK


# ---------------------------------------------------------------------------
# validate — the integrity gate (doctrine/04 section 4)
# ---------------------------------------------------------------------------


def collect_validation_problems(workspace: Path) -> List[str]:
    registry = load_registry(workspace)
    entries: Dict[str, Any] = registry.get("entries", {})
    problems: List[str] = []

    declared = registry.get("n_entries")
    if declared is not None and declared != len(entries):
        problems.append(f"n_entries={declared} but the registry holds {len(entries)} entries")

    for entry_id, entry in entries.items():
        if not ID_RE.match(entry_id):
            problems.append(f"{entry_id}: malformed entry id")
        if entry.get("id") != entry_id:
            problems.append(f"{entry_id}: entry.id is {entry.get('id')!r}, key mismatch")

        schema_name = SCHEMA_FOR_TYPE.get(entry.get("type", ""))
        if schema_name is None:
            problems.append(f"{entry_id}: unknown type {entry.get('type')!r}")
            continue
        from _core import load_schema, validate_schema  # local import keeps the CLI fast

        for err in validate_schema(entry, load_schema(schema_name), entry_id):
            problems.append(err)

        if entry["type"] == "task":
            for dep in entry.get("dependencies", []) or []:
                if dep not in entries:
                    problems.append(f"{entry_id}: dependency {dep} does not exist")
                elif entries[dep].get("type") != "task":
                    problems.append(f"{entry_id}: dependency {dep} is not a task")

            if entry.get("status") in ("IN_PROGRESS", "COMPLETED"):
                for dep in entry.get("dependencies", []) or []:
                    dep_entry = entries.get(dep, {})
                    if dep_entry.get("status") not in ("COMPLETED", "SUPERSEDED"):
                        problems.append(
                            f"{entry_id} is {entry['status']} but dependency {dep} is "
                            f"{dep_entry.get('status')} (exit 8 condition)"
                        )

            if entry.get("frozen"):
                pre = entry.get("pre_registered", {})
                missing = [f for f in FROZEN_FIELDS if f not in pre]
                if missing:
                    problems.append(
                        f"{entry_id}: frozen but missing pre_registered fields: {missing}"
                    )
                if not pre.get("falsification_criterion"):
                    problems.append(f"{entry_id}: frozen with an empty falsification_criterion")

            if entry.get("status") == "COMPLETED":
                problems.extend(verify_entry_artifacts(workspace, registry, entry))
                if normalize_verdict(entry.get("verdict")) is None:
                    problems.append(f"{entry_id}: COMPLETED with a null verdict")

            if normalize_verdict(entry.get("verdict")) == "STUMPED" and not entry.get(
                "unblock_criterion"
            ):
                problems.append(f"{entry_id}: STUMPED with no unblock_criterion")

        elif entry["type"] == "claim":
            if entry.get("source_task") not in entries:
                problems.append(f"{entry_id}: source_task {entry.get('source_task')} not found")
            for ev in entry.get("evidence", []) or []:
                if ev not in entries:
                    problems.append(f"{entry_id}: evidence {ev} not found")
            if entry.get("load_bearing") and not entry.get("rederive"):
                problems.append(
                    f"{entry_id}: load-bearing claim with no rederive recipe — the cold "
                    "Auditor would have nothing to re-derive it from (Law 4)"
                )

        elif entry["type"] == "artifact_ref":
            err = verify_artifact_ref(workspace, entry)
            if err:
                problems.append(err)

        elif entry["type"] == "decision":
            if entry.get("kind") == "unfreeze" and not entry.get("cites_authz"):
                problems.append(
                    f"{entry_id}: an unfreeze Decision must cite an Authorization (Law 9)"
                )
            cited = entry.get("cites_authz")
            if cited and cited not in entries:
                problems.append(f"{entry_id}: cites_authz {cited} not found")

    # Orphan IN_PROGRESS: a task in flight whose wave has no live Wave General.
    # We cannot see processes from here, so we report them for the babysit loop's
    # classifier, which cross-checks liveness (doctrine/07 section 2).
    orphans = [
        e["id"]
        for e in entries.values()
        if e.get("type") == "task" and e.get("status") == "IN_PROGRESS"
    ]
    if len(orphans) > 1:
        problems.append(
            f"more than one task IN_PROGRESS at once: {orphans} — violates the "
            "serial-banking invariant (at most one task unbanked, doctrine/03 section 5)"
        )

    problems.extend(collect_resume_problems(workspace))

    return problems


# The five interruption classes a RESUME directive must declare (doctrine/07 §6).
RESUME_CLASSES = {
    "interrupted",
    "halted",  # halted-<reason>: the reason is a free suffix, the stem is fixed
    "stalled-nothing-banked",
    "stalled-partial",
    "awaiting-bg",
}


def collect_resume_problems(workspace: Path) -> List[str]:
    """Validate every WAVE_*_RESUME.md (doctrine/07 §6).

    "A resume that doesn't classify the interruption is rejected by dispatch.py
    validate." A vague resume directive is precisely what invites a relaunched
    Wave General to fabricate — the classification is what tells it whether to
    clean-restart, checkpoint-resume, or consume a background compute. So a
    directive that omits or mis-declares its Interruption class is an integrity
    failure, not a style nit.
    """
    problems: List[str] = []
    halt_dir = workspace / "handoffs" / "halt_requests"
    if not halt_dir.exists():
        return problems

    for resume in sorted(halt_dir.glob("WAVE_*_RESUME.md")):
        text = resume.read_text(encoding="utf-8")
        match = re.search(r"^##\s*Interruption class:\s*(.+?)\s*$", text, re.MULTILINE)
        if not match:
            problems.append(
                f"{resume.name}: no '## Interruption class:' line. A resume directive "
                "that does not classify its interruption is rejected (doctrine/07 §6) — "
                "the class is what tells the relaunched Wave General whether to "
                "clean-restart, checkpoint-resume, or consume a background compute."
            )
            continue
        # The line may list options with '|' in the template; a real directive
        # names exactly one. Take the first token stem before any '-<reason>'.
        declared = match.group(1).strip().lower()
        if "|" in declared or declared.startswith("<"):
            problems.append(
                f"{resume.name}: the Interruption class is still the template "
                f"placeholder ({match.group(1).strip()!r}). Pick exactly one of "
                + ", ".join(sorted(RESUME_CLASSES)) + "."
            )
            continue
        stem = declared.split("-")[0] if declared.startswith("halted") else declared
        if declared not in RESUME_CLASSES and stem != "halted":
            problems.append(
                f"{resume.name}: Interruption class {match.group(1).strip()!r} is not "
                "one of " + ", ".join(sorted(RESUME_CLASSES)) + " (doctrine/07 §6)."
            )

    return problems


def cmd_validate(args: argparse.Namespace) -> int:
    workspace = find_workspace(Path(args.workspace) if args.workspace else None)
    problems = collect_validation_problems(workspace)

    if args.json:
        print(json.dumps({"clean": not problems, "problems": problems}, indent=2))
    else:
        if not problems:
            print("validate: clean")
        else:
            print(f"validate: {len(problems)} problem(s)")
            print(hr())
            for problem in problems:
                print(f"  - {problem}")
    return EXIT_OK if not problems else EXIT_SCHEMA


# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dispatch.py", description="The atomic REGISTRY merger."
    )
    parser.add_argument("--workspace", help="mission workspace root (default: discover upward)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_update = sub.add_parser("update", help="apply an atomic, version-checked patch")
    p_update.add_argument("--disc", required=True, help="entry id (any type; historical flag name)")
    p_update.add_argument("--patch", help="path to a JSON patch file")
    p_update.add_argument("--set", help="inline JSON patch")
    p_update.add_argument("--expect-version", type=int, help="assert the version you read")
    p_update.add_argument(
        "--unfreeze",
        action="append",
        help="frozen field to unfreeze, e.g. TASK_0009.falsification_criterion (repeatable)",
    )
    p_update.add_argument("--authz", help="the AUTHZ_ id authorizing an unfreeze")
    p_update.set_defaults(func=cmd_update)

    p_new = sub.add_parser("new", help="create an entry")
    p_new.add_argument(
        "--type",
        required=True,
        choices=["task", "claim", "artifact_ref", "decision", "authorization"],
    )
    p_new.add_argument("--id", help="explicit id (default: next free)")
    p_new.add_argument("--title")
    p_new.add_argument("--deps", help="comma-separated dependency ids")
    p_new.add_argument("--lens")
    p_new.add_argument("--model", help="model_hint: most-capable | capable | cheap")
    p_new.add_argument("--fields", help="inline JSON of additional fields")
    p_new.set_defaults(func=cmd_new)

    p_show = sub.add_parser("show", help="pretty-print one entry (read-only, no lock)")
    p_show.add_argument("--disc", required=True)
    p_show.set_defaults(func=cmd_show)

    p_validate = sub.add_parser("validate", help="full cross-entry integrity gate")
    p_validate.add_argument("--json", action="store_true")
    p_validate.set_defaults(func=cmd_validate)

    p_tail = sub.add_parser("audit-tail", help="the last N mutations")
    p_tail.add_argument("n", nargs="?", type=int, default=20)
    p_tail.set_defaults(func=cmd_audit_tail)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    run_cli(main)
