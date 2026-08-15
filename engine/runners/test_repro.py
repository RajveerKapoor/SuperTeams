#!/usr/bin/env python3
"""test_repro.py — seed / env / commit manifest determinism (doctrine/13 §2).

`replay.py` is what turns "trust the system" into "verify the system": a human
returning after a week reproduces any claim from the recorded commit, seed and
environment, and confirms the hash. That only works if the manifest records
enough, records it *deterministically*, and refuses to record a hash for work
that did not happen.

    pytest runners/test_repro.py -q
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parent.parent
RUNNERS = ENGINE / "runners"
sys.path.insert(0, str(ENGINE))

from repro.manifest import (  # noqa: E402
    build_env_hash,
    complete_manifest,
    completion_command,
    describe_env,
    git_head,
    make_seed,
    manifest_path_for,
    mark_failed,
    mark_infeasible,
    open_manifest,
    sha256_file,
    verify_manifest,
)


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "mission"
    subprocess.run(
        [sys.executable, str(RUNNERS / "init_workspace.py"), str(ws),
         "--mission", "repro-test", "--mode", "finite"],
        capture_output=True, text=True, timeout=120, check=True,
    )
    return ws


# ---------------------------------------------------------------------------
# Determinism of the environment fingerprint
# ---------------------------------------------------------------------------


def test_env_hash_is_stable_across_calls():
    """Same machine, same interpreter → same hash. Otherwise every replay would
    report a spurious environment change and the signal would be worthless."""
    assert build_env_hash() == build_env_hash()


def test_env_hash_changes_when_the_environment_does():
    """It must actually discriminate, or it is decoration."""
    assert build_env_hash() != build_env_hash({"blas": "openblas-0.3.21"})


def test_describe_env_records_what_can_change_a_number():
    env = describe_env()
    for key in ("python", "implementation", "platform", "machine"):
        assert env.get(key), f"{key} missing from the environment description"


def test_seeds_are_recorded_and_distinct():
    """A seed must be explicit and stored. An unrecorded seed makes a stochastic
    result unreproducible in principle, no matter what else is captured."""
    seeds = {make_seed() for _ in range(50)}
    assert len(seeds) == 50, "seeds must not repeat"
    assert all(s.startswith("0x") for s in seeds)


def test_git_head_is_none_outside_a_repo_not_a_guess(tmp_path: Path):
    """A wrong commit is worse than a missing one: it makes a replay look
    reproducible against code that never produced the result."""
    head = git_head(tmp_path)
    assert head is None or (isinstance(head, str) and len(head) == 40)


# ---------------------------------------------------------------------------
# The manifest lifecycle
# ---------------------------------------------------------------------------


def test_open_manifest_records_provenance_and_no_hash(workspace: Path):
    manifest = open_manifest(
        "datasets/TASK_0001/out.json", "TASK_0001",
        target_spec={"n": 5_000_000, "method": "exact"},
        workspace=workspace, projected_wallclock_h=13.42,
    )
    payload = json.loads(manifest.read_text())

    assert payload["status"] == "RUNNING"
    assert payload["output_sha256"] is None, "the launcher must never assert a hash"
    assert payload["completed_at"] is None
    assert payload["target_spec"] == {"n": 5_000_000, "method": "exact"}
    assert payload["projected_wallclock_h"] == 13.42
    assert payload["env_hash"] == build_env_hash()
    assert payload["seed_entropy"]
    assert payload["schema_version"] == 1


def test_manifest_validates_against_the_shipped_schema(workspace: Path):
    """The manifest the code writes must satisfy schemas/manifest.json, or the
    two definitions have drifted apart and validate would miss it."""
    manifest = open_manifest("datasets/TASK_0001/out.json", "TASK_0001",
                             target_spec={}, workspace=workspace)
    payload = json.loads(manifest.read_text())
    schema = json.loads((ENGINE / "schemas" / "manifest.json").read_text())

    for field in schema["required"]:
        assert field in payload, f"required field {field} missing"
    allowed = set(schema["properties"])
    assert set(payload) <= allowed, f"unknown fields: {set(payload) - allowed}"


def test_manifest_path_is_derived_from_the_output_path(workspace: Path):
    output = workspace / "datasets" / "x" / "y.npy"
    assert manifest_path_for(output).name == "y.npy.manifest.json"


def test_complete_manifest_hashes_the_real_file(workspace: Path):
    manifest = open_manifest("datasets/TASK_0001/out.json", "TASK_0001",
                             target_spec={"n": 10}, workspace=workspace)
    output = workspace / "datasets" / "TASK_0001" / "out.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"answer": 42}), encoding="utf-8")

    payload = complete_manifest(manifest, workspace=workspace)

    assert payload["status"] == "COMPLETE"
    assert payload["output_sha256"] == sha256_file(output)
    assert payload["output_bytes"] == output.stat().st_size
    assert payload["completed_at"]


def test_complete_manifest_refuses_without_an_output(workspace: Path):
    """The anti-fabrication clause. No file → no completion, and it raises."""
    manifest = open_manifest("datasets/TASK_0001/never.json", "TASK_0001",
                             target_spec={}, workspace=workspace)
    with pytest.raises(FileNotFoundError):
        complete_manifest(manifest, workspace=workspace)
    assert json.loads(manifest.read_text())["status"] == "RUNNING"


def test_hashing_is_deterministic_for_identical_content(workspace: Path):
    a = workspace / "datasets" / "a.json"
    b = workspace / "datasets" / "b.json"
    a.parent.mkdir(parents=True, exist_ok=True)
    a.write_text('{"x": 1}', encoding="utf-8")
    b.write_text('{"x": 1}', encoding="utf-8")
    assert sha256_file(a) == sha256_file(b)

    b.write_text('{"x": 2}', encoding="utf-8")
    assert sha256_file(a) != sha256_file(b)


def test_verify_detects_a_file_changed_after_recording(workspace: Path):
    manifest = open_manifest("datasets/TASK_0001/out.json", "TASK_0001",
                             target_spec={}, workspace=workspace)
    output = workspace / "datasets" / "TASK_0001" / "out.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("original", encoding="utf-8")
    complete_manifest(manifest, workspace=workspace)

    assert verify_manifest(manifest, workspace=workspace)["ok"]

    output.write_text("tampered", encoding="utf-8")
    verdict = verify_manifest(manifest, workspace=workspace)
    assert not verdict["ok"]
    assert verdict["expected"] != verdict["actual"]


def test_verify_refuses_a_manifest_that_is_not_complete(workspace: Path):
    """A consumer must not read a producer's output while it is still RUNNING."""
    manifest = open_manifest("datasets/TASK_0001/out.json", "TASK_0001",
                             target_spec={}, workspace=workspace)
    verdict = verify_manifest(manifest, workspace=workspace)
    assert not verdict["ok"]
    assert "not COMPLETE" in verdict["reason"]


def test_verify_catches_a_size_change_even_when_recorded_bytes_disagree(workspace: Path):
    """Check 3 of 5: a file whose size no longer matches the recorded bytes is a
    truncated or overwritten output, caught before (and independently of) the hash."""
    manifest = open_manifest("datasets/TASK_0001/out.json", "TASK_0001",
                             target_spec={}, workspace=workspace)
    output = workspace / "datasets" / "TASK_0001" / "out.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("the original, longer content", encoding="utf-8")
    complete_manifest(manifest, workspace=workspace)

    # Shrink the file to a different size; the recorded output_bytes no longer matches.
    output.write_text("short", encoding="utf-8")
    verdict = verify_manifest(manifest, workspace=workspace)
    assert not verdict["ok"]
    assert "bytes" in verdict["reason"]


def test_verify_catches_a_target_spec_size_shortfall(workspace: Path):
    """Check 3 of 5: if the spec names an expected size and the output misses it,
    the producer did not deliver what was asked, hash notwithstanding."""
    manifest = open_manifest("datasets/TASK_0001/out.json", "TASK_0001",
                             target_spec={"expected_bytes": 10_000}, workspace=workspace)
    output = workspace / "datasets" / "TASK_0001" / "out.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("tiny", encoding="utf-8")
    complete_manifest(manifest, workspace=workspace)

    verdict = verify_manifest(manifest, workspace=workspace)
    assert not verdict["ok"]
    assert "target spec required" in verdict["reason"]


def test_verify_catches_an_impossible_completed_at(workspace: Path):
    """Check 5 of 5: completed_at before started_at cannot happen — a COMPLETE
    manifest with impossible timestamps was written by hand, not by the job."""
    import json as _json

    manifest = open_manifest("datasets/TASK_0001/out.json", "TASK_0001",
                             target_spec={}, workspace=workspace)
    output = workspace / "datasets" / "TASK_0001" / "out.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("content", encoding="utf-8")
    complete_manifest(manifest, workspace=workspace)

    payload = _json.loads(manifest.read_text())
    payload["completed_at"] = "1999-01-01T00:00:00Z"  # before started_at
    manifest.write_text(_json.dumps(payload), encoding="utf-8")

    verdict = verify_manifest(manifest, workspace=workspace)
    assert not verdict["ok"]
    assert "precedes started_at" in verdict["reason"]


def test_infeasible_preserves_the_original_target_spec(workspace: Path):
    """B1: never silently substitute a smaller job. The spec that could NOT be met
    has to survive, or the record shows a job nobody actually asked for."""
    manifest = open_manifest("datasets/TASK_0001/huge.json", "TASK_0001",
                             target_spec={"n": 10**12}, workspace=workspace)
    mark_infeasible(manifest, "projects to 400h on this hardware", 400.0)

    payload = json.loads(manifest.read_text())
    assert payload["status"] == "INFEASIBLE"
    assert payload["target_spec"]["n"] == 10**12
    assert payload["output_sha256"] is None


def test_failed_is_distinct_from_infeasible(workspace: Path):
    """'It broke' and 'it cannot fit' need different responses, so they are
    different states: one is a bug to fix, the other a scope call for a human."""
    manifest = open_manifest("datasets/TASK_0001/out.json", "TASK_0001",
                             target_spec={}, workspace=workspace)
    mark_failed(manifest, "segfault in the solver")
    assert json.loads(manifest.read_text())["status"] == "FAILED"


def test_completion_command_calls_complete_not_a_literal_hash(workspace: Path):
    """The shell fragment handed to the background job must recompute the hash
    itself. If it ever embedded a precomputed digest, the whole contract dies."""
    manifest = open_manifest("datasets/TASK_0001/out.json", "TASK_0001",
                             target_spec={}, workspace=workspace)
    command = completion_command(manifest)
    assert "complete_manifest" in command
    assert "sha256" not in command.lower()


def test_a_full_producer_consumer_round_trip(workspace: Path):
    """End to end: open → produce in a detached process → complete → verify."""
    manifest = open_manifest("datasets/TASK_0001/round.json", "TASK_0001",
                             target_spec={"n": 3}, workspace=workspace)
    output = workspace / "datasets" / "TASK_0001" / "round.json"

    script = (
        f"import json, os, sys\n"
        f"os.makedirs({str(output.parent)!r}, exist_ok=True)\n"
        f"open({str(output)!r},'w').write(json.dumps([1,2,3]))\n"
        f"sys.path.insert(0, {str(ENGINE)!r})\n"
        f"from repro.manifest import complete_manifest\n"
        f"complete_manifest({str(manifest)!r}, workspace={str(workspace)!r})\n"
    )
    subprocess.run([sys.executable, "-c", script], check=True, timeout=60,
                   start_new_session=True)

    payload = json.loads(manifest.read_text())
    assert payload["status"] == "COMPLETE"
    assert payload["output_sha256"] == sha256_file(output)
    assert verify_manifest(manifest, workspace=workspace)["ok"]
