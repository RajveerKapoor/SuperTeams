# 12 — Implementation Order

The build order mirrors the predecessor's own hard-won sequence: it built **Tier 0** (the entire
infrastructure stack — integrators, stats, registry, dispatch, freeze, replay) to completion *before
testing a single discovery*, because a verification campaign standing on unverified infrastructure is
worthless. SuperTeam builds its infrastructure the same way: the kernel and the gates first, the
continuity engine second, the domain lenses and human interface last, and it *dogfoods itself* — the
first mission SuperTeam runs is hardening SuperTeam.

A guiding principle from the predecessor's design philosophy governs the whole build: **the system is a
guiding scaffold, not a rigid template.** It is doctrine (the operating manuals + the Ten Operating
Laws), plus exemplars (the predecessor's real `handoffs/` tree, kept as the verbatim reference), plus a
mechanical substrate (`dispatch.py` and the CLI family). The Orchestrator designs each mission's own
structure; the engine provides the substrate and the doctrine, never a fill-in-the-blanks form.

Each stage below states its **goal**, the **files** it produces, its **acceptance check** (a test that
must pass before the next stage begins), and the **predecessor precedent** that proves the approach.

---

## Stage 0 — The kernel and the freeze (the atomic foundation)
**Goal:** an atomic, versioned, freezable `REGISTRY.json` that cannot be corrupted by concurrent
writers and cannot have its goalposts moved.

**Files:** `runners/dispatch.py` (the predecessor's, generalized to typed entries + exit codes 7/8),
`runners/pre_register.py` (freeze), `schemas/*.json` (entry + handoff schemas), `REGISTRY.json` seed.

**Acceptance check** (the predecessor's exact race + freeze tests, which passed):
```bash
# concurrency: 20 parallel non-conflicting updates all succeed; 5 parallel same-entry → exactly 1 winner
python -m pytest runners/test_dispatch.py -k "race" -q
# freeze: a patch to a frozen criterion is rejected (exit 6); --unfreeze with an authz bypasses + audits
runners/pre_register.py && runners/dispatch.py update --disc TASK_0001 --patch bad_criterion.json ; echo "exit=$?"   # expect 6
```
**Precedent:** the predecessor's `dispatch.py` passed "20-parallel non-conflicting in 0.40s; 5-parallel
same-entry → exactly 1 winner, 4 conflicts" and its freeze enforced `EXIT_FROZEN=6` with an audited
`--unfreeze`. Kept verbatim.

---

## Stage 1 — The banking gate and replay (anti-fabrication)
**Goal:** a completion is impossible without a persisted, hashed, re-derivable artifact; a dependency
cannot be jumped.

**Files:** the exit-7 (artifact-missing) and exit-8 (dependency-not-met) logic in `dispatch.py`,
`runners/replay.py`, `runners/log_artifact.py`, `artifacts.jsonl`.

**Acceptance check:**
```bash
runners/dispatch.py update --disc TASK_0001 --patch done_no_artifact.json ; echo "exit=$?"   # expect 7
runners/dispatch.py update --disc TASK_0009 --patch start.json ; echo "exit=$?"               # deps unmet → expect 8
runners/replay.py CLAIM_0001                                                                   # re-derives; hash matches
```
**Precedent:** the predecessor's `replay.py` re-ran a producer's recorded command and checked the SHA
matched — "the ultimate fabrication detector." Exit 7/8 make Law 1 and the dependency contract
mechanical instead of remembered.

---

## Stage 2 — The handoffs tree, charters, and scaffolding
**Goal:** the durable communication bus and the role doctrine, plus templated wave scaffolding so
bookkeeping cannot drift.

**Files:** the `handoffs/` tree (all subdirs); the three charters copied from the predecessor and
generalized — `ORCHESTRATOR_RUNBOOK.md`, `WAVE_GENERAL_OPERATING_MANUAL.md`, `WAVE_INDEX.md` — plus the
audit charter section; `runners/new_wave.py`, `runners/wave_status.py`, `runners/checkpoint.py`,
`runners/close_wave.py`.

**Acceptance check:**
```bash
runners/new_wave.py 0test --tasks TASK_0001            # scaffolds handoffs/{waves,briefs,status,checkpoints,...}
runners/dispatch.py validate                            # every scaffolded file schema-valid, no missing fields
runners/close_wave.py 0test ; echo "exit=$?"            # refuses (no WAVE_0test_AUDIT.md PASS) → non-zero
```
**Precedent:** the predecessor's `handoffs/` tree and its `ORCHESTRATOR_RUNBOOK.md` /
`WAVE_GENERAL_OPERATING_MANUAL.md` are the exemplar. Its "missing NOTES files / ad-hoc STATUS fields"
drift is cured by `new_wave.py` scaffolding every required file and `validate` making omissions errors.

---

## Stage 3 — The continuity engine (survival)
**Goal:** the system survives every interruption class without loss or fabrication, and parks across the
weekly cap.

**Files:** `runners/window.py`, `runners/park.py`, `runners/resume.py`; the background-compute contract
(manifest + hash, in `new_wave.py`/`checkpoint.py`); the `babysit loop` classifier (a script the
`Cron` job runs); the three-signal liveness check; `WINDOW_STATE.json`.

**Acceptance check** (induced-failure tests — the heart of the system):
```bash
# kill a Wave General mid-wave after 1 banked task → fresh Wave General resumes; exactly 1 task re-done, no loss
# stall (nothing banked) → classifier returns "clean restart"; stall (partial) → "checkpoint-resume"
# producer launched via background Bash outlives a killed session; consumer validates hash on relaunch
python -m pytest runners/test_continuity.py -q
runners/park.py "test cap" && runners/resume.py         # park + resume re-derives state from disk, no loss
```
**Precedent:** every mechanism here traces to a real incident — Wave 2c (serial banking), Wave 2j
(stall → clean restart), Wave 0b's 87/192 buckets (atomic partial-writes), Wave 2h (weekly-reset ride).

---

## Stage 4 — Launchers, rotation, and the single-loop invariant
**Goal:** sessions spawn, rotate, and never double-launch; exactly one babysit loop runs.

**Files:** `bin/_spawn_wave.sh`, `bin/_launch_wave.sh`, `bin/_spawn_orchestrator.sh`,
`bin/_launch_orchestrator.sh`, `bin/_commit.sh`; the rotation sequence; the pre-launch liveness check;
the `AUTO_ADVANCE_POLICY.md` allow-rule wiring.

**Acceptance check:**
```bash
# rotation: outgoing Orchestrator writes SESSION_HANDOFF, spawns successor, disarms its own Cron → exactly 1 loop
# no-double-launch: _spawn_wave.sh refuses if a live, progressing wave-<id>-general process exists
runners/status.py     # shows exactly one live loop after a rotation
```
**Precedent:** the predecessor's `_spawn_wave.sh` / `_spawn_orchestrator.sh` behind a single allow-rule,
the session-rotation workflow that cured the 5-day bloat, and memory pin #13 (single loop, pre-launch
liveness, no double-launch). Kept.

---

## Stage 5 — The Curiosity Protocol and lenses
**Goal:** record-all serendipity in any domain, with FDR-gated promotion so the system never cries wolf.

**Files:** `lenses/{research,engineering,ops,writing,generic}.py`, the Curiosity Protocol engine, the
FDR-gated promotion pass (a later harvest wave), `curiosity/constants.py` (the research lens's matcher).

**Acceptance check:**
```bash
# record-all: a task logs every artifact (including boring ones) to artifacts.jsonl with provenance
# no pre-gating: no artifact carries a status that excludes it from the later promotion pass
# promotion pass: applies Benjamini–Hochberg across the whole pool; promotes nothing in-wave
python -m pytest lenses/test_lenses.py -q
```
**Precedent:** the predecessor's Curiosity Protocol (constants match, pairwise ratios, PSLQ,
τ-thresholds, BH at "Wave 4b") is the `research` lens; the "record ALL, never pre-gate" policy and the
provenance field are kept exactly.

---

## Stage 6 — The human interface
**Goal:** silent by default, interruptible only on genuine decisions, steerable without stopping.

**Files:** `AUTO_ADVANCE_POLICY.md` (touchpoint tuning), `STEERING.md`/`INBOX.md`/`OUTBOX.md`, the
`PushNotification` escalation matrix, `runners/status.py` (catch-up).

**Acceptance check:**
```bash
# auto-advance: a clean wave close advances + digests to OUTBOX with NO PushNotification
# escalate: an audit FAIL / authz request / scope fork fires exactly one PushNotification with a recommendation
# steer: a directive in STEERING.md is read at the next wave boundary and becomes a Decision record
runners/status.py     # one-command human catch-up prints mission state from disk
```
**Precedent:** the predecessor's `AUTO_ADVANCE_POLICY.md` (auto-advance after a clean audit; pause+ping
only for audit-FAIL / HALT / unfreeze / done) is the template; the escalation matrix generalizes it.

---

## Stage 7 — The DAG, roadmap, and mission init
**Goal:** an adaptive dependency graph the Orchestrator packs into window-sized waves, and one-command
mission bootstrap.

**Files:** `runners/roadmap.py` (frontier, pack, add-task, SUPERSEDED), `runners/init_workspace.py`,
the `MISSION.md` charter template.

**Acceptance check:**
```bash
runners/init_workspace.py demo-mission --mode finite     # scaffolds the whole workspace
runners/roadmap.py frontier                              # prints ready tasks (deps COMPLETED)
runners/roadmap.py pack --window-budget 4.5h             # proposes a window-sized wave
```
**Precedent:** the predecessor's `WAVE_LAUNCH_QUEUE.md` + dependency edges are the static ancestor;
`roadmap.py` makes the graph adaptive while the Orchestrator still authors each wave plan.

---

## Stage 8 — Dogfood: the acceptance battery (doc 13)
**Goal:** prove the whole system end to end by running the canary missions and the acceptance battery in
`13_END_TO_END_VERIFICATION.md`. The system is not "done" until it has autonomously run a canary mission
through plan → freeze → serial-banked waves → independent audit → advance → synthesis → DONE, survived
an induced kill and an induced stall with zero loss and zero fabrication, and correctly escalated a
planted decision while staying silent on everything else.

---

## The build-order rationale (one paragraph)

Truth before everything (Stage 0: the kernel is what every other stage reconciles against). Then make
truth *honest* (Stage 1: no fabricated completions). Then the durable bus and doctrine (Stage 2). Then
*survival* (Stage 3), because an unattended weeks-long system that can't survive interruption is a toy.
Then *coordination* (Stage 4: spawn/rotate without double-launch). Then *curiosity* (Stage 5) and the
*human interface* (Stage 6), which only matter once the machine reliably runs. Then the *adaptive DAG*
(Stage 7), which sits on top of everything. Then *prove it* (Stage 8). This is precisely the
predecessor's order — infrastructure to completion, then work — and it worked for seven weeks.
