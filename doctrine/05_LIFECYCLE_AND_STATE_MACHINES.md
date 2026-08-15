# 05 — Lifecycles and State Machines

Three nested state machines govern the system: the **mission** (weeks), the **wave** (one window),
and the **task** (one subagent). Each transition names who may cause it and what must be true on disk
for it to be legal. The predecessor's lifecycle was implicit in prose across the runbook and manual;
here it is explicit, because an unattended system that runs for weeks cannot rely on a human
remembering the legal transitions.

---

## 1. The mission lifecycle

```
             init_workspace.py        Orchestrator decomposes        freeze
  ┌──────┐ ───────────▶ ┌──────┐ ───────────────▶ ┌───────────┐ ──────▶ ┌──────────┐
  │ NONE │              │ INIT │                   │  PLANNED  │         │  ACTIVE  │
  └──────┘              └──────┘                   └───────────┘         └────┬─────┘
                                                                              │  (Orchestrator loops waves)
                                                        ┌─────────────────────┤
                                                        │                     │
                                              persistent│              finite │ all leaves DONE
                                                intake   │                     ▼
                                                        │              ┌──────────────┐
                                                        │              │  SYNTHESIS   │  (Orchestrator-only wave)
                                                        │              └──────┬───────┘
                                                        │                     ▼
                                                        ▼              ┌──────────────┐
                                                   (never ends)        │     DONE     │
                                                                       └──────────────┘

  Any state ──human "stop"/weekly cap──▶ PARKED ──resume.py──▶ (prior state, from disk)
```

- **INIT → PLANNED:** the Orchestrator (or a planning subagent it spawns for a large decomposition)
  turns `MISSION.md` into a DAG of tasks with draft criteria in the registry. Nothing is frozen yet;
  the human may review `ROADMAP.md` and drop steering.
- **PLANNED → ACTIVE:** `pre_register.py` locks every task's acceptance criterion. This is the
  anti-goalpost-moving line: after it, no subagent can change what "done" means. The babysit loop is
  armed; the first wave launches.
- **ACTIVE loop:** the Orchestrator repeatedly packs a wave from the DAG frontier, launches a Wave General, banks
  the closed+audited wave, re-plans on surprise, rotates itself. This is the steady state, and it is
  where the system spends 99% of its life.
- **finite → SYNTHESIS → DONE:** when every leaf task is DONE, a final Orchestrator-only wave produces the
  mission deliverable (report, merged branch, shipped artifact) and the mission reaches DONE. The
  human is pinged.
- **persistent:** there is no leaf-exhaustion; the Orchestrator ingests new tasks from the intake channel
  each boundary and never terminates. "Done" is replaced by "healthy and current."
- **PARKED:** on a weekly-cap hit or a human "stop," `park.py` writes a park-state, disarms the
  babysit loop, and the system sleeps. `resume.py` re-derives everything from disk and continues.
  Parking is graceful, not a crash — the distinction that lets the system survive multi-day rate-limit
  resets (the predecessor rode out "a multi-day weekly reset" mid-wave exactly this way).

---

## 2. The wave lifecycle (the workhorse)

A wave is one Wave General session, one ~5h window, a set of frontier tasks. Its states are the ones the
babysit loop classifies on every tick.

```
   Orchestrator packs + launches
  ┌─────────┐ ─────────────▶ ┌──────────┐   Wave General serial-banks tasks   ┌─────────────┐
  │ PLANNED │                │ RUNNING  │ ───────────────────────────▶│  AUDITING   │
  └─────────┘                └────┬─────┘   (all tasks non-pending)    └──────┬──────┘
                                  │                                           │ Auditor verdict
              ┌───────────────────┼───────────────────┐                       │
     halt     │          window   │        long       │                       ▼
     trigger  ▼          exhausted▼        compute     ▼             PASS ┌──────────┐  FAIL
          ┌────────┐   ┌──────────────┐  ┌────────────────────────┐  ────▶│ COMPLETE │  ───┐
          │ HALTED │   │ INTERRUPTED  │  │ AWAITING_BG_COMPUTE     │       └──────────┘     │
          └───┬────┘   └──────┬───────┘  └───────────┬────────────┘                         │
              │ RESUME.md     │ fresh Wave General           │ output ready + hash OK               │
              ▼               ▼ from CHECKPOINT       ▼ (Wave General relaunch)                      ▼
          (RUNNING)       (RUNNING)              (RUNNING)                            re-plan / re-run
```

Transitions and their disk preconditions:

- **PLANNED → RUNNING:** a Wave General session is live and has read the plan + the frozen claims. `STATUS.json`
  flips to RUNNING.
- **RUNNING → AUDITING:** every task in scope is non-pending in the registry (DONE/FAILED/BLOCKED/etc).
  The Wave General runs its local audit-trail (the deterministic acceptance checks), *then* requests an
  independent Auditor. The ordering is enforced: the local audit-trail must timestamp before the
  SUMMARY asserts anything (the predecessor's Wave-0a lesson, now a `close_wave.py` precondition).
- **AUDITING → COMPLETE:** the auditor writes `WAVE_<id>_AUDIT.md` with PASS, timestamped before
  `close_wave.py` runs. `close_wave.py` refuses (Law 4) if there is no PASS or if its timestamp is after
  the close attempt. This is the completion gate that makes "audit before you assert done" impossible to
  skip.
- **AUDITING → re-plan/re-run (on FAIL):** an audit FAIL is not swept under the rug and it is not
  auto-fixed by the same mind. The Orchestrator is pinged (touchpoint tier: decision), the failing claim is
  reverted to UNAUDITED, and the Orchestrator either commissions a corrective task or escalates. The
  predecessor's `/audit` command's whole spirit — "champion a redoing of the wave if quality/
  curiosity/resilience fell short" — lives here as a gated transition.
- **RUNNING → HALTED:** a genuine halt trigger fired (a needed authorization, a contradiction with
  disk, a frozen-window conflict, a corrupted kernel, a plan directive to escalate). The Wave General writes
  `HALT.md`, checkpoints, exits cleanly. **It does not loop, retry, or improvise a workaround.** The
  The Orchestrator responds with `RESUME.md` (`/revive`).
- **RUNNING → INTERRUPTED:** rate limit, laptop sleep, killed process, closed terminal. There may be no
  clean SUMMARY. `CHECKPOINT.md` is the protection: a fresh Wave General reads it, reconciles against the
  registry (registry wins), reverts any orphan IN_PROGRESS to PENDING, and resumes from the first pending
  task. Because banking is serial, at most one task is re-done.
- **RUNNING → AWAITING_BG_COMPUTE:** a task needs compute that outlives the session. The Wave General records
  the manifest + shell id in the checkpoint, sets STATUS, and exits cleanly; the background process
  keeps running under the OS. On relaunch the Wave General polls the manifest, validates the hash, and spawns
  the consumer. (Full contract in `07` §4.)

---

## 3. The task lifecycle (one subagent)

```
   deps DONE          dispatch.py update        subagent returns + banked
  ┌──────────────┐ ─────────▶ ┌──────────────┐ ─────────▶ ┌────────────────────────────┐
  │ BLOCKED_ON_  │            │ IN_PROGRESS  │            │ DONE | FAILED | STUMPED |   │
  │    DEPS      │            └──────┬───────┘            │ DEFERRED | REVISED | TRIVIAL│
  └──────────────┘                  │                    └────────────────────────────┘
        ▲  deps not DONE            │ session dies mid-task
        │                          ▼
   (dispatch.py update rejects, exit 8)  reverted to PENDING on resume (no orphan IN_PROGRESS)
```

The task's terminal verdict is one of the honest set (`04` §2). The banking gate (`dispatch.py update`,
exit 7) makes DONE require a persisted, hashed, re-derivable artifact. STUMPED requires an
`unblock_criterion`. REVISED requires the `criterion_mismatch_flag` and a surfaced description. There
is no "silently passed" transition — every terminal state is honest by construction.

---

## 4. Re-planning: how the DAG stays alive

The predecessor's queue was mostly static and it deliberately avoided pre-loading conclusions into
downstream plans. The generalization keeps that discipline but makes the DAG *adaptive*, with a
precise protocol for the two kinds of change:

**Methodology change (allowed, automatic).** A wave discovers that *how* a downstream task should be
done must change (wrong data source, a needed tool, a superseded technique). The Orchestrator (or a
planning subagent for a big change) patches the downstream task's protocol and, if needed, its *draft*
criterion — but only if that criterion is not yet frozen, or via an audited unfreeze if it is. This is
a Decision record.

**Finding change (forbidden as a patch).** A wave discovers that an *assumption a downstream task will
test* was wrong. The system does **not** pre-write the conclusion into the downstream task. It records
the finding in `LOG.md` for situational awareness and lets the downstream task rediscover it
independently through its own honest process — a free second check on the first (Law 8). The Orchestrator's
re-plan review rejects any patch that pre-stages a conclusion.

**Invalidation (structural).** A wave's result can make downstream tasks *moot* (a branch is dead) or
*newly-required* (a surprise opened a question). A planning subagent revises the DAG: dead branches
move to a `SUPERSEDED` state (kept for audit, not executed); new tasks are added with draft criteria and
frozen before they run. Re-planning that changes the *shape* of the graph is done in an isolated
planning-subagent session precisely so it doesn't bloat the Orchestrator.

**Re-plan triggers** (any of these makes the babysit loop flag the Orchestrator, which may spawn a
planning subagent):
- an audit FAIL that implicates the mission's structure, not just one task;
- a task returning REVISED/DEFINITION-DEPENDENT that changes what a whole branch means;
- the human dropping a steering directive that redirects the goal;
- a persistent-mode intake event adding a new frontier;
- the window budget repeatedly under-fitting (waves too big) or over-fitting (waves too small).

---

## 5. Who may cause what (the authority table)

| Transition | Legal causer | Illegal for |
|---|---|---|
| freeze a criterion | Orchestrator (via `pre_register.py`) | Subagent, Wave General |
| unfreeze a criterion | Orchestrator **with a cited Authorization** | anyone without an AZ record |
| start a task | Wave General (deps must be DONE) | — |
| complete a task | Wave General, only after artifact validates | Subagent directly (it returns; Wave General banks) |
| close a wave | Wave General, only after an audit PASS | Wave General without an audit |
| audit verdict | **the cold auditor session** (independent) | the Wave General that ran the wave |
| re-shape the DAG | a planning subagent (or Orchestrator for small edits) | Subagent |
| escalate to human | Orchestrator/babysit loop per touchpoint policy | Subagent (it returns STUMPED; the Wave General/Orchestrator escalates) |
| rotate a session | the session itself, on its trigger | — |
| park/resume | babysit loop (cap) or human (stop) | — |

The single most important separation in this table: **the audit verdict is the one thing the doer
may never issue.** Everything else can be same-mind; the completion gate cannot.

---

## 6. A worked wave (concrete trace)

To make the machinery tangible, here is one wave, start to close, in an engineering mission.

1. **Orchestrator** runs `roadmap.py frontier`, sees `TASK_0031, TASK_0032, TASK_0033` PENDING with
   deps met, and `roadmap.py pack --window-budget 4.5h` proposes all three (est 1.2h + 0.8h + 2.0h =
   4.0h < budget). It runs `new_wave.py 2k --tasks TASK_0031,TASK_0032,TASK_0033`, writes
   `WAVE_2k_PLAN.md` + `WAVE_2k_BRIEF.md`, and spawns the Wave General: `_spawn_wave.sh 2k auto`.
2. **Wave General** reads `WAVE_GENERAL_OPERATING_MANUAL.md` → `WAVE_2k_PLAN.md` → the three frozen
   criteria from `REGISTRY`. It dispatches a Subagent for `TASK_0031` (in-session `Agent`,
   model=capable, lens=engineering).
3. **Subagent TASK_0031** refactors, runs the acceptance check (`pytest tests/config && grep -rn
   _GLOBAL_CFG`), persists the pytest log + diff to `reports/TASK_0031_*`, `log_artifact.py`s them,
   runs the Curiosity Protocol (logs a surprising perf regression it noticed as a side-finding),
   returns `{verdict: DONE, report_path, report_sha256, artifacts:[ART_0044,ART_0045]}`.
4. **Wave General** validates: report exists, hash matches, artifacts logged. `dispatch.py update --disc
   TASK_0031 --patch done.json` (exit 0). `checkpoint.py 2k`. **Only now** dispatches `TASK_0032`.
5. `TASK_0032` returns STUMPED (needs a credential the Wave General doesn't have). `dispatch.py update`
   with verdict STUMPED + unblock_criterion "needs staging DB read creds." Checkpoint. Dispatch
   `TASK_0033`.
6. `TASK_0033` needs a 90-minute build+test matrix → returns DEFERRED-COMPUTE-RUNNING with a background
   manifest; the Wave General sets STATUS `AWAITING_BACKGROUND_COMPUTE`, checkpoints, and — because its
   window still has budget — arms a `Monitor` on the manifest's completion instead of tight-polling.
7. Monitor fires: output ready, hash validates. Wave General spawns the consumer Subagent, which reads
   the persisted matrix result and banks `TASK_0033` DONE.
8. All three tasks non-pending. Wave General runs the local acceptance checks, timestamps the
   audit-trail log, and requests the independent audit (`_spawn_wave.sh audit-2k auto`, a cold session).
9. **The cold audit** reads only the frozen criteria + the artifacts, re-derives `CLAIM_0031` (re-runs
   the grep + pytest at the recorded commit), re-derives the deferred matrix claim from its manifest,
   and writes `WAVE_2k_AUDIT.md: PASS`. (It flags the STUMPED task as correctly STUMPED, not a failure.)
10. **Wave General** `close_wave.py 2k` (gate passes: audit PASS timestamp precedes close), writes
    `WAVE_2k_SUMMARY.md` + `WAVE_2k_STATUS.json: COMPLETE`, `_commit.sh`, exits.
11. **babysit loop** tick sees COMPLETE + audit PASS + `dispatch.py validate` clean → auto-advances:
    updates `WAVE_LAUNCH_QUEUE.md` + `CAMPAIGN_LOG.md`, packs the next wave, and (because the touchpoint
    policy says nothing here is a decision) posts a one-line digest to `OUTBOX.md` rather than a
    `PushNotification`. The Orchestrator rotates its session. The loop continues while the human sleeps.

That trace is the system's entire life in miniature: serial banking, honest verdicts, a deferral that
survives its session, an independent audit gate, and an auto-advance that never wakes the human for a
non-decision.
