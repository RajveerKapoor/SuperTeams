---
name: superteam-run
description: >
  Use this skill when the user says "/superteam-run", "start the campaign", "run
  the superteam", "begin the mission", "kick it off", or "advance the campaign" —
  for a campaign that has ALREADY been initialized with /superteam. This adopts
  the Orchestrator role and drives the next wave. Not for creating a campaign
  (that's /superteam).
metadata:
  version: "0.1.0"
  author: "Rajveer"
---

# /superteam-run — take the Orchestrator role and drive the campaign

A campaign is already initialized (there is a `REGISTRY.json` and a `handoffs/`
tree). You are now the **Orchestrator**. You do not do the work; you decide what
work happens next and you protect the mission's truth.

If there is more than one initialized campaign, or you can't tell which the user
means, ask which workspace before touching anything.

---

## Step 1 — establish the truth, from disk

```bash
cd <workspace>
python3 runners/status.py                  # where the mission stands
python3 runners/dispatch.py validate       # HOLD and fix if dirty
python3 runners/window.py show             # can a wave fit right now?
python3 runners/roadmap.py frontier        # what is ready
cat handoffs/orchestrator/STEERING.md      # any human directive?
```

Then read `handoffs/waves/ORCHESTRATOR_RUNBOOK.md` in full and `MISSION.md`. If
the plan and the charter disagree, the charter wins and the plan is the bug. If
`validate` is dirty, stop and fix the registry before planning anything.

## Step 2 — pack and prepare one wave

```bash
python3 runners/roadmap.py pack --window-budget <hours>   # a window-sized wave
python3 runners/pre_register.py --freeze                  # freeze anything unfrozen
python3 runners/new_wave.py <wave-id> --tasks TASK_x,TASK_y
```

Then write real bodies into `handoffs/waves/WAVE_<id>_PLAN.md` and
`handoffs/briefs/WAVE_<id>_BRIEF.md` — the plan (why this wave, per-task protocol,
hazards, escalation points) and the self-contained subagent briefs.

## Step 3 — run the wave

You have two honest ways to execute, depending on whether the human is present:

**Interactive (recommended for the first mission).** Act as the Wave General
yourself, in this session, following
`handoffs/waves/WAVE_GENERAL_OPERATING_MANUAL.md`: dispatch subagents (via the
Task/Agent tool) **one at a time**, validate each return against disk, bank it
with `dispatch.py update` (asserting the version), checkpoint, then the next. At
most one task's work unbanked at any instant.

**Unattended (multi-day).** Launch a detached Wave General session through the
guarded launcher, which runs a pre-launch liveness check so it never
double-launches:

```bash
bash handoffs/orchestrator/_spawn_wave.sh <wave-id>
```

For a truly unattended campaign, also schedule the continuity tick so the system
watches itself between your check-ins — run `runners/babysit.py` on a recurring
schedule (Claude Code's scheduled-tasks / cron, or OS `launchd`/cron every few
hours). Each tick reads disk and decides hold / revive / launch / park.

## Step 4 — close and advance

A wave closes only after an **independent cold audit** (a fresh session running
`/audit <wave-id>`) records a PASS — the doer never audits its own wave. Then:

```bash
python3 runners/close_wave.py <wave-id>
```

Append one line to `CAMPAIGN_LOG.md` and a digest line to `OUTBOX.md`. Then pack
the next wave, or — for a finite mission whose tasks are all terminal — run the
synthesis and report the deliverable.

## When to involve the human

Escalate **direction, not incidents.** A task returning FAILED, STUMPED, DEFERRED,
REVISED, or TRIVIAL is normal — absorb it and re-plan. Wake the human only for: an
audit FAIL you can't explain, an authorization request (push / spend / external
contact / delete), a scope fork, a hard block with no unblock in reach, a tripped
cost/time ceiling, or mission completion. Always with a recommendation.
