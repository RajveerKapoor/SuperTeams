#!/usr/bin/env python3
"""close_wave.py — the completion gate. The checker is never the doer.

A wave reaches COMPLETE only if a cold Auditor wrote a PASS into
handoffs/orchestrator/WAVE_<id>_AUDIT.md and that PASS is timestamped BEFORE the
close attempt (doctrine/05 section 2, doctrine/06 D1+D2).

The timestamp ordering is not pedantry: the predecessor's Wave 0a drafted its
SUMMARY eleven minutes before the audit that was supposed to justify it. The
substance was fine; the ordering was a lie waiting to happen. Here it is
unskippable.

  close_wave.py 2k
  close_wave.py 2k --dry-run
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _core import (  # noqa: E402
    EXIT_GENERIC,
    EXIT_OK,
    EXIT_SCHEMA,
    append_audit,
    atomic_write_json,
    die,
    find_workspace,
    hr,
    load_registry,
    now_iso,
    parse_iso,
    read_json,
    run_cli,
    validate_against,
    wave_paths,
)

VERDICT_RE = re.compile(
    r"^\s*(?:#+\s*)?(?:\*\*)?verdict(?:\*\*)?\s*[:=]\s*(?:\*\*)?"
    r"(PASS_WITH_NOTES|PASS|FAIL)(?:\*\*)?",
    re.IGNORECASE | re.MULTILINE,
)
AUDITED_AT_RE = re.compile(
    r"^\s*(?:\*\*)?audited[_ ]at(?:\*\*)?\s*[:=]\s*(?:\*\*)?([0-9T:\-\+Z\. ]+)",
    re.IGNORECASE | re.MULTILINE,
)
# NB: the whitespace after the colon is [ \t]*, NOT \s* — \s* would greedily
# cross the newline and capture the FOLLOWING line as the auditor name, so an
# empty "Auditor:" would silently inherit the "Audited_at:" value and defeat the
# auditor-identity gate. Horizontal whitespace only.
AUDITOR_RE = re.compile(
    r"^[ \t]*(?:\*\*)?auditor(?:\*\*)?[ \t]*[:=][ \t]*(?:\*\*)?([^\n*]+)",
    re.IGNORECASE | re.MULTILINE,
)


def parse_audit(path: Path) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Return (verdict, audited_at, auditor) from an AUDIT.md."""
    text = path.read_text(encoding="utf-8")
    verdict_match = VERDICT_RE.search(text)
    at_match = AUDITED_AT_RE.search(text)
    who_match = AUDITOR_RE.search(text)
    return (
        verdict_match.group(1).upper() if verdict_match else None,
        at_match.group(1).strip() if at_match else None,
        who_match.group(1).strip() if who_match else None,
    )


def main() -> int:
    parser = argparse.ArgumentParser(prog="close_wave.py")
    parser.add_argument("wave_id")
    parser.add_argument("--workspace")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    workspace = find_workspace(Path(args.workspace) if args.workspace else None)
    paths = wave_paths(workspace, args.wave_id)
    registry = load_registry(workspace)
    problems: List[str] = []

    # ---- 1. every task in scope is non-pending -----------------------------
    wave_tasks = [
        e
        for e in registry.get("entries", {}).values()
        if e.get("type") == "task" and e.get("wave") == args.wave_id
    ]
    if not wave_tasks:
        problems.append(f"no tasks are assigned to wave {args.wave_id}")
    unfinished = [
        e["id"]
        for e in wave_tasks
        if e.get("status") not in ("COMPLETED", "SUPERSEDED")
    ]
    if unfinished:
        problems.append(
            "these tasks are still open: " + ", ".join(sorted(unfinished))
            + " — a wave cannot close over an unfinished task. An incomplete wave "
            "that closes quietly is worse than a crash (Face-2 failure)."
        )

    # ---- 2. the audit gate -------------------------------------------------
    audit_path = paths["audit"]
    audit_verdict = None
    audited_at_raw = None
    auditor = None
    if not audit_path.exists():
        problems.append(
            f"no independent audit at {audit_path.relative_to(workspace)}. "
            "The doer may never issue its own completion verdict (Law 4). Spawn a "
            "cold Auditor session."
        )
    else:
        audit_verdict, audited_at_raw, auditor = parse_audit(audit_path)

        # ---- the separation the system never relaxes (D1, Law 4, 05 §5) ------
        # "The audit verdict is the one thing the doer may never issue." The
        # cold-Auditor role is only a real separation if the close gate refuses
        # a verdict signed by the session that ran the wave. Without this check
        # a Wave General can PASS its own wave — which was true of this build
        # until an adversarial audit closed a wave with `Auditor: <the doer>`.
        doer_session = read_json(paths["status"], {}).get("wavegen_session")
        normalized_auditor = (auditor or "").strip()
        if not normalized_auditor:
            problems.append(
                f"{audit_path.name} has no 'Auditor: <session>' line. The auditor must "
                "be named so the gate can confirm it was NOT the doer — an anonymous "
                "audit cannot be checked for independence (D1, Law 4)."
            )
        elif doer_session and normalized_auditor == str(doer_session).strip():
            problems.append(
                f"the audit was signed by {normalized_auditor}, which is the session "
                f"that RAN wave {args.wave_id} (wavegen_session). The doer may never "
                "audit its own wave — the checker is never the doer (D1, Law 4). Spawn "
                "a cold Auditor session with no memory of the doing."
            )

        if audit_verdict is None:
            problems.append(
                f"{audit_path.name} has no parseable verdict line. Expected a line like "
                "'Verdict: PASS' (PASS | PASS_WITH_NOTES | FAIL)."
            )
        elif audit_verdict == "FAIL":
            problems.append(
                "the independent audit FAILED. The wave does not close. The failing "
                "claim reverts to UNAUDITED and the Orchestrator is pinged — the doer "
                "never grades its own redo."
            )
        if audited_at_raw is None:
            problems.append(
                f"{audit_path.name} has no 'Audited_at: <iso8601>' line. The close gate "
                "compares that timestamp to the close attempt (D2)."
            )
        else:
            audited_at = parse_iso(audited_at_raw)
            if audited_at is None:
                problems.append(f"could not parse Audited_at: {audited_at_raw!r}")
            else:
                from datetime import datetime, timezone

                if audited_at > datetime.now(timezone.utc):
                    problems.append(
                        f"the audit claims to have happened in the future "
                        f"({audited_at_raw}). Refusing to close."
                    )

    # ---- 3. registry integrity --------------------------------------------
    from dispatch import collect_validation_problems

    integrity = collect_validation_problems(workspace)
    if integrity:
        problems.append(
            f"dispatch.py validate is dirty ({len(integrity)} problem(s)); "
            "a wave never closes over a dirty registry. Run `dispatch.py validate`."
        )

    # ---- 4. summary exists -------------------------------------------------
    if not paths["summary"].exists():
        problems.append(
            f"no {paths['summary'].name}. It is the Orchestrator's ONLY window into "
            "this wave (<=2000 words); without it the wave has not reported."
        )

    if problems:
        print(f"close_wave {args.wave_id}: REFUSED")
        print(hr())
        for problem in problems:
            print(f"  - {problem}")
        return EXIT_GENERIC

    if args.dry_run:
        print(f"close_wave {args.wave_id}: gate would PASS (dry run, nothing written)")
        print(f"  audit verdict {audit_verdict} by {auditor or 'unnamed auditor'} at {audited_at_raw}")
        return EXIT_OK

    status = read_json(paths["status"])
    status["state"] = "COMPLETE"
    status["audit_state"] = audit_verdict
    status["final_audit_at"] = audited_at_raw
    status["summary_path"] = str(paths["summary"].relative_to(workspace))
    status["task_in_progress"] = None
    status["updated_at"] = now_iso()
    status["next_action"] = "orchestrator: ingest SUMMARY + AUDIT, advance the queue"
    validate_against(status, "status", str(paths["status"]))
    atomic_write_json(paths["status"], status)

    append_audit(
        workspace,
        entry_id=f"WAVE_{args.wave_id}",
        action="close_wave",
        patch={
            "audit_verdict": audit_verdict,
            "audited_at": audited_at_raw,
            "auditor": auditor,
        },
    )

    print(f"close_wave {args.wave_id}: COMPLETE")
    print(f"  audit {audit_verdict} by {auditor or 'unnamed auditor'} at {audited_at_raw}")
    print(f"  tasks: {status['tasks_done']}/{status['tasks_total']}")
    print("  next: the Orchestrator ingests SUMMARY + AUDIT only — never the FULL_RECORD.")
    return EXIT_OK


if __name__ == "__main__":
    run_cli(main)
