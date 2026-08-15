# ORCHESTRATOR HANDOFF — {{MISSION}}

**Mode:** {{MODE}}  ·  **Workspace:** {{WORKSPACE}}
**Written:** {{CREATED_AT}}  ·  **By:** (init)  ·  **To:** the first Orchestrator

> The rotation baton. The outgoing Orchestrator writes this, spawns its successor,
> and disarms its own babysit loop — in that order — so that **exactly one loop and
> exactly one Orchestrator exist at any instant.** Rotation every wave is what keeps
> the Orchestrator's context small enough to reason well; the predecessor's five-day
> single-session bloat is the failure this cures.
>
> This file is overwritten at each rotation. The durable narrative is
> `CAMPAIGN_LOG.md`; this is only "what the next mind needs in its first minute."

---

## 1. Where the mission stands

<!-- Three sentences. Not a history — a position. -->

## 2. What just closed

| wave | verdict | audit | one-line outcome |
|---|---|---|---|

## 3. What is in flight right now

- **Live wave:** <!-- id, state, or "none" -->
- **Background computes:** <!-- manifest paths + expected completion, or "none" -->
- **Babysit loop:** <!-- armed by whom, cadence, or "disarmed pending successor" -->
- **Open authorizations awaiting the human:** <!-- or "none" -->

## 4. The next decision you must make

<!-- The single thing your first act should address. Be specific enough that the
     successor does not have to re-derive the reasoning. -->

## 5. Live constraints

- Window: <!-- `window.py show` output at handoff time -->
- Weekly: <!-- used fraction, park ceiling, reset time -->
- Anything the human said recently that is not yet a Decision record

## 6. Judgment carried forward

<!-- What you learned about THIS mission that is not in any document: which
     estimates run long, which task types come back STUMPED, which parts of the
     domain are shakier than the plan assumes, where the criteria are brittle.
     This section is the actual value of a handoff. Write it honestly — a
     successor that inherits a rosier picture than the truth will plan badly. -->

## 7. Traps specific to this mission

<!-- The mistakes you nearly made, or made and corrected. Say what the mistake
     would look like from the inside, so the successor recognises it early. -->

---

## Successor's first five commands

```bash
python3 runners/status.py                  # the whole mission from disk
python3 runners/dispatch.py validate       # HOLD and fix if this is dirty
python3 runners/window.py show             # can a wave even fit right now?
python3 runners/roadmap.py frontier        # what is ready
cat handoffs/orchestrator/STEERING.md      # what the human asked for
```

Then read `ORCHESTRATOR_RUNBOOK.md` in full before touching anything. Read
`MISSION.md` before you read any plan — the plan is downstream of the charter, and
if they disagree, the charter wins and the plan is the bug.
