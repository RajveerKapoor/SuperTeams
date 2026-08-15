# 09 — The Human Interface

The design target: the human may **sleep, step away for days, or drop in at any instant to steer.**
The system must therefore be *silent by default, interruptible on genuine decisions only, and steerable
without ever stopping the machine.* Law 10 governs everything here: **spend the human's attention on
direction, never on incident.**

---

## 1. The two-surface interface

In the steady state the human touches exactly two files, plus one notification channel:

- **`control/OUTBOX.md`** — the one file to *read*. A batched, append-only digest the system writes:
  wave closures, verdicts, findings promoted, decisions made, anything noteworthy. Reading it is
  optional; nothing waits on it.
- **`control/STEERING.md`** — the one file to *write* to steer. The human drops a directive here at any
  instant; the Orchestrator reads it at the next wave boundary and re-plans (methodology change, priority
  change, new constraint, new task, "stop"). The machine never stops to wait for it — steering is
  pull, at boundaries, not push.
- **`PushNotification`** — the only channel that *interrupts* the human, reserved for the escalation
  matrix's genuine-decision events (§3).

`control/INBOX.md` exists for freeform human→system notes that aren't crisp directives (the Orchestrator
triages them into tasks or Decisions). That is the whole surface. There is no dashboard to babysit, no
stream to watch, no prompt to answer on a schedule.

---

## 2. The touchpoint policy (silent by default)

The policy lives in `control/POLICY.md` (per-mission, overriding the engine default) and is the
generalization of the predecessor's auto-advance policy. Its core statement:

> **Auto-advance is the default. The human is interrupted only for a genuine decision the machine
> cannot make itself. Everything else is absorbed and, at most, digested.**

Absorbed silently (no interruption, at most a one-line OUTBOX digest):
- a task returning FAILED, BLOCKED, DEFERRED, REVISED, TRIVIAL — all normal verdicts (Law 10);
- a wave closing with a clean audit → auto-advance to the next wave;
- a near-coincidence / candidate finding flagged (never promoted in-wave; promotion is a later gated
  pass, §8 of `08`);
- a re-plan that is a *methodology* change (not a scope fork);
- an interruption survived (rate limit, kill, park/resume) — the continuity engine handles it.

The predecessor's auto-advance policy enumerated exactly this: the babysit loop auto-launches the next
wave after a clean closure audit, "pausing + pinging only for genuine decisions." Kept and generalized.

---

## 3. The escalation matrix (the only interrupts)

`PushNotification` fires only for these, each a decision the machine is structurally forbidden from
making itself:

| Event | Why it's the human's | Default framing in the notification |
|---|---|---|
| **Audit FAIL** that can't be self-explained | A trust breach; the doer may not grade its own redo (Law 4). | "Wave C-00xx audit FAILED on claim CL-00yy: <what didn't re-derive>. Options: A) commission corrective task, B) re-run wave, C) accept-with-note. Recommend A." |
| **Scope fork** | Two valid readings of the mission diverge; only the human owns the mission's meaning (Law 10). | "Task T-00xx surfaced a fork: <interpretation 1> vs <interpretation 2>. This changes what the mission targets. Which?" |
| **Authorization request** | An irreversible or scarce-resource action, or a criterion unfreeze (Law 2/9). | "Need authorization to <push branch / delete X / spend Y / unfreeze CL-00zz criterion>. Reason: <…>. Grant?" |
| **Hard block, no unblock in reach** | The mission cannot progress without the human. | "Mission blocked: <k> frontier tasks all BLOCKED on <shared unblock, e.g. staging creds>. Nothing else is ready. Need: <the one thing>." |
| **Mission complete** (finite mode) | The deliverable is ready for review. | "Mission DONE. Deliverable: <path>. Summary: <one paragraph>. Audit: PASS. Review?" |
| **Cost/time ceiling** | A pre-set guardrail tripped. | "Mission has consumed <budget>; ceiling was <X>. Continue, adjust, or stop?" |

Every notification carries a **recommendation** and enough context to decide from the notification
alone — so a human who drops in for thirty seconds can answer without reading anything else. The
predecessor's halt-response protocol always presented "Options I see: A/B/C" with a recommendation;
this makes that the notification format.

**Batching rule:** non-urgent OUTBOX digests are batched (e.g., one digest per wave, or a daily roll-up
in persistent mode). Only escalation-matrix events break through immediately. The predecessor's fatal
counter-example — a five-day session that piled up ~20 unprocessed monitor ticks — is the reason the
system batches *out* aggressively and interrupts *in* rarely.

---

## 4. Steering without stopping

The steering channel is the mechanism that makes "drop in at any moment to steer" work without the
machine ever idling on the human.

- The human writes a directive to `control/STEERING.md` at any instant. It is timestamped by the human
  or on first read.
- The **Orchestrator reads STEERING.md at every wave boundary** (before packing the next wave) — never
  mid-wave, so a directive never corrupts an in-flight wave's frozen scope.
- If a directive is *urgent* (the human wants an in-flight wave redirected now), the human can also
  `SendMessage` the live Wave General — the Orchestrator's live channel — which the Wave General reads at its next
  **task** boundary (again, never mid-task, to protect serial banking). This is the rare push path;
  the default is the pull-at-boundary path.
- Every directive becomes a **Decision** record (and, if it authorizes something, an **Authorization**
  record) — Law 9. A steering word that isn't written to disk didn't happen.

This gives the human real-time control that is nonetheless *safe*: no directive can land in the middle
of an atomic operation, and every directive is durably recorded.

---

## 5. What the human sees on drop-in (the "catch me up" path)

When the human drops in after days away and asks "where are we," the answer is one command:

```
status.py
```

which prints, from disk: mission state, the frontier, the in-flight wave + its progress, the last N
OUTBOX digests, any pending escalations, the window/weekly budget, and any unread steering. It is the
generalization of the predecessor's session-handoff FIRST-ACTIONS block (verify HEAD, registry counts,
live processes, the clock) into a single read-only catch-up. The human never has to reconstruct state
from a transcript — the transcript is not the truth; the registry is.

---

## 6. Persistent-team mode

In persistent mode the interface shifts from "ping at completion" to "steady digest + escalate on
decision":

- **Intake.** New work arrives via `STEERING.md`, an intake directory (`handoffs/orchestrator/intake/`), or a polled
  external source (`WebFetch` on a schedule). The Orchestrator ingests it at wave boundaries, turns it
  into tasks with draft criteria, freezes them, and packs them into the rolling frontier.
- **Digest cadence.** A periodic OUTBOX roll-up (default daily) replaces the completion ping — "here is
  what the team did while you were away, here is what's queued, here is anything that needs you."
- **Standing escalations.** The escalation matrix is unchanged, but "mission complete" is replaced by
  "an SLA/health threshold tripped" for ops-style standing missions.
- **No termination.** The DAG is a rolling frontier; there is no SYNTHESIS→DONE. The babysit loop runs
  indefinitely, parking through weekly caps and resuming.

The same engine, the same registry, the same audit gate — only the intake and the termination condition
differ. "Pursue a goal to completion" and "run as a standing team" are one system.

---

## 7. Trust calibration: how the human learns to leave it alone

A system meant to run for weeks unattended must *earn* the human's absence. The design earns it three
ways:

1. **Every claim is replayable** (`replay.py`). The human can, at any time, independently reproduce
   any result the system reports — the ultimate trust primitive. Trust is not asked for; it is
   verifiable on demand.
2. **The audit gate is visible.** Every wave's `AUDIT.md` is a plain-language, independent
   re-derivation the human can read. The human isn't trusting the doer; they're trusting a cold checker
   whose work they can inspect.
3. **The escalation record is honest.** Because the system escalates *only* genuine decisions and
   absorbs *all* incidents, a human who returns to "3 escalations in 5 days" knows those three were
   real — the signal isn't diluted by noise. The predecessor's discipline of pausing only for
   audit-FAIL / HALT / unfreeze / done is what makes the escalation channel high-signal enough to
   trust.

The end state: the human checks OUTBOX when curious, answers a `PushNotification` when one genuinely
arrives, drops a steering directive when direction changes — and otherwise lets a self-defending,
self-auditing, self-continuing system carry the mission for days at a stretch.
