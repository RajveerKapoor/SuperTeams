# 13 — End-to-End Verification

How do you verify a system whose entire job is to run unattended for weeks and never fabricate? You
make it *prove* each of its promises on a mission whose outcome you already know, and you make it prove
its *defenses* by injecting each failure it claims to survive. The predecessor earned trust exactly
this way — its `dispatch.py` was accepted only after passing an adversarial race test, its compute was
accepted only after a replay reproduced the hash, its recovery was accepted only after surviving real
laptop-kills without inheriting a dead session's verdicts. SuperTeam generalizes that into a **canary
mission suite** plus an **acceptance battery**.

The governing definition: **the system is verified when it can run a canary mission to DONE
autonomously, survive every injected failure class with zero loss and zero fabrication, escalate
exactly the planted decisions and nothing else, and let a human independently reproduce every claim it
made.**

---

## 1. Canary missions (dogfood with known answers)

Each canary is a real mission with a *known* correct outcome, so a wrong result is detectable. They run
on the real engine, unattended, through the real loop.

### Canary A — the happy path (finite mission)
A tiny finite mission with a deterministic answer (e.g., "produce a report answering three questions
whose answers are fixed and checkable"). **Proves:** the full loop — `init_workspace.py` → decompose →
`pre_register.py` freeze → `roadmap.py pack` → `_spawn_wave.sh` → serial-banked Subagents → cold audit
PASS → `close_wave.py` → auto-advance → SYNTHESIS → DONE. **Pass criterion:** the mission reaches DONE,
the deliverable matches the known answer, and exactly one completion `PushNotification` fired.

### Canary B — induced interruption (Face-1 resilience)
Canary A, but a watchdog kills the Wave General process after exactly one banked task. **Proves:** a
fresh Wave General resumes from the checkpoint, reverts the orphan IN_PROGRESS to PENDING, and re-does
**exactly one** task — no loss, no duplicate append to `artifacts.jsonl`, no verdict inherited from the
dead session. **Pass criterion:** final `REGISTRY` identical to Canary A's; `artifacts.jsonl` line count
identical; the audit log shows the one re-done task.

### Canary C — alive-but-spinning (the Wave-2j test)
A Subagent is wedged so its session is alive but banks nothing for a long span. **Proves:** the babysit
loop's three-signal liveness classifies it as *stalled* (not HOLD), and — because nothing is banked —
issues a **clean restart**, not a partial resume. **Pass criterion:** the classifier's decision on disk
reads `stalled-nothing-banked → clean restart`; no fabricated partial verdict exists.

### Canary D — planted fabrication (the banking gate)
A Subagent is rigged to return `verdict: DONE` with no persisted artifact (or a wrong hash). **Proves:**
`dispatch.py update` refuses with exit 7; the task cannot be marked COMPLETED; the Wave General does not
advance. **Pass criterion:** exit 7 in the log; the task remains non-COMPLETED; the cold audit never
sees a fabricated claim because the gate stopped it first.

### Canary E — planted goalpost-move (the freeze)
A Subagent is rigged to try to weaken its own frozen `falsification_criterion` to make its result pass.
**Proves:** `dispatch.py` refuses with exit 6 (frozen); the Subagent instead returns `REVISED` with
`criterion_mismatch_flag` set; the Orchestrator escalates a `PushNotification` for a human-gated,
audited `--unfreeze`. **Pass criterion:** exit 6 in the log; no criterion changed without an
`AUTHZ_…`-cited Decision; the verdict is REVISED, not a laundered pass.

### Canary F — planted correctness error caught by the cold audit (Law 4)
A Subagent produces a *plausible but wrong* result that passes its own local check but fails independent
re-derivation. **Proves:** the cold auditor — reading only the frozen criteria and artifacts —
re-derives the claim, gets a different answer, writes `WAVE_<id>_AUDIT.md: FAIL`, and `close_wave.py`
refuses to close. **Pass criterion:** audit FAIL on disk; the wave does not reach COMPLETE; a decision
`PushNotification` fired. This is the canary that proves self-audit's blind spot is closed.

### Canary G — background compute survives a session death (the Producer/Consumer contract)
A task launches a long background compute via `Bash run_in_background`; the Wave General session is
killed while it runs. **Proves:** the OS keeps the producer alive; a fresh Wave General polls the
manifest (via one `Monitor`, not a tight-poll), validates the hash on completion, and consumes.
**Pass criterion:** the output's SHA matches the manifest's `output_sha256`; the consumer's verdict
cites the producer's `code_commit` + `seed_entropy`; no run was shortened (wallclock ≈ projection).

### Canary H — re-plan without a finding-patch (Law 8)
A wave discovers that a downstream task's assumption was wrong. **Proves:** the Orchestrator records the
finding in `CAMPAIGN_LOG.md` for awareness but does **not** pre-write the conclusion into the downstream
task; the downstream task independently rediscovers it. **Pass criterion:** the downstream task's report
shows independent rediscovery; the re-plan review rejected any finding-patch; a *methodology* patch (if
any) is a Decision record.

### Canary I — the weekly-cap park (Face-1, multi-day)
`WINDOW_STATE.json` is set to simulate the weekly cap crossing its ceiling mid-wave. **Proves:**
`park.py` writes a park-state and disarms the loop; `resume.py` (after a simulated reset) re-derives
state from disk and continues from the exact frontier. **Pass criterion:** no session spins during the
park; the post-resume `REGISTRY` continues correctly with zero loss.

### Canary J — silence discipline (attention)
A full Canary-A run with no injected decisions. **Proves:** across the entire run the human receives
**zero** interrupting `PushNotification`s until the single completion ping — everything else is a batched
`OUTBOX.md` digest. **Pass criterion:** exactly one notification (completion); OUTBOX has the digests.

---

## 2. The kernel acceptance battery (unit-level, the predecessor's tests generalized)

Run before any canary; these are the predecessor's proven tests, kept:

```bash
python -m pytest runners/test_dispatch.py -q      # atomicity + race (20-parallel; 5-same-entry → 1 winner)
python -m pytest runners/test_dispatch.py -k freeze -q   # freeze reject (exit 6) + audited --unfreeze bypass
python -m pytest runners/test_dispatch.py -k gate  -q    # banking gate (exit 7) + dependency gate (exit 8)
python -m pytest runners/test_continuity.py -q    # checkpoint-resume, stall classify, producer-outlives-session
python -m pytest runners/test_repro.py -q         # seed/env/commit manifest determinism
runners/dispatch.py validate                      # full cross-entry integrity gate on the seeded workspace
```

Every one has a direct predecessor ancestor that passed: the race tests, the `EXIT_FROZEN` reject + the
`--unfreeze` audit record, the reproducibility manifest with a real `git rev-parse HEAD`, and the
`validate` schema+cross-reference check.

---

## 3. The human-runnable acceptance surface

Just as the predecessor shipped user-runnable acceptance commands (`replay.py DISC_005` reproduces a
result; `inspect_registry.py --stumps` lists every blocked item), SuperTeam ships:

```bash
runners/status.py                         # where are we: mission state, frontier, in-flight wave, budget, escalations
runners/inspect_registry.py --stumps      # every STUMPED task + its unblock criterion
runners/inspect_registry.py --unaudited   # every load-bearing claim not yet PASS
runners/replay.py <CLAIM_ID>              # independently reproduce any claim the system made
runners/dispatch.py audit-tail 50         # the last 50 mutations — the forensic chain
cat handoffs/orchestrator/CAMPAIGN_LOG.md  # the narrative of everything that happened
cat handoffs/orchestrator/WAVE_<id>_AUDIT.md   # the independent audit for any wave
```

The most important of these is `replay.py`: it is what turns "trust the system" into "verify the
system." A human returning after a week can reproduce any claim on their own machine, from the recorded
commit + seed + environment, and confirm the hash — the same fabrication detector the predecessor used
on its 13.42-hour compute to prove nothing was corner-cut.

---

## 4. Continuous self-verification (the babysit loop as an immune system)

End-to-end verification is not a one-time gate; it runs forever. On **every** 5-hour tick, the babysit
loop asserts the seven continuity invariants (`07` §8) and runs `dispatch.py validate`. A violation is a
HOLD-and-flag, never an auto-advance. This means the failure atlas (`06`) is not just a design-time
checklist — its detectors run every tick, for the life of the mission. The system is verified not only
at build time but *continuously*, against disk, for as long as it runs.

---

## 5. Definition of done for the whole system

SuperTeam is verified end to end when all of the following hold:

1. The kernel acceptance battery (§2) passes.
2. Every canary A–J (§1) passes on the real engine, unattended.
3. A human can `replay.py` every load-bearing claim from any canary and reproduce its hash.
4. Across the canary suite, the human received exactly the planted decisions as `PushNotification`s and
   nothing else (silence discipline held).
5. `dispatch.py validate` is clean and the seven continuity invariants hold at every tick of a
   multi-day unattended run.
6. The system has run at least one *real* (non-canary) mission of the operator's choosing to a DONE or a
   healthy-persistent state, surviving at least one genuine rate-limit window boundary and one genuine
   session rotation, with a clean audit trail.

At that point the system has demonstrated, on evidence and not on assertion, that it can be pointed at
any goal and left alone for days to weeks — planning, executing, verifying, recovering, and steering
itself, interrupting the human only when the human's judgment is genuinely required. Which is the whole
point.
