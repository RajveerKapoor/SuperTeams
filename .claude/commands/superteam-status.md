# /superteam-status
# Usage: /superteam-status

Give the user a read-only catch-up on an initialized SuperTeam campaign — where it
stands, its health, what's blocked, and what (if anything) needs their decision.
Changes nothing.

<instructions>
Read the canonical status skill in this repository and execute it in full:

    skills/superteam-status/SKILL.md      (relative to this repo's root)

It reports from disk only (`status.py`, `dispatch.py validate`,
`inspect_registry.py`, `window.py show`, the `OUTBOX.md` digest), summarizes
plainly, and offers the next move. Never invent numbers — report only what the
runners print.
</instructions>
