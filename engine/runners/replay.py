#!/usr/bin/env python3
"""replay.py — the ultimate fabrication detector.

Re-derive any load-bearing claim by re-running its recorded recipe and checking
that its evidence still hashes to what the registry recorded. A shortcut or a
fabrication changes the hash and fails replay (doctrine/08 section 1).

This is also the trust primitive for the human: returning after a week, you can
independently reproduce anything the system claimed, rather than taking its word
(doctrine/09 section 7).

  replay.py CLAIM_0031
  replay.py CLAIM_0031 --no-exec      # hash check only, do not run the recipe
  replay.py --all                     # every load-bearing claim
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _core import (  # noqa: E402
    EXIT_GENERIC,
    EXIT_OK,
    die,
    find_workspace,
    hr,
    load_registry,
    run_cli,
    truncate,
    verify_artifact_ref,
)


def replay_claim(
    workspace: Path, registry: Dict[str, Any], claim: Dict[str, Any], execute: bool, timeout: int
) -> Tuple[bool, List[str]]:
    notes: List[str] = []
    ok = True
    entries = registry.get("entries", {})

    if not claim.get("evidence"):
        notes.append("no evidence artifacts referenced")
        ok = False
    for art_id in claim.get("evidence", []) or []:
        art = entries.get(art_id)
        if art is None:
            notes.append(f"evidence {art_id} does not exist in the registry")
            ok = False
            continue
        err = verify_artifact_ref(workspace, art)
        if err:
            notes.append(f"HASH FAIL: {err}")
            ok = False
        else:
            notes.append(f"hash ok: {art_id} -> {art['path']}")

    recipe = claim.get("rederive")
    if not recipe:
        notes.append("no rederive recipe — this claim cannot be independently re-derived")
        ok = False
    elif execute:
        proc = subprocess.run(
            recipe,
            shell=True,
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if proc.returncode == 0:
            notes.append(f"recipe exited 0: {truncate(recipe, 70)}")
        else:
            notes.append(f"RECIPE FAILED (exit {proc.returncode}): {truncate(recipe, 60)}")
            tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-5:]
            for line in tail:
                notes.append(f"    | {line}")
            ok = False
    else:
        notes.append(f"recipe not run (--no-exec): {truncate(recipe, 66)}")

    return ok, notes


def main() -> int:
    parser = argparse.ArgumentParser(prog="replay.py")
    parser.add_argument("claim", nargs="?", help="CLAIM_ id")
    parser.add_argument("--workspace")
    parser.add_argument("--all", action="store_true", help="replay every load-bearing claim")
    parser.add_argument("--no-exec", action="store_true", help="hash check only")
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()

    workspace = find_workspace(Path(args.workspace) if args.workspace else None)
    registry = load_registry(workspace)
    entries = registry.get("entries", {})

    if args.all:
        claims = [
            e for e in entries.values() if e.get("type") == "claim" and e.get("load_bearing")
        ]
    elif args.claim:
        claim = entries.get(args.claim)
        if claim is None:
            raise die(EXIT_GENERIC, f"no such entry: {args.claim}")
        if claim.get("type") != "claim":
            raise die(EXIT_GENERIC, f"{args.claim} is not a claim")
        claims = [claim]
    else:
        raise die(EXIT_GENERIC, "give a CLAIM_ id or --all")

    if not claims:
        print("no load-bearing claims to replay")
        return EXIT_OK

    failures = 0
    for claim in sorted(claims, key=lambda c: c["id"]):
        ok, notes = replay_claim(workspace, registry, claim, not args.no_exec, args.timeout)
        mark = "PASS" if ok else "FAIL"
        print(f"{mark}  {claim['id']}  {truncate(claim.get('statement', ''), 56)}")
        for note in notes:
            print(f"      {note}")
        print(hr())
        if not ok:
            failures += 1

    print(f"replay: {len(claims) - failures}/{len(claims)} re-derived")
    return EXIT_OK if failures == 0 else EXIT_GENERIC


if __name__ == "__main__":
    run_cli(main)
