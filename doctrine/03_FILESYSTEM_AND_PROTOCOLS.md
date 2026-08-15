# 03 — Filesystem Layout and Protocols

The filesystem is the durable source of truth and the communication bus. This document specifies every
directory, every file, its owner (who writes), its readers, and the protocols that move state between
roles. It keeps the predecessor's `handoffs/` tree and `REGISTRY`/`artifacts.jsonl`/`runners/`/
`reports/` layout — the same names the operator already knows — and generalizes only the contents.

---

## 1. Two roots: the engine and the mission workspace

**The engine** is the reusable subset, installed once and independent of any mission:

```
~/superteam/
  runners/                       # the CLI family (KEPT from the predecessor + small new helpers)
    dispatch.py                  # atomic REGISTRY merger — fcntl.flock + optimistic version + tmp/fsync/rename
    replay.py                    # re-derive any claim from its recorded recipe; check artifact hash
    inspect_registry.py          # read-only views (--status, --stumps, --unaudited, --promotions)
    pre_register.py              # freeze the acceptance criteria (definition-of-done)
    roadmap.py                   # NEW: the DAG — frontier, pack a window-sized wave, add-task
    new_wave.py                  # NEW: scaffold handoffs/{waves,briefs,status,...} for a wave
    wave_status.py               # NEW: schema-validated STATUS.json writer
    checkpoint.py                # NEW: schema-validated CHECKPOINT.md writer
    close_wave.py                # NEW: the wave-close gate (refuses unless WAVE_x_AUDIT.md PASS precedes)
    log_artifact.py              # NEW: append a Curiosity-Protocol artifact line to artifacts.jsonl
    park.py / resume.py          # NEW: graceful park / resume across the weekly cap
    window.py                    # NEW: rate-limit window + weekly-cap tracker
    status.py                    # NEW: one-shot human catch-up ("where are we")
    init_workspace.py            # NEW: scaffold a mission workspace
  lenses/                        # pluggable Curiosity-Protocol lenses (research/engineering/ops/writing/generic)
  curiosity/ stats/ repro/       # reusable libs (research lens's constants.py, seed/env manifest, etc.)
  schemas/                       # JSON Schemas for every REGISTRY entry type + handoff file
  handoffs/waves/                # the canonical charters (templates, copied into a mission on init)
    ORCHESTRATOR_RUNBOOK.md
    WAVE_GENERAL_OPERATING_MANUAL.md
    WAVE_INDEX.md
  bin/
    _spawn_wave.sh _launch_wave.sh _spawn_orchestrator.sh _launch_orchestrator.sh _commit.sh
  VERSION
```

**A mission workspace** is created per goal (`init_workspace.py <mission>`) and follows the
predecessor's `verification/` tree exactly, generalized:

```
<mission>/
  MISSION.md                     # the charter: goal, definition of done, constraints, no-go list, mode
  REGISTRY.json                  # the typed entry store — atomic, versioned (04_REGISTRY_AND_DISPATCH)
  REGISTRY.audit.log             # append-only audit of every mutation
  REGISTRY.lock                  # fcntl lock file (git-ignored; transient)
  artifacts.jsonl                # append-only Curiosity-Protocol pool (every artifact the work produced)
  runners/                       # dispatch.py etc. (pinned copy/symlink of the engine for this mission's version)
                                 #   + per-task scripts the Subagents write (e.g. _wave2k_sub1_*.py)
  reports/                       # per-task reports: <TASK_ID>.md + WAVE_<id>_SUB<n>_NOTES.md
  datasets/                      # produced outputs + their .manifest.json (the background-compute contract)
  systems/ lib/ …                # domain work products (engineering: the repo; research: the models; etc.)
  handoffs/
    waves/                       # WAVE_<id>_PLAN.md  +  the three charters (copied from engine)
    briefs/                      # WAVE_<id>_BRIEF.md         (Orchestrator → Wave General launch prompt)
    summaries/                   # WAVE_<id>_SUMMARY.md       (Wave General → Orchestrator, ≤2000 words)
    status/                      # WAVE_<id>_STATUS.json      (heartbeat)
    checkpoints/                 # WAVE_<id>_CHECKPOINT.md    (resume state after every task)
    full_records/                # WAVE_<id>_FULL_RECORD.md   (unbounded audit trail) + final-audit logs
    halt_requests/               # WAVE_<id>_HALT.md, WAVE_<id>_RESUME.md
    orchestrator/                # the Orchestrator's own space:
      CAMPAIGN_LOG.md            #   append-only narrative
      WAVE_LAUNCH_QUEUE.md       #   ordered queue + dependencies + status marks
      AUTO_ADVANCE_POLICY.md     #   this mission's touchpoint + auto-advance tuning
      ORCHESTRATOR_HANDOFF.md    #   the role handoff template
      SESSION_HANDOFF_<iso>.md   #   session-rotation handoffs
      WAVE_<id>_AUDIT.md         #   the independent audit verdicts (the completion gate)
      WINDOW_STATE.json          #   NEW: rate-limit window + weekly-cap tracker
      ROADMAP.md                 #   NEW: the DAG rendered + rationale
      STEERING.md                #   NEW: human → Orchestrator directive inbox (read at every boundary)
      INBOX.md / OUTBOX.md       #   NEW: human ↔ system message log / batched digest
      _spawn_wave.sh _launch_wave.sh _spawn_orchestrator.sh _launch_orchestrator.sh
      _wave<id>_monitor_baseline.json   # the artifacts-count baseline the babysit loop diffs against
```

Two choices worth stating:

- **The workspace mirrors the predecessor's `verification/`.** An engineering mission's workspace can
  *be* its code repo (with `REGISTRY.json` + `handoffs/` alongside the code, as the predecessor lived
  inside the repo it studied); a standalone research mission is a fresh directory. The names are
  unchanged so nothing about navigating it has to be re-learned.
- **New human-facing files live under `handoffs/orchestrator/`.** `STEERING.md`, `INBOX.md`,
  `OUTBOX.md`, `WINDOW_STATE.json`, `ROADMAP.md` are the only genuinely new files; everything else is
  the predecessor's. `AUTO_ADVANCE_POLICY.md` already existed and is the touchpoint policy.

---

## 2. File ownership and access matrix

The matrix is a *contract*, and several entries are load-bearing safety properties (a role that must
not read a file is how the context budget is enforced).

| Path | Writer | Readers | Notes |
|---|---|---|---|
| `MISSION.md` | Orchestrator (on scope change, with authorization) | all | The charter. Changes are Decisions. |
| `REGISTRY.json` | **only `dispatch.py`** (atomic) | all read freely | Truth. Never hand-edited. |
| `REGISTRY.audit.log` | `dispatch.py` | Orchestrator, audit | Append-only forensic chain. |
| `artifacts.jsonl` | Subagents (append via `log_artifact.py`) | audit, harvest | Append-only. Orchestrator never ingests the body. |
| `reports/<TASK>.md` | Subagent owning the task | audit, downstream Subagents | Per-task report + NOTES. |
| `datasets/**` + `*.manifest.json` | producer Subagent | audit, consumers | Background-compute outputs + provenance. |
| `handoffs/waves/WAVE_<id>_PLAN.md` | Orchestrator | Wave General | Wave plan. |
| `handoffs/briefs/WAVE_<id>_BRIEF.md` | Orchestrator | Wave General terminal (launch) | Launch prompt. |
| `handoffs/status/WAVE_<id>_STATUS.json` | Wave General (`wave_status.py`) | Orchestrator, babysit loop | Heartbeat. |
| `handoffs/checkpoints/WAVE_<id>_CHECKPOINT.md` | Wave General (`checkpoint.py`) | relaunched Wave General | Resume state. |
| `handoffs/full_records/WAVE_<id>_FULL_RECORD.md` | Wave General | **audit only** (never Orchestrator) | Unbounded audit trail. |
| `handoffs/summaries/WAVE_<id>_SUMMARY.md` | Wave General | Orchestrator | ≤2000 words. Cross-role currency. |
| `handoffs/orchestrator/WAVE_<id>_AUDIT.md` | **auditor (cold)** | Orchestrator | Completion gate. |
| `handoffs/halt_requests/WAVE_<id>_HALT.md` | Wave General | Orchestrator | Halt escalation. |
| `handoffs/halt_requests/WAVE_<id>_RESUME.md` | Orchestrator (`/revive`) | relaunched Wave General | Resume directive. |
| `handoffs/orchestrator/CAMPAIGN_LOG.md` | Orchestrator | Orchestrator, human | Append-only narrative. |
| `handoffs/orchestrator/STEERING.md` | **human** | Orchestrator (at boundaries) | The steering channel. |
| `handoffs/orchestrator/OUTBOX.md` | Orchestrator, babysit loop | **human** | The digest out. |
| `handoffs/orchestrator/SESSION_HANDOFF_<iso>.md` | outgoing Orchestrator | incoming Orchestrator | Session rotation. |

The two structurally important "never reads":
- **The Orchestrator never reads `FULL_RECORD.md` or `artifacts.jsonl`.** Its context stays small
  because its only window into a wave is the ≤2000-word `SUMMARY.md` plus the `WAVE_<id>_AUDIT.md`
  verdict. This is the exact discipline that let the predecessor's Orchestrator coordinate 38 sub-waves
  without drowning.
- **The auditor never reads the Wave General's `SUMMARY.md` before auditing.** The SUMMARY is the
  doer's story; the auditor must form its own verdict from the artifacts + frozen criteria, then
  compare. (It may read the SUMMARY *after* forming its verdict, to reconcile.) This preserves
  independence.

---

## 3. The handoff protocol (the durable channel)

All cross-role, cross-session state moves through files, because sessions die and messages don't
survive them. Each transfer is a small, named, schema-validated file — the predecessor's exact
protocol.

**Orchestrator → Wave General (launch a wave).** Orchestrator writes `WAVE_<id>_PLAN.md` (full plan)
and `WAVE_<id>_BRIEF.md` (launch prompt, referencing the plan + operating manual + the specific
`REGISTRY` entry ids in scope). It launches the Wave General with `_spawn_wave.sh <id> auto`. The Wave
General reads: operating manual → wave plan → the frozen criteria from `REGISTRY` (not the plan's
copies — a plan carries stale precisions).

**Wave General → Subagent (dispatch a task).** The Wave General builds a **self-contained brief** from
a template (§7 of `04`) containing: the task id, the frozen acceptance criterion *quoted from
`REGISTRY` by id*, the protocol, the tools/lenses available, the dependencies (which must be COMPLETED
in `REGISTRY`), the output requirements (report path + artifact-logging + the small structured return),
and the Curiosity Protocol inline. The Subagent never has to find its own instructions.

**Subagent → Wave General (return a result).** The Subagent returns a JSON object (≤3000 tokens) —
verdict, value(s), CI/confidence, methods, side-findings, blocker-or-null, report path + report hash.
Detailed reasoning lives in `reports/<TASK>.md`, not the return. The Wave General validates the return
against disk (report exists? hash matches? artifacts logged?) before banking.

**Wave General → REGISTRY (bank a result).** `dispatch.py update --disc <TASK> --patch <patch.json>` —
atomic, version-checked. Then `checkpoint.py <wave>`. Then the next Subagent. **Never batched** — bank
each before dispatching the next (the serial-banking rule; §5).

**Wave General → Orchestrator (close a wave).** After all tasks are non-pending and the audit PASSED,
the Wave General writes `SUMMARY.md` + `STATUS.json`, commits, exits. The Orchestrator ingests only
these.

**Wave General → Orchestrator (halt).** On a genuine halt trigger, the Wave General writes `HALT.md`
(reason category + what-it-needs + options), sets `STATUS.json.state = HALTED`, checkpoints, and exits
cleanly — no looping, no workaround. The Orchestrator responds with `RESUME.md` (the `/revive` step).

**Orchestrator → Orchestrator (rotate).** On wave close + clean audit + advance, the outgoing
Orchestrator writes `SESSION_HANDOFF_<iso>.md`, spawns its successor (`_spawn_orchestrator.sh`), and
disarms its own babysit loop (`CronDelete`).

---

## 4. STATUS.json — the heartbeat schema

The single most-polled file. Small, cheap, the babysit loop's primary signal (cross-checked against
process liveness and the artifacts delta — never trusted alone). Written by `wave_status.py`
(schema-validated), so the predecessor's "STATUS.json missing several conventional fields" drift cannot
recur — a missing required field is a validation error.

```json
{
  "wave_id": "2k",
  "state": "RUNNING",
  "state_enum": "PLANNED|RUNNING|HALTED|AWAITING_BACKGROUND_COMPUTE|COMPLETE|FAILED",
  "wavegen_session": "wave-2k-general",
  "wavegen_pid_hint": 54120,
  "tasks_total": 3,
  "tasks_done": 2,
  "task_in_progress": "TASK_0031",
  "tasks_pending": ["TASK_0033"],
  "artifacts_at_start": 1940,
  "artifacts_now": 1972,
  "last_checkpoint_at": "2026-07-03T09:14:00Z",
  "audit_state": "NOT_REQUESTED|REQUESTED|PASS|FAIL|PASS_WITH_NOTES",
  "deferred_compute": [{"task": "TASK_0033", "manifest": "datasets/matrix.manifest.json"}],
  "summary_path": null,
  "final_audit_at": null,
  "next_action": "dispatch TASK_0032"
}
```

---

## 5. The serial-banking protocol (the #1 rate-limit defense)

Elevated from "a discipline the Wave General should follow" to a *protocol its tooling enforces*,
because it was the predecessor's most expensive lesson: a Wave General once parallel-spawned four
Subagents in one message; the batch blew a fresh 5-hour window in ~68 minutes and **persisted nothing**
— all four were in-flight when the limit hit. It became memory pin #11, "the #1 rate-limit defense."

The protocol, per Subagent, in strict order:
1. Dispatch exactly **one** Subagent.
2. Wait for its return (via the native completion callback — not a tight poll).
3. **Validate** against disk: report exists, report hash matches, artifacts appended.
4. **Bank** atomically: `dispatch.py update`.
5. **Checkpoint**: `checkpoint.py <wave>` — the wave is now resumable from exactly here.
6. **Only then** dispatch the next Subagent.

The invariant: **at any instant, at most one task's work is unbanked.** A rate limit, a laptop sleep,
or a kill can cost at most the single in-flight task, never a whole window. A fresh Wave General
resuming from the checkpoint re-dispatches only that one task (reverting its `REGISTRY` state from
IN_PROGRESS to PENDING). The predecessor's serial resume "banked atomically, no batch lost" — this
makes that the only possible outcome.

Parallelism is not forbidden globally — the *DAG* is parallel, and independent waves could run in
parallel sessions if the human enables it and the window budget allows. But *within a wave*, Subagents
are serial-banked. Parallelism across waves is a scheduling choice the Orchestrator makes with the
window budget in hand; parallelism within a wave is the trap that loses windows.

---

## 6. Git discipline

The workspace is committed on `main` (or a mission branch), never pushed unless the human asks. Two
hard rules, both traced to real predecessor incidents:

- **Commit staging is explicit and allow-listed** (`_commit.sh`). Stage only the `handoffs/`,
  `REGISTRY.json`, `artifacts.jsonl`, `reports/`, `runners/`, `datasets/` paths the role owns, and
  **never** stage unrelated user files, `.DS_Store`, a parallel human-owned track sharing the repo, or
  `REGISTRY.lock`. The predecessor twice swept pre-staged non-orchestrator files into a commit; the cure
  is allow-listed staging that refuses anything outside the list and prints what it skipped.
- **Never `git push`, `git reset --hard`, `git rebase`, or `--no-verify`** without an explicit,
  recorded human Decision. These are the irreversible actions of Law 2.

---

## 7. Schema validation as a gate

Every REGISTRY entry and handoff file has a JSON Schema under `~/superteam/schemas/`. `dispatch.py
validate` checks the whole workspace: REGISTRY integrity (§4 of `04`), every STATUS/CHECKPOINT/manifest
against its schema, and cross-references (every artifact referenced by an entry exists, every
dependency id exists, no orphan IN_PROGRESS states). The babysit loop runs `dispatch.py validate` on
every tick; a validation failure is a HOLD-and-flag, never an auto-advance. This turns the
predecessor's class of "bookkeeping convention drift" bugs (missing NOTES files, mislabeled hashes,
ad-hoc state strings, inconsistent artifact counts) into hard, detected errors instead of silent,
accumulating rot.
