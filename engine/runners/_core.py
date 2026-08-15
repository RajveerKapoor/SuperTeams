"""_core.py — the shared kernel every SuperTeam runner stands on.

Pure standard library, Python 3.9+. No third-party dependencies, by design: a
system that must survive weeks of unattended operation on someone else's machine
cannot depend on a pip install succeeding.

This module owns four things and nothing else:

  1. The atomic write primitive          (tmp -> fsync -> rename)
  2. The registry lock                   (fcntl.flock, LOCK_EX | LOCK_NB, polled)
  3. Hashing and workspace discovery
  4. The exit-code vocabulary            (doc 04 section 1)

Everything policy-shaped lives in the runner that implements it. See
doctrine/04_REGISTRY_AND_DISPATCH.md for the contract this file implements.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Exit codes (doctrine/04 section 1). The first seven are the predecessor's;
# 7 and 8 are the additions that make Law 1 and the dependency contract
# kernel-enforced instead of agent-remembered.
# ---------------------------------------------------------------------------

EXIT_OK = 0
EXIT_GENERIC = 1
EXIT_NOT_FOUND = 2
EXIT_VERSION_CONFLICT = 3
EXIT_LOCK_TIMEOUT = 4
EXIT_SCHEMA = 5
EXIT_FROZEN = 6
EXIT_ARTIFACT_MISSING = 7
EXIT_DEPENDENCY_NOT_MET = 8

EXIT_NAMES = {
    0: "OK",
    1: "GENERIC",
    2: "NOT_FOUND",
    3: "VERSION_CONFLICT",
    4: "LOCK_TIMEOUT",
    5: "SCHEMA",
    6: "FROZEN",
    7: "ARTIFACT_MISSING",
    8: "DEPENDENCY_NOT_MET",
}

LOCK_TIMEOUT_S = 30.0
LOCK_POLL_S = 0.05

# The honest-verdict vocabulary (doc 04 section 2). BLOCKED is accepted as an
# alias for STUMPED because doc 10 and Law 5 use that name; STUMPED is canonical
# because doc 04 defines the schema. DEFERRED is an alias for
# DEFERRED-COMPUTE-RUNNING for the same reason.
VERDICTS = [
    "DONE",
    "FAILED",
    "STUMPED",
    "DEFERRED-COMPUTE-RUNNING",
    "REVISED",
    "TRIVIAL",
    "DEFINITION-DEPENDENT",
    "META-QUESTION",
]
VERDICT_ALIASES = {"BLOCKED": "STUMPED", "DEFERRED": "DEFERRED-COMPUTE-RUNNING"}

TASK_STATUSES = ["BLOCKED_ON_DEPS", "PENDING", "IN_PROGRESS", "COMPLETED", "SUPERSEDED"]

WAVE_STATES = [
    "PLANNED",
    "RUNNING",
    "HALTED",
    "INTERRUPTED",
    "AWAITING_BACKGROUND_COMPUTE",
    "AUDITING",
    "COMPLETE",
    "FAILED",
]

AUDIT_STATES = ["NOT_REQUESTED", "REQUESTED", "PASS", "FAIL", "PASS_WITH_NOTES"]

# The five freezable fields (doc 04 section 3). The doc-04 names are canonical;
# the doc-08 names are accepted as aliases so either vocabulary works at the CLI.
FROZEN_FIELDS = [
    "falsification_criterion",
    "acceptance_check",
    "required_precision_se",
    "stumped_ci_width",
    "target_n",
]
FROZEN_FIELD_ALIASES = {
    "definition_of_done": "falsification_criterion",
    "confidence_target": "required_precision_se",
    "blocked_ci_width": "stumped_ci_width",
}

ID_PREFIXES = {
    "TASK": "task",
    "CLAIM": "claim",
    "ART": "artifact_ref",
    "DEC": "decision",
    "AUTHZ": "authorization",
    # The predecessor's ids remain valid entry ids.
    "DISC": "task",
    "GAP": "task",
}

ID_RE = re.compile(r"^(TASK|CLAIM|ART|DEC|AUTHZ|DISC|GAP)_(\d{4,})$")


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class SuperTeamError(Exception):
    """An error that maps onto a specific process exit code."""

    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def die(code: int, message: str) -> "SuperTeamError":
    return SuperTeamError(code, message)


def run_cli(main_fn) -> None:
    """Wrap a runner's main() so SuperTeamError becomes a clean exit code."""
    try:
        rc = main_fn()
        sys.exit(rc if isinstance(rc, int) else EXIT_OK)
    except SuperTeamError as exc:
        name = EXIT_NAMES.get(exc.code, str(exc.code))
        print(f"error [{name}]: {exc.message}", file=sys.stderr)
        sys.exit(exc.code)
    except BrokenPipeError:
        sys.exit(EXIT_OK)
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        sys.exit(EXIT_GENERIC)


# ---------------------------------------------------------------------------
# Time, hashing, ids
# ---------------------------------------------------------------------------


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(value: str) -> Optional[datetime]:
    if not value:
        return None
    txt = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(txt)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def next_id(registry: Dict[str, Any], prefix: str) -> str:
    """Allocate the next free id for a prefix. Caller must hold the lock."""
    highest = 0
    for entry_id in registry.get("entries", {}):
        match = ID_RE.match(entry_id)
        if match and match.group(1) == prefix:
            highest = max(highest, int(match.group(2)))
    return f"{prefix}_{highest + 1:04d}"


def normalize_verdict(verdict: Optional[str]) -> Optional[str]:
    if verdict is None:
        return None
    v = verdict.strip().upper()
    return VERDICT_ALIASES.get(v, v)


def normalize_frozen_field(field: str) -> str:
    return FROZEN_FIELD_ALIASES.get(field, field)


# ---------------------------------------------------------------------------
# Workspace discovery
# ---------------------------------------------------------------------------


def find_workspace(start: Optional[Path] = None) -> Path:
    """Walk up from `start` looking for a REGISTRY.json.

    $SUPERTEAM_WORKSPACE overrides the search entirely, which is how a spawned
    session that starts in an unrelated cwd finds its mission.
    """
    env = os.environ.get("SUPERTEAM_WORKSPACE")
    if env:
        candidate = Path(env).expanduser().resolve()
        if not (candidate / "REGISTRY.json").exists():
            raise die(
                EXIT_NOT_FOUND,
                f"SUPERTEAM_WORKSPACE={candidate} has no REGISTRY.json",
            )
        return candidate

    here = (start or Path.cwd()).resolve()
    for directory in [here, *here.parents]:
        if (directory / "REGISTRY.json").exists():
            return directory
    raise die(
        EXIT_NOT_FOUND,
        "no REGISTRY.json found in this directory or any parent. "
        "Run init_workspace.py to create a mission workspace, or set "
        "SUPERTEAM_WORKSPACE.",
    )


def engine_root() -> Path:
    """The engine directory (the parent of runners/)."""
    return Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Atomic writes
# ---------------------------------------------------------------------------


def atomic_write_bytes(path: Path, payload: bytes) -> None:
    """open(tmp) -> write -> flush -> fsync -> rename. Atomic on POSIX when tmp
    and dest share a filesystem, which they do because tmp is a sibling."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    with open(tmp, "wb") as fh:
        fh.write(payload)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    # fsync the directory so the rename itself is durable.
    dir_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def atomic_write_text(path: Path, text: str) -> None:
    atomic_write_bytes(path, text.encode("utf-8"))


def atomic_write_json(path: Path, data: Any) -> None:
    atomic_write_text(path, json.dumps(data, indent=2, sort_keys=False) + "\n")


def append_line(path: Path, line: str) -> None:
    """Append one line, O_APPEND so concurrent appends interleave safely."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line.rstrip("\n") + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        if default is not None:
            return default
        raise die(EXIT_NOT_FOUND, f"missing file: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise die(EXIT_SCHEMA, f"{path} is not valid JSON: {exc}") from exc


# ---------------------------------------------------------------------------
# The registry lock
# ---------------------------------------------------------------------------


@contextmanager
def registry_lock(workspace: Path, timeout: float = LOCK_TIMEOUT_S):
    """Exclusive flock on REGISTRY.lock with a polled soft timeout.

    Layer 1 of the two-layer contract in doc 04 section 1. Layer 2 (the
    optimistic version check) lives in dispatch.py, because locking alone
    cannot catch a read-modify-write race across processes that each read
    before either locked.
    """
    lock_path = workspace / "REGISTRY.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(lock_path, "w")
    deadline = time.monotonic() + timeout
    try:
        while True:
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise die(
                        EXIT_LOCK_TIMEOUT,
                        f"could not acquire {lock_path} within {timeout:.0f}s; "
                        "another writer is holding it",
                    )
                time.sleep(LOCK_POLL_S)
        try:
            fh.write(f"{os.getpid()} {now_iso()}\n")
            fh.flush()
        except OSError:
            pass
        yield
    finally:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        finally:
            fh.close()


# ---------------------------------------------------------------------------
# Registry I/O
# ---------------------------------------------------------------------------


def registry_path(workspace: Path) -> Path:
    return workspace / "REGISTRY.json"


def load_registry(workspace: Path) -> Dict[str, Any]:
    return read_json(registry_path(workspace))


def save_registry(workspace: Path, registry: Dict[str, Any]) -> None:
    """Persist the registry. Caller MUST hold the lock."""
    registry["n_entries"] = len(registry.get("entries", {}))
    registry["updated_at"] = now_iso()
    atomic_write_json(registry_path(workspace), registry)


def get_entry(registry: Dict[str, Any], entry_id: str) -> Dict[str, Any]:
    entries = registry.get("entries", {})
    if entry_id not in entries:
        raise die(EXIT_NOT_FOUND, f"no such entry: {entry_id}")
    return entries[entry_id]


def append_audit(
    workspace: Path,
    *,
    entry_id: str,
    action: str,
    patch: Any = None,
    prior_version: Optional[int] = None,
    new_version: Optional[int] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """One JSON line per applied mutation — the forensic chain (doc 04 s.1)."""
    record = {
        "ts": now_iso(),
        "entry_id": entry_id,
        "action": action,
        "patch": patch,
        "prior_version": prior_version,
        "new_version": new_version,
        "pid": os.getpid(),
        "argv": sys.argv,
    }
    if extra:
        record.update(extra)
    append_line(workspace / "REGISTRY.audit.log", json.dumps(record, sort_keys=False))


# ---------------------------------------------------------------------------
# A minimal JSON Schema subset validator
#
# We ship real JSON Schema files under engine/schemas/ so external tools can use
# them, and validate against them here with a stdlib implementation of the
# subset those schemas use. Adding a jsonschema dependency would trade a real
# runtime guarantee (it always works) for a cosmetic one (broader keyword
# coverage we do not use).
# ---------------------------------------------------------------------------

_JSON_TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "number": (int, float),
    "integer": int,
    "boolean": bool,
    "null": type(None),
}


def validate_schema(instance: Any, schema: Dict[str, Any], path: str = "$") -> List[str]:
    """Return a list of human-readable violations. Empty list == valid."""
    errors: List[str] = []

    if "type" in schema:
        types = schema["type"]
        types = types if isinstance(types, list) else [types]
        ok = False
        for t in types:
            expected = _JSON_TYPES.get(t)
            if expected is None:
                ok = True
                break
            # bool is a subclass of int in Python; JSON keeps them distinct.
            if t in ("number", "integer") and isinstance(instance, bool):
                continue
            if isinstance(instance, expected):
                ok = True
                break
        if not ok:
            errors.append(f"{path}: expected type {'|'.join(types)}, got {type(instance).__name__}")
            return errors

    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: {instance!r} not one of {schema['enum']}")

    if "pattern" in schema and isinstance(instance, str):
        if not re.search(schema["pattern"], instance):
            errors.append(f"{path}: {instance!r} does not match /{schema['pattern']}/")

    if isinstance(instance, dict):
        for required in schema.get("required", []):
            if required not in instance:
                errors.append(f"{path}: missing required property {required!r}")
        props = schema.get("properties", {})
        for key, value in instance.items():
            if key in props:
                errors.extend(validate_schema(value, props[key], f"{path}.{key}"))
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}: unexpected property {key!r}")

    if isinstance(instance, list) and "items" in schema:
        for index, item in enumerate(instance):
            errors.extend(validate_schema(item, schema["items"], f"{path}[{index}]"))

    return errors


_SCHEMA_CACHE: Dict[str, Dict[str, Any]] = {}


def load_schema(name: str) -> Dict[str, Any]:
    if name not in _SCHEMA_CACHE:
        path = engine_root() / "schemas" / f"{name}.json"
        if not path.exists():
            raise die(EXIT_SCHEMA, f"missing schema: {path}")
        _SCHEMA_CACHE[name] = read_json(path)
    return _SCHEMA_CACHE[name]


def validate_against(instance: Any, schema_name: str, label: str) -> None:
    errors = validate_schema(instance, load_schema(schema_name))
    if errors:
        detail = "\n  - ".join(errors)
        raise die(EXIT_SCHEMA, f"{label} failed schema {schema_name}:\n  - {detail}")


# ---------------------------------------------------------------------------
# Path helpers for the handoffs tree (doc 03 section 1)
# ---------------------------------------------------------------------------


def handoffs(workspace: Path) -> Path:
    return workspace / "handoffs"


def orch_dir(workspace: Path) -> Path:
    return handoffs(workspace) / "orchestrator"


def wave_paths(workspace: Path, wave_id: str) -> Dict[str, Path]:
    h = handoffs(workspace)
    return {
        "plan": h / "waves" / f"WAVE_{wave_id}_PLAN.md",
        "brief": h / "briefs" / f"WAVE_{wave_id}_BRIEF.md",
        "status": h / "status" / f"WAVE_{wave_id}_STATUS.json",
        "checkpoint": h / "checkpoints" / f"WAVE_{wave_id}_CHECKPOINT.md",
        "full_record": h / "full_records" / f"WAVE_{wave_id}_FULL_RECORD.md",
        "summary": h / "summaries" / f"WAVE_{wave_id}_SUMMARY.md",
        "halt": h / "halt_requests" / f"WAVE_{wave_id}_HALT.md",
        "resume": h / "halt_requests" / f"WAVE_{wave_id}_RESUME.md",
        "audit": orch_dir(workspace) / f"WAVE_{wave_id}_AUDIT.md",
        "baseline": orch_dir(workspace) / f"_wave{wave_id}_monitor_baseline.json",
    }


def window_state_path(workspace: Path) -> Path:
    return orch_dir(workspace) / "WINDOW_STATE.json"


def artifacts_pool(workspace: Path) -> Path:
    return workspace / "artifacts.jsonl"


def count_artifacts(workspace: Path) -> int:
    pool = artifacts_pool(workspace)
    if not pool.exists():
        return 0
    with open(pool, "r", encoding="utf-8") as fh:
        return sum(1 for line in fh if line.strip())


def iter_artifacts(workspace: Path) -> Iterable[Dict[str, Any]]:
    pool = artifacts_pool(workspace)
    if not pool.exists():
        return
    with open(pool, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


# ---------------------------------------------------------------------------
# Artifact verification — the shared half of the banking gate
# ---------------------------------------------------------------------------


def verify_artifact_ref(workspace: Path, art: Dict[str, Any]) -> Optional[str]:
    """Return an error string if the artifact does not verify, else None."""
    rel = art.get("path")
    if not rel:
        return f"{art.get('id')} has no path"
    target = workspace / rel
    if not target.exists():
        return f"{art.get('id')} references missing file: {rel}"
    recorded = art.get("sha256")
    if not recorded:
        return f"{art.get('id')} has no recorded sha256"
    actual = sha256_file(target)
    if actual != recorded:
        return (
            f"{art.get('id')} hash mismatch for {rel}: "
            f"recorded {recorded[:12]}…, on disk {actual[:12]}…"
        )
    return None


def verify_entry_artifacts(
    workspace: Path, registry: Dict[str, Any], entry: Dict[str, Any]
) -> List[str]:
    """Re-hash every artifact an entry references. The heart of exit 7."""
    problems: List[str] = []
    entries = registry.get("entries", {})
    for art_id in entry.get("artifacts", []) or []:
        art = entries.get(art_id)
        if art is None:
            problems.append(f"{entry['id']} references unknown artifact {art_id}")
            continue
        err = verify_artifact_ref(workspace, art)
        if err:
            problems.append(err)

    report = entry.get("report_path")
    if report:
        target = workspace / report
        if not target.exists():
            problems.append(f"{entry['id']} report_path missing on disk: {report}")
        else:
            recorded = entry.get("report_sha256")
            if not recorded:
                problems.append(f"{entry['id']} has report_path but no report_sha256")
            else:
                actual = sha256_file(target)
                if actual != recorded:
                    problems.append(
                        f"{entry['id']} report hash mismatch for {report}: "
                        f"recorded {recorded[:12]}…, on disk {actual[:12]}…"
                    )
    return problems


# ---------------------------------------------------------------------------
# Small formatting helpers shared by the read-only runners
# ---------------------------------------------------------------------------


def hr(char: str = "─", width: int = 78) -> str:
    return char * width


def kv(label: str, value: Any, width: int = 26) -> str:
    return f"  {label.ljust(width)} {value}"


def truncate(text: str, limit: int) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"
