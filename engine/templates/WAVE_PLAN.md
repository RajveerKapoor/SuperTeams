# WAVE {{WAVE_ID}} PLAN — {{MISSION}}

**Scaffolded:** {{CREATED_AT}}
**Tasks:** {{TASKS}}
**Artifact baseline at scaffold:** {{BASELINE}}

> Written by the **Orchestrator**, executed by the **Wave General**.
> This file is context. The **frozen criterion in the REGISTRY is law** — the Wave
> General reads each task's criterion with `dispatch.py show --disc <TASK>`, never
> from the copies below, which go stale the moment anything is revised.

---

## 1. Why this wave exists

<!-- What does the mission gain when this wave closes? One paragraph. Name the
     downstream tasks that unblock. -->

## 2. Tasks in scope

{{TASK_LIST}}

For each task, the Orchestrator fills in:

| task | one-line goal | lens | depends on | est. hours | notes |
|---|---|---|---|---|---|

## 3. Window fit

- Estimated total: **__ h** of the window's budget
- Check before launch: `window.py show`
- If the wave does not fit, **cut tasks, never the protocol.** A wave that ends
  mid-task at a rate limit costs a window; a wave with one fewer task costs one task.

## 4. Dispatch order (serial — this is the whole protocol)

1. `TASK_____` — dispatch, await, validate against disk, bank, checkpoint
2. `TASK_____` — …

**At most one task's work is unbanked at any instant.** No parallel Subagent
spawns inside a wave. Cross-wave parallelism is the Orchestrator's call, made
with the window budget in hand — never the Wave General's.

## 5. Protocol per task

<!-- Method, tools, data, what "good" looks like. The Subagent brief is built from
     this plus the frozen criterion. Give no wall-clock cap: quality is the only
     metric, and a long compute goes to the background-compute contract. -->

## 6. Known hazards for this wave

<!-- What is likely to go wrong here, drawn from doctrine/06. E.g. a tool that
     hangs (TIMEOUT, never a return value); a criterion whose file pointer may be
     stale (expect REVISED, never self-unfreeze); a compute that may exceed the
     window (manifest first, then background Bash). -->

## 7. Escalation points

<!-- Where the Wave General should HALT rather than improvise. Everything not
     listed here it handles itself and records. -->

## 8. Acceptance for the wave as a whole

- [ ] every task non-pending (DONE / FAILED / STUMPED / DEFERRED / REVISED / TRIVIAL)
- [ ] every completion has a persisted, hashed artifact (`dispatch.py` exit 7 proves it)
- [ ] local acceptance checks run and the audit-trail log timestamped
- [ ] **independent cold audit requested and PASS** — the doer never audits itself
- [ ] `WAVE_{{WAVE_ID}}_SUMMARY.md` written (≤2000 words), *after* the audit timestamp
- [ ] `close_wave.py {{WAVE_ID}}` accepted
