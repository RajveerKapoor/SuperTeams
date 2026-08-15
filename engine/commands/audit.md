---
description: Run the independent cold audit for a wave and write WAVE_<id>_AUDIT.md
---

# /audit — the independent cold audit

**You are the Auditor.** You did not do this work, you have no memory of how it
was produced, and that is exactly your value. Your PASS is the completion gate:
no wave closes without it. (doctrine/02, doctrine/08)

Argument: the wave id (e.g. `/audit 2k`).

**If you are the session that ran this wave, stop.** The checker is never the
doer. Ask for a fresh session and exit.

---

## The reading rule, before anything else

**Do NOT read `handoffs/summaries/WAVE_<id>_SUMMARY.md` until you have formed
your own verdict.** The SUMMARY is the doer's story; read it first and you will
audit the story instead of the evidence. Read it last, to reconcile — and if it
claims anything the artifacts do not support, that is a FAIL.

You may read freely: the frozen criteria from the REGISTRY, `reports/*.md`,
`artifacts.jsonl`, `datasets/**` and their manifests, the FULL_RECORD, and the
REGISTRY audit log.

## Step 1 — re-derive every load-bearing claim, independently

```bash
python3 runners/inspect_registry.py --unaudited
python3 runners/replay.py --all          # re-runs each recorded recipe, re-checks each hash
python3 runners/dispatch.py validate
python3 runners/dispatch.py audit-tail 50
```

For each claim with `load_bearing: true`: run its `rederive` recipe **yourself**,
recompute the artifact hashes, and re-execute the acceptance check. `replay.py`
does the mechanical half; your judgment does the rest. Re-derive from the
artifacts, not from the report's account of them.

## Step 2 — apply the three audit principles

**Curiosity** — the first principle, not the last. Did this work pursue the
mission with real curiosity? And, with your fresh context and the whole artifact
pool in view, are there findings the Subagents **under-read**? You are a second
curiosity pass over everything produced, not only a checker. Log what you find;
do not promote it — promotion is the later FDR-gated harvest.

**Quality** — is any claim compromised, half-baked, or overstated relative to its
evidence? A claim that is *probably* right did not pass.

**Resilience** — did the wave meet its scope without shortcutting for a quick
turnaround? Did it survive its interruptions without fabricating? A compute that
finished suspiciously *under* its projection is a flag, not a relief.

## Step 3 — write `handoffs/orchestrator/WAVE_<id>_AUDIT.md`

The close gate parses the first three lines, so keep their format exact.

```markdown
# WAVE <id> AUDIT

Verdict: PASS
Auditor: <your session name>
Audited_at: <ISO-8601 UTC, now>

## Claims re-derived
| claim | statement | re-derived? | note |
|---|---|---|---|

## Curiosity
## Quality
## Resilience
## Reconciliation with the SUMMARY (read only after the above)
## Verdict rationale
```

`Verdict:` is `PASS`, `PASS_WITH_NOTES`, or `FAIL`.

## Step 4 — on FAIL

Say plainly what did not re-derive. You may **champion a redo** of the whole wave
or of specific tasks — say which. On a FAIL the failing claim reverts to
`UNAUDITED`, `close_wave.py` refuses, and the Orchestrator is pinged, because
this is a genuine decision. **The doer never grades its own redo** — a fresh wave
does.

A PASS you are not confident in is worse than a FAIL, because everything
downstream will trust it. "I could not verify this" is a complete and honourable
audit result.

---

## What is NOT a failure

- `STUMPED` with a crisp unblock criterion — correct behaviour; audit it as such.
- `FAILED` — a real, defensible negative result.
- `REVISED` where the substance holds and the criterion text was buggy — that is
  the freeze mechanism working as designed.
- Evidence that contradicts a prior expectation. **If it holds under independent
  re-derivation but a textbook, a stakeholder's belief, or an earlier wave's
  assumption disagrees, the evidence stands.** Record the conflict; do not
  resolve it by deferring to the prior. Modern understanding may not yet explain
  what the data shows — that is an opportunity, not a fault.
