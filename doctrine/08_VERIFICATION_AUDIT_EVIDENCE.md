# 08 — Verification, Audit, and the Curiosity Protocol

Three interlocking systems make the output *trustworthy*: the **anti-fabrication kernel** (a
completion is a persisted, hashed, re-derivable fact), the **freeze + independent audit gate** (the
goalposts can't move and the checker isn't the doer), and the **Curiosity Protocol** (record all,
promote later under discipline — so the system finds things without crying wolf). Each generalizes a
predecessor mechanism that was proven in practice.

---

## 1. The anti-fabrication kernel

Trust begins with a single definition, enforced by the kernel, not by good behavior:

> **A task is DONE if and only if an artifact exists on disk, its hash is recorded in the registry, and
> the claim it supports is independently re-derivable from that artifact.**

This is Law 1 made mechanical. Its three enforcement points:

1. **Banking gate** (`dispatch.py update`, exit 7). Before a task can move to DONE, the kernel
   recomputes the SHA-256 of every referenced artifact and compares it to the patch's claimed hash. No
   file, or a mismatched hash → hard failure. An agent that "completed" but wrote nothing cannot be
   marked done. This is the structural end of the Wave-2j "spun 5.5h, banked nothing" mislabel and the
   general "agent completed but wrote nothing did NOT complete."
2. **Producer hash-honesty** (`07` §4). For background compute, the *finished job* computes the hash,
   never the launcher. A hash in a manifest is proof of a completed run, not an assertion made in
   advance.
3. **Replay** (`replay.py <claim>`). Any load-bearing claim can be re-derived by re-running its
   recorded recipe in its recorded environment (commit + seed + env hash) and checking the artifact
   hash reproduces. This is the ultimate fabrication detector — a shortcut or a fabrication changes the
   hash and fails replay. The predecessor's `replay.py` did exactly this for the physics; `replay.py`
   generalizes it: for a compute domain it re-runs the command; for an engineering domain it re-runs
   the acceptance check at the recorded commit; for a writing/ops domain it re-checks the acceptance
   condition.

The kernel's stance on a hung or ambiguous tool is absolute: **a hung tool is a TIMEOUT, never a
return value.** No artifact means no completion — it means a retry or a BLOCKED, and the transcript's
optimistic partial output is ignored. This is the predecessor's most-pinned discipline, and here it
needs no discipline: a hung tool simply produces no hashed artifact, so the gate stops it cold.

---

## 2. The freeze: anti-goalpost-moving

Detailed in `04` §3; summarized here for its role in trust. Before any Subagent starts, each task's
acceptance criterion is **frozen** — `definition_of_done`, `acceptance_check`, `confidence_target`,
`blocked_ci_width`. After freeze, no Subagent, Wave General, or Orchestrator can alter a frozen criterion; only the
human, via an audited Authorization + `--unfreeze`, can move a goalpost, and every move is forever in
the audit log.

This is the generalization of pre-registration from the science context (freeze falsification criteria
before collecting data, to prevent p-hacking) to *any* mission (freeze the definition of done before
starting work, to prevent a subagent rationalizing its output into a pass). The value is identical: the
verdict is rendered against a criterion committed *before the result was seen*.

Its correctness is proven by the predecessor's record: **nine** times a frozen criterion turned out to
have a text/pointer bug, and **nine** times the system did the right thing — the Subagent surfaced the
mismatch (`REVISED` + `criterion_mismatch_flag`), never self-unfroze, and the human authorized an
audited unfreeze only when warranted. A system that let subagents fix their own criteria would have
laundered nine judgment calls; the freeze made all nine visible and accountable.

---

## 3. The independent audit gate

The completion gate: **no wave reaches COMPLETE without a PASS from an Auditor that is not the doer,
timestamped before the close** (`05` §2, Laws 4 + D1/D2).

**What the Auditor does.** Given a closed wave, a fresh Auditor session (cold context, top model
tier):
1. Reads *only* the frozen criteria and the persisted artifacts — **not** the Wave General's SUMMARY (yet).
2. For every load-bearing Claim (`load_bearing: true`), independently re-derives it: re-runs the
   `rederive` recipe, recomputes hashes, re-executes the acceptance check. This is the predecessor's
   "independently re-derive every load-bearing number" made a role instead of an Orchestrator side
   task.
3. Applies the **audit principles** the predecessor codified in its `/audit` command — Curiosity,
   Quality, Resilience:
   - **Curiosity** (its #1 principle): did the work pursue the mission with real curiosity, and — with
     the Auditor's superior fresh context — are there findings in the artifacts the Subagents under-read?
     The Auditor is itself a curiosity pass, not just a checker.
   - **Quality:** is any claim compromised, half-baked, or overstated relative to its evidence?
   - **Resilience:** did the wave meet its scope without shortcutting for a quick turnaround, and did
     it survive any interruption without fabrication?
4. Writes `AUDIT.md` with a verdict (PASS / PASS_WITH_NOTES / FAIL) and, on FAIL, the exact claim that
   did not re-derive.
5. *Then* reads the SUMMARY and reconciles — if the SUMMARY claims something the artifacts don't
   support, that is a FAIL.

**What a FAIL does.** The failing claim reverts to UNAUDITED; the wave cannot close; the Orchestrator is
pinged (a genuine decision — touchpoint tier). The Auditor may **champion a redo** of the whole wave
or a targeted re-run — exactly the authority the predecessor's `/audit` charter granted ("you can
champion a redoing of the wave, or partially redoing some of the tasks"). The doer never grades its
own redo; a fresh wave does.

**Why cold and independent.** A same-mind audit shares the doer's blind spots and its convictions
about a plausible-but-wrong result. The Auditor's value is precisely that it *doesn't know how the
sausage was made* — it only knows what the frozen criterion demanded and what the artifacts show. This
is the one separation the system never relaxes.

---

## 4. The Curiosity Protocol (record all, promote later)

The predecessor's Curiosity Protocol was its soul: every number the work touched was logged and swept
for structure, because "the deepest findings hide in routine-looking numbers." That protocol was
physics-specific (a constants library, continued fractions, integer-relation search, τ-thresholds,
Benjamini–Hochberg correction). The generalization keeps its *spirit and its discipline* while making
the *lens* pluggable.

**The invariant (domain-independent):**
- **Record ALL, never pre-gate.** Every artifact the work produces is logged to `artifacts.jsonl` with
  a default `promotion_status: LOGGED` — including the ones that look routine. "It looked boring" is
  exactly the case the protocol exists for, and uniform logging is also the defense against
  fabrication-by-selection (only examining the results you already suspect). The predecessor made this
  a hard rule after nearly pre-gating away foundational null results; it is Law-of-the-protocol here.
- **Log continuously; promote in a batch, later, under multiple-comparison discipline.** A candidate
  finding is never promoted to a real result inside the wave that found it. Promotion happens in a
  dedicated later pass (the generalization of the predecessor's "Wave 4b BH harvest") that applies a
  false-discovery-rate correction across the *whole* pool, so the system never cries wolf on the
  coincidences that a large enough pool is guaranteed to contain.
- **Provenance, not pre-judgment.** Every artifact carries a `provenance` tag (which lens produced it,
  from which task, whether it's a real measurement or a synthetic/canary/derived value) so the later
  promotion pass can apply differentiated criteria — but every artifact enters the pool. The
  predecessor's rule "never assign a pre-judging status that excludes an artifact from later
  assessment; use the separate provenance field instead" is kept exactly.

**The artifact record** (generalized from the predecessor's `artifacts.jsonl` schema):
```json
{
  "artifact_id": "E-1973",
  "value": 0.5391,                     // or a structured object for non-numeric findings
  "kind": "measurement|relationship|null-result|anomaly|regression|smell|scaling|infeasibility|novel-form",
  "context": "step-ratio over 41 configs, engineering-lens perf sweep",
  "source_task": "TASK_0031",
  "source_wave": "2k",
  "lens": "engineering",
  "provenance": "real|derived|synthetic|canary|textbook",
  "promotion_status": "LOGGED|FLAGGED|PROMOTED|REJECTED",
  "candidate_note": "close to 1/2; also close to a small rational — recheck under BH",
  "p_value": null,
  "fdr_q": null,
  "reverify_recipe": "…",
  "ts_iso": "…"
}
```

### Pluggable lenses (`~/superteam/lib/lenses/`)
A **lens** is the domain-specific "what counts as a candidate finding, and how do I sweep for it." Each
lens implements one interface: given the artifacts a task produced, emit candidate findings with
provenance. The lens is chosen per task (`task.lens`).

- **`research` lens** — the predecessor's Curiosity Protocol, verbatim in spirit: known-constant match,
  pairwise ratios, continued-fraction expansion, integer-relation search, near-coincidence thresholds,
  reproduction under nuisance variation, FDR correction. This is the specialized case, now one lens
  among many.
- **`engineering` lens** — every surprising behavior is a candidate: a performance cliff, a flaky test,
  a dependency smell, a TODO that hides a real gap, a coupling that shouldn't exist, an error path
  that's never exercised. "Record all" means the refactor task that noticed a latent perf regression
  logs it even though it wasn't asked to.
- **`ops` lens** — every anomaly is a candidate: a metric out of band, a log pattern that's new, a
  config drift, a resource creeping. Serendipity here is catching the incident before it's an incident.
- **`writing` lens** — every unstated assumption, every claim that outran its support, every structural
  gap, every reader-question the draft raises and doesn't answer.
- **`generic` lens** — for a mixed or novel domain: log everything with `kind` and `context`; the later
  promotion pass decides framing. This honors the predecessor's deepest point — "gravity and calculus
  were not matches against an existing library" — a system that filters findings through "must match
  something I already know" will miss anything genuinely new, so the generic lens pre-judges nothing.

The lens registry is how the system serves *any* mission while keeping the discipline constant:
**record all, promote later, provenance-tag, FDR-gate.** The predecessor's physics was one lens; the
machinery was always general.

---

## 5. Theory/expectation conflict is not a falsification

A predecessor principle worth stating on its own because it is a judgment most systems get wrong: **if
the evidence holds under independent re-derivation but a prior expectation (a textbook result, a
stakeholder's belief, a prior wave's assumption) disagrees, the evidence stands.** The verdict is
"established, with a conflict flagged," and the conflict is recorded — not resolved by deferring to the
prior. Modern understanding may not yet explain what the data shows; that is an opportunity, not a
fault. The predecessor encoded this as `PROVEN-EMPIRICAL` with `theoretical_conflict: true`; the
generalization is a `conflict` flag on any Claim whose evidence contradicts a documented prior, routed
to the human as *information*, never auto-suppressed. This is the epistemic backbone of a system built
to *discover*, not merely to *confirm*.

---

## 6. The trust chain, end to end

Putting the three systems together, a claim earns trust by passing through a chain where every link is
structural:

```
frozen criterion  →  subagent produces artifact  →  banking gate (hash exists + matches, exit 7)
      →  claim logged with rederive recipe  →  Curiosity Protocol logs all artifacts (no pre-gate)
      →  cold Auditor re-derives every load-bearing claim from artifacts alone  →  AUDIT PASS (gate)
      →  wave close (PASS timestamp precedes close)  →  Orchestrator ingests only SUMMARY + AUDIT
      →  (later) FDR-gated promotion pass over the whole pool  →  a candidate becomes a real finding
      →  replay.py reproduces the artifact hash on demand, forever
```

No link trusts the previous one's *word*; each re-checks against disk. That is why the mission's output
is trustworthy after weeks of unattended operation across dozens of dead-and-reborn sessions: nothing
in the chain ever advanced on a belief.
