#!/usr/bin/env python3
"""log_artifact.py — persist an artifact reference and feed the Curiosity pool.

Two writes, one command:
  1. An ART_ entry in the REGISTRY, with the file's real SHA-256. This is what
     the banking gate re-hashes at completion time (exit 7).
  2. An append to artifacts.jsonl — the Curiosity Protocol pool.

Record ALL, never pre-gate (doctrine/08 section 4). Boring-looking artifacts are
exactly the case the protocol exists for, and uniform logging is the defense
against fabrication-by-selection. `promotion_status` always starts at LOGGED;
pre-judgment belongs in `provenance`, never in a status that would exclude an
artifact from the later FDR-gated promotion pass.

  log_artifact.py --task TASK_0031 --path reports/TASK_0031_pytest.log \\
      --kind measurement --lens engineering --context "config suite, post-refactor"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _core import (  # noqa: E402
    EXIT_NOT_FOUND,
    EXIT_OK,
    append_audit,
    append_line,
    artifacts_pool,
    die,
    find_workspace,
    get_entry,
    load_registry,
    next_id,
    now_iso,
    registry_lock,
    run_cli,
    save_registry,
    sha256_file,
    validate_against,
)


def main() -> int:
    parser = argparse.ArgumentParser(prog="log_artifact.py")
    parser.add_argument("--workspace")
    parser.add_argument("--task", required=True, help="the producing task id")
    parser.add_argument("--path", required=True, help="workspace-relative path to the artifact")
    parser.add_argument(
        "--kind",
        default="artifact",
        choices=[
            "measurement",
            "relationship",
            "null-result",
            "anomaly",
            "regression",
            "smell",
            "scaling",
            "infeasibility",
            "novel-form",
            "artifact",
        ],
    )
    parser.add_argument("--context", help="what this is, in one line")
    parser.add_argument("--lens", help="research | engineering | ops | writing | generic")
    parser.add_argument(
        "--provenance",
        default="real",
        choices=["real", "derived", "synthetic", "canary", "textbook"],
        help="what kind of thing this is — NOT a pre-judgment of its worth",
    )
    parser.add_argument("--value", help="JSON scalar or object, if this artifact carries a value")
    parser.add_argument("--note", help="candidate_note: why this might matter later")
    parser.add_argument("--reverify", help="the recipe that reproduces this artifact")
    parser.add_argument("--manifest", help="background-compute manifest, if any")
    parser.add_argument("--report", action="store_true", help="also set the task's report_path")
    args = parser.parse_args()

    workspace = find_workspace(Path(args.workspace) if args.workspace else None)
    target = (workspace / args.path).resolve()
    if not target.exists():
        raise die(
            EXIT_NOT_FOUND,
            f"nothing at {args.path}. An artifact is logged AFTER it is written — "
            "a hash asserted in advance is not evidence (Law 1).",
        )
    try:
        rel = str(target.relative_to(workspace))
    except ValueError as exc:
        raise die(EXIT_NOT_FOUND, f"{args.path} is outside the workspace") from exc

    digest = sha256_file(target)
    size = target.stat().st_size

    with registry_lock(workspace):
        registry = load_registry(workspace)
        task = get_entry(registry, args.task)

        art_id = next_id(registry, "ART")
        art = {
            "id": art_id,
            "type": "artifact_ref",
            "path": rel,
            "sha256": digest,
            "bytes": size,
            "manifest": args.manifest,
            "produced_by": args.task,
            "logged_at": now_iso(),
            "version": 1,
        }
        validate_against(art, "artifact_ref", art_id)
        registry["entries"][art_id] = art

        artifacts = task.setdefault("artifacts", [])
        if art_id not in artifacts:
            artifacts.append(art_id)
        if args.report:
            task["report_path"] = rel
            task["report_sha256"] = digest
        task["version"] = task.get("version", 1) + 1

        save_registry(workspace, registry)
        append_audit(
            workspace,
            entry_id=art_id,
            action="log_artifact",
            patch={"path": rel, "sha256": digest, "produced_by": args.task},
            new_version=1,
        )
        wave = task.get("wave")

    record = {
        "artifact_id": art_id,
        "value": json.loads(args.value) if args.value else None,
        "kind": args.kind,
        "context": args.context,
        "source_task": args.task,
        "source_wave": wave,
        "lens": args.lens,
        "provenance": args.provenance,
        "promotion_status": "LOGGED",
        "candidate_note": args.note,
        "p_value": None,
        "fdr_q": None,
        "reverify_recipe": args.reverify,
        "path": rel,
        "sha256": digest,
        "ts_iso": now_iso(),
    }
    validate_against(record, "artifact_log", f"artifacts.jsonl line for {art_id}")
    append_line(artifacts_pool(workspace), json.dumps(record))

    print(f"{art_id}  {rel}  sha256={digest[:12]}…  ({size} bytes)")
    if args.report:
        print(f"  set as {args.task}.report_path")
    return EXIT_OK


if __name__ == "__main__":
    run_cli(main)
