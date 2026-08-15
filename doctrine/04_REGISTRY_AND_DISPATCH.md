# 04 — The REGISTRY and the dispatch.py Kernel

`REGISTRY.json` is the durable source of truth; `dispatch.py` is the atomic primitive that protects it.
This is the one place the predecessor's implementation is kept almost verbatim, because it was *proven
correct under the exact adversarial conditions this system faces* — its `dispatch.py` passed a
20-way-parallel non-conflicting race test and a 5-way same-entry race that produced exactly one winner
and four clean conflicts. That is not a property to redesign; it is a property to generalize and build
on. The name stays `dispatch.py`; only the entry *types* it stores are generalized.

---

## 1. The kernel: how a write is made atomic

Every mutation of `REGISTRY.json` goes through `dispatch.py` and obeys the predecessor's two-layer
contract:

1. **OS-level exclusive file lock** on `REGISTRY.lock` via `fcntl.flock(LOCK_EX | LOCK_NB)` in a
   polling loop with a 30-second soft timeout. Serializes writers: one process in the critical section
   at a time.
2. **Optimistic version check.** Every entry carries a `version` integer. A patch must assert the
   `version` it read. If another writer bumped it between read and lock acquisition, the patch is
   refused (`EXIT_VERSION_CONFLICT`). This catches the read-modify-write race that locking alone cannot.

The write itself is `open(tmp,"w") → flush → os.fsync → os.rename(tmp, dest)`, atomic on POSIX when
`tmp` and `dest` share a filesystem. Every applied mutation appends one JSON line to `REGISTRY.audit.log`
with timestamp, entry id, the patch, prior/new version, caller pid, and argv — the forensic chain that
lets a corrupted registry be reconstructed and any surprising write be traced.

**Exit codes** (referenced by tests and the babysit loop's decision table). The first seven are the
predecessor's; codes 7 and 8 are the only additions:

```
0  OK                    3  VERSION_CONFLICT       6  FROZEN (criterion change without --unfreeze)
1  GENERIC               4  LOCK_TIMEOUT           7  ARTIFACT_MISSING (complete with no persisted+hashed artifact)  [NEW]
2  NOT_FOUND             5  SCHEMA                 8  DEPENDENCY_NOT_MET (start/complete before deps COMPLETED)      [NEW]
```

Codes 7 and 8 make two of the predecessor's most-pinned disciplines *kernel-enforced* rather than
agent-remembered. On a status-to-COMPLETED patch, `dispatch.py` recomputes the SHA-256 of every
referenced artifact and refuses (exit 7) if a referenced artifact is absent or its hash does not match
the patch's claimed hash. An agent that "completed" but wrote nothing gets a hard error, not a silent
success — the Wave-2j "spun 5.5h, banked nothing" mislabel becomes structurally impossible.

---

## 2. The REGISTRY holds typed entries

The predecessor's registry held one entry type (86 discovery verdicts, keyed `DISC_###` / `GAP_###`).
The generalization holds five, keyed by id prefix, all under one atomic file so one lock protects every
cross-entry invariant:

```json
{
  "schema_version": 2,
  "mission": "clarity-refactor",
  "mode": "finite | persistent",
  "created_at": "…",
  "pre_registered_frozen_at": "2026-07-03T12:00:00Z",
  "n_entries": 92,
  "entries": {
    "TASK_0001": { …task… },
    "CLAIM_0001": { …claim… },
    "ART_0001":  { …artifact_ref… },
    "DEC_0001":  { …decision… },
    "AUTHZ_0001":{ …authorization… }
  }
}
```

The `DISC_`/`GAP_` ids the operator knows remain valid entry ids; `TASK_`/`CLAIM_`/`ART_`/`DEC_`/
`AUTHZ_` are the general prefixes. `dispatch.py update --disc <ID>` takes any entry id (the flag name is
the historical one; it selects a registry entry).

### Task (`TASK_…`) — a node in the DAG (generalizes a discovery)
```json
{
  "id": "TASK_0031",
  "type": "task",
  "title": "Refactor the config loader to remove the global singleton",
  "wave": "2k",
  "status": "PENDING",
  "status_enum": "BLOCKED_ON_DEPS|PENDING|IN_PROGRESS|COMPLETED",
  "verdict": null,
  "verdict_enum": "DONE|FAILED|STUMPED|DEFERRED-COMPUTE-RUNNING|REVISED|TRIVIAL|DEFINITION-DEPENDENT|META-QUESTION",
  "verdict_value": null,
  "verdict_ci_95": null,
  "dependencies": ["TASK_0028", "TASK_0030"],
  "pre_registered": {
    "falsification_criterion": "config.load() has no module-level state; all 41 call sites updated; suite green; no new public API",
    "acceptance_check": "pytest tests/config -q → 0 failures AND grep -rn '_GLOBAL_CFG' src/ → 0 hits",
    "required_precision_se": "deterministic",
    "stumped_ci_width": null,
    "target_n": 1
  },
  "model_hint": "capable",
  "lens": "engineering",
  "agent_id": "wave-2k-sub1",
  "started_at": null, "finished_at": null,
  "methods_used": [], "numerics_config": {},
  "code_commit": null, "env_hash": null, "input_data_hashes": {},
  "report_path": null, "report_sha256": null,
  "artifacts": [], "side_findings": [],
  "unblock_criterion": null, "criterion_mismatch_flag": false,
  "theoretical_conflict": false,
  "version": 3
}
```

The `verdict_enum` keeps the predecessor's honest-verdict vocabulary, which generalizes cleanly:
`DONE` (met the criterion — the general form of PROVEN), `FAILED` (definitively did not — DISPROVEN),
`STUMPED` (couldn't decide; carries an `unblock_criterion`), `DEFERRED-COMPUTE-RUNNING` (long compute
handed off), `REVISED` (substance established but the frozen criterion has a text/pointer bug — surface
it, don't self-fix), `TRIVIAL` (the "claim" is an identity/tautology, not a finding),
`DEFINITION-DEPENDENT` / `META-QUESTION` (the answer hinges on a definition/an open question the
criterion left ambiguous). Every one is an *honest* terminal verdict; none is a failure of the system.
The operator already knows all of them.

### Claim (`CLAIM_…`) — a load-bearing assertion the audit must re-derive
A task produces Claims — anything the mission relies on downstream (a measured value, a
"byte-identical," a "suite green at commit X," a decision-relevant fact). Each carries its evidence
pointer, its re-derivation recipe, and an `audit_state`. The auditor re-derives every Claim with
`load_bearing: true` from artifacts alone.

```json
{ "id": "CLAIM_0031", "type": "claim",
  "statement": "All 41 call sites of _GLOBAL_CFG removed; suite green at commit a1b2c3d",
  "source_task": "TASK_0031", "load_bearing": true,
  "evidence": ["ART_0044", "ART_0045"],
  "rederive": "git checkout a1b2c3d && pytest tests/config -q && grep -rn '_GLOBAL_CFG' src/",
  "audit_state": "UNAUDITED|PASS|FAIL|PASS_WITH_NOTES", "audited_by": null, "version": 1 }
```

### ArtifactRef (`ART_…`) — a pointer to a persisted, hashed output
The registry holds *references*; the bytes live under `datasets/` or `reports/`. (The predecessor's
`DISC_005` entry already carried an `artifacts` array of exactly such paths.)

```json
{ "id": "ART_0044", "type": "artifact_ref",
  "path": "reports/TASK_0031_pytest_config.log", "sha256": "…", "bytes": 8134,
  "manifest": "datasets/…manifest.json", "produced_by": "TASK_0031", "version": 1 }
```

### Decision (`DEC_…`) and Authorization (`AUTHZ_…`) — the accountability layer
Every non-mechanical Orchestrator choice (re-plan, wave-ordering change, escalation, unfreeze, scope
change) is a **Decision** with its rationale and the entries it touched. Every human authorization is an
**Authorization** with who/what/when/scope — written *before* the Orchestrator acts on it (Law 9). A
Decision that depends on a human's word cites the `AUTHZ_…` id. This makes the predecessor's "capture
out-of-band authorizations to disk" a schema requirement: an unfreeze Decision with no cited
Authorization is a validation error.

```json
{ "id": "AUTHZ_0003", "type": "authorization", "granted_by": "human",
  "grants": "unfreeze CLAIM_0009.falsification_criterion (criterion points at wrong file)",
  "scope": "one-time, CLAIM_0009 only", "granted_at": "2026-07-03T15:04:00Z",
  "channel": "STEERING.md line 12", "version": 1 }
```

---

## 3. The freeze: definition-of-done is immutable once work starts

The predecessor's pre-registration freeze (anti-p-hacking) is kept verbatim in mechanism and
generalized in meaning to **anti-goalpost-moving**. Before any Subagent starts a task, its
`pre_registered` block is frozen: `pre_register.py` sets `pre_registered_frozen_at` and marks each
criterion frozen. After that, `dispatch.py update` **rejects** any patch that alters a frozen
`pre_registered.*` field (`EXIT_FROZEN=6`) unless the caller passes `--unfreeze <ID>.<field>` — which
requires a cited Authorization and writes a double audit record (the mutation *and* an `unfreeze: true`
marker). The four freezable fields are the predecessor's, reinterpreted:

| Field (kept name) | Meaning (generalized) |
|---|---|
| `falsification_criterion` | what "done" means, in prose |
| `acceptance_check` | the mechanical check that decides it |
| `required_precision_se` | how sure we must be (an SE, a p-value, or the literal string `"deterministic"`) |
| `stumped_ci_width` | how uncertain before we honestly STUMP |
| `target_n` | sample size, or `1` for a structural/deterministic task |

This is the structural form of Law 3 ("never relax a frozen window to fit"). A Subagent whose result
lands outside the frozen window cannot make itself pass; it HALTs-and-investigates, or returns REVISED
with the mismatch surfaced. **Only the human, through an audited Authorization, can move a goalpost** —
every move forever traceable. The predecessor's transparent handling of `target_n=1` for its 11
structural (non-statistical) claims is exactly the pattern a general mission uses for deterministic
tasks. Its record of **nine** criterion-text-bugs, each handled correctly (flag → REVISED →
user-gated unfreeze) and never self-unfrozen, is the evidence this mechanism works.

---

## 4. `dispatch.py validate` — the integrity gate

Beyond schema-checking each entry, `dispatch.py validate` enforces cross-entry invariants:
- every `dependencies[]` id exists, and a COMPLETED/IN_PROGRESS task's deps are COMPLETED (else exit 8);
- every `artifacts[]`/`evidence[]`/`input_data_hashes` id exists and its file is present with a matching
  hash;
- no orphan `IN_PROGRESS` (a task IN_PROGRESS whose wave has no live Wave General is reverted to PENDING
  on resume, with a note — the predecessor's "no orphan in-progress states across sessions");
- `n_entries` matches; a frozen entry has all five `pre_registered` fields; a load-bearing Claim has a
  non-empty `rederive`; an unfreeze Decision cites an Authorization.

The babysit loop runs this every tick. It is the generalized cure for the predecessor's entire class of
"bookkeeping drift" incidents — they become detected schema/invariant failures, not silent rot.

---

## 5. The CLI family (real command lines)

Kept from the predecessor: **`dispatch.py`**, **`replay.py`**, **`inspect_registry.py`**,
**`pre_register.py`**. New thin helpers for the new capabilities, named in the predecessor's snake_case
style. Every mutation is atomic and audited through `dispatch.py`.

```bash
# ── plan (roadmap.py = the DAG; NEW) ───────────────────────────────────────
runners/roadmap.py add-task --title "…" --deps TASK_0028,TASK_0030 --lens engineering --model capable
runners/pre_register.py --set --disc TASK_0031 --dod "…" --check "pytest … && grep …" --precision deterministic
runners/pre_register.py                                   # freeze ALL criteria; sets pre_registered_frozen_at
runners/roadmap.py frontier                               # print PENDING tasks whose deps are COMPLETED
runners/roadmap.py pack --window-budget 4.5h              # propose the next wave's task set (07 §1)

# ── wave lifecycle ─────────────────────────────────────────────────────────
runners/new_wave.py 2k --tasks TASK_0031,TASK_0032,TASK_0033   # scaffold handoffs/{waves,briefs,status,…}
runners/wave_status.py 2k --set state=RUNNING --task-in-progress TASK_0031   # schema-validated STATUS
runners/checkpoint.py 2k                                   # snapshot resumable state after a task banks

# ── banking a result (the anti-fabrication gate lives in dispatch.py) ──────
runners/dispatch.py update --disc TASK_0031 --patch start.json      # PENDING → IN_PROGRESS (deps gate, exit 8)
runners/log_artifact.py --task TASK_0031 --path reports/TASK_0031_pytest_config.log   # append ART + hash
runners/dispatch.py update --disc TASK_0031 --patch done.json       # → COMPLETED; re-hashes artifacts, exit 7 if absent

# ── audit (the /audit pass, run cold → WAVE_<id>_AUDIT.md) ─────────────────
# auditor session re-derives load-bearing claims, writes handoffs/orchestrator/WAVE_2k_AUDIT.md (PASS/FAIL/…)
runners/close_wave.py 2k                                   # refuses unless WAVE_2k_AUDIT.md PASS timestamp < now

# ── freeze bypass (human-gated) ────────────────────────────────────────────
# 1) write the Authorization entry, 2) apply the unfreeze citing it:
runners/dispatch.py update --disc AUTHZ_0003 --patch authz.json
runners/dispatch.py update --disc TASK_0009 --patch fix.json --unfreeze TASK_0009.falsification_criterion

# ── reproduce / inspect (KEPT) ─────────────────────────────────────────────
runners/replay.py CLAIM_0031                              # re-run the rederive recipe; check artifact hash
runners/dispatch.py show --disc TASK_0031                 # pretty-print one entry (read-only, no lock)
runners/inspect_registry.py --stumps                      # every STUMPED task + unblock criterion
runners/inspect_registry.py --status PENDING              # entries by status
runners/inspect_registry.py --unaudited                   # load-bearing claims not yet PASS
runners/dispatch.py validate                              # full integrity gate (§4)
runners/dispatch.py audit-tail 20                         # last N audit-log entries

# ── continuity (NEW) ───────────────────────────────────────────────────────
runners/window.py show                                    # rate-limit window + weekly-cap tracker
runners/park.py "weekly cap hit; resume after reset"      # graceful stop: write park-state, disarm loops
runners/resume.py                                         # re-arm from park-state, from disk truth
bin/_spawn_orchestrator.sh handoffs/orchestrator/SESSION_HANDOFF_<iso>.md   # rotate the Orchestrator
bin/_commit.sh -m "wave 2k complete"                      # allow-listed staging only
runners/status.py                                         # one-shot human catch-up
```

The design keeps every property that made the predecessor's kernel trustworthy — atomicity, optimistic
concurrency, freeze enforcement, audited unfreeze bypass, replay — and adds exactly the enforcement the
predecessor had to *remember* instead of *check*: **no completion without a persisted, hashed artifact
(exit 7)**, **no start before dependencies are COMPLETED (exit 8)**, and **no wave close before an
independent audit passes (`close_wave.py`)**. Judgment that lived in prose becomes exit codes, and the
command names the operator already types (`dispatch.py update --disc … --patch …`,
`pre_register.py`, `replay.py`, `inspect_registry.py`) are unchanged.
