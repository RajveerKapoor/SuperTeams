#!/usr/bin/env python3
"""test_continuity.py — the survival battery (doctrine/12 stage 3, doctrine/13 §2).

Every test here is an *induced failure*. A system whose whole claim is "it
survives interruption" earns that claim only by being interrupted on purpose:

  - kill a wave mid-flight after one banked task → resume re-does exactly one
  - stall with nothing banked → classifier says clean restart, not partial resume
  - stall with something banked → classifier says checkpoint-resume
  - a live, progressing wave → the gate refuses to launch a rival
  - "cannot tell" → the gate refuses, because unknown is not gone (C1)
  - a background producer outlives the session that launched it
  - park across the weekly cap and resume from disk with zero loss

    pytest runners/test_continuity.py -q
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parent.parent
RUNNERS = ENGINE / "runners"

EXIT_OK = 0
EXIT_SAFE = 0
EXIT_ALIVE_PROGRESSING = 10
EXIT_ALIVE_STALLED = 11
EXIT_ALIVE_PAUSED = 12
EXIT_UNKNOWN = 13


def run(workspace: Path, script: str, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, SUPERTEAM_WORKSPACE=str(workspace))
    return subprocess.run(
        [sys.executable, str(RUNNERS / script), *args],
        capture_output=True, text=True, env=env, timeout=120,
    )


def registry_of(workspace: Path) -> dict:
    return json.loads((workspace / "REGISTRY.json").read_text(encoding="utf-8"))


def status_of(workspace: Path, wave: str) -> dict:
    path = workspace / "handoffs" / "status" / f"WAVE_{wave}_STATUS.json"
    return json.loads(path.read_text(encoding="utf-8"))


def artifact_count(workspace: Path) -> int:
    pool = workspace / "artifacts.jsonl"
    if not pool.exists():
        return 0
    return len([line for line in pool.read_text(encoding="utf-8").splitlines() if line.strip()])


def current_version(workspace: Path, task: str) -> int:
    return registry_of(workspace)["entries"][task]["version"]


def update(workspace: Path, task: str, patch: dict) -> subprocess.CompletedProcess:
    """Update an entry, asserting the version currently on disk (04 §1)."""
    body = dict(patch)
    body.setdefault("version", current_version(workspace, task))
    return run(workspace, "dispatch.py", "update", "--disc", task,
               "--set", json.dumps(body))


def bank(workspace: Path, task: str) -> subprocess.CompletedProcess:
    report = workspace / "reports" / f"{task}.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(f"# {task}\n\nreal content\n", encoding="utf-8")
    run(workspace, "log_artifact.py", "--task", task,
        "--path", f"reports/{task}.md", "--report", "--kind", "measurement",
        "--lens", "generic", "--context", "banked by the continuity test")
    # Version read AFTER logging the artifact — log_artifact bumps it.
    return update(workspace, task, {"status": "COMPLETED", "verdict": "DONE"})


@pytest.fixture()
def wave(tmp_path: Path):
    """A workspace with wave `2k` scaffolded over three frozen tasks."""
    ws = tmp_path / "mission"
    subprocess.run(
        [sys.executable, str(RUNNERS / "init_workspace.py"), str(ws),
         "--mission", "continuity-test", "--mode", "finite"],
        capture_output=True, text=True, timeout=120, check=True,
    )
    for index in range(3):
        run(ws, "roadmap.py", "add-task", "--title", f"step {index}", "--lens", "generic")
    for task in ("TASK_0001", "TASK_0002", "TASK_0003"):
        run(ws, "pre_register.py", "--set", "--disc", task,
            "--dod", "the report exists", "--check", f"reports/{task}.md exists",
            "--precision", "deterministic", "--target-n", "1")
    run(ws, "pre_register.py", "--freeze")
    result = run(ws, "new_wave.py", "2k", "--tasks", "TASK_0001,TASK_0002,TASK_0003")
    assert result.returncode == EXIT_OK, result.stdout + result.stderr
    return ws


# ---------------------------------------------------------------------------
# Checkpoint / resume
# ---------------------------------------------------------------------------


def test_checkpoint_is_derived_from_registry_not_from_claims(wave: Path):
    """A checkpoint records what the KERNEL accepted, never what a caller says.

    Otherwise a dying session could checkpoint a completion the registry refused,
    and the resume would inherit a verdict that never happened.
    """
    bank(wave, "TASK_0001")
    assert run(wave, "checkpoint.py", "2k").returncode == EXIT_OK

    body = (wave / "handoffs" / "checkpoints" / "WAVE_2k_CHECKPOINT.md").read_text()
    payload = json.loads(body.split("```json")[1].split("```")[0])

    assert payload["completed"] == ["TASK_0001"]
    assert set(payload["pending"]) == {"TASK_0002", "TASK_0003"}
    assert payload["reconcile_rule"].startswith("registry wins")


def test_kill_after_one_banked_task_redoes_exactly_one(wave: Path):
    """Canary B. Kill mid-wave; a fresh Wave General resumes with no loss.

    The invariant that makes this cheap: banking is serial, so at most ONE task's
    work is ever unbanked. The kill costs that one task and nothing else.
    """
    bank(wave, "TASK_0001")
    run(wave, "checkpoint.py", "2k")

    # TASK_0002 starts, then the session dies before it can bank.
    update(wave, "TASK_0002", {"status": "IN_PROGRESS"})
    artifacts_at_death = artifact_count(wave)

    # --- a fresh Wave General resumes from disk ---
    entries = registry_of(wave)["entries"]
    assert entries["TASK_0001"]["status"] == "COMPLETED"
    assert entries["TASK_0002"]["status"] == "IN_PROGRESS"  # the orphan

    # It reverts the orphan and re-does exactly that one task.
    update(wave, "TASK_0002", {"status": "PENDING",
                               "notes": "orphan IN_PROGRESS reverted on resume"})
    bank(wave, "TASK_0002")
    bank(wave, "TASK_0003")

    entries = registry_of(wave)["entries"]
    assert [entries[t]["status"] for t in ("TASK_0001", "TASK_0002", "TASK_0003")] == [
        "COMPLETED", "COMPLETED", "COMPLETED"
    ]
    # No loss and no duplicate: exactly two artifacts appended after the death.
    assert artifact_count(wave) == artifacts_at_death + 2
    assert run(wave, "dispatch.py", "validate").returncode == EXIT_OK


def test_no_verdict_is_inherited_from_a_dead_session(wave: Path):
    """The orphan task must carry no verdict — a dead session's belief is not a result."""
    update(wave, "TASK_0001", {"status": "IN_PROGRESS"})
    orphan = registry_of(wave)["entries"]["TASK_0001"]
    assert orphan.get("verdict") is None
    assert orphan["status"] != "COMPLETED"


# ---------------------------------------------------------------------------
# Liveness classification — the four process conditions
# ---------------------------------------------------------------------------


def spawn_named(session: str, busy: bool = False) -> subprocess.Popen:
    """A stand-in Wave General process whose COMMAND LINE carries the session name.

    Liveness matches by session name via `pgrep -f` (doctrine/07 section 2), not
    by pid, so a fake session has to look like a real one to the same matcher
    production uses. `busy=True` burns CPU so the three-signal check reads it as
    progressing rather than paused.
    """
    body = (
        "import time\nend=time.time()+60\nx=0\nwhile time.time()<end: x+=1\n"
        if busy
        else "import time; time.sleep(60)"
    )
    return subprocess.Popen([sys.executable, "-c", body, session])


def mark_running(wave: Path, session: str, checkpoint_at: str = None) -> None:
    status_path = wave / "handoffs" / "status" / "WAVE_2k_STATUS.json"
    status = json.loads(status_path.read_text())
    status["state"] = "RUNNING"
    status["wavegen_session"] = session
    if checkpoint_at is not None:
        status["last_checkpoint_at"] = checkpoint_at
    status_path.write_text(json.dumps(status, indent=2))


def test_stall_with_nothing_banked_classifies_as_clean_restart(wave: Path):
    """Wave 2j. Alive but banking nothing, zero tasks done → clean restart.

    'Clean restart' matters because there is nothing to preserve: a partial
    resume here would invent state that never existed.
    """
    session = f"wave-2k-general-stall-{os.getpid()}"
    proc = spawn_named(session)
    try:
        time.sleep(0.3)
        # Backdate the checkpoint so the wave reads as stalled rather than fresh.
        mark_running(wave, session, checkpoint_at="2020-01-01T00:00:00Z")

        result = run(wave, "liveness.py", "2k", "--json")
        payload = json.loads(result.stdout)

        assert payload["condition"] == "alive-stalled", payload
        assert payload["safe_to_launch"] is False
        assert "nothing is banked" in payload["reason"].lower()
        assert "clean-restart" in payload["reason"].lower().replace(" ", "-")
        assert result.returncode == EXIT_ALIVE_STALLED
    finally:
        proc.kill()
        proc.wait()


def test_stall_with_something_banked_classifies_as_checkpoint_resume(wave: Path):
    """Same stall, but work exists: the answer is resume, never a clean restart."""
    bank(wave, "TASK_0001")
    run(wave, "checkpoint.py", "2k")

    session = f"wave-2k-general-partial-{os.getpid()}"
    proc = spawn_named(session)
    try:
        time.sleep(0.3)
        mark_running(wave, session, checkpoint_at="2020-01-01T00:00:00Z")

        payload = json.loads(run(wave, "liveness.py", "2k", "--json").stdout)
        assert payload["condition"] == "alive-stalled", payload
        assert "checkpoint-resume" in payload["reason"].lower()
    finally:
        proc.kill()
        proc.wait()


def test_gone_process_is_safe_to_launch(wave: Path):
    """An interrupted wave whose process is genuinely gone may be relaunched."""
    run(wave, "wave_status.py", "2k", "--set", "state=RUNNING",
        "--set", "wavegen_session=wave-2k-general-not-a-real-process-xyzzy")
    result = run(wave, "liveness.py", "2k", "--json")
    payload = json.loads(result.stdout)
    assert payload["condition"] == "gone"
    assert payload["safe_to_launch"] is True
    assert result.returncode == EXIT_SAFE


def test_planned_wave_with_no_session_is_safe_to_launch(wave: Path):
    result = run(wave, "liveness.py", "2k", "--json")
    payload = json.loads(result.stdout)
    assert payload["condition"] == "gone"
    assert payload["safe_to_launch"] is True


def test_a_live_progressing_wave_refuses_a_second_launch(wave: Path):
    """C1 / memory pin #13. The gate's whole job: never double-launch."""
    bank(wave, "TASK_0001")
    session = f"wave-2k-general-live-{os.getpid()}"
    proc = spawn_named(session, busy=True)
    try:
        time.sleep(0.5)  # let it accumulate CPU so it reads as progressing
        run(wave, "checkpoint.py", "2k")
        mark_running(wave, session)

        result = run(wave, "liveness.py", "2k", "--json")
        payload = json.loads(result.stdout)
        assert payload["condition"] == "alive-progressing", payload
        assert payload["safe_to_launch"] is False
        assert result.returncode == EXIT_ALIVE_PROGRESSING
    finally:
        proc.kill()
        proc.wait()


def test_paused_session_is_not_treated_as_gone(wave: Path):
    """C1's subtlety: alive-but-idle is a rate-limit pause holding warm context.

    Relaunching over it throws away that context AND creates a rival writer. The
    right move is a human paste into the paused session, so the gate must name
    this condition rather than collapsing it into 'stalled' or 'gone'.
    """
    bank(wave, "TASK_0001")
    session = f"wave-2k-general-paused-{os.getpid()}"
    proc = spawn_named(session, busy=False)  # alive, ~zero CPU
    try:
        time.sleep(0.3)
        run(wave, "checkpoint.py", "2k")  # a RECENT checkpoint
        mark_running(wave, session)

        result = run(wave, "liveness.py", "2k", "--json")
        payload = json.loads(result.stdout)
        assert payload["condition"] == "alive-paused", payload
        assert payload["safe_to_launch"] is False
        assert "warm context" in payload["reason"]
        assert result.returncode == EXIT_ALIVE_PAUSED
    finally:
        proc.kill()
        proc.wait()


def test_babysit_tick_pings_human_paste_for_a_paused_session(wave: Path):
    """The DAEMON, not just the pre-launch gate, must distinguish alive-paused.

    Before this, babysit.py had its own 2-signal classifier that never sampled
    CPU and emitted RESTART_CLEAN ('kill it') for a rate-limit-paused warm
    session — the exact C1 hazard. The tick now delegates to the same
    four-condition gate and must recommend a human paste, never a kill.
    """
    bank(wave, "TASK_0001")
    session = f"wave-2k-general-bpaused-{os.getpid()}"
    proc = spawn_named(session, busy=False)  # alive, ~zero CPU
    try:
        time.sleep(0.3)
        run(wave, "checkpoint.py", "2k")  # recent checkpoint
        mark_running(wave, session)

        payload = json.loads(run(wave, "babysit.py", "--json").stdout)
        assert payload["action"] == "PING_HUMAN_PASTE", payload
        assert "do not launch" in payload["detail"].lower()
        assert "kill" not in payload["detail"].lower().split("do not")[0]
    finally:
        proc.kill()
        proc.wait()


def test_spawn_script_refuses_when_the_gate_refuses(wave: Path):
    """The bash launcher must actually honour the gate, not merely consult it."""
    bank(wave, "TASK_0001")
    session = f"wave-2k-general-guard-{os.getpid()}"
    proc = spawn_named(session, busy=True)
    try:
        time.sleep(0.5)
        run(wave, "checkpoint.py", "2k")
        mark_running(wave, session)

        script = wave / "handoffs" / "orchestrator" / "_spawn_wave.sh"
        env = dict(os.environ, SUPERTEAM_WORKSPACE=str(wave), SUPERTEAM_DRY_RUN="1")
        result = subprocess.run(["bash", str(script), "2k"],
                                capture_output=True, text=True, env=env, timeout=120)
        assert result.returncode != 0
        assert "refused" in (result.stdout + result.stderr).lower()
    finally:
        proc.kill()
        proc.wait()


# ---------------------------------------------------------------------------
# Background compute outliving its session
# ---------------------------------------------------------------------------


def test_producer_outlives_the_session_and_the_job_writes_the_hash(wave: Path, tmp_path: Path):
    """Canary G. The launcher never writes the hash; the finished job does.

    A hash asserted before the work completes is not evidence — it is a promise.
    So `open_manifest` leaves output_sha256 null and only `complete_manifest`,
    running after the output exists, may fill it.
    """
    sys.path.insert(0, str(ENGINE))
    from repro.manifest import complete_manifest, open_manifest, verify_manifest

    output_rel = "datasets/TASK_0001/result.json"
    manifest = open_manifest(
        output_rel, "TASK_0001",
        target_spec={"n": 1000, "method": "exact"},
        workspace=wave, projected_wallclock_h=0.001,
    )
    opened = json.loads(manifest.read_text())
    assert opened["status"] == "RUNNING"
    assert opened["output_sha256"] is None, "the launcher must not assert a hash"
    assert opened["code_commit"] is None or isinstance(opened["code_commit"], str)
    assert opened["seed_entropy"].startswith("0x")

    # The "compute" runs in a detached process that outlives its launcher.
    output_abs = wave / output_rel
    script = (
        f"import json,os,time,sys\n"
        f"time.sleep(0.3)\n"
        f"os.makedirs({str(output_abs.parent)!r}, exist_ok=True)\n"
        f"open({str(output_abs)!r},'w').write(json.dumps({{'n':1000,'answer':42}}))\n"
        f"sys.path.insert(0,{str(ENGINE)!r})\n"
        f"from repro.manifest import complete_manifest\n"
        f"complete_manifest({str(manifest)!r}, workspace={str(wave)!r})\n"
    )
    proc = subprocess.Popen([sys.executable, "-c", script], start_new_session=True)
    proc.wait(timeout=60)

    done = json.loads(manifest.read_text())
    assert done["status"] == "COMPLETE"
    assert done["output_sha256"], "the finished job must write the hash"
    assert done["completed_at"]

    verdict = verify_manifest(manifest, workspace=wave)
    assert verdict["ok"], verdict

    # And the consumer's gate must catch a file that changed after recording.
    output_abs.write_text(json.dumps({"n": 1000, "answer": 43}), encoding="utf-8")
    tampered = verify_manifest(manifest, workspace=wave)
    assert not tampered["ok"]
    assert "hash does not match" in tampered["reason"]


def test_complete_manifest_refuses_when_nothing_was_produced(wave: Path):
    """A compute that produced no file cannot be marked COMPLETE."""
    sys.path.insert(0, str(ENGINE))
    from repro.manifest import complete_manifest, open_manifest

    manifest = open_manifest("datasets/TASK_0002/missing.json", "TASK_0002",
                             target_spec={}, workspace=wave)
    with pytest.raises(FileNotFoundError):
        complete_manifest(manifest, workspace=wave)

    assert json.loads(manifest.read_text())["status"] == "RUNNING"


def test_infeasible_is_recorded_not_silently_shrunk(wave: Path):
    """B1. The system says 'I cannot do this' rather than quietly doing less."""
    sys.path.insert(0, str(ENGINE))
    from repro.manifest import mark_infeasible, open_manifest

    manifest = open_manifest("datasets/TASK_0003/huge.json", "TASK_0003",
                             target_spec={"n": 10**12}, workspace=wave)
    mark_infeasible(manifest, "n=1e12 projects to 400h on this hardware", 400.0)

    payload = json.loads(manifest.read_text())
    assert payload["status"] == "INFEASIBLE"
    assert payload["projected_wallclock_h"] == 400.0
    assert payload["target_spec"]["n"] == 10**12, "the ORIGINAL spec must survive"


# ---------------------------------------------------------------------------
# Park / resume across the weekly cap
# ---------------------------------------------------------------------------


def test_park_then_resume_rederives_state_from_disk(wave: Path):
    """Canary I. Park at the cap, resume from disk, continue at the exact frontier."""
    bank(wave, "TASK_0001")
    run(wave, "checkpoint.py", "2k")

    parked = run(wave, "park.py", "weekly cap reached in the test")
    assert parked.returncode == EXIT_OK, parked.stdout + parked.stderr

    window = json.loads(
        (wave / "handoffs" / "orchestrator" / "WINDOW_STATE.json").read_text()
    )
    assert window["park_state"], "park.py must record a park state"

    # While parked, the loop holds — it does not spin.
    tick = run(wave, "babysit.py", "--json")
    assert json.loads(tick.stdout)["action"] == "HOLD"

    resumed = run(wave, "resume.py", "--json")
    assert resumed.returncode == EXIT_OK, resumed.stdout + resumed.stderr

    window = json.loads(
        (wave / "handoffs" / "orchestrator" / "WINDOW_STATE.json").read_text()
    )
    assert not window.get("park_state"), "resume.py must clear the park state"

    # Zero loss: the banked task is still banked and the frontier is intact.
    entries = registry_of(wave)["entries"]
    assert entries["TASK_0001"]["status"] == "COMPLETED"
    assert entries["TASK_0002"]["status"] == "PENDING"
    assert run(wave, "dispatch.py", "validate").returncode == EXIT_OK


def test_babysit_holds_on_a_dirty_registry(wave: Path):
    """Invariant: a validation failure is HOLD-and-flag, never an auto-advance."""
    bank(wave, "TASK_0001")
    (wave / "reports" / "TASK_0001.md").write_text("tampered\n", encoding="utf-8")

    payload = json.loads(run(wave, "babysit.py", "--json").stdout)
    assert payload["action"] == "FIX_INTEGRITY", payload
