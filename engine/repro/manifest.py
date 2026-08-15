#!/usr/bin/env python3
"""manifest.py — the background-compute / reproducibility manifest.

The Producer/Consumer contract (doctrine/07 section 4) in code:

    manifest = open_manifest(                 # BEFORE launching. status=RUNNING,
        output_path="datasets/TASK_0033/matrix.json",   # output_sha256=null
        producer_task="TASK_0033",
        target_spec={"n": 5_000_000, "method": "exact"},
        projected_wallclock_h=13.4,
    )
    # ... the background job runs, outliving this session ...
    complete_manifest(manifest_path)          # computes the hash FROM THE FILE

`complete_manifest` is the anti-fabrication clause made mechanical: it hashes the
file on disk and refuses if the file is absent. Nothing can stamp COMPLETE on a
compute that did not produce an output.

The shell one-liner in `completion_command()` is what a Producer actually appends
to its background command, so the *finished job* — not the launcher — writes the
hash back.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import secrets
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

SCHEMA_VERSION = 1


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(chunk)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# Environment capture
# ---------------------------------------------------------------------------


def git_head(cwd: Optional[Path] = None) -> Optional[str]:
    """The commit that produced this. None when not in a repo — recorded as None
    rather than guessed, because a wrong commit is worse than a missing one."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None if result.returncode == 0 else None


def describe_env() -> Dict[str, Any]:
    """Everything that could plausibly change a numeric result."""
    return {
        "python": sys.version.split()[0],
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor() or None,
    }


def build_env_hash(extra: Optional[Dict[str, Any]] = None) -> str:
    """A stable digest of the environment description."""
    payload = describe_env()
    if extra:
        payload["extra"] = extra
    blob = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def make_seed() -> str:
    """A recorded seed. Explicit and stored, never implicit — an unrecorded seed
    makes a stochastic result unreproducible in principle."""
    return hex(secrets.randbits(64))


# ---------------------------------------------------------------------------
# The manifest lifecycle
# ---------------------------------------------------------------------------


def manifest_path_for(output_path: Path) -> Path:
    return output_path.with_name(output_path.name + ".manifest.json")


def open_manifest(
    output_path: str,
    producer_task: str,
    *,
    target_spec: Dict[str, Any],
    workspace: Optional[Path] = None,
    projected_wallclock_h: Optional[float] = None,
    expected_completion_at: Optional[str] = None,
    shell_id: Optional[str] = None,
    seed: Optional[str] = None,
    consumers: Optional[list] = None,
) -> Path:
    """Write the RUNNING manifest. Call BEFORE launching the compute.

    `output_sha256` is null here and stays null until the finished job fills it.
    That ordering is the contract.
    """
    root = Path(workspace) if workspace else Path.cwd()
    target = (root / output_path).resolve()
    path = manifest_path_for(target)

    payload: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "output_path": output_path,
        "producer_task": producer_task,
        "target_spec": target_spec,
        "code_commit": git_head(root),
        "env_hash": build_env_hash(),
        "seed_entropy": seed if seed is not None else make_seed(),
        "started_at": _now(),
        "expected_completion_at": expected_completion_at,
        "projected_wallclock_h": projected_wallclock_h,
        "status": "RUNNING",
        "shell_id": shell_id,
        "output_sha256": None,
        "output_bytes": None,
        "completed_at": None,
        "infeasible_reason": None,
        "consumers": consumers or [producer_task],
    }
    _atomic_write_json(path, payload)
    return path


def complete_manifest(manifest: Path, workspace: Optional[Path] = None) -> Dict[str, Any]:
    """Hash the produced file and stamp COMPLETE. Refuses if there is no file.

    This is the anti-fabrication clause. A compute that claims to have finished
    but left nothing on disk did not finish, and this raises rather than
    recording a completion nobody can verify.
    """
    manifest = Path(manifest)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    root = Path(workspace) if workspace else manifest.parent.parent
    output = (root / payload["output_path"]).resolve()
    if not output.exists():
        output = manifest.with_name(manifest.name.replace(".manifest.json", ""))
    if not output.exists():
        raise FileNotFoundError(
            f"{payload['output_path']} does not exist, so this compute produced "
            "nothing to hash. A manifest cannot be marked COMPLETE without its "
            "output — that would be a completion with no evidence behind it."
        )

    payload["output_sha256"] = sha256_file(output)
    payload["output_bytes"] = output.stat().st_size
    payload["completed_at"] = _now()
    payload["status"] = "COMPLETE"
    _atomic_write_json(manifest, payload)
    return payload


def mark_failed(manifest: Path, reason: str) -> Dict[str, Any]:
    manifest = Path(manifest)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["status"] = "FAILED"
    payload["completed_at"] = _now()
    payload["infeasible_reason"] = reason
    _atomic_write_json(manifest, payload)
    return payload


def mark_infeasible(
    manifest: Path, reason: str, projected_wallclock_h: Optional[float] = None
) -> Dict[str, Any]:
    """The hardware genuinely cannot do the full spec in the time available.

    The Wave General then HALTs to the Orchestrator. It NEVER silently
    substitutes a smaller job — that is the B1 failure, and a quietly shrunk
    target produces a number that looks like the one that was asked for.
    """
    manifest = Path(manifest)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["status"] = "INFEASIBLE"
    payload["completed_at"] = _now()
    payload["infeasible_reason"] = reason
    if projected_wallclock_h is not None:
        payload["projected_wallclock_h"] = projected_wallclock_h
    _atomic_write_json(manifest, payload)
    return payload


def verify_manifest(manifest: Path, workspace: Optional[Path] = None) -> Dict[str, Any]:
    """The consumer's gate: the FIVE checks (doctrine/07 §4), in order.

    1. status == COMPLETE
    2. the output file exists
    3. its size matches what the manifest recorded (and the spec, if it names one)
    4. its recomputed SHA-256 matches
    5. completed_at is sane — present, parseable, not in the future, ≥ started_at

    Returns {ok, reason, expected, actual}. Hash alone is the strongest of the
    five, but the other four catch failure modes the hash can mask or that occur
    before hashing is even worth doing: a still-RUNNING producer, a truncated
    write, a clock/ordering anomaly that signals the manifest was hand-edited.
    A consumer that skips these is trusting a file it never checked.
    """
    manifest = Path(manifest)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    root = Path(workspace) if workspace else manifest.parent.parent
    expected = payload.get("output_sha256")

    # 1. status
    if payload.get("status") != "COMPLETE":
        return {
            "ok": False,
            "reason": f"manifest status is {payload.get('status')}, not COMPLETE",
            "expected": expected,
            "actual": None,
        }

    # 2. exists
    output = (root / payload["output_path"]).resolve()
    if not output.exists():
        return {
            "ok": False,
            "reason": f"{payload['output_path']} is missing but the manifest says COMPLETE",
            "expected": expected,
            "actual": None,
        }

    # 3. size matches — recorded output_bytes, and target_spec's expected size if given
    actual_bytes = output.stat().st_size
    recorded_bytes = payload.get("output_bytes")
    if recorded_bytes is not None and actual_bytes != recorded_bytes:
        return {
            "ok": False,
            "reason": (
                f"output is {actual_bytes} bytes but the manifest recorded "
                f"{recorded_bytes}. The file changed size after completion — a "
                "truncated or overwritten output. Do NOT consume it."
            ),
            "expected": expected,
            "actual": None,
        }
    spec = payload.get("target_spec") or {}
    spec_bytes = spec.get("output_bytes") or spec.get("expected_bytes")
    if isinstance(spec_bytes, int) and actual_bytes != spec_bytes:
        return {
            "ok": False,
            "reason": (
                f"output is {actual_bytes} bytes but the target spec required "
                f"{spec_bytes}. The producer did not deliver the specified size."
            ),
            "expected": expected,
            "actual": None,
        }

    # 4. hash
    actual = sha256_file(output)
    if actual != expected:
        return {
            "ok": False,
            "reason": (
                "output hash does not match the manifest. The file changed after "
                "it was recorded, or a different run overwrote it. Do NOT consume it."
            ),
            "expected": expected,
            "actual": actual,
        }

    # 5. completed_at sane
    sanity = _completion_time_problem(payload)
    if sanity:
        return {"ok": False, "reason": sanity, "expected": expected, "actual": actual}

    return {"ok": True, "reason": "all five checks pass", "expected": expected, "actual": actual}


def _completion_time_problem(payload: Dict[str, Any]) -> Optional[str]:
    """None if completed_at is sane, else why not. A COMPLETE manifest whose
    timestamps are impossible was almost certainly written by hand, not by the
    finished job — which is exactly the fabrication shape this contract exists
    to make hard."""
    completed_raw = payload.get("completed_at")
    if not completed_raw:
        return "manifest is COMPLETE but has no completed_at timestamp"
    try:
        completed = datetime.fromisoformat(completed_raw.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return f"completed_at {completed_raw!r} is not a parseable ISO-8601 time"
    now = datetime.now(timezone.utc)
    # A small skew tolerance; a completion a full minute in the future is wrong.
    if completed > now.replace(microsecond=0) and (completed - now).total_seconds() > 60:
        return f"completed_at {completed_raw} is in the future — an impossible completion"
    started_raw = payload.get("started_at")
    if started_raw:
        try:
            started = datetime.fromisoformat(started_raw.replace("Z", "+00:00"))
            if completed < started:
                return (
                    f"completed_at {completed_raw} precedes started_at {started_raw} — "
                    "the job finished before it began, which cannot happen"
                )
        except (ValueError, AttributeError):
            pass
    return None


def completion_command(manifest: Path, python: str = "python3") -> str:
    """The shell fragment a Producer appends to its background command, so the
    FINISHED JOB writes the hash back — not the launcher that started it."""
    engine = Path(__file__).resolve().parent.parent
    return (
        f'{python} -c "import sys; sys.path.insert(0, {str(engine)!r}); '
        f'from repro.manifest import complete_manifest; '
        f'complete_manifest({str(manifest)!r})"'
    )
