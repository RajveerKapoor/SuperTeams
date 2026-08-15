---
name: superteam-status
description: >
  Use this skill when the user says "/superteam-status", "how's the campaign",
  "where are we", "show me the mission", "what's the superteam doing", or wants a
  catch-up on an initialized campaign. Read-only: it reports from disk, changes
  nothing.
metadata:
  version: "0.1.0"
  author: "Rajveer"
---

# /superteam-status — human catch-up, from disk

Give the human a clear picture of where their campaign stands, read entirely from
disk. Change nothing.

If there are multiple campaigns, list them and ask which (or summarize each in one
line).

## Step 1 — read the truth

```bash
cd <workspace>
python3 runners/status.py                     # mission state, frontier, in-flight wave, budget
python3 runners/dispatch.py validate          # is the registry clean?
python3 runners/inspect_registry.py --stumps      # every STUMPED task + its unblock criterion
python3 runners/inspect_registry.py --unaudited   # load-bearing claims not yet audited
python3 runners/window.py show                # window + weekly-cap budget
tail -n 40 handoffs/orchestrator/OUTBOX.md    # the digest
```

## Step 2 — summarize, plainly

Report, in a few lines each:

- **Where it is** — mode, tasks done / total, the in-flight wave (if any) and its
  state, what's on the ready frontier.
- **Health** — does the registry validate clean? any wave HALTED or PARKED? is a
  session paused at a rate limit (warm context — needs a paste, not a relaunch)?
- **What's blocked** — every STUMPED task and the one thing that would unblock the
  most work.
- **What needs the human** — any pending authorization, audit FAIL, or scope fork
  waiting in the escalation surface. If nothing needs them, say so — silence is
  the default and it's a good sign.
- **Recent** — the last few `OUTBOX.md` digest lines.

## Step 3 — offer the next move

If a wave is ready to launch → suggest `/superteam-run`. If a wave awaits audit →
suggest spawning a cold Auditor (`/audit <wave-id>` in a fresh session). If
something needs a decision → surface it with a recommendation. If it's healthy and
mid-flight → say so and get out of the way.

Optionally, offer a visual dashboard (a small self-contained HTML artifact: a
column per wave, task counts, audit states, budget dials) if the user would rather
see it than read it. Build it only from what the runners printed — never invent
numbers.
