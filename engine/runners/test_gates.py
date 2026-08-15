#!/usr/bin/env python3
"""test_gates.py — the separation gates the doctrine "never relaxes".

Two properties that were prose-only until an adversarial audit showed they could
be bypassed:

  * the audit verdict is the ONE thing the doer may never issue (05 §5, 06 D1,
    Law 4) — close_wave must refuse a self-signed audit;
  * a RESUME directive that does not classify its interruption is rejected by
    `dispatch.py validate` (07 §6).

    pytest runners/test_gates.py -q
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

EXIT_OK = 0
EXIT_SCHEMA = 5


def run(workspace: Path, script: str, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, SUPERTEAM_WORKSPACE=str(workspace))
    return subprocess.run(
        [sys.executable, str(RUNNERS / script), *args],
        capture_output=True, text=True, env=env, timeout=120,
    )


def registry_of(workspace: Path) -> dict:
    return json.loads((workspace / "REGISTRY.json").read_text(encoding="utf-8"))


def bank(workspace: Path, task: str) -> None:
    report = workspace / "reports" / f"{task}.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(f"# {task}\n\nreal content\n", encoding="utf-8")
    run(workspace, "log_artifact.py", "--task", task, "--path", f"reports/{task}.md",
        "--report", "--kind", "measurement", "--lens", "generic", "--context", "banked")
    version = registry_of(workspace)["entries"][task]["version"]
    result = run(workspace, "dispatch.py", "update", "--disc", task,
                 "--set", json.dumps({"status": "COMPLETED", "verdict": "DONE",
                                      "version": version}))
    assert result.returncode == EXIT_OK, result.stdout + result.stderr


def write_audit(workspace: Path, wave: str, auditor: str, verdict: str = "PASS") -> None:
    (workspace / "handoffs" / "orchestrator" / f"WAVE_{wave}_AUDIT.md").write_text(
        f"# WAVE {wave} AUDIT\n\n"
        f"Verdict: {verdict}\n"
        f"Auditor: {auditor}\n"
        "Audited_at: 2020-01-01T00:00:00Z\n\n"
        "## Claims re-derived\n| c | s | y | n |\n|---|---|---|---|\n",
        encoding="utf-8",
    )


def write_summary(workspace: Path, wave: str) -> None:
    (workspace / "handoffs" / "summaries" / f"WAVE_{wave}_SUMMARY.md").write_text(
        f"# WAVE {wave} SUMMARY\n\nAll tasks banked, audit PASS.\n", encoding="utf-8"
    )


@pytest.fixture()
def closable_wave(tmp_path: Path) -> Path:
    """A workspace with wave 2k fully banked, ready to close but for the audit."""
    ws = tmp_path / "mission"
    subprocess.run(
        [sys.executable, str(RUNNERS / "init_workspace.py"), str(ws),
         "--mission", "gate-test", "--mode", "finite"],
        capture_output=True, text=True, timeout=120, check=True,
    )
    for _ in range(2):
        run(ws, "roadmap.py", "add-task", "--title", "t", "--lens", "generic")
    for task in ("TASK_0001", "TASK_0002"):
        run(ws, "pre_register.py", "--set", "--disc", task, "--dod", "report exists",
            "--check", f"reports/{task}.md exists", "--precision", "deterministic",
            "--target-n", "1")
    run(ws, "pre_register.py", "--freeze")
    run(ws, "new_wave.py", "2k", "--tasks", "TASK_0001,TASK_0002")
    run(ws, "wave_status.py", "2k", "--set", "state=RUNNING",
        "--set", "wavegen_session=wave-2k-general-abc")
    bank(ws, "TASK_0001")
    bank(ws, "TASK_0002")
    write_summary(ws, "2k")
    return ws


# ---------------------------------------------------------------------------
# The audit is the one thing the doer may never issue (D1, Law 4)
# ---------------------------------------------------------------------------


def test_close_refuses_a_self_signed_audit(closable_wave: Path):
    """The doer auditing its own wave is the D1 blind spot. The close gate must
    refuse an audit whose Auditor is the session that ran the wave."""
    write_audit(closable_wave, "2k", auditor="wave-2k-general-abc")  # the doer
    result = run(closable_wave, "close_wave.py", "2k")
    assert result.returncode != EXIT_OK
    assert "audit its own wave" in (result.stdout + result.stderr)
    assert registry_of(closable_wave)  # untouched
    status = json.loads(
        (closable_wave / "handoffs" / "status" / "WAVE_2k_STATUS.json").read_text()
    )
    assert status["state"] != "COMPLETE"


def test_close_refuses_an_anonymous_audit(closable_wave: Path):
    """An unnamed auditor cannot be checked for independence, so it is refused."""
    write_audit(closable_wave, "2k", auditor="")
    result = run(closable_wave, "close_wave.py", "2k")
    assert result.returncode != EXIT_OK
    assert "no 'Auditor:" in (result.stdout + result.stderr) or "anonymous" in (
        result.stdout + result.stderr
    )


def test_close_accepts_a_distinct_cold_auditor(closable_wave: Path):
    """The honest path must still work: a different session's PASS closes the wave."""
    write_audit(closable_wave, "2k", auditor="cold-auditor-xyz")
    result = run(closable_wave, "close_wave.py", "2k")
    assert result.returncode == EXIT_OK, result.stdout + result.stderr
    status = json.loads(
        (closable_wave / "handoffs" / "status" / "WAVE_2k_STATUS.json").read_text()
    )
    assert status["state"] == "COMPLETE"


# ---------------------------------------------------------------------------
# A RESUME directive must classify its interruption (07 §6)
# ---------------------------------------------------------------------------


@pytest.fixture()
def mission(tmp_path: Path) -> Path:
    ws = tmp_path / "mission"
    subprocess.run(
        [sys.executable, str(RUNNERS / "init_workspace.py"), str(ws),
         "--mission", "resume-test", "--mode", "finite"],
        capture_output=True, text=True, timeout=120, check=True,
    )
    return ws


def write_resume(mission: Path, wave: str, class_line: str) -> None:
    (mission / "handoffs" / "halt_requests" / f"WAVE_{wave}_RESUME.md").write_text(
        f"# WAVE {wave} RESUME DIRECTIVE\n{class_line}\n"
        "## Verified on-disk state: 1 banked, 2 pending\n",
        encoding="utf-8",
    )


def test_validate_accepts_a_well_classified_resume(mission: Path):
    write_resume(mission, "2k", "## Interruption class: stalled-nothing-banked")
    result = run(mission, "dispatch.py", "validate")
    assert result.returncode == EXIT_OK, result.stdout + result.stderr


def test_validate_accepts_a_halted_reason_suffix(mission: Path):
    write_resume(mission, "2k", "## Interruption class: halted-needs-authorization")
    result = run(mission, "dispatch.py", "validate")
    assert result.returncode == EXIT_OK, result.stdout + result.stderr


def test_validate_rejects_a_resume_with_no_class(mission: Path):
    write_resume(mission, "2k", "## (forgot to classify)")
    result = run(mission, "dispatch.py", "validate")
    assert result.returncode == EXIT_SCHEMA
    assert "Interruption class" in (result.stdout + result.stderr)


def test_validate_rejects_the_template_placeholder(mission: Path):
    write_resume(mission, "2k", "## Interruption class: <one of the five above>")
    result = run(mission, "dispatch.py", "validate")
    assert result.returncode == EXIT_SCHEMA
    assert "placeholder" in (result.stdout + result.stderr)


def test_validate_rejects_an_unknown_class(mission: Path):
    write_resume(mission, "2k", "## Interruption class: got-bored")
    result = run(mission, "dispatch.py", "validate")
    assert result.returncode == EXIT_SCHEMA
    assert "not one of" in (result.stdout + result.stderr)
