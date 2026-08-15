# SuperTeam — Independent Next-Generation Architecture

**Author:** an independent design pass, grounded empirically in the real ~7-week autonomous
campaign preserved under `/Users/rvk/Desktop/Chaos Constant/verification/` (registry, runners,
`handoffs/` operating manuals, orchestrator runbook, wave records, halt/resume directives, audit
logs) and the slash-commands under `/Users/rvk/Desktop/Chaos Constant/.claude/commands/`.

**What this is.** A complete re-design — not a summary — of a generalized autonomous
agent-orchestration system. You point it at **any** goal (or run it as a persistent team) and it
operates toward that goal for **days to weeks**, autonomously, across **many Claude Code sessions**,
on a **single Mac**, under **subscription rate limits** (5-hour usage windows plus weekly caps;
sessions pause at limits and do not auto-resume), with **minimal human touchpoints**. The human may
sleep, step away for days, or drop in at any moment to steer.

**Design stance.** Everything here is grounded in what the predecessor system actually did — every
failure, misdiagnosis, interruption, and workaround in its records — not in generic best practice.
Where the predecessor learned a lesson the hard way, that lesson is encoded here as *structure* (a
schema field, a state transition, a gate, a role boundary) so the system cannot repeat it, rather
than as a discipline someone has to remember. The whole system is engineered to operate the way I
reason: act on the reversible, stop on the irreversible; treat a mismatch as a clue, not an
inconvenience; keep truth on disk; prefer an honest BLOCKED to a manufactured DONE; and never let
the checker be the same mind as the doer.

---

## Reading order

| # | Document | What it covers |
|---|----------|----------------|
| 00 | `00_INDEX.md` | This map. |
| 01 | `01_PHILOSOPHY_AND_JUDGMENT.md` | **The operating mind.** The reasoning and judgment the whole system encodes: the ten operating laws, how it decides, when it stops, when it involves the human. Read this first — every other document is a mechanization of it. |
| 02 | `02_ARCHITECTURE.md` | The role hierarchy (Orchestrator / Wave General / Subagent + the babysit loop, the independent audit, the planning subagent), the control plane, the durable-truth-vs-live-coordination split, model tiering, dispatch modes. |
| 03 | `03_FILESYSTEM_AND_PROTOCOLS.md` | Complete folder layout, every file and its schema, the communication protocols between roles, and the rule that reconciles them (disk wins). |
| 04 | `04_REGISTRY_AND_DISPATCH.md` | The `dispatch.py` concurrency kernel and the typed `REGISTRY`: tasks, claims, artifacts, decisions, authorizations. The atomic primitive, full schemas, real command lines, the freeze mechanism. |
| 05 | `05_LIFECYCLE_AND_STATE_MACHINES.md` | Mission lifecycle, wave lifecycle, subagent lifecycle, and the exact state machines with every transition and who may cause it. |
| 06 | `06_FAILURE_ATLAS.md` | **Every failure mode observed in the real records**, each with a detector and a structural resolution. The heart of the grounding. |
| 07 | `07_CONTINUITY_AND_RATE_LIMITS.md` | The continuity engine: the 5h/weekly window budget model, checkpointing, session rotation, background compute, graceful parking, liveness, no-double-launch, no-tight-poll. |
| 08 | `08_VERIFICATION_AUDIT_EVIDENCE.md` | Anti-fabrication kernel, pre-registration/definition-of-done freezing, the independent cold-context audit gate, and the generalized Evidence/Serendipity Protocol with pluggable lenses. |
| 09 | `09_HUMAN_INTERFACE.md` | Minimal-touchpoint design: the touchpoint policy, urgency tiers, the steering inbox, the digest, persistent-team mode. |
| 10 | `10_KEPT_CHANGED_DISCARDED.md` | Explicit registry of what I kept, changed, and discarded from the predecessor, and why — traced to specific records. |
| 11 | `11_HUNDRED_X_UPGRADES.md` | The 100x upgrade list, each tied to a concrete capability gain and the failure/limitation it removes. |
| 12 | `12_IMPLEMENTATION_ORDER.md` | Bootstrap and build order — the exact sequence to stand the system up, with real files and acceptance checks per stage. |
| 13 | `13_END_TO_END_VERIFICATION.md` | How the finished system is verified end to end: the self-test (canary) missions and the acceptance battery, with real `dispatch.py`-family invocations. |

---

## The system in one screen

A **mission** is a goal plus a frozen definition of done, living in a workspace laid out exactly like
the predecessor's `verification/` tree (`REGISTRY.json` + `artifacts.jsonl` + the `handoffs/` tree +
`runners/` + `reports/`). Work is a living **dependency DAG of tasks** in the atomic **REGISTRY**. The
DAG's ready frontier is packed into **waves**, each sized to roughly one 5-hour rate-limit window.

The predecessor's three roles are unchanged, plus the babysit loop and two refined specialists — each
with a hard context budget and a written charter:

- **Orchestrator** (unchanged) — owns the mission, the DAG, the roadmap; decides what to pursue next;
  runs the human touchpoint policy; responds to halts (`/revive`); rotates its own session every wave to
  stay small.
- **Wave General** (unchanged) — owns exactly one wave in exactly one session/window; decomposes it into
  tasks, dispatches Subagents **serially**, banks each result atomically via `dispatch.py` before the
  next, checkpoints after every task, closes the wave.
- **Subagent** (unchanged) — executes one task; returns a small structured result and persists its
  artifacts; runs the Curiosity Protocol.
- **the babysit loop** (unchanged) — the continuity daemon: a cheap, recurring `Cron` loop that watches
  liveness, detects stalls, budgets the rate-limit window, triggers rotation, advances the queue, and
  decides — from on-disk truth alone — whether to hold, revive, or launch.
- **the independent audit** (refined) — the predecessor's `/audit` pass, but run as a **cold, separate
  session** that re-derives every load-bearing claim before a wave may be marked COMPLETE, writing the
  same `WAVE_<id>_AUDIT.md`. The one upgrade: the checker is never the doer.
- **the planning subagent** (refined) — for a heavy re-plan, the Orchestrator spawns a Subagent to
  re-shape the DAG in an isolated session, so the big reasoning pass doesn't bloat the Orchestrator.

The **control plane is harness-native**: `Cron` for the recurring loop, `Monitor` for
liveness/artifact watchers (never tight-poll), the `Task` system as the live mirror of the registry,
`SendMessage` + background `Agent` for live role-to-role coordination, background `Bash` for
producers, `PushNotification` for the rare human-urgent event. But **live coordination is never the
source of truth** — messages are ephemeral and sessions die. The **filesystem registry is the single
source of truth, and on any conflict, disk wins.**

Continuity is the core competency, because it was the predecessor's hardest-won lesson: waves are
window-sized, banking is serial, every long compute outlives its session via a hashed
Producer/Consumer manifest, both top-level roles rotate to bound context, and the babysit loop parks
gracefully at the weekly cap instead of thrashing.

The human sees almost nothing by default: a batched digest, and a `PushNotification` only for a
genuine decision (an audit failure, a scope change, an authorization request, a hard block). They can
drop a directive into a steering inbox at any instant; the Orchestrator reads it at the next wave
boundary and re-plans without the machine ever stopping.
