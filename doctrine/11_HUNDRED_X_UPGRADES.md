# 11 — The 100x Upgrade List

"100x" is not a throughput claim; it is a *capability and reliability* claim. The predecessor could
verify 86 discoveries in one physics mission, driven by disciplined human operators who remembered
hard-won rules, launching each wave by hand, auditing its own work, and surviving interruptions by
attention. SuperTeam pursues *any* mission, defends itself structurally against every failure the
predecessor hit, runs its control plane on native primitives, and needs the human only for genuine
decisions. Each upgrade below names the concrete capability gained and the specific limitation or
failure it removes.

Ordered by leverage — the ones nearest the top change what the system *can be*, not just how well it
runs.

### 1. Generality: any mission, one engine
The single largest upgrade. Every physics assumption is lifted out of the kernel into a pluggable
**lens**; the falsification criterion becomes a domain-general **acceptance criterion**; the registry
becomes a typed **registry**. The system now serves research, engineering, operations, writing — or runs
as a persistent standing team — with the same machinery. *Removes:* the hard coupling to one domain.
*Gains:* a goal-pursuit engine, not a physics verifier.

### 2. Harness-native control plane
`Cron` (the loop), `Monitor` (liveness/artifact waits), the `Task` system (live work mirror + completion
callbacks), `SendMessage` + background `Agent` (live role coordination), `PushNotification` (human
escalation) replace hand-rolled osascript-and-poll machinery. *Removes:* the tight-poll failure class
(a Monitor can't get a subagent interrupted the way a poll loop did), the manual-launch bottleneck, and
the blind "check on wave N" human poll. *Gains:* a non-blocking, self-driving control plane.

### 3. Independent cold Auditor as a completion gate
The checker is never the doer, and it works from a fresh session with no memory of the doing. No wave
closes without an independent PASS timestamped before the close. *Removes:* the self-audit blind spot
(the predecessor's Orchestrator graded its own dispatch). *Gains:* trust that survives the doer's own
convictions.

### 4. Anti-fabrication as kernel exit codes, not discipline
`dispatch.py update` recomputes artifact hashes and refuses a completion with no persisted artifact
(exit 7); `dispatch.py update` refuses before dependencies are DONE (exit 8); `close_wave.py` refuses
before an audit passes. The predecessor's most-pinned rules become impossible to violate. *Removes:*
"agent completed but wrote nothing" mislabels (Wave 2j). *Gains:* completion means a re-derivable fact.

### 5. Adaptive dependency DAG + window-budgeted wave packing
Work is a living graph whose ready frontier is packed into window-sized waves; a planning subagent
re-plans on surprise. *Removes:* the static hand-authored queue (a general mission's shape is discovered, not
known). *Gains:* the system adapts its own plan without a human re-authoring it.

### 6. Continuity engine with graceful parking
Window/weekly-cap budgeting, serial banking (one-unbanked-max), per-unit atomic partial-writes, and
`park.py`/`resume` across multi-day caps. *Removes:* window-blowout-with-nothing-persisted (Wave 2c),
weekly-cap thrashing. *Gains:* a mission that survives days of forced pause intact.

### 7. Mandatory dual rotation, single-loop invariant
Both Orchestrator and Wave General rotate to bound context; exactly one babysit loop exists, transferred atomically
on rotation. *Removes:* the 5-day context-bloat / instant-rate-limit incident (A2) and the
double-launch hazard. *Gains:* sessions stay small and replaceable indefinitely.

### 8. Three-signal, four-condition liveness
Liveness = CPU-delta + artifacts-delta + checkpoint-advance, and the classifier distinguishes
alive-progressing / alive-stalled / alive-paused / gone. *Removes:* the "alive but spinning, banked
nothing" mistake (A5) and the "double-launched a warm session" mistake (C1). *Gains:* the babysit loop acts
on progress, not on process-existence.

### 9. Definition-of-done freezing (anti-goalpost-moving)
Acceptance criteria frozen before work starts; only a human, via an audited authorization, can move a
goalpost. *Removes:* a subagent rationalizing its output into a pass. *Gains:* verdicts rendered against
criteria committed before the result was seen — for any domain, not just science.

### 10. The Curiosity Protocol with pluggable lenses
Record-all / promote-later / provenance-tag / FDR-gate, with the domain-specific "what's a candidate
finding" swapped per task (research / engineering / ops / writing / generic). *Removes:* the
physics-only Curiosity Protocol and the pre-gating that nearly discarded foundational nulls. *Gains:*
serendipitous discovery in any domain, without crying wolf.

### 11. Typed multi-object registry with an accountability layer
Tasks, Claims, Artifacts, **Decisions**, and **Authorizations** as first-class objects. *Removes:* the
"out-of-band authorization evaporates" hazard (F1) and the inability to record *why* a choice was made.
*Gains:* a forensic record of every decision and human word.

### 12. The `dispatch.py` family — kept, extended, replay-backed
The predecessor's proven CLI (`dispatch.py`, `replay.py`, `inspect_registry.py`, `pre_register.py`) is
kept name-for-name and extended with thin snake_case helpers (`roadmap.py`, `new_wave.py`,
`close_wave.py`, `park.py`/`resume.py`, `window.py`) — no monolithic rewrite, nothing to re-learn.
*Removes:* the scatter of ad-hoc per-wave scripts. *Gains:* every result reproducible on demand
(`replay.py`), every integrity property checkable (`dispatch.py validate`), continuity operations
first-class.

### 13. Templated scaffolding + schema-validated state
`new_wave.py` creates every required file; `dispatch.py validate` makes a missing field an error. *Removes:*
the entire "bookkeeping convention drift" class (missing NOTES, ad-hoc STATUS strings, inconsistent
counts — Waves 0d/0e/1e). *Gains:* state that cannot silently rot.

### 14. The `/revive` resume schema
A formal re-entry brief (the predecessor's `/revive`, now schema'd) that classifies the interruption
(stalled-nothing-banked vs partial vs
awaiting-bg) and, per pending item, decides recompute-vs-synthesize. *Removes:* vague resume directives
and the recompute-that-duplicates-the-append-only-pool hazard (A4). *Gains:* every recovery is precise
and non-fabricating.

### 15. Model tiering
Top tier for the mission's quality ceiling (Orchestrator / planning subagent / audit), reliability tier for orchestration
(Wave General), task-matched for Subagents, cheap for the babysit loop daemon. *Removes:* burning a top model on a
mechanical loop. *Gains:* the rate-limit budget spent where it buys capability.

### 16. Dual dispatch modes, formalized
Session-spawn (own window, own context, own rate-limit envelope) for Orchestrator/Wave General; in-session `Agent`
for Subagents. *Removes:* the risk of one exhausted envelope taking down the whole tree. *Gains:* deaths
are contained to one session; the tree survives.

### 17. Steering-without-stopping
A steering inbox read at wave boundaries (never mid-wave), plus a rare live-push path read at task
boundaries. *Removes:* the choice between "stop to ask the human" and "ignore the human." *Gains:*
real-time redirection that never corrupts an atomic operation.

### 18. Self-defending failure atlas
Every known failure has a **detector** (in `dispatch.py validate` / the babysit loop classifier) and a structural
cure. *Removes:* reliance on an operator remembering thirteen memory pins. *Gains:* an immune system —
the system notices its own failure modes and responds structurally.

### 19. Multi-mission babysit loop
One babysit loop daemon can carry several missions' queues, sharing the window budget across them (round-robin
by priority within the rate-limit envelope). *Removes:* one-mission-at-a-time. *Gains:* a single Mac can
run a portfolio of autonomous missions under one rate-limit budget.

### 20. Persistent-team mode as a first-class configuration
Intake channel + rolling frontier + digest cadence + no termination, on the identical engine. *Removes:*
the assumption that a mission must end. *Gains:* "pursue a goal" and "be a standing team" are one system,
one config flag apart.

### 21. Replay-backed trust calibration
Because `replay.py` reproduces any claim on demand and every `AUDIT.md` is a readable independent
re-derivation, the human can *verify* rather than *trust*. *Removes:* the leap of faith required to
leave a system alone for a week. *Gains:* earned, verifiable absence.

---

## Why these compound

The upgrades are not independent; they reinforce. Generality (#1) is only *safe* because the
anti-fabrication kernel (#4) and the independent audit (#3) make any domain's output trustworthy. The
native control plane (#2) is only *reliable* because the continuity engine (#6) and liveness signals
(#8) keep it from the predecessor's coordination failures. The DAG's adaptivity (#5) is only *honest*
because the freeze (#9) and the no-finding-patch rule (`05` §4) preserve independent rediscovery. The
system is 100x not because any one piece is 100x better, but because the pieces that made the
predecessor *survivable by disciplined humans* are now *structural*, and the pieces that made it
*physics-specific* are now *general* — so the same hard-won reliability now applies to any mission the
human can name, for as long as they care to leave it running.
