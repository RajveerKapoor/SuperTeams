# /superteam
# Usage: /superteam

Bootstrap a new autonomous SuperTeam campaign from this repository: interview the
user, then scaffold and freeze a complete, ready-to-run campaign. Nothing needs to
exist beforehand — you create the registry, the charter, the coordination tree,
and the initial frozen tasks.

<instructions>
Read the canonical bootstrap skill in this repository and execute it in full —
do not summarize it, run it:

    skills/superteam/SKILL.md      (relative to this repo's root)

That file is the authoritative procedure: locate the engine, interview the user
(goal, mode, definition of done, autonomy envelope, resources, workspace path),
run `engine/runners/init_workspace.py` with their answers, fill in `MISSION.md`,
decompose the goal into an initial DAG, and `pre_register.py --freeze` it. End by
telling the user the campaign is ready and that `/superteam-run` starts it.

If you cannot find `skills/superteam/SKILL.md`, you are not at the repo root — say
so rather than improvising.
</instructions>
