#!/usr/bin/env python3
"""test_dispatch.py — the kernel acceptance battery (doctrine/13 section 2).

The predecessor's own tests, generalized:

    pytest runners/test_dispatch.py -q              # everything
    pytest runners/test_dispatch.py -k race -q      # atomicity under contention
    pytest runners/test_dispatch.py -k freeze -q    # exit 6 + audited --unfreeze
    pytest runners/test_dispatch.py -k gate -q      # exit 7 banking, exit 8 dependency

These are adversarial by construction. Each one tries to do the thing the kernel
promises is impossible, and passes only when the kernel refuses.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parent.parent
RUNNERS = ENGINE / "runners"

EXIT_OK = 0
EXIT_VERSION_CONFLICT = 3
EXIT_SCHEMA = 5
EXIT_FROZEN = 6
EXIT_ARTIFACT_MISSING = 7
EXIT_DEPENDENCY_NOT_MET = 8


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def run(workspace: Path, script: str, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, SUPERTEAM_WORKSPACE=str(workspace))
    return subprocess.run(
        [sys.executable, str(RUNNERS / script), *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )


def registry_of(workspace: Path) -> dict:
    return json.loads((workspace / "REGISTRY.json").read_text(encoding="utf-8"))


def audit_lines(workspace: Path) -> list:
    text = (workspace / "REGISTRY.audit.log").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def current_version(workspace: Path, entry_id: str) -> int:
    return registry_of(workspace)["entries"][entry_id]["version"]


def bump(workspace: Path, entry_id: str, patch: dict, *extra: str) -> subprocess.CompletedProcess:
    """Update an entry, asserting the version currently on disk.

    Version assertion is mandatory (04 §1), so every update path threads it.
    Reading the version immediately before the write is exactly what the Wave
    General does at bank time — after logging artifacts, which is what bumps it.
    """
    body = dict(patch)
    body.setdefault("version", current_version(workspace, entry_id))
    return run(workspace, "dispatch.py", "update", "--disc", entry_id,
               "--set", json.dumps(body), *extra)


def _bump(args) -> int:
    """Module-level so ProcessPoolExecutor can pickle it. Reads the version, then
    asserts it — so racing writers on the same entry conflict, as they must."""
    workspace, entry_id, field, value = args
    env = dict(os.environ, SUPERTEAM_WORKSPACE=str(workspace))
    version = json.loads(
        (Path(workspace) / "REGISTRY.json").read_text(encoding="utf-8")
    )["entries"][entry_id]["version"]
    result = subprocess.run(
        [
            sys.executable,
            str(RUNNERS / "dispatch.py"),
            "update",
            "--disc",
            entry_id,
            "--set",
            json.dumps({field: value, "version": version}),
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    return result.returncode


def _bump_with_version(args) -> int:
    """Same, but asserting a version — this is what makes writers conflict."""
    workspace, entry_id, value, version = args
    env = dict(os.environ, SUPERTEAM_WORKSPACE=str(workspace))
    result = subprocess.run(
        [
            sys.executable,
            str(RUNNERS / "dispatch.py"),
            "update",
            "--disc",
            entry_id,
            "--set",
            json.dumps({"notes": value}),
            "--expect-version",
            str(version),
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    return result.returncode


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    """A freshly initialised mission with 3 frozen tasks; TASK_0003 depends on 1+2."""
    ws = tmp_path / "mission"
    result = subprocess.run(
        [
            sys.executable,
            str(RUNNERS / "init_workspace.py"),
            str(ws),
            "--mission",
            "kernel-test",
            "--mode",
            "finite",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == EXIT_OK, result.stderr

    run(ws, "roadmap.py", "add-task", "--title", "first", "--lens", "generic")
    run(ws, "roadmap.py", "add-task", "--title", "second", "--lens", "generic")
    run(ws, "roadmap.py", "add-task", "--title", "third", "--lens", "generic",
        "--deps", "TASK_0001,TASK_0002")

    for task in ("TASK_0001", "TASK_0002", "TASK_0003"):
        run(ws, "pre_register.py", "--set", "--disc", task,
            "--dod", f"{task} is done when its report exists",
            "--check", f"reports/{task}.md exists",
            "--precision", "deterministic", "--target-n", "1")
    assert run(ws, "pre_register.py", "--freeze").returncode == EXIT_OK
    return ws


def complete_task(workspace: Path, task: str) -> subprocess.CompletedProcess:
    """The honest path: write a report, log it, then bank the completion."""
    report = workspace / "reports" / f"{task}.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(f"# {task}\n\nA real report with real content.\n", encoding="utf-8")
    logged = run(workspace, "log_artifact.py", "--task", task,
                 "--path", f"reports/{task}.md", "--report",
                 "--kind", "measurement", "--lens", "generic",
                 "--context", "the test's report")
    assert logged.returncode == EXIT_OK, logged.stderr
    # Read the version AFTER logging the artifact — log_artifact bumps it.
    return bump(workspace, task, {"status": "COMPLETED", "verdict": "DONE"})


# ---------------------------------------------------------------------------
# Race / atomicity
# ---------------------------------------------------------------------------


def test_race_20_parallel_non_conflicting_all_succeed(workspace: Path):
    """20 concurrent writers to 20 different entries: every one must land.

    The predecessor's number, kept. This is the property that lets many roles
    write the registry at once without a coordinator.
    """
    for index in range(20):
        run(workspace, "roadmap.py", "add-task", "--title", f"racer {index}",
            "--lens", "generic")

    ids = [
        entry_id
        for entry_id, entry in registry_of(workspace)["entries"].items()
        if entry.get("type") == "task" and entry.get("title", "").startswith("racer")
    ]
    assert len(ids) == 20

    jobs = [(workspace, entry_id, "notes", f"written-{entry_id}") for entry_id in ids]
    with ProcessPoolExecutor(max_workers=20) as pool:
        codes = list(pool.map(_bump, jobs))

    assert codes == [EXIT_OK] * 20, f"some non-conflicting writes were lost: {codes}"

    entries = registry_of(workspace)["entries"]
    for entry_id in ids:
        assert entries[entry_id]["notes"] == f"written-{entry_id}"


def test_race_5_parallel_same_entry_exactly_one_winner(workspace: Path):
    """5 writers assert the same version of ONE entry: exactly 1 wins, 4 conflict.

    This is the optimistic-concurrency half. Without it, last-write-wins would
    silently discard four agents' work and nobody would ever know.
    """
    version = registry_of(workspace)["entries"]["TASK_0001"]["version"]

    jobs = [(workspace, "TASK_0001", f"writer-{i}", version) for i in range(5)]
    with ProcessPoolExecutor(max_workers=5) as pool:
        codes = list(pool.map(_bump_with_version, jobs))

    winners = [c for c in codes if c == EXIT_OK]
    conflicts = [c for c in codes if c == EXIT_VERSION_CONFLICT]
    assert len(winners) == 1, f"expected exactly 1 winner, got {codes}"
    assert len(conflicts) == 4, f"expected 4 version conflicts, got {codes}"


def test_race_registry_never_left_corrupt(workspace: Path):
    """After heavy contention the registry is still valid JSON that validates."""
    for index in range(10):
        run(workspace, "roadmap.py", "add-task", "--title", f"racer {index}",
            "--lens", "generic")
    ids = [
        entry_id
        for entry_id, entry in registry_of(workspace)["entries"].items()
        if entry.get("type") == "task"
    ]
    jobs = [(workspace, entry_id, "notes", "concurrent") for entry_id in ids] * 2
    with ProcessPoolExecutor(max_workers=12) as pool:
        list(pool.map(_bump, jobs))

    registry_of(workspace)  # raises if the file was torn
    assert run(workspace, "dispatch.py", "validate").returncode == EXIT_OK


# ---------------------------------------------------------------------------
# Freeze (exit 6)
# ---------------------------------------------------------------------------


def test_freeze_rejects_a_goalpost_move(workspace: Path):
    """Weakening a frozen criterion is refused with exit 6."""
    patch = {"pre_registered": {"falsification_criterion": "anything at all counts"}}
    result = bump(workspace, "TASK_0001", patch)

    assert result.returncode == EXIT_FROZEN, result.stdout + result.stderr
    assert "frozen goalpost" in (result.stdout + result.stderr)

    current = registry_of(workspace)["entries"]["TASK_0001"]["pre_registered"]
    assert current["falsification_criterion"] != "anything at all counts"


def test_freeze_allows_a_no_op_write(workspace: Path):
    """Re-writing a frozen field with its CURRENT value is not a goalpost move.

    Without this, an idempotent retry — the most ordinary thing an interrupted
    agent does on resume — would trip the freeze gate and look like an attack.
    """
    current = registry_of(workspace)["entries"]["TASK_0001"]["pre_registered"]
    patch = {"pre_registered": {"falsification_criterion": current["falsification_criterion"]}}
    result = bump(workspace, "TASK_0001", patch)
    assert result.returncode == EXIT_OK, result.stdout + result.stderr


def test_freeze_unfreeze_requires_an_authorization(workspace: Path):
    """--unfreeze without --authz is refused: only a human may move a goalpost."""
    patch = {"pre_registered": {"falsification_criterion": "a corrected criterion"}}
    result = bump(workspace, "TASK_0001", patch,
                  "--unfreeze", "TASK_0001.falsification_criterion")
    assert result.returncode == EXIT_FROZEN
    assert "--authz" in (result.stdout + result.stderr)


def test_freeze_unfreeze_with_authz_succeeds_and_is_audited(workspace: Path):
    """The legitimate path: an Authorization exists, is cited, and is recorded twice."""
    created = run(workspace, "dispatch.py", "new", "--type", "authorization",
                  "--title", "human approves correcting TASK_0001's criterion typo")
    assert created.returncode == EXIT_OK, created.stderr
    authz_id = created.stdout.strip().splitlines()[-1].split()[0]
    assert authz_id.startswith("AUTHZ_"), created.stdout

    patch = {"pre_registered": {"falsification_criterion": "a corrected criterion"}}
    result = bump(workspace, "TASK_0001", patch,
                  "--unfreeze", "TASK_0001.falsification_criterion",
                  "--authz", authz_id)
    assert result.returncode == EXIT_OK, result.stdout + result.stderr

    entry = registry_of(workspace)["entries"]["TASK_0001"]
    assert entry["pre_registered"]["falsification_criterion"] == "a corrected criterion"

    # A goalpost move must never be a single easily-missed log line.
    unfreezes = [
        line for line in audit_lines(workspace)
        if line.get("action") == "UNFREEZE" and line.get("entry_id") == "TASK_0001"
    ]
    assert len(unfreezes) == 1, "the unfreeze was not separately audited"
    assert unfreezes[0]["authz"] == authz_id


def test_freeze_unfreeze_rejects_an_unknown_authz(workspace: Path):
    patch = {"pre_registered": {"falsification_criterion": "sneaky"}}
    result = bump(workspace, "TASK_0001", patch,
                  "--unfreeze", "TASK_0001.falsification_criterion",
                  "--authz", "AUTHZ_9999")
    assert result.returncode != EXIT_OK
    assert registry_of(workspace)["entries"]["TASK_0001"]["pre_registered"][
        "falsification_criterion"
    ] != "sneaky"


# ---------------------------------------------------------------------------
# Gates: banking (exit 7) and dependencies (exit 8)
# ---------------------------------------------------------------------------


def test_gate_completion_without_an_artifact_is_refused(workspace: Path):
    """Canary D: verdict DONE with nothing on disk → exit 7, task stays open."""
    result = bump(workspace, "TASK_0001", {"status": "COMPLETED", "verdict": "DONE"})

    assert result.returncode == EXIT_ARTIFACT_MISSING, result.stdout + result.stderr
    assert registry_of(workspace)["entries"]["TASK_0001"]["status"] != "COMPLETED"


def test_gate_completion_with_an_artifact_succeeds(workspace: Path):
    """The honest path must actually work, or the gate is just an obstacle."""
    result = complete_task(workspace, "TASK_0001")
    assert result.returncode == EXIT_OK, result.stdout + result.stderr

    entry = registry_of(workspace)["entries"]["TASK_0001"]
    assert entry["status"] == "COMPLETED"
    assert entry["verdict"] == "DONE"
    assert entry["report_path"] == "reports/TASK_0001.md"
    assert entry["artifacts"]


def test_gate_tampered_artifact_is_caught(workspace: Path):
    """Log an artifact, then edit the file: the recorded hash no longer matches.

    This is the fabrication detector at rest — the registry's hash and the bytes
    on disk disagree, and `validate` says so.
    """
    complete_task(workspace, "TASK_0001")
    (workspace / "reports" / "TASK_0001.md").write_text(
        "# TASK_0001\n\nSomething else entirely.\n", encoding="utf-8"
    )
    result = run(workspace, "dispatch.py", "validate")
    assert result.returncode != EXIT_OK
    assert "TASK_0001" in (result.stdout + result.stderr)


def test_gate_dependency_not_met_is_refused(workspace: Path):
    """Canary: TASK_0003 depends on 1+2; starting it early → exit 8."""
    result = bump(workspace, "TASK_0003", {"status": "IN_PROGRESS"})
    assert result.returncode == EXIT_DEPENDENCY_NOT_MET, result.stdout + result.stderr


def test_gate_dependency_met_allows_the_start(workspace: Path):
    complete_task(workspace, "TASK_0001")
    complete_task(workspace, "TASK_0002")
    result = bump(workspace, "TASK_0003", {"status": "IN_PROGRESS"})
    assert result.returncode == EXIT_OK, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# Honest-verdict invariants
# ---------------------------------------------------------------------------


def test_stumped_without_an_unblock_criterion_is_refused(workspace: Path):
    """Law 5: STUMPED means 'here is exactly what would let me' — or it is noise."""
    report = workspace / "reports" / "TASK_0001.md"
    report.write_text("# stumped\n", encoding="utf-8")
    run(workspace, "log_artifact.py", "--task", "TASK_0001",
        "--path", "reports/TASK_0001.md", "--report", "--kind", "artifact")

    result = bump(workspace, "TASK_0001", {"status": "COMPLETED", "verdict": "STUMPED"})
    assert result.returncode == EXIT_SCHEMA
    assert "unblock_criterion" in (result.stdout + result.stderr)


def test_revised_requires_the_mismatch_flag(workspace: Path):
    """Canary E's other half: REVISED must SURFACE the mismatch, not bury it."""
    report = workspace / "reports" / "TASK_0001.md"
    report.write_text("# revised\n", encoding="utf-8")
    run(workspace, "log_artifact.py", "--task", "TASK_0001",
        "--path", "reports/TASK_0001.md", "--report", "--kind", "artifact")

    result = bump(workspace, "TASK_0001", {"status": "COMPLETED", "verdict": "REVISED"})
    assert result.returncode == EXIT_SCHEMA
    assert "criterion_mismatch_flag" in (result.stdout + result.stderr)


# ---------------------------------------------------------------------------
# Version assertion is mandatory (04 §1)
# ---------------------------------------------------------------------------


def test_update_without_an_asserted_version_is_refused(workspace: Path):
    """The race guard is mandatory, not opt-in. A versionless update on an
    existing entry is refused with EXIT_VERSION_CONFLICT — an opt-in guard
    guards nothing, because the racing writers are the ones who skip it."""
    result = run(workspace, "dispatch.py", "update", "--disc", "TASK_0001",
                 "--set", json.dumps({"notes": "no version asserted"}))
    assert result.returncode == EXIT_VERSION_CONFLICT, result.stdout + result.stderr
    assert "assert the version" in (result.stdout + result.stderr)


def test_update_with_a_stale_version_is_refused(workspace: Path):
    """Two writers both read v_n; the first bumps it, the second's assertion is
    now stale and must lose — the read-modify-write race flock cannot catch."""
    stale = current_version(workspace, "TASK_0001")
    bump(workspace, "TASK_0001", {"notes": "first writer wins"})  # bumps the version
    result = run(workspace, "dispatch.py", "update", "--disc", "TASK_0001",
                 "--set", json.dumps({"notes": "second writer", "version": stale}))
    assert result.returncode == EXIT_VERSION_CONFLICT, result.stdout + result.stderr


def test_validate_is_clean_on_a_fresh_workspace(workspace: Path):
    result = run(workspace, "dispatch.py", "validate")
    assert result.returncode == EXIT_OK, result.stdout + result.stderr
    assert "clean" in result.stdout
