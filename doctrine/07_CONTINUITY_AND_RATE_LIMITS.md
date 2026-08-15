# 07 — The Continuity Engine

Continuity is the system's core competency, because it was the predecessor's hardest-won lesson: more
of its records concern *surviving interruption without loss or fabrication* than concern any actual
domain work. A system that must run unattended for weeks under 5-hour usage windows and weekly caps —
where sessions pause at limits and do **not** auto-resume — lives or dies on this engine. Everything
here is grounded in a specific predecessor incident (cross-referenced to `06`).

---

## 1. The rate-limit model

The subscription exposes two limits the system must respect and exploit:

- **The 5-hour usage window.** Work proceeds until the window's budget is spent; then the session
  pauses and does not auto-resume. A new window opens on a rolling 5-hour cadence.
- **The weekly cap.** A hard ceiling across windows; when hit, the system must park until the weekly
  reset (which can be days away).

Two design consequences drive the whole architecture:

1. **One Wave General session ≈ one window ≈ one wave.** Waves are *packed to fit a window* so that a normal
   wave completes inside one window and a fresh window is available to launch the next. The
   predecessor discovered this alignment empirically ("the 5h cadence is window-aligned … launching the
   next wave on the fire that closes the prior one hands it a fresh window") and it is baked in here.
2. **The launch cadence is window-aligned.** The babysit loop fires on a 5-hour `Cron` cadence, matched to
   the window, so that the tick that closes one wave launches the next into a fresh window.

`control/WINDOW_STATE.json` is the tracker the babysit loop owns:

```json
{
  "window_started_at": "2026-07-03T08:00:00Z",
  "window_length_h": 5.0,
  "window_budget_remaining_frac": 0.62,
  "weekly_cap_reset_at": "2026-07-06T00:00:00Z",
  "weekly_used_frac": 0.71,
  "cadence_cron": "13 */5 * * *",
  "last_tick_at": "2026-07-03T10:13:00Z",
  "park_state": null
}
```

`weekly_used_frac` is estimated from observed usage; when it crosses a configurable ceiling (default
0.9) with the reset still far off, the babysit loop parks rather than starting a wave it cannot finish.

---

## 2. The babysit loop classifier (the heart of the loop)

On every `Cron` tick, the babysit loop runs one classification from **on-disk truth alone**, and takes one
action. It never reasons from a transcript; it reads files. This is the babysit loop and the
auto-advance policy, generalized and made rigorous.

**Inputs (all from disk):**
- the in-flight wave from `QUEUE.md` and its `STATUS.json`;
- process liveness for the Wave General (via `ps`/pgrep — is the named session alive?);
- the **three liveness signals** (`06` A5): CPU-time delta, artifacts-count delta vs the wave
  baseline, checkpoint-timestamp advance;
- `dispatch.py validate` result;
- `WINDOW_STATE.json` and `STEERING.md` (any new human directive?).

**The decision table:**

| Wave STATUS | Process | Progressing? (3-signal) | Action |
|---|---|---|---|
| RUNNING | alive | yes | **HOLD.** Post nothing. The wave is working. |
| RUNNING | alive | **no** (stalled, A5) | If **nothing banked** → kill + clean restart. If **something banked** → kill + checkpoint-resume via a `/revive` RESUME. |
| RUNNING | **gone** | (n/a) | INTERRUPTED. Orchestrator writes RESUME (`/revive`); relaunch from checkpoint (pre-launch liveness check first, C1). |
| RUNNING | alive-**paused** at limit | warm context worth keeping | Do **not** double-launch. Write RESUME; **ping human to paste** into the paused session (preserves warm context). |
| HALTED | (any) | — | Read HALT.md; classify; Orchestrator decides; write RESUME or escalate per touchpoint policy. |
| AWAITING_BG_COMPUTE | — | producer manifest COMPLETE + hash OK? | If ready → relaunch Wave General to consume. If still running → HOLD (Monitor-armed, not polled). |
| COMPLETE | — | AUDIT PASS + validate clean? | **Auto-advance:** update QUEUE + LOG, commit, pack + launch next wave, rotate Orchestrator, digest to OUTBOX. If audit FAIL / validate dirty → **PAUSE + ping** (decision). |
| — | — | weekly cap near | **Park** gracefully (§7). |
| — | — | new STEERING directive | Route to Orchestrator at the wave boundary (re-plan). |

The two subtleties the predecessor paid for in blood are both here: **alive ≠ progressing** (A5 — a
spinning session banks nothing), and **alive-paused ≠ gone** (C1 — never double-launch a session whose
warm context is worth a human paste). The classifier distinguishes all four process conditions
(alive-progressing / alive-stalled / alive-paused / gone) because collapsing any two of them was a
real bug.

---

## 3. Checkpointing (the resumability contract)

`handoffs/checkpoints/WAVE_<id>_CHECKPOINT.md` is overwritten after **every** task banks (never batched), so a fresh
Wave General can resume from exactly the last banked task.

```json
{
  "wave_id": "2k",
  "completed": ["TASK_0031", "TASK_0032"],
  "in_progress": null,
  "pending": ["TASK_0033"],
  "deferred": [{"task": "TASK_0033", "manifest": "artifacts/TASK_0033/out.manifest.json", "shell_id": "bg-9f3"}],
  "artifacts_baseline": 1940,
  "artifacts_at_checkpoint": 1972,
  "last_checkpoint_at": "2026-07-03T09:14:00Z",
  "reconcile_rule": "registry wins on any conflict"
}
```

On resume, the Wave General: reads the checkpoint → cross-checks against the registry (**registry wins**) →
reverts any orphan IN_PROGRESS to PENDING with a note → resumes from the first pending task. Because
banking is serial (`03` §5), at most one task is re-done. The predecessor's "no orphan in-progress
states across sessions" and "registry wins on conflict" are both here verbatim.

---

## 4. The background-compute contract (Producer → Wave General → Consumer)

For any compute that cannot finish inside one session — the exact reason the predecessor built this —
work is handed to a background process that **outlives the Claude session** (the OS keeps a
`run_in_background` Bash shell alive after the session closes). This is what makes "never shorten a run
to fit a session" (B1) actually achievable: the run simply outlives the session.

**Actor 1 — Producer (a Subagent) launches, does not wait.**
1. Chooses a canonical output path: `artifacts/<task>/<name>_<key-params>.<ext>`.
2. Writes the **manifest** *before* launching, at `<output>.manifest.json`:

```json
{
  "schema_version": 1,
  "output_path": "artifacts/TASK_0033/matrix_result.json",
  "producer_task": "TASK_0033",
  "target_spec": {"…the full spec that defines the work…"},
  "code_commit": "<git HEAD>",
  "env_hash": "<hash>",
  "seed_entropy": "0x…",
  "started_at": "…",
  "expected_completion_at": "…",
  "status": "RUNNING",
  "shell_id": "<run_in_background id>",
  "output_sha256": null,
  "completed_at": null,
  "consumers": ["TASK_0033"]
}
```

3. Launches the compute via **background `Bash`**. **The bash command itself** computes the output
   hash on completion and writes `output_sha256` + `completed_at` + `status: COMPLETE` back into the
   manifest atomically. (Anti-fabrication clause: the Producer subagent never writes the hash before
   the work is done — the hash is computed by the finished job, not asserted by the launcher.)
4. Returns `{verdict: DEFERRED, manifest_path, shell_id, expected_completion}` and **exits.**

**Actor 2 — Wave General polls (via Monitor, not a loop), validates, spawns the consumer.**
- Records the deferral in the checkpoint. Continues other non-dependent tasks (serial-banked).
- To wait: **arms one `Monitor`** on the output file appearing with a non-null manifest hash (C2 — no
  tight-poll).
- Before consuming, the **five-check validation**: manifest `status == COMPLETE`; output file exists;
  size matches the spec; recomputed SHA matches `output_sha256`; `completed_at` is sane. Any failure →
  HALT (this is a producer-failure or tampering case; never silently use suspicious data).
- If the Wave General's own window expires while the producer runs: STATUS → `AWAITING_BG_COMPUTE`, exit
  cleanly; the bash shell keeps running under the OS; a fresh Wave General resumes the poll-validate-consume.

**Actor 3 — Consumer (a Subagent or the Wave General directly) reads the persisted output, renders the verdict.**
- Re-validates the hash, loads the output, runs the analysis, banks the task with the manifest's
  provenance copied in (so the verdict is traceable to the exact producer run + commit + seed).
- **Respawn-vs-direct (C3):** if consuming is pure synthesis of on-disk data, the Wave General does it directly
  rather than spawning an idle consumer.

**Multi-consumer reuse:** if two tasks need the same expensive output, the first produces it and the
second's brief includes a *reuse check* — if the output already exists with a valid hash, skip the
producer entirely. (The predecessor shared one n=5M array across two waves exactly this way.)

**`INFEASIBLE`:** if the hardware genuinely cannot complete the full spec in available time, the
producer writes `status: INFEASIBLE` with the projected wallclock and the Wave General HALTs to the Orchestrator —
it **never** silently substitutes a smaller job. This is the structural guarantee behind B1.

---

## 5. Session rotation (bounding context)

Both top-level roles rotate to obey Law 6 and prevent A2.

**Orchestrator rotation** — after a wave closes, audits clean, and advances:
1. Write `handoffs/SESSION_HANDOFF_<iso>.md` — a self-contained re-entry brief (template below).
2. `_spawn_orchestrator.sh --handoff <file>` → spawns a fresh Orchestrator session with the handoff as its
   opening prompt, then **disarms its own babysit loop `Cron` loop** (`CronDelete`), so exactly one
   Orchestrator loop exists at a time.
3. The fresh Orchestrator's first act: **verify everything against disk** — never inherit the handoff's
   numbers. (The predecessor's handoffs all carried the instruction "On restore: VERIFY everything vs
   disk — never inherit the numbers below." Kept.)

**Wave General rotation** — a Wave General does not rotate mid-wave; it *is* the wave. When its window is exhausted
it checkpoints and exits; the *next* Wave General session (fresh window) resumes the same wave from the
checkpoint. This is rotation-by-wave-boundary, which keeps each Wave General session bounded by one window.

**The handoff brief** (`SESSION_HANDOFF_<iso>.md`) contains, in order: the FIRST-ACTIONS checklist
(verify HEAD, registry counts, live processes, the clock); the session-rotation reminder; the state at
handoff-write (marked VERIFY!); pending human-gated decisions; the standing policy + invariants; and
the queue/what's-next. This is exactly the predecessor's `SESSION_HANDOFF_<date>.md` structure, which
worked; it is templated so every rotation produces a complete one.

**Single-loop invariant:** at most one babysit loop `Cron` loop runs at any time. Rotation transfers loop
ownership atomically (new Orchestrator arms its loop only after the old one disarms). The predecessor's
memory pin #13 — "single orchestrator loop, pre-launch liveness check, no double-launch" — is the
invariant; the rotation sequence enforces it.

---

## 6. The `/revive` resume directive and its schema

When a session needs a re-entry brief (interrupted, halted, stalled), the **Orchestrator** authors a
`RESUME.md` from on-disk truth — the predecessor's `/revive` step. The one addition is a **strict
schema**, so a resume directive is never vague and never invites fabrication.

`RESUME.md` schema:
```markdown
# WAVE <id> RESUME DIRECTIVE
## Interruption class: interrupted | halted-<reason> | stalled-nothing-banked | stalled-partial | awaiting-bg
## Verified on-disk state: <registry counts, banked tasks, artifacts count, HEAD, what is/isn't persisted>
## What to preserve: <the persisted compute that must NOT be recomputed — cite hashes>
## What to (re)do: <the pending tasks; for a stall-nothing-banked, "clean restart, nothing to recompute">
## Recompute-vs-synthesize: <for each pending item: new compute → respawn Subagent; on-disk synthesis → drive directly (A4/C3)>
## Do NOT: double-launch if alive (C1); recompute persisted artifacts (A4); shorten any run (B1); self-unfreeze (D3)
## Close: <the exact close sequence — local audit-trail before SUMMARY (D2); audit PASS gate (D1); allow-listed commit (E2)>
## Principles: on-disk = truth; investigate WHY before adjusting a window; record ALL; promote nothing (the audit gates).
```

The schema forces the two distinctions the predecessor learned to draw: **stalled-nothing-banked**
(clean restart — nothing to recompute) vs **stalled-partial** (checkpoint-resume), and
**recompute-vs-synthesize** per pending item (A4/C3). A resume that doesn't classify the interruption
is rejected by `dispatch.py validate`.

The Orchestrator writes the directive (`/revive`); it never *executes* the resume — that is the
relaunched Wave General's job.
And a resume directive is authored to instill the principles "to an extent even greater than it was
previously pursuing" (the predecessor's `/revive` charter) — recovery is an opportunity to raise the
bar, not merely restore it.

---

## 7. Graceful parking (surviving the weekly cap)

When the weekly cap looms (or the human says "stop"):
1. `park.py "<reason>"` writes `WINDOW_STATE.json.park_state` with the reason, the frontier, and the
   resume condition, and disarms the babysit loop `Cron` loop.
2. The system sleeps. No session spins, no window is wasted, no work is lost — the registry and
   checkpoints hold everything.
3. On the weekly reset (or the human's "go"), `resume.py` re-derives the full state from disk,
   re-arms the babysit loop window-aligned to the fresh window, and continues from the exact frontier.

Parking is why a multi-day rate-limit reset is a non-event (A6). The predecessor rode one out by
manual attention; here it is a state transition the babysit loop makes autonomously and reverses cleanly.

---

## 8. The continuity invariants (one place)

Everything above reduces to seven invariants the babysit loop asserts on every tick:

1. **At most one task's work is ever unbanked** (serial banking).
2. **At most one babysit loop runs** (single-loop, rotation-transferred).
3. **No role session exceeds its context/age budget** (rotation, or flag).
4. **No live-and-progressing process is ever double-launched** (three-signal + four-condition liveness).
5. **No background job is tight-polled** (Monitor-armed).
6. **No completion exists without a persisted, hashed, re-derivable artifact** (banking gate).
7. **The weekly cap parks gracefully; the 5h window rolls the cadence** (window budget).

If any invariant is violated, the tick's action is HOLD-and-flag, never auto-advance. The system's
continuity is not a hope; it is these seven assertions, checked every five hours against disk.
