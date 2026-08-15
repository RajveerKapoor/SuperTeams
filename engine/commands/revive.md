---
description: Author a WAVE_<id>_RESUME.md directive from on-disk truth after an interruption
---

# /revive — author a resume directive

**You are the Orchestrator.** You write this directive. You never execute it — the
relaunched Wave General does. (doctrine/07 section 6)

Argument: the wave id (e.g. `/revive 2k`). If none was given, infer it from the
one wave whose STATUS is `RUNNING`, `HALTED`, or `INTERRUPTED`, and say which you
picked.

---

## Step 1 — establish the truth, from disk only

Run these and use **only** what they report. Do not use your memory of the wave,
and do not use the wave's own SUMMARY or FULL_RECORD.

```bash
python3 runners/status.py
python3 runners/dispatch.py validate
python3 runners/liveness.py <id> --json
python3 runners/wave_status.py <id> --show
cat handoffs/checkpoints/WAVE_<id>_CHECKPOINT.md
cat handoffs/halt_requests/WAVE_<id>_HALT.md   # if it exists
git rev-parse HEAD
```

If `validate` is dirty: **stop**. Fix the registry first. A resume directive
written on top of an inconsistent registry propagates the inconsistency into the
next session.

If liveness says **alive-progressing**: stop, and write no directive. The wave is
working. If it says **alive-paused**: the session holds warm context — write the
directive, then ping the human to paste it into the paused session rather than
relaunching.

## Step 2 — classify the interruption

Exactly one, and the distinction is load-bearing:

| class | when | what it implies |
|---|---|---|
| `interrupted` | the process is gone, work was banked | checkpoint-resume |
| `halted-<reason>` | the Wave General wrote HALT.md | read the reason; it may need a human first |
| `stalled-nothing-banked` | alive but wedged, **0** tasks banked | **clean restart** — there is nothing to recompute, and a partial resume would invent state |
| `stalled-partial` | alive but wedged, ≥1 task banked | checkpoint-resume, preserving what banked |
| `awaiting-bg` | a producer manifest is still RUNNING | do not relaunch to redo it; relaunch to *consume* when the hash validates |

## Step 3 — write `handoffs/halt_requests/WAVE_<id>_RESUME.md`

Every section is required. `dispatch.py validate` rejects a directive that does
not classify its interruption.

```markdown
# WAVE <id> RESUME DIRECTIVE
## Interruption class: <one of the five above>
## Verified on-disk state: <registry counts, banked tasks, artifacts count, git HEAD, what IS and IS NOT persisted>
## What to preserve: <persisted compute that must NOT be recomputed — cite the sha256 of each>
## What to (re)do: <the pending tasks; for stalled-nothing-banked write "clean restart, nothing to recompute">
## Recompute-vs-synthesize: <PER pending item: new compute → respawn a Subagent; pure synthesis of on-disk data → the Wave General drives it directly>
## Do NOT: double-launch if alive (C1); recompute persisted artifacts (A4); shorten any run to fit the window (B1); self-unfreeze a criterion (D3)
## Close: <the exact close sequence — local audit-trail timestamped BEFORE the SUMMARY (D2); independent audit PASS gate (D1); allow-listed commit (E2)>
## Principles: on-disk = truth; investigate WHY before adjusting a window; record ALL artifacts; promote nothing (the audit gates that).
```

**Per-item recompute-vs-synthesize is the section people skip and should not.**
Respawning a Subagent to "redo" something that is already on disk with a valid
hash burns a window re-deriving a fact the system already owns.

## Step 4 — hand it off

Write the directive, then relaunch through the guarded path — never the raw one:

```bash
bash handoffs/orchestrator/_spawn_wave.sh <id> --resume
```

It re-runs the liveness gate and refuses to launch beside a live session.

---

## The standard to write to

Write the directive so the resumed wave pursues the mission's principles **to a
greater extent than it was pursuing them before the interruption.** A recovery is
an opportunity to raise the bar, not merely to restore it. If the interruption
exposed something — a task that was under-specified, a criterion that was
brittle, a protocol step that got skipped under time pressure — say so in
`What to (re)do` and fix it in the resumed run.
