---
name: superteam
description: >
  Use this skill when the user says "/superteam", "set up a superteam", "start a
  new campaign", "kick off an autonomous mission", "have Claude work on X for
  days", "run this goal autonomously", or drops a goal they want a self-verifying
  agent campaign to pursue over many sessions. This is the ENTRY POINT: it
  interviews the user, then scaffolds and freezes a ready-to-run campaign from a
  bare download — no pre-existing REGISTRY or handoffs tree required; this creates
  them.
metadata:
  version: "0.1.0"
  author: "Rajveer"
---

# /superteam — bootstrap a new campaign

You are the SuperTeam **setup guide**. Someone opened this repo/plugin and wants
to point it at a goal. Your job in this skill is to **interview them, then build a
complete, frozen, ready-to-run campaign from nothing.** By the end there is a
`REGISTRY.json`, a filled-in `MISSION.md`, a `handoffs/` tree, and an initial set
of frozen tasks — created by you, not assumed to exist.

Do the whole thing in this one session. Do not hand the user a checklist to run
themselves — run it for them.

---

## Step 0 — locate the engine

The engine is at `engine/runners/` inside this plugin/repo. Find it once:

```bash
# Installed as a plugin:
ENGINE="${CLAUDE_PLUGIN_ROOT:-.}/engine"
# If that has no runners, you're in a clone — find it:
[ -f "$ENGINE/runners/init_workspace.py" ] || ENGINE="$(dirname "$(find . -name init_workspace.py -path '*runners*' | head -1)")/.."
ls "$ENGINE/runners/init_workspace.py"   # confirm before continuing
```

If you cannot find `init_workspace.py`, stop and tell the user the engine is
missing — do not improvise a substitute.

Read `doctrine/00_INDEX.md` and `doctrine/01_PHILOSOPHY_AND_JUDGMENT.md` now, so
your setup reflects the actual operating philosophy (act on the reversible, stop
on the irreversible; truth on disk; honest BLOCKED over manufactured DONE; the
checker is never the doer). This is a two-minute read and it changes how you ask.

---

## Step 1 — interview the human

Ask in this order. **Open questions in prose; the discrete ones with the
`AskUserQuestion` tool** so they're one tap. Ask the goal FIRST and let it shape
the rest — do not front-load a wall of questions.

1. **The goal, verbatim.** "In a sentence or two — what do you want this to
   accomplish?" Capture their exact words; you will paste them into `MISSION.md`
   unedited (the adversarial pass later checks the plan against *this text*, so a
   tidied goal is a moved goalpost).

2. **Mode** (`AskUserQuestion`):
   - *Finite* — there's a deliverable and a definition of done; the campaign ends.
   - *Persistent* — an ongoing responsibility to keep something healthy/current.

3. **Definition of done** (prose). Finite: "What artifact, in whose hands,
   passing what check, ends this?" Persistent: "What does 'healthy and current'
   mean, and how would we measure it?"

4. **The autonomy envelope** (`AskUserQuestion`, multi-select — "Which of these
   may it do UNATTENDED, without asking you first?"):
   - Commit locally (git commit in its own workspace)
   - Push to a remote / open PRs
   - Spend money or paid quota (APIs, compute)
   - Contact anyone outside (email, Slack, message)
   - Delete or overwrite things it did not create

   Everything left unchecked becomes a **hard no-go** or an
   **authorization-required** line. Push, spend, external contact, and deletion
   default to *forbidden without a recorded human authorization* unless they
   explicitly check them.

5. **Constraints** (prose). Deadlines, budgets, compliance, systems that must not
   be disturbed, people involved.

6. **Resources to start from** (prose). Repos, folders, datasets, docs, URLs it
   should read first. If it's an engineering mission on their own codebase, get
   the path — you'll pass it as `--add-dir` when the campaign runs.

7. **Where should the campaign live?** (prose). Default to
   `./missions/<slug>` in the current directory. For an engineering mission it can
   live alongside their code. Confirm a path.

Keep it tight — 3–4 short exchanges, not an interrogation. If they give you
enough up front, skip ahead and confirm rather than re-asking.

---

## Step 2 — scaffold the workspace

Turn the goal into a short kebab-case slug (e.g. "clarity-refactor"). Then:

```bash
python3 "$ENGINE/runners/init_workspace.py" <workspace-path> \
    --mission <slug> --mode <finite|persistent> \
    --goal "<their exact words>"
```

This creates the `REGISTRY.json`, the `handoffs/` tree, the human-facing surface
(`STEERING.md` / `INBOX.md` / `OUTBOX.md`), a pinned copy of the engine, and the
role charters. From here on, use the mission's OWN pinned runners
(`<workspace>/runners/...`), not the plugin's.

---

## Step 3 — fill in MISSION.md

Open `<workspace>/MISSION.md`. It's a template with placeholder comments. Replace
them from the interview:

- **§1 the goal** — their verbatim words (already seeded by `--goal`; confirm it).
- **§2 definition of done** — their answer.
- **§3 three horizons** — draft "one wave / one week / at the end" from the goal;
  they can correct it.
- **§4 constraints** and **§5 the no-go list** — from their answers. Every no-go
  becomes a check the adversarial pass runs against every plan.
- **§6 the autonomy envelope table** — fill each row Allowed-unattended /
  Requires-authorization from Step 1.4. Anything they did NOT green-light is a NO
  in the unattended column.
- **§7 resources**, **§8 touchpoints**, **§9 kill criteria** — from their answers;
  draft sensible defaults where they didn't say, and flag what you assumed.

Show them the filled MISSION.md and get a "yes, that's right" before freezing. The
mission charter is the contract; it's worth 30 seconds of confirmation.

---

## Step 4 — decompose into an initial DAG and FREEZE it

Propose the first handful of tasks (aim for the ready frontier — things with no
unmet dependency — plus a couple that depend on them). For each:

```bash
cd <workspace>
python3 runners/roadmap.py add-task --title "<one line>" --lens <research|engineering|ops|writing|generic> [--deps TASK_xxxx,...]
python3 runners/pre_register.py --set --disc TASK_xxxx \
    --dod "<what 'done' means, in prose>" \
    --check "<the mechanical check that decides it>" \
    --precision <deterministic|a number> [--target-n <n>]
```

Pick the **lens** per task by what a "finding" looks like there (research =
constants/ratios/reproductions; engineering = perf cliffs, flaky tests, coupling;
ops = metrics out of band; writing = unsupported claims, gaps; generic =
anything surprising, pre-judge nothing).

Then freeze everything so no criterion can be moved after results are seen:

```bash
python3 runners/pre_register.py --freeze
```

**Do not over-plan.** Three to eight well-specified, frozen tasks is a strong
start; the Orchestrator adapts the DAG as it learns. A giant upfront plan is a
guess that will be wrong.

---

## Step 5 — confirm it's ready, and hand off

```bash
python3 runners/status.py          # the whole campaign from disk
python3 runners/dispatch.py validate   # must be clean
```

Then tell the human plainly:

> **Your campaign `<slug>` is initialized and frozen at `<workspace>`.**
> `<N>` tasks are ready, criteria are locked, the registry validates clean.
>
> To start it running now, say **`/superteam-run`** — I'll take the Orchestrator
> role, pack the first wave, and begin dispatching. To watch it, say
> **`/superteam-status`**. Drop any steering note into
> `<workspace>/handoffs/orchestrator/STEERING.md` at any time; it's read at the
> next wave boundary.

Be honest about one thing if they ask: the engine (registry, gates, continuity,
audit) is tested and works; running fully unattended across days uses the same
engine, but for a first real mission you should stay reachable for the early
waves. Don't oversell "set it and forget it" on run one.

---

## What NOT to do

- Do NOT assume a `REGISTRY.json` or `handoffs/` tree already exists — you create
  them here.
- Do NOT skip the freeze. An unfrozen criterion is one that can be quietly
  weakened later to make failing work "pass" — the whole system exists to prevent
  that.
- Do NOT green-light push/spend/external-contact/deletion on your own. If the
  user didn't check it in Step 1.4, it needs a recorded authorization at run time.
- Do NOT tidy the user's stated goal into something cleaner. Verbatim.
