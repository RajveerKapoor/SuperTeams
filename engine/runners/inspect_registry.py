#!/usr/bin/env python3
"""inspect_registry.py — read-only views. Never takes the lock.

  inspect_registry.py --status PENDING
  inspect_registry.py --stumps        # every blocked task + what would unblock it
  inspect_registry.py --unaudited     # load-bearing claims not yet PASS
  inspect_registry.py --promotions    # Curiosity pool candidates awaiting the FDR pass
  inspect_registry.py --decisions
  inspect_registry.py --summary
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _core import (  # noqa: E402
    EXIT_OK,
    TASK_STATUSES,
    find_workspace,
    hr,
    iter_artifacts,
    kv,
    load_registry,
    run_cli,
    truncate,
)


def main() -> int:
    parser = argparse.ArgumentParser(prog="inspect_registry.py")
    parser.add_argument("--workspace")
    parser.add_argument("--status", choices=TASK_STATUSES)
    parser.add_argument("--verdict")
    parser.add_argument("--stumps", action="store_true")
    parser.add_argument("--unaudited", action="store_true")
    parser.add_argument("--promotions", action="store_true")
    parser.add_argument("--decisions", action="store_true")
    parser.add_argument("--authz", action="store_true")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()

    workspace = find_workspace(Path(args.workspace) if args.workspace else None)
    registry = load_registry(workspace)
    entries = registry.get("entries", {})
    tasks = {k: v for k, v in entries.items() if v.get("type") == "task"}
    any_view = False

    if args.summary or not any(
        [
            args.status,
            args.verdict,
            args.stumps,
            args.unaudited,
            args.promotions,
            args.decisions,
            args.authz,
        ]
    ):
        any_view = True
        print(f"mission: {registry.get('mission')}   mode: {registry.get('mode')}")
        print(kv("entries", len(entries)))
        print(kv("frozen at", registry.get("pre_registered_frozen_at") or "(not frozen)"))
        status_counts = Counter(t.get("status") for t in tasks.values())
        verdict_counts = Counter(t.get("verdict") for t in tasks.values() if t.get("verdict"))
        print(hr())
        print("  task status:")
        for status, count in sorted(status_counts.items()):
            print(kv(f"  {status}", count))
        if verdict_counts:
            print("  verdicts:")
            for verdict, count in sorted(verdict_counts.items()):
                print(kv(f"  {verdict}", count))
        type_counts = Counter(e.get("type") for e in entries.values())
        print("  entry types:")
        for etype, count in sorted(type_counts.items()):
            print(kv(f"  {etype}", count))

    if args.status:
        any_view = True
        print(f"\ntasks with status {args.status}")
        print(hr())
        for entry_id, entry in sorted(tasks.items()):
            if entry.get("status") == args.status:
                print(f"  {entry_id}  {truncate(entry.get('title', ''), 60)}")

    if args.verdict:
        any_view = True
        want = args.verdict.upper()
        print(f"\ntasks with verdict {want}")
        print(hr())
        for entry_id, entry in sorted(tasks.items()):
            if (entry.get("verdict") or "").upper() == want:
                print(f"  {entry_id}  {truncate(entry.get('title', ''), 60)}")

    if args.stumps:
        any_view = True
        print("\nSTUMPED tasks — each with the one thing that would unblock it")
        print(hr())
        found = False
        for entry_id, entry in sorted(tasks.items()):
            if entry.get("verdict") == "STUMPED":
                found = True
                print(f"  {entry_id}  {truncate(entry.get('title', ''), 58)}")
                print(f"      unblock: {entry.get('unblock_criterion')}")
        if not found:
            print("  (none)")

    if args.unaudited:
        any_view = True
        print("\nload-bearing claims not yet PASS")
        print(hr())
        found = False
        for entry_id, entry in sorted(entries.items()):
            if (
                entry.get("type") == "claim"
                and entry.get("load_bearing")
                and entry.get("audit_state") != "PASS"
            ):
                found = True
                print(
                    f"  {entry_id}  [{entry.get('audit_state')}]  "
                    f"{truncate(entry.get('statement', ''), 50)}"
                )
        if not found:
            print("  (none — every load-bearing claim has an independent PASS)")

    if args.promotions:
        any_view = True
        print("\nCuriosity pool — candidates awaiting the FDR-gated promotion pass")
        print(hr())
        counts = Counter()
        flagged = []
        for record in iter_artifacts(workspace):
            counts[record.get("promotion_status", "?")] += 1
            if record.get("promotion_status") == "FLAGGED":
                flagged.append(record)
        for status, count in sorted(counts.items()):
            print(kv(f"  {status}", count))
        if flagged:
            print("\n  flagged candidates:")
            for record in flagged[:40]:
                print(
                    f"    {record.get('artifact_id')}  [{record.get('kind')}]  "
                    f"{truncate(record.get('candidate_note') or record.get('context') or '', 48)}"
                )
        print(
            "\n  Nothing is promoted inside the wave that found it. Promotion is a later,\n"
            "  batched pass under multiple-comparison discipline (doctrine/08 section 4)."
        )

    if args.decisions:
        any_view = True
        print("\ndecisions")
        print(hr())
        for entry_id, entry in sorted(entries.items()):
            if entry.get("type") == "decision":
                cite = f"  cites {entry['cites_authz']}" if entry.get("cites_authz") else ""
                print(f"  {entry_id}  [{entry.get('kind') or 'other'}]{cite}")
                print(f"      {truncate(entry.get('decision', ''), 68)}")
                print(f"      why: {truncate(entry.get('rationale', ''), 62)}")

    if args.authz:
        any_view = True
        print("\nauthorizations (every human word, on disk — Law 9)")
        print(hr())
        for entry_id, entry in sorted(entries.items()):
            if entry.get("type") == "authorization":
                mark = " REVOKED" if entry.get("revoked") else ""
                print(f"  {entry_id}  {entry.get('granted_at')}{mark}")
                print(f"      grants: {truncate(entry.get('grants', ''), 62)}")
                print(f"      scope:  {truncate(entry.get('scope', ''), 62)}")
                print(f"      via:    {entry.get('channel')}")

    return EXIT_OK if any_view else EXIT_OK


if __name__ == "__main__":
    run_cli(main)
