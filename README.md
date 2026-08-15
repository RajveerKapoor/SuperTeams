# SuperTeams

A generalized, self-hardening system for running **autonomous agent campaigns**:
point it at a goal (or run it as a persistent team) and it operates toward that
goal for days to **months**, unattended, across many Claude Code sessions, on a single
machine, under subscription rate limits — pausing at limits, recovering from
interruptions, and interrupting a human only when the human's judgment is
genuinely required.

<img width="1264" height="898" alt="Screenshot 2026-08-15 at 4 57 54 PM" src="https://github.com/user-attachments/assets/c438a183-1e80-4cf5-b6cb-05ed08f03052" />

It is grounded empirically in a real ~7-week autonomous campaign: every failure,
misdiagnosis, interruption, and workaround that campaign hit is encoded here as
*structure* — a schema field, a state transition, a gate, a role boundary — so the
system cannot repeat it, rather than as a discipline someone has to remember.

## The design stance

> Act on the reversible; stop on the irreversible or genuinely ambiguous. Treat a
> mismatch as a clue, not an inconvenience. Keep truth on disk. Prefer an honest
> BLOCKED to a manufactured DONE. Never let the checker be the same mind as the doer.

## Layout

| Path | What it is |
|------|------------|
| [`doctrine/`](doctrine/) | The specification — 14 documents. Start at [`00_INDEX.md`](doctrine/00_INDEX.md), then [`01_PHILOSOPHY_AND_JUDGMENT.md`](doctrine/01_PHILOSOPHY_AND_JUDGMENT.md). |
| [`engine/runners/`](engine/runners/) | The CLI kernel: the atomic registry (`dispatch.py`), the freeze/banking/dependency gates, continuity (`window`/`park`/`resume`/`checkpoint`/`liveness`), the wave lifecycle, and `harvest.py`. |
| [`engine/lenses/`](engine/lenses/) | The pluggable Curiosity-Protocol lenses (research / engineering / ops / writing / generic) — record-all, promote-later under FDR. |
| [`engine/repro/`](engine/repro/), [`engine/stats/`](engine/stats/), [`engine/curiosity/`](engine/curiosity/) | Reusable libs: the reproducibility manifest, the multiple-comparison machinery, the constants matcher. |
| [`engine/schemas/`](engine/schemas/) | JSON Schemas for every registry entry type and handoff file. |
| [`engine/templates/`](engine/templates/) | The role charters (Orchestrator / Wave General / Auditor / Subagent) and wave scaffolds. |
| [`engine/bin/`](engine/bin/) | The guarded session launchers and the allow-listed commit script. |
| [`engine/commands/`](engine/commands/) | The `/revive` and `/audit` slash commands. |

## The roles

- **Orchestrator** — owns the mission and the dependency DAG; decides what to pursue next; rotates its own session every wave to stay small.
- **Wave General** — owns exactly one wave in one session/window; dispatches Subagents **serially**, banking each result atomically before the next.
- **Subagent** — executes one task; persists every artifact; runs the Curiosity Protocol.
- **the babysit loop** — the continuity daemon: watches liveness, budgets the rate-limit window, parks at the weekly cap, and decides from on-disk truth alone whether to hold, revive, or launch.
- **the cold Auditor** — re-derives every load-bearing claim from artifacts alone before a wave may close. The checker is never the doer.

## Quickstart

```bash
# scaffold a mission workspace
python3 engine/runners/init_workspace.py ./my-mission --mission my-mission --mode finite

# run the acceptance battery
python3 -m pytest engine/runners/ engine/lenses/ -q
```

## Status

The kernel and gates, the continuity engine, the launchers, the Curiosity
Protocol, the human interface, and the adaptive DAG are implemented and pass an
acceptance battery of ~95 tests (`engine/runners/test_*.py`,
`engine/lenses/test_lenses.py`), including adversarial race, freeze, banking,
dependency, audit-independence, version-conflict, and induced-interruption tests.
The end-to-end canary missions (doc 13 §1) that require live unattended sessions
are specified but not yet automated.
