#!/usr/bin/env bash
# _spawn_orchestrator.sh — the GUARDED Orchestrator launcher. Call this one.
#
# Enforces the single-Orchestrator invariant. Rotation TRANSFERS ownership; it
# does not duplicate it. The correct sequence, and the reason this script refuses
# when a live Orchestrator exists:
#
#   1. the outgoing Orchestrator writes handoffs/SESSION_HANDOFF_<iso>.md
#   2. the outgoing Orchestrator EXITS (or is about to)
#   3. _spawn_orchestrator.sh --handoff <file>   ← you are here
#   4. the successor arms its babysit loop only after the predecessor disarmed its own
#
#   _spawn_orchestrator.sh --handoff handoffs/SESSION_HANDOFF_2026-08-15T09-00Z.md
#   _spawn_orchestrator.sh --first-run
#
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)/_lib.sh"

ARGS=()
GATE_FLAGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --allow-unknown) GATE_FLAGS+=("--allow-unknown"); shift ;;
    *) ARGS+=("$1"); shift ;;
  esac
done

WS="$(st_workspace)"
LIVENESS="$(st_runner "$WS" liveness.py)"

st_rule
st_note "single-Orchestrator gate"
# Match on the session-name prefix every Orchestrator session carries.
rc=0
python3 "$LIVENESS" --session "orchestrator-" --kind orchestrator \
  ${GATE_FLAGS[@]+"${GATE_FLAGS[@]}"} >&2 || rc=$?
if (( rc != 0 )); then
  st_rule
  st_die "an Orchestrator is already live (exit $rc). Rotation transfers ownership — \
let the incumbent write its handoff and exit first. Nothing was launched."
fi

exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)/_launch_orchestrator.sh" \
  ${ARGS[@]+"${ARGS[@]}"}
