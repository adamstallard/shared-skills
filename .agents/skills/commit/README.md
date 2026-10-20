# Commit

Splits the working tree into `TYPE(Scope):` commits and creates them. The
subject of a commit an agent wrote ends with `(agentic)`. Runs
[`bug-hunter`](../bug-hunter/README.md) on each commit that contains code,
when bug-hunter is installed.

It does not take over a commit another skill is already making.

> Agent instructions: [SKILL.md](SKILL.md).

## One-time setup

Ask the agent: **"Install the commit skill"**. Try it in the current agent
chat. Open a new chat only if the agent does not see the skill.

If the agent doesn't know how, set up shared skills first. Do
[Install](../../../README.md#install) in the repo root, then ask again.

Installing this skill is what turns "commit this" over to it. Until then,
`bug-hunter` answers that phrase itself.

| Installed | "commit this" does |
| --- | --- |
| `bug-hunter` only | Hunts, then commits, without this skill splitting the tree |
| `commit` only | Organize and commit, no hunt |
| Both | This skill owns the phrase, then runs `bug-hunter` on each code commit |

## Using it

> Commit this
> Commit my changes
> Split this into commits
> Organize commits

Skip hunt this turn:

> Skip bug-hunter
> Commit without hunting

## Troubleshooting

**Skill not found** — ask again in this chat. If the agent still does not see
it, open a new chat.

**Still going straight to bug-hunter** — this skill is not installed in that
agent's skill directory. Install it, then try this tab before opening a new
one.

**Hunt ran and you didn't want it** — say "Skip bug-hunter" or "Commit without
hunting" for this turn, or uninstall `bug-hunter` if you want organize-only.
