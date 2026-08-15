# WAVE {{WAVE_ID}} BRIEF — {{MISSION}}

**Scaffolded:** {{CREATED_AT}}
**Tasks:** {{TASKS}}

> The **self-contained** dispatch material. A Subagent receives one section of this
> file and must never have to hunt for anything else. If a Subagent has to go
> looking, this brief is incomplete — fix the brief, not the Subagent.

---

## Standing text — goes into EVERY subagent brief in this wave

You execute **one task**. Your acceptance criterion is **frozen**; you cannot change
it. Read it from the registry:

```bash
python3 runners/dispatch.py show --disc <YOUR_TASK_ID>
```

**You have no deadline.** Quality is the only metric. Do not substitute a smaller
sample, a coarser resolution, or a cheaper method to fit a perceived time budget.
If the honest work outlives this session, use the background-compute contract
(manifest first, then background Bash, then return `DEFERRED-COMPUTE-RUNNING`).

**Nothing you say counts until it is on disk.** Write `reports/<TASK_ID>.md` and log
every artifact:

```bash
python3 runners/log_artifact.py --task <TASK_ID> --path <path> \
    --kind <kind> --lens <lens> --context "one line"
```

A hung tool is a **TIMEOUT, never a return value.** No output means no artifact
means no completion.

**If your result lands outside the frozen criterion, investigate WHY.** Do not widen
the window. If the criterion itself has a text or pointer bug while the substance
verifies, return `REVISED` with `criterion_mismatch_flag: true` and describe the
mismatch precisely. **Never self-unfreeze.**

**Run the Curiosity Protocol over everything you produced — record ALL, pre-gate
nothing**, including the boring-looking artifacts. You do not promote findings;
promotion is a separate, later, FDR-gated pass across the whole pool. Flag
candidates with `--note`.

**Return ≤3000 tokens**, structured: verdict, value, confidence, methods,
side_findings, blocker, unblock_criterion, report_path, report_sha256, artifacts.
Detailed reasoning lives in the report.

Verdicts: `DONE` · `FAILED` · `STUMPED` (requires an `unblock_criterion`) ·
`DEFERRED-COMPUTE-RUNNING` · `REVISED` · `TRIVIAL` · `DEFINITION-DEPENDENT` ·
`META-QUESTION`. Every one is honest. A fabricated `DONE` is the only real failure.

---

## Per-task briefs

### TASK_____

- **Title:**
- **Frozen criterion (quote verbatim from the registry, with its `frozen_at`):**
- **Lens:** research | engineering | ops | writing | generic
- **Inputs:** <!-- exact paths, commits, dataset ids -->
- **Protocol:** <!-- step by step -->
- **Outputs:** `reports/TASK_____.md`, plus artifacts to log
- **Dependencies:** <!-- already COMPLETED — the kernel enforces this (exit 8) -->
- **What would make this FAILED rather than DONE:**
- **What would make this STUMPED, and what would unblock it:**

<!-- repeat per task -->
