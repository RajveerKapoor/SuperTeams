#!/usr/bin/env python3
"""harvest.py — the FDR-gated promotion pass. The ONLY thing that may PROMOTE.

The generalization of the predecessor's "Wave 4b BH harvest". Three properties
make it trustworthy, and all three are structural rather than remembered:

1. **It runs across the WHOLE pool, once, later.** Never inside the wave that
   produced the artifacts. A large pool is guaranteed to contain coincidences;
   promoting per-wave means promoting those coincidences one at a time, each
   looking convincing on its own because you never see the other ten thousand.

2. **It is the only writer of `promotion_status: PROMOTED`.** A lens may only
   FLAG. `--check-no-pregating` proves nobody skipped the queue.

3. **It rewrites the pool atomically** and appends to the audit log, so a harvest
   is as reviewable as any other mutation.

  harvest.py --dry-run                 # what would be promoted, and why
  harvest.py --q 0.10 --apply          # promote, writing q-values back
  harvest.py --check-no-pregating      # the invariant test
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _core import (  # noqa: E402
    EXIT_GENERIC,
    EXIT_OK,
    EXIT_SCHEMA,
    append_audit,
    artifacts_pool,
    atomic_write_text,
    find_workspace,
    hr,
    now_iso,
    run_cli,
    validate_against,
)

try:
    from lenses import Candidate, benjamini_hochberg, bh_q_values, sweep_pool
except ImportError:  # the mission's pinned copy sits beside runners/
    sys.path.insert(0, str(Path(__file__).resolve().parent / "lenses"))
    from lenses import Candidate, benjamini_hochberg, bh_q_values, sweep_pool  # type: ignore

DEFAULT_Q = 0.10


def read_pool(workspace: Path) -> List[Dict[str, Any]]:
    path = artifacts_pool(workspace)
    if not path.exists():
        return []
    records: List[Dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise SystemExit(
                f"artifacts.jsonl line {line_no} is not valid JSON: {exc}. "
                "The pool is append-only and machine-written; a malformed line "
                "means something wrote to it by hand. Fix it before harvesting."
            )
    return records


def write_pool(workspace: Path, records: List[Dict[str, Any]]) -> None:
    for record in records:
        validate_against(record, "artifact_log", record.get("artifact_id", "?"))
    body = "\n".join(json.dumps(r) for r in records)
    atomic_write_text(artifacts_pool(workspace), body + ("\n" if body else ""))


def check_no_pregating(records: List[Dict[str, Any]]) -> List[str]:
    """The invariant: nothing was promoted or rejected outside a harvest.

    A PROMOTED record with no q-value was promoted by something that is not this
    script — which means a finding skipped the multiple-comparison gate.
    """
    problems: List[str] = []
    for record in records:
        status = record.get("promotion_status")
        artifact_id = record.get("artifact_id", "?")
        if status == "PROMOTED" and record.get("fdr_q") is None:
            problems.append(
                f"{artifact_id}: PROMOTED with no fdr_q — promoted outside the "
                "harvest, i.e. it never faced the multiple-comparison gate"
            )
        if status == "REJECTED" and record.get("fdr_q") is None:
            problems.append(
                f"{artifact_id}: REJECTED with no fdr_q — an artifact was excluded "
                "from later assessment by a pre-judgment. Use `provenance` for what "
                "kind of thing it is; never a status that removes it from the pool."
            )
        if status not in ("LOGGED", "FLAGGED", "PROMOTED", "REJECTED"):
            problems.append(f"{artifact_id}: unknown promotion_status {status!r}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(prog="harvest.py")
    parser.add_argument("--workspace")
    parser.add_argument("--q", type=float, default=DEFAULT_Q, help="target FDR (default 0.10)")
    parser.add_argument("--apply", action="store_true", help="write results back to the pool")
    parser.add_argument("--dry-run", action="store_true", help="report only (the default)")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--check-no-pregating",
        action="store_true",
        help="assert nobody promoted or rejected outside a harvest, then exit",
    )
    args = parser.parse_args()

    workspace = find_workspace(Path(args.workspace) if args.workspace else None)
    records = read_pool(workspace)

    if args.check_no_pregating:
        problems = check_no_pregating(records)
        if problems:
            print(f"pre-gating check: {len(problems)} violation(s)")
            print(hr())
            for problem in problems:
                print(f"  - {problem}")
            return EXIT_SCHEMA
        print(f"pre-gating check: clean ({len(records)} artifacts in the pool)")
        return EXIT_OK

    if not records:
        print("the pool is empty — nothing to harvest")
        return EXIT_OK

    by_id = {r.get("artifact_id"): r for r in records}
    candidates: List[Candidate] = sweep_pool(records)

    # ---- the FDR gate, over every candidate that carries a p-value ----------
    scored = [c for c in candidates if c.p_value is not None]
    unscored = [c for c in candidates if c.p_value is None]

    promoted_ids: set = set()
    q_by_id: Dict[str, float] = {}
    if scored:
        p_values = [c.p_value for c in scored]
        rejections = benjamini_hochberg(p_values, args.q)  # type: ignore[arg-type]
        q_values = bh_q_values(p_values)  # type: ignore[arg-type]
        for candidate, reject, q_value in zip(scored, rejections, q_values):
            previous = q_by_id.get(candidate.artifact_id)
            if previous is None or q_value < previous:
                q_by_id[candidate.artifact_id] = q_value
            if reject:
                promoted_ids.add(candidate.artifact_id)

    flagged_ids = {c.artifact_id for c in candidates} - promoted_ids

    # ---- apply --------------------------------------------------------------
    notes: Dict[str, List[str]] = {}
    for candidate in candidates:
        notes.setdefault(candidate.artifact_id, []).append(candidate.note())

    changed = 0
    if args.apply:
        for artifact_id, record in by_id.items():
            if artifact_id in promoted_ids:
                new_status = "PROMOTED"
            elif artifact_id in flagged_ids:
                new_status = "FLAGGED"
            else:
                # Untouched by any lens stays LOGGED. It is NOT rejected: an
                # artifact no lens happened to fire on is an artifact no lens
                # happened to fire on, not a negative result.
                continue
            if record.get("promotion_status") != new_status or artifact_id in q_by_id:
                changed += 1
            record["promotion_status"] = new_status
            if artifact_id in q_by_id:
                record["fdr_q"] = round(q_by_id[artifact_id], 6)
            joined = "; ".join(notes.get(artifact_id, []))
            record["candidate_note"] = joined[:2000] if joined else record.get("candidate_note")

        write_pool(workspace, records)
        append_audit(
            workspace,
            entry_id="HARVEST",
            action="harvest",
            patch={
                "q": args.q,
                "pool": len(records),
                "candidates": len(candidates),
                "promoted": sorted(promoted_ids),
                "at": now_iso(),
            },
        )

    # ---- report -------------------------------------------------------------
    payload = {
        "pool": len(records),
        "candidates": len(candidates),
        "with_p_value": len(scored),
        "without_p_value": len(unscored),
        "q": args.q,
        "promoted": sorted(promoted_ids),
        "flagged": len(flagged_ids),
        "applied": bool(args.apply),
        "records_changed": changed,
    }

    if args.json:
        print(json.dumps(payload, indent=2))
        return EXIT_OK

    print(hr())
    print(f"  pool: {len(records)} artifacts   candidates: {len(candidates)}   q={args.q}")
    print(f"  with a p-value: {len(scored)}   qualitative only: {len(unscored)}")
    print(hr())
    if promoted_ids:
        print(f"  PROMOTED ({len(promoted_ids)}) — survived BH at q={args.q}:")
        for artifact_id in sorted(promoted_ids):
            q_value = q_by_id.get(artifact_id)
            print(f"    {artifact_id}  q={q_value:.4g}" if q_value else f"    {artifact_id}")
            for note in notes.get(artifact_id, [])[:3]:
                print(f"        {note}")
    else:
        print("  PROMOTED: none survived the FDR gate.")
        print("  That is a result, not a failure. A pool this size contains")
        print("  coincidences by arithmetic; promoting none of them is the gate working.")
    print(hr())
    print(f"  FLAGGED (kept for the next harvest, not promoted): {len(flagged_ids)}")
    if not args.apply:
        print("\n  dry run — nothing written. Re-run with --apply to persist.")
    return EXIT_OK


if __name__ == "__main__":
    run_cli(main)
