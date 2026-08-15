# WAVE INDEX — {{MISSION}}

The one-screen map of every wave. Maintained by the Orchestrator at each wave
close; the source of truth remains the REGISTRY and each wave's `STATUS.json`.
If this table and disk disagree, **disk wins** — fix the table.

**Mission:** {{MISSION}}  ·  **Mode:** {{MODE}}  ·  **Initialised:** {{CREATED_AT}}

---

| wave | scope (one line) | tasks | state | audit | closed | summary |
|------|------------------|-------|-------|-------|--------|---------|
| | | | | | | |

**States:** `PLANNED` → `LAUNCHED` → `IN_PROGRESS` → `AWAITING_AUDIT` → `COMPLETE`
Off-path: `HALTED` (needs a resume directive) · `PARKED` (weekly cap) ·
`ABANDONED` (superseded by a re-plan; say what replaced it).

**Audit column:** `NOT_REQUESTED` · `REQUESTED` · `PASS` · `PASS_WITH_NOTES` · `FAIL`.
A wave may not be `COMPLETE` without a PASS whose timestamp precedes its SUMMARY.
`close_wave.py` enforces this; the column is for humans.

---

## Reading order for a new session

1. `MISSION.md` — the charter
2. this index — where the campaign is
3. `handoffs/orchestrator/CAMPAIGN_LOG.md` — the narrative
4. the current wave's `PLAN` + `STATUS.json` + `CHECKPOINT`
5. the role charter for whoever you are:
   - Orchestrator → `ORCHESTRATOR_RUNBOOK.md`
   - Wave General → `WAVE_GENERAL_OPERATING_MANUAL.md`
   - Auditor → `AUDITOR_CHARTER.md`
   - Subagent → `SUBAGENT_CHARTER.md` (plus your brief, which is self-contained)

Do **not** read another wave's `FULL_RECORD` unless you are its Auditor. Context
discipline is a load-bearing part of the design, not a nicety.

---

## Superseded and abandoned waves

<!-- Keep them listed. A wave that was abandoned for a good reason is evidence of
     re-planning working; deleting it makes the campaign look tidier than it was
     and hides the reasoning from the next session. -->
