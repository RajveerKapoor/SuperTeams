# WAVE {{WAVE_ID}} FULL RECORD — {{MISSION}}

**Scaffolded:** {{CREATED_AT}}
**Tasks:** {{TASKS}}
**Artifact baseline:** {{BASELINE}}

> The unabridged wave record: every dispatch, every return, every banking, every
> surprise. Append-only. It exists so the **Auditor** can reconstruct what happened
> without asking anyone, and so a successor Wave General can resume cold.
>
> **The Orchestrator must NEVER read this file.** Its window into the wave is the
> ≤2000-word SUMMARY plus the AUDIT verdict. That boundary is what let the
> predecessor's Orchestrator coordinate 38 sub-waves without drowning in context.

---

## Dispatch ledger

| # | task | dispatched | returned | verdict | banked | checkpoint | notes |
|---|------|-----------|----------|---------|--------|-----------|-------|

## Per-task record

### TASK_____

**Frozen criterion at dispatch** (id + `frozen_at`):

**Brief given** (or a pointer into `WAVE_{{WAVE_ID}}_BRIEF.md`):

**Return** (verbatim JSON):

```json
```

**Disk validation before banking:**
- report exists: `reports/TASK_____.md`
- `shasum -a 256` matches the claimed `report_sha256`: yes / no
- artifacts logged: __ (`artifacts.jsonl` count before → after)

**Banking:** `dispatch.py update --disc TASK_____ --patch done.json` → exit __
**Checkpoint written:** <!-- timestamp -->

**Surprises, deviations, and what was done about them:**

<!-- repeat per task -->

---

## Interruptions

<!-- Every rate limit, kill, stall, laptop sleep. For each: what was in flight,
     what was banked, what the resume recomputed vs synthesized. An interruption
     handled honestly is a system working; an interruption papered over is the
     fabrication that poisons everything downstream. -->

## Background computes launched

| manifest | output path | launched | status | output_sha256 | consumer |
|---|---|---|---|---|---|

## Deviations from the PLAN

<!-- What the plan said, what actually happened, why. A methodology patch is
     normal and gets recorded here. A finding patch — pre-writing a conclusion
     into a downstream task — is forbidden; if one was tempting, say so and say
     what was done instead. -->

## Local acceptance checks

<!-- Commands run, exit codes, timestamps. The audit trail the Auditor re-runs. -->
