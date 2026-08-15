#!/usr/bin/env bash
# _lib.sh — shared plumbing for the SuperTeam launchers.
#
# Sourced, never executed. Everything here is deliberately boring: the launchers
# are the one place where a mistake spawns a *rival session*, and a rival session
# is how the predecessor lost a window.

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration (override via the environment)
# ---------------------------------------------------------------------------
CLAUDE_BIN="${SUPERTEAM_CLAUDE_BIN:-claude}"
MODEL="${SUPERTEAM_MODEL:-opus}"
# acceptEdits, not bypassPermissions: an unattended system should still be
# stopped by the permission layer before it does something irreversible. Law 2
# is not a thing we turn off for convenience.
PERMISSION_MODE="${SUPERTEAM_PERMISSION_MODE:-acceptEdits}"
EXTRA_FLAGS="${SUPERTEAM_CLAUDE_FLAGS:-}"

st_die() { printf 'error: %s\n' "$*" >&2; exit 1; }
st_note() { printf '  %s\n' "$*" >&2; }

st_rule() { printf '%s\n' "──────────────────────────────────────────────────────────────────────────────" >&2; }

# ---------------------------------------------------------------------------
# Workspace discovery — same contract as _core.find_workspace
# ---------------------------------------------------------------------------
st_workspace() {
  if [[ -n "${SUPERTEAM_WORKSPACE:-}" ]]; then
    [[ -f "$SUPERTEAM_WORKSPACE/REGISTRY.json" ]] \
      || st_die "SUPERTEAM_WORKSPACE=$SUPERTEAM_WORKSPACE has no REGISTRY.json"
    printf '%s\n' "$SUPERTEAM_WORKSPACE"
    return 0
  fi
  local dir="${1:-$PWD}"
  dir="$(cd "$dir" && pwd -P)"
  while [[ "$dir" != "/" ]]; do
    if [[ -f "$dir/REGISTRY.json" ]]; then printf '%s\n' "$dir"; return 0; fi
    dir="$(dirname "$dir")"
  done
  st_die "no REGISTRY.json here or in any parent. Run init_workspace.py first, or set SUPERTEAM_WORKSPACE."
}

st_runner() {
  # Prefer the workspace's pinned runner copy: a mission's engine must not shift
  # under it mid-flight because someone edited the shared engine.
  local ws="$1" name="$2"
  if [[ -x "$ws/runners/$name" || -f "$ws/runners/$name" ]]; then
    printf '%s\n' "$ws/runners/$name"
  else
    printf '%s\n' "$(cd "$(dirname "${BASH_SOURCE[0]}")/../runners" && pwd -P)/$name"
  fi
}

# ---------------------------------------------------------------------------
# The pre-launch gate
# ---------------------------------------------------------------------------
# Refuses on alive-progressing / alive-stalled / alive-paused / unknown, and
# prints the runner's own explanation. `unknown` refusing is the point: guessing
# "gone" because pgrep was unavailable is precisely the C1 double-launch bug.
st_require_launchable() {
  local ws="$1"; shift
  local liveness; liveness="$(st_runner "$ws" liveness.py)"
  local rc=0
  python3 "$liveness" --workspace "$ws" "$@" >&2 || rc=$?
  if (( rc != 0 )); then
    st_rule
    st_die "pre-launch liveness gate refused (exit $rc). Nothing was launched."
  fi
}

st_logfile() {
  local ws="$1" name="$2"
  mkdir -p "$ws/handoffs/orchestrator/logs"
  printf '%s\n' "$ws/handoffs/orchestrator/logs/${name}.$(date -u +%Y%m%dT%H%M%SZ).log"
}

# ---------------------------------------------------------------------------
# The actual spawn
# ---------------------------------------------------------------------------
# Headless (-p), detached (nohup/setsid-ish), logged. The session NAME matters:
# it is what liveness.py pgreps for, so it must be unique and stable.
st_launch_session() {
  local ws="$1" session="$2" prompt_file="$3"
  [[ -f "$prompt_file" ]] || st_die "prompt file not found: $prompt_file"

  local log; log="$(st_logfile "$ws" "$session")"
  st_note "session : $session"
  st_note "model   : $MODEL   permission-mode: $PERMISSION_MODE"
  st_note "prompt  : $prompt_file"
  st_note "log     : $log"

  if [[ -n "${SUPERTEAM_DRY_RUN:-}" ]]; then
    st_note "DRY RUN — not spawning. The command would be:"
    printf '%s --name %q --model %q --permission-mode %q --add-dir %q %s -p <prompt>\n' \
      "$CLAUDE_BIN" "$session" "$MODEL" "$PERMISSION_MODE" "$ws" "$EXTRA_FLAGS" >&2
    return 0
  fi

  command -v "$CLAUDE_BIN" >/dev/null 2>&1 \
    || st_die "$CLAUDE_BIN not on PATH. Set SUPERTEAM_CLAUDE_BIN."

  # shellcheck disable=SC2086  # EXTRA_FLAGS is intentionally word-split
  nohup "$CLAUDE_BIN" \
      --name "$session" \
      --model "$MODEL" \
      --permission-mode "$PERMISSION_MODE" \
      --add-dir "$ws" \
      $EXTRA_FLAGS \
      -p "$(cat "$prompt_file")" \
      >"$log" 2>&1 &
  local pid=$!
  disown "$pid" 2>/dev/null || true
  st_note "pid     : $pid"
  printf '%s\n' "$pid"
}
