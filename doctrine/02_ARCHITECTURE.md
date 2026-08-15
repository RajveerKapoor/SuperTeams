# 02 — Architecture

## 0. The reconception

The predecessor was a three-tier hierarchy hard-specialized to one job: verify 86 chaos-theory
discoveries. Its unit of work was "a discovery," its unit of dispatch was "a wave," and its whole
vocabulary (integrators, Benettin, RMT, the constants library) was physics.

The generalization keeps the predecessor's **names and structure** — Orchestrator, Wave General,
Subagent, waves, `REGISTRY.json`, `dispatch.py`, the `handoffs/` tree, the `babysit loop`, the
Curiosity Protocol — and lifts only the *domain* out of them. A single substitution, repeated:

| Predecessor (physics-specific) | SuperTeam (general, same names) |
|---|---|
| a *discovery* to verify | a **task** — a node in a living dependency DAG (still a `REGISTRY` entry) |
| a *wave* (one terminal, one 5h window) | a **wave** — a window-sized batch of ready tasks (unchanged) |
| the *Orchestrator* | the **Orchestrator** (unchanged) |
| the *Wave General* | the **Wave General** (unchanged) |
| a *Subagent* | a **Subagent** (unchanged) |
| *REGISTRY.json* of 86 verdicts | *REGISTRY.json* of typed entries: tasks, claims, artifacts, decisions, authorizations |
| the *falsification criterion* | the frozen **acceptance criterion** (definition of done) — same `pre_registered` block |
| the *Curiosity Protocol* (constants + τ + BH) | the **Curiosity Protocol** with pluggable domain **lenses** (research is one lens) |
| the *babysit loop* | the **babysit loop** (unchanged; now harness-native `Cron`) |
| *chaos physics* | **any domain** — research, engineering, operations, writing, anything |

Nothing about the machinery was ever really physics. The predecessor's `systems/` directory already
proved this: over its life it swapped the double pendulum for the standard map, the Lorenz system, a
coupled-quartic Hamiltonian, and Hénon–Heiles, reusing the identical `dispatch.py` / `REGISTRY` /
`handoffs/` / background-compute machinery each time. The generalization finishes that job: lift the
last physics assumptions out of the kernel and make the domain a *pluggable lens*, not a hard-coded
core — while renaming nothing the operator already knows.

---

## 1. The roles

The three tiers are exactly the predecessor's, with the same names and the same reason for existing
(absorb context shock so the role that reasons about the *whole* campaign never ingests the *raw
output* of the work). Two specialist functions the predecessor performed ad hoc — the `/audit` pass
and heavy re-planning — are given a clean home. Each role has a single responsibility, a hard context
budget, a written charter it reads on spawn, and an explicit read/write allow-list.

### Orchestrator — owns the campaign (unchanged)
- Holds the mission charter, the DAG, and the roadmap; verifies dependencies; packs the next wave;
  writes its `PLAN.md` + `BRIEF.md`; launches the Wave General; on wave close, ingests **only** the
  Wave General's ≤2000-word `SUMMARY.md` + `STATUS.json` + the audit verdict; appends `CAMPAIGN_LOG.md`;
  runs the `babysit loop`; responds to `HALT.md` with `RESUME.md` (the `/revive` step); re-plans on
  surprise; and **rotates its own session** each wave (`SESSION_HANDOFF_<date>.md`).
- **Context budget — strict.** Reads freely: wave `SUMMARY`/`STATUS`, `WAVE_<id>_AUDIT.md`, targeted
  `REGISTRY` lookups, the steering inbox, `WINDOW_STATE.json`. **Never** ingests: a Subagent's raw
  output, a wave's `FULL_RECORD.md`, `artifacts.jsonl`, or per-task `reports/*.md` bodies. This is the
  predecessor's exact discipline ("never ingest a wave's raw tool output, only its SUMMARY"), and here
  the Orchestrator's charter lists the forbidden paths explicitly.

### Wave General — owns one wave (unchanged)
- One wave, one session, one ~5h rate-limit window. Reads `WAVE_GENERAL_OPERATING_MANUAL.md` → its
  `WAVE_<id>_PLAN.md` → the frozen criteria from `REGISTRY` (not the plan's copies of them). Decomposes
  the wave into Subagent tasks; dispatches Subagents **serially**; after each returns,
  **validate → bank atomically via `dispatch.py` → checkpoint** before the next; appends
  `FULL_RECORD.md` continuously; on scope complete, runs the local audit-trail, requests the
  independent audit, writes `SUMMARY.md` + `STATUS.json`, commits, exits.
- **One Wave General per wave, ever.** The `REGISTRY`'s optimistic-version guard makes a second Wave
  General's writes fail loudly rather than corrupt state.

### Subagent — executes one task (unchanged)
- One task. Reads a self-contained brief (which cites the frozen criterion by `REGISTRY` id); does the
  work at full fidelity; persists every artifact to disk with a hash; runs the Curiosity Protocol over
  everything it produced; returns a small structured result (≤3000 tokens). Hits a wall → writes what
  it has, returns `STUMPED` with an unblock criterion. **No wall-clock cap** — quality is the only
  metric; a genuinely long compute is handed to the background-compute contract (`07`), never shortened.

### The independent audit (the `/audit` pass, run cold) — refined
- The predecessor ran `/audit` **inside the Orchestrator's own session** ("independently re-derive
  every load-bearing number"). It mostly caught things — but a self-audit shares the doer's frame. The
  one refinement here: the audit is run as a **separate, cold session** (an *auditor* spawned like a
  Wave General but for auditing) that re-derives every load-bearing claim from the frozen criteria and
  the persisted artifacts, with no memory of how the work was produced, and writes
  `handoffs/orchestrator/WAVE_<id>_AUDIT.md`. Its PASS is the **gate**: no wave reaches COMPLETE
  without it, timestamped before the close. Same artifact name (`WAVE_<id>_AUDIT.md`), same `/audit`
  spirit (Curiosity / Quality / Resilience), one structural upgrade: the checker is never the doer.

### The planning subagent (heavy re-planning) — refined
- In the predecessor the Orchestrator authored every wave plan and re-planned itself. That is kept for
  normal planning. The one refinement: for a *heavy* re-plan (a surprise that reshapes a whole branch
  of the DAG), the Orchestrator spawns a **planning subagent** in an isolated session, so the big
  reasoning pass doesn't bloat the Orchestrator's rotating context. It returns a revised DAG the
  Orchestrator applies. This is not a new tier — it is a Subagent doing planning instead of execution.

### The babysit loop — the continuity daemon (unchanged)
- A cheap, recurring process (`CronCreate`, session-only) that on each tick, from **on-disk truth
  alone**, answers: *what should happen next?* It classifies the in-flight wave (running-and-progressing
  → HOLD; dead/stalled → revive; complete-and-clean → advance), budgets the rate-limit window, triggers
  rotation, and either auto-advances the queue or pauses and pings the human — strictly per
  `AUTO_ADVANCE_POLICY.md`. It reasons only from files, so it works no matter which sessions have died.

```
                 ┌──────────────┐         ┌──────────────┐
                 │ BABYSIT LOOP │◀────────│   Cron (5h)  │   continuity daemon; on-disk truth only
                 │  (daemon)    │         └──────────────┘
                 └──────┬───────┘
                        │ classifies, advances, rotates, pauses
                        ▼
                 ┌──────────────┐   spawns for    ┌───────────────────┐ ┌───────────────────┐
                 │ ORCHESTRATOR │────────────────▶│ audit (cold /audit│ │ planning subagent │
                 │  (rotates/   │                 │ → WAVE_x_AUDIT.md) │ │  (heavy re-plan)  │
                 │   wave)      │                 └───────────────────┘ └───────────────────┘
                 └──────┬───────┘
                        │ launches one wave (_spawn_wave.sh)
                        ▼
                 ┌──────────────┐
                 │ WAVE GENERAL │  one wave = one session = one 5h window
                 │  (resumes/   │
                 │   window)    │
                 └──────┬───────┘
                        │ dispatches SERIALLY, banks each via dispatch.py
             ┌──────────┼──────────┐
             ▼          ▼          ▼
         ┌────────┐ ┌────────┐ ┌────────┐
         │SUBAGENT│ │SUBAGENT│ │SUBAGENT│   one task each
         └────────┘ └────────┘ └────────┘
```

---

## 2. The control plane: durable truth vs live coordination

This is the single most important architectural decision, and where the 100x leap lives.

The predecessor hand-rolled its entire control plane on a bare-terminal assumption: it spawned each
wave with `osascript` into a new Terminal window (`_spawn_wave.sh`), the user pasted launch commands
manually, and every piece of coordination went through files that other sessions polled. That was
robust (files survive death) but slow, manual, and blind (no session could actively watch another;
"check on wave N" was a human-triggered poll).

This harness provides native primitives the predecessor did not have. The design uses them for the
**live** plane while keeping the **durable** plane exactly as the predecessor proved it:

**Durable plane — the source of truth (filesystem).**
- `REGISTRY.json` (atomic, versioned via `dispatch.py`) and the artifacts on disk. This is what every
  role reconciles against; it survives every session death. On any conflict, **disk wins.**
- The `handoffs/` tree: plans, briefs, checkpoints, summaries, resume directives, the campaign log,
  window state. All files.

**Live plane — coordination, never truth (harness-native).**
- **`Cron`** (`CronCreate`/`CronList`/`CronDelete`) runs the `babysit loop` on a 5h window-aligned
  cadence and can fire one-shot scheduled launches. Replaces the manual "user pastes the launch
  command." (The predecessor already moved here late in its life — the babysit `/loop` on a 5h cron.)
- **`Monitor`** arms a *single* watcher on a condition (a process exit, an artifact file appearing, a
  `REGISTRY` field flipping) and returns when it fires. This is the structural cure for the
  predecessor's worst live-coordination bug — a Wave General *tight-polling* a background job, which
  got a Subagent interrupted (its memory pin: "arm ONE watcher and WAIT; don't loop-Read the output
  file"). The rule becomes a primitive: **arm one Monitor and wait.**
- **The `Task` system** (`TaskCreate`/`TaskUpdate`/`TaskList`/`TaskGet`) is the *live mirror* of the
  `REGISTRY`'s task entries — the operational view the babysit loop and Orchestrator query cheaply, and
  the mechanism by which a background Subagent's completion notifies its Wave General. `REGISTRY`
  remains the durable record; the Task system is the dashboard and the doorbell.
- **`Agent` (background) + `SendMessage`** give the Wave General a live channel to its Subagents and the
  Orchestrator a live channel to its Wave General — for steering and status, *not* for banking results
  (results are banked from disk).
- **`Bash` (background)** runs long producers that outlive their session (`07` §4).
- **`PushNotification`** is the *only* channel that interrupts the human, reserved for the touchpoint
  policy's genuine-decision events.

**The reconciliation rule:** live-plane state is a *hint*; durable-plane state is *truth*. A
`SendMessage` saying "task X done" does not complete task X — the Wave General completes it only after
reading the artifact off disk and validating its hash (via `dispatch.py`, exit 7). A `Monitor` firing
on "process exited" tells the babysit loop to *go look at disk*, not to conclude anything. This is the
direct generalization of the predecessor's "on-disk = truth; an agent that completed but wrote nothing
did NOT complete." Messages are ephemeral and can lie by omission (a crash swallows the "done"
message); disk does not.

---

## 3. Dispatch modes: session-spawn vs in-session

There is a real tension between **isolation** (each role should have its own context budget and
rate-limit envelope so a death is contained) and **coordination** (a parent should bank a child's
result and steer it live). The design resolves it with two dispatch modes, chosen by tree level — the
predecessor's actual practice, made explicit:

- **Session-spawn** (own OS session / Terminal window via `_spawn_wave.sh` / `_spawn_orchestrator.sh`)
  for the **Orchestrator** and the **Wave General**. Each gets its own window, its own context, its own
  rate-limit envelope; each can rotate or die independently; each maps cleanly to "one session = one 5h
  window." Where the harness exposes a native session launcher it is preferred, with `osascript` as the
  portable fallback the predecessor used.
- **In-session `Agent`** for **Subagents** within a Wave General's wave. The Wave General must bank each
  Subagent serially and atomically anyway, so it wants the Subagent inside its own session where it
  gets a completion callback and a `SendMessage` steering channel. **The Wave General's session *is* the
  wave's rate-limit window;** when exhausted, the wave checkpoints and a fresh Wave General resumes.

The independent audit and the planning subagent are session-spawned when they need isolation (an audit
*must* be cold and separate) and in-session for quick passes.

**Why not run everything as in-session background Agents?** A background Agent shares its parent's
context and rate-limit envelope. Making Wave Generals background-agents of the Orchestrator would
recreate exactly the failure the predecessor's session isolation prevented: one exhausted envelope
taking down the whole tree, and one context growing without bound (the 5-day bloat incident). The top
of the tree must be OS-isolated. A deliberate, recorded judgment call.

---

## 4. Model tiering

Roles are not equally hard, and the rate-limit budget is shared, so model choice is a first-class knob
(the `Agent` tool and `_launch_wave.sh` both take `--model`). The predecessor ran everything on one
top-tier model because its manual launcher lacked the knob; exposing it is pure efficiency with no
capability loss where it matters.

| Role | Default tier | Rationale |
|---|---|---|
| Orchestrator | most capable | Holds the whole campaign; its judgment sets the ceiling. Rotation keeps its cost bounded. |
| planning subagent | most capable | Decomposition/re-planning is the highest-leverage reasoning. |
| independent audit | most capable | An audit is only as trustworthy as the mind running it; the checker must not be weaker than the doer. |
| Wave General | capable | Orchestration + banking is mechanical-but-careful; reliability over depth. |
| Subagent | **task-dependent** | Reasoning-heavy task → top tier; mechanical task (forensics, running a pinned script) → cheaper/faster. The task entry carries a `model_hint`. |
| babysit loop | **cheap** | It reads files and applies a decision table; a top model on a 5h loop is waste. |

---

## 5. Two mission shapes

The same machinery serves two mission types:

- **Finite-goal mode.** The DAG has terminal leaves; when all are done, a final Orchestrator-only wave
  runs (the predecessor's Wave 6 synthesis) and the mission reaches DONE.
- **Persistent-team mode.** No terminal state. The Orchestrator periodically ingests new tasks from an
  intake channel (the steering inbox, an intake directory, or a polled external source via `WebFetch`),
  never terminates, and the touchpoint policy shifts from "ping at completion" to "periodic digest +
  escalate on decision." The DAG becomes a rolling frontier.

The difference is entirely the *termination condition* and the *intake*; the roles, the `REGISTRY`, the
continuity engine, and the audit gate are identical. "Pursue a goal to completion" and "run as a
standing team" are two configurations of one engine.

---

## 6. Where the intricacy lives (and where it deliberately does not)

Complexity is spent only where it buys capability — where the predecessor's real failures clustered:

1. **The continuity engine** (`07`) — window budgeting, checkpointing, rotation, background compute,
   parking. The core competency; the most detail.
2. **The anti-fabrication + audit kernel** (`08`) — the banking gate, the freeze, the independent audit,
   replay. The trust foundation; the most rigor.
3. **The failure atlas** (`06`) — every observed failure with a detector and a structural cure. Where
   hard-won judgment becomes code.
4. **The `REGISTRY` schema and `dispatch.py` kernel** (`04`) — the atomic primitive everything stands on.

Everywhere else the design is deliberately plain: the roles are the predecessor's, the `handoffs/`
layout is the predecessor's, the CLI is the predecessor's `dispatch.py` family plus a few small
helpers. A system that runs unattended for weeks cannot afford cleverness in its bones; it needs
cleverness only in its defenses.
