# 06 — The Failure Atlas

This is the empirical core of the design. Every entry is a failure the predecessor system *actually
hit*, drawn from its records (campaign log, halt/resume directives, session handoffs, audit memos).
For each: the **incident** (what happened, with the evidence), the **detector** (how the system now
notices it), and the **structural cure** (the schema field, gate, or role boundary that makes it not
recur — not a discipline to remember). The residual **human touchpoint**, if any, is noted.

The organizing claim: the predecessor survived every one of these through *disciplined operators
remembering hard-won rules*. This system converts each rule into structure, so survival no longer
depends on memory.

---

## Class A — Continuity failures (the core threat)

Rate limits, laptop sleep, killed processes, and context bloat. These were the most frequent and most
dangerous, because a mishandled one silently *loses work* or *fabricates recovery*.

### A1 — Parallel dispatch blows a whole window, persists nothing
- **Incident:** Wave 2c's general parallel-spawned four subagents in one message; the batch blew a
  fresh 5-hour window in ~68 minutes and **persisted nothing** — all four were in-flight when the
  limit hit. The user then mandated SERIAL dispatch (it became the predecessor's memory pin #11, "the
  #1 rate-limit defense"). Wave 2i's brief later warned explicitly that "a parallel multi-spawn blew a
  full 5h window in Wave 2c with nothing persisted."
- **Detector:** the Wave General's tooling knows how many Subagents are in-flight; more than one unbanked task
  is a violation.
- **Structural cure:** the **serial-banking protocol** (`03` §5) is the Wave General's only dispatch path.
  Dispatch one → wait → validate → `dispatch.py update` → `checkpoint.py` → next. At any instant at
  most one task is unbanked, so a limit costs at most one task, never a window. Cross-wave
  parallelism is a separate, Orchestrator-level scheduling choice made with the window budget in hand;
  within-wave parallelism (the trap) is simply not a code path.

### A2 — Long-lived session bloats, goes stale, rate-limits instantly
- **Incident:** the 2026-06-25→29 episode — a single Orchestrator session ran for five days,
  piled up ~20 unprocessed babysit ticks, and its context bloated until it rate-limited almost
  immediately on wake. The fix invented mid-campaign was **session rotation**: after each wave, write
  a fresh handoff, spawn a replacement Orchestrator, and disarm the old loop.
- **Detector:** the babysit loop tracks each role session's age and unprocessed-tick count; past budget →
  stale.
- **Structural cure:** **mandatory rotation** (`07` §5). Both top-level roles rotate: an Orchestrator
  rotates after each wave close; a Wave General rotates when its window is exhausted. Rotation is a session
  writing its successor's handoff, spawning it, and disarming its own loop. Small, replaceable
  sessions structurally cannot accrue five days of context. Enforced by Law 6 and the babysit loop's
  stale-session flag.

### A3 — Session dies mid-work; recovery must not fabricate
- **Incident:** repeated. Wave 0b lost a background canary at 87/192 buckets to a laptop power-off;
  Wave 0c was laptop-killed mid-benchmark; Wave 0d died mid-finalization with modules on disk but a
  rejected tool-use; Waves 1a/1b/2a took rate-limit interrupts between compute-completion and
  bookkeeping. In every case the correct recovery was to **reconcile against disk, inherit no verdict
  from the dead session, and re-run any "passed" claim in the live session.**
- **Detector:** on relaunch, `dispatch.py validate` finds orphan IN_PROGRESS states and any claim whose
  artifact is absent/mismatched.
- **Structural cure:** three mechanisms compose. (1) **Checkpoint after every task** so at most one
  task is un-checkpointed. (2) **Atomic per-unit partial-writes** for any multi-item compute, so a kill
  preserves completed units bit-for-bit (Wave 0b's 87 buckets survived exactly this way; the pattern
  became standard). (3) The **resume contract**: a fresh Wave General reads the checkpoint, reverts orphan
  IN_PROGRESS → PENDING, and re-derives — it never marks a task DONE it didn't watch complete, because
  `dispatch.py update` re-hashes the artifact regardless of who claims it's done (exit 7). Law 1 made
  mechanical.

### A4 — "Finish from persisted compute" vs "recompute" (the diff-only reverify)
- **Incident:** Waves 1a/1b were interrupted *after* the real compute finished but *before* the
  verdict was packaged. Re-running the finalize step would have **duplicated rows in the append-only
  artifact pool**. The predecessor's cure was a *diff-only reverify* script: re-load each persisted
  output, recompute its hash against the manifest, re-run only the cheap verdict math, and confirm
  bit-identical — without re-running the compute that would corrupt the append-only pool.
- **Detector:** the checkpoint records exactly which artifacts are persisted+hashed; the resume logic
  compares "what's on disk" to "what the verdict needs."
- **Structural cure:** the `/revive` resume directive (`07` §6) explicitly classifies the interruption:
  *is the missing work new compute (respawn a Subagent) or just synthesis of data already on disk (drive
  it directly, diff-only)?* The append-only artifact pool plus per-artifact hashes make the diff-only
  path safe and detectable. Generalizes the predecessor's memory pin "respawn interrupted subagents to
  finish their own work; but drive synthesis directly when the needed data already exists on disk."

### A5 — Alive-but-spinning: a session that looks busy but banks nothing
- **Incident:** Wave 2j's general launched, ran 5.5 hours, and banked **nothing** — `completed: []`,
  no reports, artifacts frozen at baseline, checkpoint frozen at the start timestamp. The process was
  *alive* but its CPU was merely spinning (a rate-limit retry-spin / wedged session), not progressing.
  A liveness check that trusted "process alive" would have wrongly HELD.
- **Detector:** liveness is a **three-signal** judgment, never process-existence alone: (1)
  CPU-time delta over a window, (2) artifacts-count delta vs the wave baseline, (3) checkpoint
  timestamp advance. Alive + zero-artifacts-delta + frozen-checkpoint over a long span = **stalled**,
  not running.
- **Structural cure:** the babysit loop's classifier (`07` §2) uses all three. On a stall with **nothing
  banked**, the cure is a *clean restart* (there is nothing to recompute — the predecessor's exact
  reasoning: "0 is banked, so there is nothing to recompute; this is a clean restart, not a partial
  resume"). On a stall with *something* banked, it's a checkpoint-resume. The distinction is decided
  by the registry, not the transcript.

### A6 — Weekly cap hit mid-mission
- **Incident:** Wave 2h "survived a multi-day weekly reset" mid-wave. Handled by riding it out.
- **Detector:** `WINDOW_STATE.json` tracks the weekly cap; the babysit loop projects remaining budget.
- **Structural cure:** **graceful park** (`07` §7). When the weekly cap is near, `park.py` writes a
  park-state, disarms the babysit loop, and the system sleeps intact. `resume.py` re-derives from
  disk after the reset. Parking is a first-class state (`05` §1), not a crash — no thrashing, no
  fabrication, no lost work across a multi-day pause.

---

## Class B — Fabrication and shortcut risks

The failures that would corrupt the *truth* of the mission rather than lose work.

### B1 — Shortening a run to fit a perceived deadline
- **Incident:** the predecessor's whole Operating Manual §11 and the memory pins are organized against
  this. Its counter-evidence that the discipline held: a Wave 2a re-audit proved a compute took 13.42h
  vs a ~5h projection — 2× *over* budget, the anti-shortcut signal that nothing was corner-cut.
- **Detector:** every compute has a manifest with a projected wallclock; a run that finishes
  suspiciously *under* projection is a flag to the Auditor, and `replay.py` re-derives the artifact
  hash independently.
- **Structural cure:** (1) **No wall-clock cap on Subagents** — quality is the only metric; rushing is
  the named fabrication risk. (2) A genuinely long compute **must** use the Producer/Consumer manifest
  (`07` §4), which forbids substituting a smaller `n` / coarser resolution / cheaper method — the
  producer either does the full work or writes `status: INFEASIBLE` and the Wave General HALTs. (3) The
  Auditor's replay re-runs the recorded recipe and checks the hash; a shortcut changes the hash and
  fails the audit.

### B2 — Manufacturing a completion, hash, or test-pass
- **Incident:** the predecessor's cardinal sin, never committed but constantly guarded. Its memory pin:
  "treat a hung Bash/Agent as TIMEOUT; never invent return values, never claim tests green without
  re-running; on-disk state is truth."
- **Detector:** `dispatch.py update` recomputes the artifact hash; a claimed pass with no persisted
  log fails (exit 7). The Auditor re-runs the acceptance check.
- **Structural cure:** Law 1 as a kernel gate. A completion is *a persisted, hashed, re-derivable
  artifact* — not an assertion. A hung tool yields no artifact, so it yields no completion; it yields a
  BLOCKED or a retry, never a fabricated DONE.

### B3 — Non-determinism in the acceptance check
- **Incident:** Wave 0c found a compiled kernel's `fastmath` reordering produced ~1-ULP divergences
  that amplified at the system's characteristic rate, breaking a bit-exact self-test even though the
  statistical result held. The correct move was to *document the tolerance honestly* and pick the
  determinism level the criterion actually needed, not to relax the criterion to hide the
  non-determinism.
- **Detector:** the acceptance check declares its determinism level (`deterministic` vs
  `statistical(SE)`); a check that claims deterministic but varies across replays is caught by
  `replay.py` producing a different hash.
- **Structural cure:** the frozen criterion's `confidence_target` field (`04` §3) makes the required
  determinism explicit at freeze time. A statistical criterion carries its tolerance; a deterministic
  one must actually reproduce. Honest tolerance is frozen up front, never negotiated after seeing the
  result.

---

## Class C — Coordination failures

Failures of one session relating to another.

### C1 — Double-launch: relaunching a role whose process is still alive
- **Incident:** a recurring hazard; the predecessor pinned it (#9/#13): "diagnose liveness by ps/CPU,
  not log size … always keep the 'if alive, don't relaunch' carve-out," and a specific commit
  (`580c982`) recorded a double-launch PAUSE. Wave 2j's resume directive warned: "Do NOT double-launch
  while 54120 is still alive."
- **Detector:** a mandatory **pre-launch liveness check**: is there a live process for this role/wave,
  and is it progressing (three-signal, per A5)?
- **Structural cure:** every launcher (`_spawn_wave.sh`, `_spawn_orchestrator.sh`) runs the liveness check
  first and **refuses** to launch if a live, progressing process for that role/wave exists. An
  *alive-but-paused* session (at a limit, with warm context worth preserving) is handled by *pinging
  the human to paste a resume* — not by spawning a rival. An *alive-but-spinning* session (A5) is
  killed first, then relaunched. "Gone" → relaunch. The decision tree is in the babysit loop spec.

### C2 — Tight-polling a background job
- **Incident:** Wave 2g's Sub3 tight-polled a background job in a loop and got a subagent interrupted;
  it became memory pin #4, "arm ONE watcher (until-grep or block-until-artifact) and WAIT for the
  async notification; don't loop-Read the output file."
- **Detector:** structural — the Wave General has no "poll in a loop" code path.
- **Structural cure:** the harness-native **`Monitor`** primitive. To wait on a background compute, the
  Wave General arms exactly one Monitor on the completion condition (process exit, or the output file appearing
  with its hash) and yields until it fires. No loop, no repeated reads. This is the direct primitive
  form of the memory pin.

### C3 — Idle consumer: a handoff step waiting on data already on disk
- **Incident:** Wave 2h's GAP_004 consumer sat idle waiting for a background producer; the general
  correctly **drove the consume step directly** rather than spawning an idle consumer subagent, because
  the data was already persisted.
- **Detector:** when the producer manifest is `COMPLETE` and the artifact hash validates, the consume
  step is pure synthesis of on-disk data.
- **Structural cure:** the **respawn-vs-direct rule** (memory pin generalized): if the remaining work
  is *new compute*, spawn a Subagent; if it is *synthesis of data already on disk*, the Wave General does it
  directly. The Producer/Consumer contract (`07` §4) makes this decidable from the manifest state.

### C4 — The autonomy classifier blocks an autonomous action
- **Incident:** the auto-mode permission classifier blocked the orchestrator-rotation spawn as a
  self-modification guard; the predecessor's cure was to funnel each autonomous action behind a
  **single allow-listed command surface** (`_spawn_wave.sh`, `_spawn_orchestrator.sh`) pre-authorized
  by one settings rule, so the osascript child runs under the allowed parent and isn't separately
  classified. When even that was blocked, the correct move was to *flag it to the human*, not to
  improvise a bypass.
- **Detector:** the launcher returns a permission-denied signal.
- **Structural cure:** each autonomous action has exactly one allow-ruled command surface
  (`spawn_*.sh`), and the settings pre-authorize that surface. A denied call is treated as *user
  feedback* (per the harness contract), surfaced as a touchpoint — never retried with a workaround.
  This is the Law-2 boundary in operation: a blocked irreversible-ish action escalates.

---

## Class D — Verification and audit failures

### D1 — The checker is the doer (self-audit blind spots)
- **Incident:** the predecessor's Orchestrator audited its own dispatched waves. It caught most things
  ("independently re-derived every load-bearing number"), but self-audit has a structural blind spot:
  the auditor shares the doer's frame.
- **Structural cure:** the dedicated **cold Auditor** role (`02`, `08`). It re-derives from artifacts +
  frozen criteria with no memory of the doing, and its PASS is the completion gate. It reads the Wave General's
  SUMMARY only *after* forming its own verdict. Independence is enforced by role separation, not
  requested.

### D2 — Asserting COMPLETE before the audit ran
- **Incident:** Wave 0a drafted its SUMMARY 11 minutes *before* the final audit-trail re-run; the
  substance was fine but the timestamp ordering was wrong. The Operating Manual was strengthened to
  require audit-trail runs to timestamp *before* the SUMMARY asserts COMPLETE.
- **Detector:** `close_wave.py` compares the AUDIT.md PASS timestamp to the close time.
- **Structural cure:** the **close gate** — `wave close` refuses (and STATUS cannot go COMPLETE)
  unless a PASS audit exists with a timestamp preceding the close. The ordering the predecessor had to
  remember is now unskippable.

### D3 — A frozen criterion has a text/pointer bug
- **Incident:** *nine times* the predecessor found a frozen criterion pointing at the wrong file,
  column, or value while the underlying substance was verifiable elsewhere (DISC_032/058/009/015/044/
  021/017-054/023/056). Every one was handled the same correct way: return **REVISED** with the
  substance proven and the pointer mismatch surfaced; **never self-unfreeze**; the human authorizes the
  audited unfreeze.
- **Detector:** the Subagent/Auditor finds the substance passes but the literal frozen check references
  the wrong thing → sets `criterion_mismatch_flag`.
- **Structural cure:** the **REVISED verdict** + `criterion_mismatch_flag` + the freeze gate (`04` §3).
  A Subagent cannot self-unfreeze; the flag routes to the Orchestrator, who escalates to the human for an
  audited `dispatch.py update` + `--unfreeze`. That the predecessor hit this nine times and mishandled it
  zero times is the proof the mechanism is right — it is kept verbatim in spirit.

### D4 — Template placeholder vs substantive disagreement
- **Incident:** Wave 1b hit a HALT trigger on missing text that turned out to be `[FILL]` template
  placeholders the subagent left, not a substantive disagreement. The general filled them directly
  from verified data (safe) rather than HALTing (unnecessary), and the lesson was that resume
  directives must **disambiguate**: a placeholder gap is fillable from verified on-disk data; a
  substantive disagreement must HALT.
- **Structural cure:** the HALT taxonomy (`07` §6) distinguishes `template_gap` (Wave General fills from
  verified data, transparently, with pre/post hashes recorded) from `substantive_conflict` (Wave General
  HALTs). The `/revive` resume schema names which is which so the ambiguity can't recur.

---

## Class E — State and bookkeeping drift

### E1 — Missing convention files, ad-hoc state strings, inconsistent counts
- **Incident:** Waves 0d/0e were missing per-subagent NOTES files (a convention that was organic, never
  codified); Wave 1e drifted on audit-log placement, narrowed pytest scope, omitted STATUS fields, and
  mis-stated an artifact count. None invalidated substance, but they eroded the audit chain and cost
  backfill commits.
- **Detector:** `dispatch.py validate` (`04` §4) checks every required file/field/count and cross-reference.
- **Structural cure:** **templated scaffolding** (`new_wave.py` creates every required file) +
  **schema validation as a babysit loop gate** (a missing field is an error, not a silent gap) + **the
  per-subagent notes convention codified in the template**, not organic. The predecessor's own remedy —
  "plan-level convention codification prevents recurrence at the source rather than relying on
  post-completion audit" — is exactly this, made systemic.

### E2 — Inadvertent git bundling
- **Incident:** twice, pre-staged non-orchestrator files (a user-authored doc, a transient lock file)
  were swept into an orchestrator commit.
- **Structural cure:** `_commit.sh` stages an **explicit allow-list** (`handoffs/**` + `REGISTRY.json` + `reports/**` + `datasets/**` paths the role
  owns) and refuses anything outside it, printing what it skipped. The predecessor's later discipline
  (`git restore --staged` of read-only sources before every commit) becomes the default staging
  behavior.

### E3 — A library/interface contract that lies
- **Incident:** Wave 1a found a function declaring `seed_entropy: Union[int, str]` but passing strings
  to an API that only accepts int — a campaign-wide latent bug. The right fix was **at the root** (a
  coercion helper wrapping all call sites + a regression test), not a patch in the one failing runner.
- **Structural cure:** two habits, both testable: (1) **fix contracts at the root** with a regression
  test, recorded as a Decision; (2) the engine's own interfaces are schema-typed and validated, so a
  lying contract surfaces as a schema failure rather than a mysterious runtime error three waves
  later.

---

## Class F — Human-in-the-loop failures

### F1 — An out-of-band authorization nearly evaporates
- **Incident:** Wave 1f's "Option A" was authorized by the user directly in a wave terminal, out of
  band; capturing it required a deliberate handoff artifact, and the lesson (memory pin) was that
  "prose-only 'user confirmed' is not a self-contained audit trail."
- **Structural cure:** the **Authorization object** (`04` §2, Law 9). The Orchestrator writes an `AZ-…`
  record — who/what/when/scope/channel — *before* acting on any human authorization, and every
  dependent Decision cites it. An action on an uncited authorization is a validation failure.

### F2 — Escalating incident instead of direction (attention waste)
- **Incident:** the predecessor's touchpoint set was disciplined (pause only for audit-FAIL, HALT,
  unfreeze, queue-exhausted) but had to be tuned repeatedly (the auto-advance authorization, the
  double-launch PAUSE, the re-arm).
- **Structural cure:** the **touchpoint policy** (`09`) with explicit tiers and a per-mission
  `POLICY.md`. Failure verdicts auto-absorb; only genuine decisions (scope fork, authorization,
  unexplained audit-FAIL, hard block, completion) interrupt. The human's attention is spent on
  direction, never incident (Law 10).

---

## The atlas as a self-defending property

Every entry above corresponds to a **detector the babysit loop runs** and a **structural cure that is
already in the schema or the gates.** The system is therefore *self-defending*: it does not merely
avoid these failures by good behavior; it *notices* them (validate, liveness three-signal, close gate,
freeze gate, banking gate) and responds structurally (serial banking, rotation, park, cold audit,
REVISED, allow-listed commit). The predecessor's seven weeks of hard-won operator judgment is, here,
the system's built-in immune system.
