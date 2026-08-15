# SuperTeam

Point Claude Code at a goal and it runs an **autonomous, self-verifying agent
campaign** — planning, dispatching work across many sessions, banking every result
to disk, auditing its own claims, recovering from interruptions and rate limits,
and interrupting you only when your judgment is genuinely required. For days to
months. On one machine.

<img width="1264" height="898" alt="Screenshot 2026-08-15 at 4 57 54 PM" src="https://github.com/user-attachments/assets/c438a183-1e80-4cf5-b6cb-05ed08f03052" />

It's a **Claude Code plugin**. You don't hand-edit config or pre-build anything —
you run one command, answer a few questions, and it stands up the whole campaign
for you, ready to run.

## Get started in three steps

1. **Install the plugin** (add this repo as a plugin, or open the folder in an IDE
   with Claude Code).
2. **Run `/superteam`.** Claude interviews you — your goal, what "done" means, what
   it may and may not do on its own — and then scaffolds and *freezes* a complete
   campaign: a registry, a filled-in charter, the coordination tree, and an initial
   set of tasks with locked acceptance criteria. Nothing needs to exist beforehand;
   this creates it.
3. **Run `/superteam-run`.** Claude takes the Orchestrator role and starts working.
   Check in any time with `/superteam-status`; drop a steering note whenever you
   want and it's picked up at the next wave boundary.

That's the whole loop: **download → `/superteam` → answer questions → `/superteam-run`.**

## Why it can be trusted to run unattended

Everything below is *structural* — a gate in the code, not a discipline someone has
to remember. Each one comes from a real failure in a ~7-week autonomous campaign
that this system is built to not repeat.

- **Truth lives on disk.** A claim with no persisted, hashed artifact is refused —
  a completion is literally impossible without evidence on disk.
- **The checker is never the doer.** A wave can't close until a *separate*, cold
  session re-derives its claims and signs off. Self-audit is blocked mechanically.
- **Goalposts freeze.** Acceptance criteria are locked before work starts; weakening
  one to make failing work "pass" is refused unless you authorize it, on the record.
- **It survives interruption.** Work is banked one task at a time, so a rate limit,
  a laptop sleep, or a crash costs at most one task — never a window. Long computes
  outlive the session that launched them; the campaign parks gracefully at the
  weekly cap and resumes from disk.
- **It stays quiet.** A task failing, stalling, or being redone is normal operation,
  handled automatically. You're interrupted only for a genuine decision — an audit
  failure, an authorization request, a scope fork, a hard block.

## The team

- **Orchestrator** — owns the mission and the task graph; decides what's next; rotates its own session to stay sharp.
- **Wave General** — owns one ~5-hour "wave"; dispatches workers **one at a time**, banking each result before the next.
- **Subagent** — does one task; persists every artifact; sweeps its work for anything surprising.
- **the babysit loop** — a cheap recurring tick that watches liveness, budgets the rate-limit window, and decides from disk alone whether to hold, revive, or launch.
- **the cold Auditor** — re-derives every load-bearing claim from artifacts alone before a wave may close.

## Requirements

- **Claude Code** installed and signed in (this orchestrates `claude` sessions; a
  plan with real usage headroom, since the design lives within the 5-hour / weekly
  rate-limit windows).
- **Python 3** — standard library only, no `pip install`.
- **A machine that stays on** for the campaign's duration (built for a single Mac;
  Linux works with a check of the launcher flags).

## What's proven, and what you'd harden first

**Proven.** The engine — the registry, all the anti-fabrication gates, the
continuity/recovery machinery, the Curiosity lenses — is implemented and passes an
adversarial acceptance battery of ~95 tests (`engine/**/test_*.py`): parallel-write
races, freeze rejection, the banking and dependency gates, version conflicts,
self-audit rejection, induced kills and stalls, background-compute-survives-death,
and park/resume with zero loss.

**Harden first.** Running fully unattended across many days uses that same engine,
but the end-to-end path where the launchers spin up live Claude sessions for a
multi-day run hasn't been exercised at scale yet. For your first real mission, stay
reachable for the early waves; `doctrine/13` specifies exactly how the unattended
canaries are meant to be verified.

## Under the hood

The plugin skills call a Python CLI you can also drive by hand:

```bash
# what /superteam does for you, manually:
python3 engine/runners/init_workspace.py ./my-mission --mission my-mission --mode finite --goal "…"

# the acceptance battery:
python3 -m pytest engine/runners/ engine/lenses/ -q
```

| Path | What it is |
|------|------------|
| [`skills/`](skills/) | The plugin's entry points: `superteam` (bootstrap), `superteam-run`, `superteam-status`. |
| [`doctrine/`](doctrine/) | The full specification — 14 documents. Start at [`00_INDEX.md`](doctrine/00_INDEX.md). |
| [`engine/runners/`](engine/runners/) | The CLI kernel: atomic registry (`dispatch.py`), the gates, continuity (`window`/`park`/`resume`/`checkpoint`/`liveness`), the wave lifecycle, `harvest.py`. |
| [`engine/lenses/`](engine/lenses/) | The pluggable Curiosity-Protocol lenses — record-all, promote-later under FDR. |
| [`engine/templates/`](engine/templates/) | The role charters and wave scaffolds copied into each mission. |
| [`engine/schemas/`](engine/schemas/), [`engine/repro/`](engine/repro/), [`engine/stats/`](engine/stats/), [`engine/curiosity/`](engine/curiosity/) | Schemas and the reusable libs (reproducibility manifest, multiple-comparison machinery, constants matcher). |
| [`engine/bin/`](engine/bin/), [`engine/commands/`](engine/commands/) | The guarded launchers, the allow-listed commit script, and the `/revive` + `/audit` commands for running campaigns. |

## Design stance

> Act on the reversible; stop on the irreversible or genuinely ambiguous. Treat a
> mismatch as a clue, not an inconvenience. Keep truth on disk. Prefer an honest
> BLOCKED to a manufactured DONE. Never let the checker be the same mind as the doer.
