#!/usr/bin/env bash
# _spawn_wave.sh — the GUARDED Wave General launcher. This is the one to call.
#
# The guard is the whole point. The predecessor's memory pin #13 — "single loop,
# pre-launch liveness check, no double-launch" — exists because a rival session
# launched beside a live one is not a redundancy, it is two writers racing for
# one wave's state.
#
#   _spawn_wave.sh 2k
#   _spawn_wave.sh 2k --resume
#   _spawn_wave.sh 2k --allow-unknown     # only after checking by hand
#
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)/_lib.sh"

WAVE_ID="${1:-}"
[[ -n "$WAVE_ID" ]] || st_die "usage: _spawn_wave.sh <wave-id> [--resume] [--allow-unknown]"
shift || true

PASS_THROUGH=()
GATE_FLAGS=()
for arg in "$@"; do
  case "$arg" in
    --resume)        PASS_THROUGH+=("--resume") ;;
    --allow-unknown) GATE_FLAGS+=("--allow-unknown") ;;
    *) st_die "unknown flag: $arg" ;;
  esac
done

WS="$(st_workspace)"

st_rule
st_note "pre-launch liveness gate — wave ${WAVE_ID}"
st_require_launchable "$WS" "$WAVE_ID" ${GATE_FLAGS[@]+"${GATE_FLAGS[@]}"}

# Integrity gate: never launch work on top of a registry that does not validate.
# A dirty registry is a HOLD-and-flag, never an auto-advance.
st_note "registry integrity gate"
python3 "$(st_runner "$WS" dispatch.py)" --workspace "$WS" validate >&2 \
  || st_die "dispatch.py validate is dirty. Fix the registry before launching anything."

exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)/_launch_wave.sh" \
  "$WAVE_ID" ${PASS_THROUGH[@]+"${PASS_THROUGH[@]}"}
