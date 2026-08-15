# 10 — Kept, Changed, Discarded

An explicit accounting of every load-bearing element of the predecessor, and the decision made about
it, traced to the evidence that justified the decision. This is the honest registry of the redesign: what
earned its place, what had to evolve, and what was specific to the old mission and had to go.

---

## KEPT — proven under fire, generalized in name only

These are the elements the predecessor's records show *worked*, often as the very thing that saved a
window or caught a fabrication. They are kept because redesigning a proven safety property is how you
reintroduce the bug it prevents.

| Kept element | Predecessor form | Evidence it worked | SuperTeam form |
|---|---|---|---|
| **3-tier delegation to absorb context shock** | Orchestrator / Wave General / Subagent | 38 sub-waves coordinated without the Orchestrator drowning | Orchestrator / Wave General / Subagent (same names) + the babysit loop, the independent audit, a planning subagent |
| **Filesystem as durable truth; disk wins on conflict** | `handoffs/` tree + REGISTRY | every recovery reconciled against disk, never the transcript | the same `REGISTRY` + `handoffs/` tree; reconciliation rule unchanged |
| **Atomic registry kernel** | `dispatch.py`: fcntl.flock + optimistic version + tmp/fsync/rename | passed 20-parallel + 5-same-entry race tests (exactly one winner) | `dispatch.py` (kept name), identical concurrency model, generalized schema + exit 7/8 gates |
| **Pre-registration freeze + audited unfreeze** | frozen `pre_registered.*`, `EXIT_FROZEN=6`, `--unfreeze` | 9 criterion-text-bugs, all handled correctly, zero self-unfreezes | frozen `frozen_criterion`, `EXIT_FROZEN`, human-gated `--unfreeze` |
| **Background-compute Producer/Consumer manifest** | OM §10, manifest + SHA, bash outlives session | shared an n=5M array across two waves; survived session death mid-compute | `07` §4, identical contract, domain-general spec |
| **Checkpoint after every unit; serial banking** | checkpoint after each subagent | Wave 2c blowout taught it; serial resume "banked atomically, no batch lost" | `03` §5 protocol, kernel-enforced one-unbanked-max |
| **Record ALL, promote later under FDR** | Curiosity Protocol + Wave 4b BH | foundational null results nearly pre-gated away; policy reversed | Curiosity Protocol, provenance-tagged, FDR-gated promotion |
| **Handoff-driven session rotation** | `SESSION_HANDOFF_<date>.md` + spawn + disarm | cured the 5-day context-bloat incident | `07` §5, templated handoff, single-loop invariant |
| **The honest-verdict vocabulary** | PROVEN/DISPROVEN/STUMPED/REVISED/TRIVIAL/META/DEFINITION-DEPENDENT | STUMPED-with-unblock and REVISED-for-criterion-bug both load-bearing | DONE/FAILED/BLOCKED/DEFERRED/REVISED/TRIVIAL/DEFINITION-DEPENDENT |
| **Liveness by process/CPU, not log size; no double-launch; no tight-poll** | memory pins #4/#9/#13 | each pin traces to a specific incident (spinning session, idle producer, subagent interrupt) | three-signal + four-condition liveness; Monitor-armed waits |
| **Capture out-of-band authorizations to disk** | memory pin, handoff artifact | an Option-A authorization nearly evaporated | the Authorization (`AZ-…`) object, cited by every dependent Decision |
| **REVISED-for-criterion-text-bug; never self-unfreeze** | memory pin | applied 9× correctly | `REVISED` verdict + `criterion_mismatch_flag` + freeze gate |
| **No finding-patches to downstream plans; methodology-patches OK** | memory pin | preserved independent rediscovery as a free second check | the re-plan protocol (`05` §4) distinguishing the two |
| **Audit before asserting COMPLETE (timestamp ordering)** | OM §8, Wave 0a lesson | caught a SUMMARY drafted 11 min before its audit | the `wave close` gate (AUDIT PASS timestamp precedes close) |
| **The six campaign principles** | OM §11 | the epistemic spine of the whole campaign | the Ten Operating Laws (`01`), a superset |

---

## CHANGED — the same intent, a better mechanism

These evolved because the predecessor's implementation was constrained by a bare-terminal assumption or
a single-mission scope, and a better mechanism now exists or is now needed.

| Element | Predecessor | Changed to | Why |
|---|---|---|---|
| **Control plane** | osascript Terminal spawns + manual paste + file polling | harness-native `Cron`/`Monitor`/`Task`/`SendMessage`/`PushNotification`, osascript as fallback | The predecessor hand-rolled a control plane it lacked primitives for; the native ones are robust, non-blocking, and eliminate whole failure classes (tight-poll → Monitor; manual launch → Cron; blind polling → Task/SendMessage). |
| **Verification** | Orchestrator audits its own dispatched waves | dedicated **cold Auditor** role; audit is a completion gate | Self-audit shares the doer's frame; independence closes the "mostly caught it" gap (Law 4). |
| **Work structure** | mostly-static linear wave queue with hand-authored dependency edges | adaptive dependency **DAG** + window-budgeted **wave packing**; a planning subagent re-plans | A general mission's shape is discovered, not known up front; the DAG adapts to surprises without a human re-authoring a queue. |
| **The registry** | single object type (86 verdicts) | typed multi-object **REGISTRY** (Task/Claim/Artifact/Decision/Authorization) | Generality needs to record more than verdicts — decisions, authorizations, and load-bearing claims are first-class. |
| **Curiosity Protocol** | physics-specific (constants library, τ, PSLQ, BH) | **Curiosity Protocol** with pluggable domain **lenses**; research is one lens | The discipline (record-all, promote-later, FDR) is universal; only the "what's a candidate finding" is domain-specific. |
| **Definition of done** | falsification criteria (science) | frozen **acceptance criteria** (any domain): dod + check + confidence + block-width | Anti-p-hacking generalizes to anti-goalpost-moving for any mission. |
| **Resume authoring** | `/revive` slash-command (free-form directive) | same `/revive` step + a strict `RESUME.md` schema classifying interruption + recompute-vs-synthesize | The predecessor's resume directives varied in quality; a schema forces the two distinctions it learned to draw. Name kept. |
| **Human gating** | user pastes every launch; auto-advance added late | **auto-advance by default** + tunable touchpoint policy + steering inbox + batched digest | Days-to-weeks unattended requires silence-by-default; the human steers by exception, not by launching. |
| **Wave scaffolding** | hand-authored PLAN/BRIEF per wave | `new_wave.py` templates every required file | Eliminates the convention-drift class (missing NOTES, ad-hoc STATUS fields) at the source. |
| **Model usage** | one top-tier model for everything (no launcher knob) | **model tiering** by role/task | Efficiency with no capability loss where it matters; the daemon needn't burn a top model on a 5-hour loop. |

---

## DISCARDED — specific to the old mission, or superseded

Removed entirely, because keeping them would either couple the system to physics or reintroduce a
failure the predecessor cured.

| Discarded | Why |
|---|---|
| **All chaos/physics content** — integrators, Benettin, RMT, the 86 discoveries, the constants library as a *required* gate | The mission is now *any* domain; the constants library survives only as the `research` lens's optional matcher, never a gate. Requiring a constants match would violate the predecessor's own deepest lesson ("gravity and calculus were not matches against an existing library"). |
| **The bare-terminal assumption** (osascript + manual paste as the *only* path) | Superseded by the native control plane; osascript is kept as a portable fallback, not the primary. |
| **The single long-lived Orchestrator** | Directly caused the 5-day bloat incident; replaced by mandatory rotation. Keeping it would reintroduce A2. |
| **The mostly-linear queue as the primary structure** | Kept only as a *rendering* (`QUEUE.md`); the DAG is now primary. A general mission can't be a straight line. |
| **Implicit context discipline** ("the Orchestrator won't read full records") as a *habit* | Replaced by *structural* budgets: roles' charters list forbidden paths, and the cross-role currency is the ≤2000-word SUMMARY. A habit that depends on memory dies with the session. |
| **Per-wave manual plan authoring as the *only* path** | Kept as the norm (the Orchestrator still authors wave plans), but backed by templated scaffolding (`new_wave.py`) + a planning subagent for genuine re-planning; hand-authoring the whole plan from scratch every time is no longer required. |
| **Wall-clock estimates used as pressure** | The predecessor already removed subagent wall-clock caps ("take all the time you need; quality > speed"); the discard is completed — estimates are planning aids for wave packing only, never Subagent deadlines. |

---

## The through-line

The redesign kept every safety property the records show *saved* the campaign, changed every mechanism
the bare-terminal assumption made fragile, and discarded everything that was physics or that caused a
recorded failure. The predecessor was right about *what matters* (truth on disk, honest verdicts,
independent re-derivation, survive-without-fabrication, record-all) and constrained about *how to
achieve it* (manual launchers, self-audit, static queue, single session). SuperTeam keeps the *what*
and rebuilds the *how* on primitives and a generality the predecessor didn't have.
