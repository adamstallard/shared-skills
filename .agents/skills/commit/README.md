# Commit

Splits the working tree into commits and creates them. Runs
[`bug-hunter`](../bug-hunter/README.md) on each commit that contains code,
when bug-hunter is installed.

Subjects follow your repository's own commit convention: the one written in
`AGENTS.md`, `CONTRIBUTING.md` or a similar file, or else the one your
`git log` shows. A repository with neither gets `TYPE(Scope): description`. A
commit an agent wrote carries a `Co-Authored-By:` trailer naming that agent.

Every commit goes through bug-hunter's commit script when bug-hunter is
installed, including a commit with no code, which gets a `Bug-hunter: skipped …` trailer
saying why the hunt did not run. When [`prose`](../prose/README.md) is
installed, every commit also carries a `Prose:` trailer showing that its
readability check ran on the message and changed docs.

When another skill's own steps include making a commit, this skill leaves that
commit to the other skill.

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

**Still going straight to bug-hunter** — this skill is not installed in your
agent's skill directory. Install it, then try this chat before opening a new
one.

**Subjects don't match your style** — write the convention down in
`AGENTS.md` or `CONTRIBUTING.md`. The skill reads it before it falls back to
`git log`.

**Hunt ran and you didn't want it** — say "Skip bug-hunter" or "Commit without
hunting" for this turn, or uninstall `bug-hunter` if you want organize-only.
