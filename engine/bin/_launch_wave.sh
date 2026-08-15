#!/usr/bin/env bash
# _launch_wave.sh — build a Wave General's opening prompt and start the session.
#
# This is the RAW launcher. It does no liveness checking. Call `_spawn_wave.sh`
# instead unless you have already run the gate yourself and know why you are
# bypassing it.
#
#   _launch_wave.sh 2k
#   _launch_wave.sh 2k --resume            # include the RESUME directive
#
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)/_lib.sh"

WAVE_ID="${1:-}"
[[ -n "$WAVE_ID" ]] || st_die "usage: _launch_wave.sh <wave-id> [--resume]"
shift || true
WITH_RESUME=""
for arg in "$@"; do
  case "$arg" in
    --resume) WITH_RESUME=1 ;;
    *) st_die "unknown flag: $arg" ;;
  esac
done

WS="$(st_workspace)"
SESSION="wave-${WAVE_ID}-general"
PLAN="handoffs/waves/WAVE_${WAVE_ID}_PLAN.md"
BRIEF="handoffs/briefs/WAVE_${WAVE_ID}_BRIEF.md"
STATUS="handoffs/status/WAVE_${WAVE_ID}_STATUS.json"
CHECKPOINT="handoffs/checkpoints/WAVE_${WAVE_ID}_CHECKPOINT.md"
RESUME="handoffs/halt_requests/WAVE_${WAVE_ID}_RESUME.md"

[[ -f "$WS/$PLAN" ]] || st_die "$PLAN missing. Scaffold with new_wave.py and write the plan body first."
[[ -f "$WS/$STATUS" ]] || st_die "$STATUS missing. Scaffold with new_wave.py first."
if [[ -n "$WITH_RESUME" && ! -f "$WS/$RESUME" ]]; then
  st_die "--resume given but $RESUME does not exist. The Orchestrator authors the resume directive; the Wave General executes it."
fi

PROMPT="$(mktemp -t superteam-wave-prompt)"
trap 'rm -f "$PROMPT"' EXIT

{
  cat <<EOF
You are the **Wave General** for wave ${WAVE_ID} of the mission in ${WS}.

You own exactly one wave, in exactly one session, in roughly one 5-hour window.
You are not the Orchestrator and you are not a Subagent.

Work from ${WS}. Read these, in this order, before you do anything else:

1. handoffs/waves/WAVE_GENERAL_OPERATING_MANUAL.md — your charter, in full
2. ${PLAN} — this wave's plan
3. ${BRIEF} — the dispatch material
4. ${CHECKPOINT} — if this is a resume, this is where you restart from
EOF

  if [[ -n "$WITH_RESUME" ]]; then
    cat <<EOF
5. ${RESUME} — **the resume directive. Follow it.** It names the interruption
   class and, per pending item, whether to recompute or synthesize from disk.
   Do not recompute anything it tells you is already persisted and hashed.
EOF
  fi

  cat <<EOF

Then, for every task in scope, read its FROZEN criterion from the registry —
never from the plan's copy of it:

    python3 runners/dispatch.py show --disc <TASK_ID>

The plan is context. The registry is law.

**The serial-banking protocol is not optional.** One Subagent at a time: dispatch
one, await its return, validate the return against disk (report exists, sha256
matches, artifacts logged), bank it with dispatch.py update, checkpoint, and only
then dispatch the next. At most one task's work may be unbanked at any instant.
Never parallel-spawn Subagents inside a wave — that is what cost a predecessor
Wave General an entire fresh window with nothing persisted.

Give your Subagents no wall-clock cap. Quality is the only metric; a genuinely
long compute goes to the background-compute contract (manifest first, then
background Bash, then DEFERRED-COMPUTE-RUNNING).

First act: run these and reconcile what they say against this prompt. On any
conflict, **disk wins** — this prompt is a claim, the registry is the truth.

    python3 runners/wave_status.py ${WAVE_ID} --show
    python3 runners/dispatch.py validate
    python3 runners/window.py show

Then mark yourself live so the continuity loop can see you:

    python3 runners/wave_status.py ${WAVE_ID} --set state=RUNNING --set wavegen_session=${SESSION}

Close the wave only through close_wave.py, and only after an INDEPENDENT cold
audit has recorded a PASS. You never audit your own wave.

If you need an authorization you do not have, or a result contradicts disk and
you cannot explain why, or a frozen criterion conflicts with reality: write
handoffs/halt_requests/WAVE_${WAVE_ID}_HALT.md, set the status to HALTED,
checkpoint, and exit cleanly. Do not loop, retry, or improvise a workaround.
EOF
} > "$PROMPT"

st_rule
st_note "launching Wave General for wave ${WAVE_ID}"
st_launch_session "$WS" "$SESSION" "$PROMPT"
