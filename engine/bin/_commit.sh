#!/usr/bin/env bash
# _commit.sh — allow-list staging. Stages what a mission is allowed to produce
# and refuses everything else, printing what it skipped and why.
#
# The refusal is the feature. An autonomous system committing `git add -A` will
# eventually sweep up a credential file, a 2GB dataset, or a stray edit to source
# it was never asked to touch. The allow-list means a surprise in the working tree
# shows up as a printed skip, not as a commit nobody reviewed.
#
#   _commit.sh -m "wave 2k complete"
#   _commit.sh -m "wave 2k complete" --also datasets/task_31/spectrum.npy
#   _commit.sh -m "..." --dry-run
#
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)/_lib.sh"

MESSAGE=""
DRY_RUN=""
EXTRA_PATHS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    -m|--message) MESSAGE="${2:-}"; shift 2 ;;
    --also) EXTRA_PATHS+=("${2:-}"); shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    *) st_die "unknown flag: $1" ;;
  esac
done
[[ -n "$MESSAGE" ]] || st_die "usage: _commit.sh -m <message> [--also <path>] [--dry-run]"

WS="$(st_workspace)"
cd "$WS"

git rev-parse --git-dir >/dev/null 2>&1 || st_die "$WS is not a git repository."

# ---------------------------------------------------------------------------
# The allow-list (doctrine/06 E2, 03 §6): the mission's own bookkeeping, prose,
# and evidence. `datasets/` IS on the list — the produced outputs are the
# evidence a claim rests on, and the doctrine commits them. The refuse-pattern
# below still blocks the dangerous things (credentials, DBs) even inside an
# allowed directory. What is ABSENT is anything OUTSIDE the workspace, which the
# discovery logic already cannot reach.
# ---------------------------------------------------------------------------
ALLOW=(
  "REGISTRY.json"
  "REGISTRY.audit.log"
  "artifacts.jsonl"
  "MISSION.md"
  "handoffs"
  "reports"
  "datasets"
  "runners"
  ".gitignore"
)

# ---------------------------------------------------------------------------
# The refuse-list: patterns that are never committed even if inside an allowed
# directory. Checked against every path we are about to stage.
# ---------------------------------------------------------------------------
REFUSE_PATTERN='(^|/)(\.env|\.env\..*|.*\.pem|.*\.key|id_rsa.*|.*credential.*|.*secret.*|.*\.sqlite|.*\.db|REGISTRY\.lock|__pycache__|.*\.pyc|\.DS_Store)$'

st_rule
st_note "workspace: $WS"

# Read with a while-loop rather than mapfile: macOS ships bash 3.2, and a
# launcher that only works on a machine with a newer bash is a launcher that
# fails at 3am on the machine it was written for.
CHANGED=()
while IFS= read -r line; do
  [[ -n "$line" ]] && CHANGED+=("${line:3}")
done < <(git status --porcelain --untracked-files=all)

if [[ ${#CHANGED[@]} -eq 0 ]]; then
  st_note "nothing to commit — working tree clean"
  exit 0
fi

TO_STAGE=()
SKIPPED=()
for path in "${CHANGED[@]}"; do
  # `git status` quotes paths containing odd characters; strip the quoting.
  path="${path%\"}"; path="${path#\"}"
  allowed=""
  for prefix in "${ALLOW[@]}"; do
    if [[ "$path" == "$prefix" || "$path" == "$prefix"/* ]]; then allowed=1; break; fi
  done
  for extra in ${EXTRA_PATHS[@]+"${EXTRA_PATHS[@]}"}; do
    if [[ "$path" == "$extra" || "$path" == "$extra"/* ]]; then allowed=1; break; fi
  done

  if [[ -z "$allowed" ]]; then
    SKIPPED+=("$path  (not on the allow-list)")
    continue
  fi
  if [[ "$path" =~ $REFUSE_PATTERN ]]; then
    SKIPPED+=("$path  (REFUSED: matches a never-commit pattern)")
    continue
  fi
  TO_STAGE+=("$path")
done

if [[ ${#SKIPPED[@]} -gt 0 ]]; then
  st_note "skipped ${#SKIPPED[@]} path(s):"
  for entry in "${SKIPPED[@]}"; do st_note "    $entry"; done
  st_note "if one of those belongs in the commit, pass it with --also, deliberately."
fi

if [[ ${#TO_STAGE[@]} -eq 0 ]]; then
  st_note "nothing on the allow-list changed — no commit made"
  exit 0
fi

st_note "staging ${#TO_STAGE[@]} path(s):"
for path in "${TO_STAGE[@]}"; do st_note "    $path"; done

if [[ -n "$DRY_RUN" ]]; then
  st_rule
  st_note "DRY RUN — nothing staged, nothing committed"
  exit 0
fi

git add -- "${TO_STAGE[@]}"

if git diff --cached --quiet; then
  st_note "staged set is empty after add — no commit made"
  exit 0
fi

git commit -m "$MESSAGE"

st_rule
st_note "committed locally. This script NEVER pushes."
st_note "A push leaves the machine, so it is an irreversible, outward-facing act:"
st_note "it needs a recorded human Authorization, and a human runs it."
