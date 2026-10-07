# shared-skills

Agent skills you install once and use in every project, in Claude Code and in
any agent that reads `~/.agents/skills/`. Each skill is a symlink back to one
clone of this repository, so `git pull` updates them all.

Licensed under the [MIT License](LICENSE).

## Requirements

- **macOS or Linux.** Skills are installed as symlinks. Windows is not tested.
- **Python 3.8 or later**, as `python3`.
- **git 2.32 or later.** In a repository that has a `pre-commit` hook,
  `bug-hunter` and `prose` need git 2.36 or later; on an older git they refuse
  to commit there rather than skip the hook.

## Install

Clone the repository and run its installer:

```bash
git clone https://github.com/adamstallard/shared-skills.git ~/shared-skills
~/shared-skills/install.sh
```

The clone can live anywhere; the installer records where it is. Don't move it
afterwards, since every installed skill points into it.

The installer adds one skill, `manage-skills`. Ask your agent for the rest:

> "What skills are available?"
> "Install the bug-hunter skill"

Each skill is installed into both `~/.agents/skills/` and `~/.claude/skills/`;
a Claude Code mod, into `~/.claude/skills/` only.
Try a new skill in the session you're in; if the agent doesn't see it, start a
new session. [manage-skills' README](.agents/skills/manage-skills/README.md)
has the commands to run yourself.

Installing bug-hunter or prose also turns on its hook, which is written to
`~/.claude/settings.json` and `~/.cursor/hooks.json`. To turn a hook off, see
[Skills that come with a hook](.agents/skills/manage-skills/README.md#skills-that-come-with-a-hook).

## Updating

Ask the agent to "update my shared skills", or run:

```bash
python3 ~/.agents/skills/manage-skills/scripts/skills.py update
```

That runs `git pull` in the clone, which updates every installed skill at once,
and refreshes `manage-skills`, the one skill installed as a copy.

## Skills

| Skill           | What it does                                                                                          | Setup & usage                                    | Agent instructions                                |
| --------------- | ----------------------------------------------------------------------------------------------------- | ------------------------------------------------ | ------------------------------------------------- |
| `manage-skills` | Installs, removes, and diagnoses the skills below. Start here                                         | [README](.agents/skills/manage-skills/README.md) | [SKILL.md](.agents/skills/manage-skills/SKILL.md) |
| `bug-hunter`    | Catch bugs in code just written, before it is committed — every bug proven with a failing test first | [README](.agents/skills/bug-hunter/README.md)    | [SKILL.md](.agents/skills/bug-hunter/SKILL.md)    |
| `prose`         | Makes agents rewrite the text you review — docs, comments, commit messages, PR descriptions — so it reads in one pass, and proves the pass ran | [README](.agents/skills/prose/README.md) | [SKILL.md](.agents/skills/prose/SKILL.md) |
| `linear-app`    | Gives an agent its own Linear identity, an app user that can be delegated issues, with tokens minted on demand so nothing is renewed by hand | [README](.agents/skills/linear-app/README.md) | [SKILL.md](.agents/skills/linear-app/SKILL.md) |
| `discord-bot`   | Post to, read and manage Discord channels and threads as a bot account, from a laptop or a server, with no service to run | [README](.agents/skills/discord-bot/README.md) | [SKILL.md](.agents/skills/discord-bot/SKILL.md) |
| `github-app`    | Gives an agent its own GitHub identity, a GitHub App whose work shows as a bot, with tokens minted on demand and its identity only in the environment of the processes that act as it | [README](.agents/skills/github-app/README.md) | [SKILL.md](.agents/skills/github-app/SKILL.md) |
| `usage-hint`    | Claude Code mod: shows your subscription usage (5-hour and weekly, with reset times) at the end of the hint line under the prompt, using no requests | [README](.agents/skills/usage-hint/README.md) | none: a mod, not a skill |

The **Setup & usage** column is written for people. The **Agent instructions**
column is what the agent reads; you don't need to.

---

## Creating a new skill

```
.agents/skills/<skill-name>/
├── SKILL.md        # required — instructions for the agent
├── README.md       # required here — setup and usage, written for humans
├── reference.md    # optional — detailed reference the agent reads on demand
└── scripts/        # optional — helper scripts the skill runs
```

1. `SKILL.md` is the entry point the agent loads. It needs YAML frontmatter
   with `name` and `description`, where `name` must match the directory name.
   The `description` is how the agent decides when to use the skill, so state
   both what it does and when to use it, including phrases people would
   actually say. Keep the body under ~500 lines and push detail into
   `reference.md`.
2. `README.md` is for the people who install the skill, and it's the one
   thing that's easy to forget. `SKILL.md` is written for the agent and isn't
   a substitute — cover what the skill is for, any one-time setup, examples of
   what to say to the agent, and troubleshooting for the failures people will
   actually hit.
3. **Extra files are fine.** Only `SKILL.md` is special. Put helper scripts in
   `scripts/` and long reference material in `reference.md`. One caveat: don't
   put another `SKILL.md` in a subdirectory, since skill directories are
   scanned recursively and it would be treated as a separate skill.
   - If a skill ships scripts, put tests beside them as `scripts/test_*.py` —
     standard library only, runnable with plain `python3`, no fixtures to
     install. `bug-hunter` and `manage-skills` both have some.
   - If those scripts accumulate non-obvious decisions, add a `DECISIONS.md`
     next to `SKILL.md`: decision, why, and **what was tried and rejected**.
     Point at it from the top of the script. It is read before choosing an
     approach, which is where a comment at the relevant line arrives too late —
     see [bug-hunter](.agents/skills/bug-hunter/DECISIONS.md).
   - A skill can also ship a `hook.json` to run one or more scripts around
     agent events, wired up on install. See the Hooks section of
     [manage-skills/SKILL.md](.agents/skills/manage-skills/SKILL.md).
   - Code shared by several skills lives in `.agents/lib/<name>/`, and each
     skill calls it from a thin script of its own. A skill enforcing a commit
     trailer uses [`commit-trailer`](.agents/lib/commit-trailer/DECISIONS.md),
     the way `bug-hunter` does. Skills reach it through their symlink into the
     clone, so a skill folder copied on its own loses it and says so.
4. **Add a row to the table above** with a one-line description and links to
   both the README and `SKILL.md`.

A Claude Code mod lives in `.agents/skills/<mod-name>/` too, with
`.claude-plugin/plugin.json` in place of `SKILL.md`, a `README.md`, and its
tests. Give it a `.gitignore` for `.claude-plugin/types/`, which Claude Code
writes into the mod's folder each time it loads it. See
[usage-hint](.agents/skills/usage-hint/).

Keep skills tool-agnostic. `SKILL.md` is a portable format, and every skill
here is installed into more than one location and read by more than one agent —
so avoid naming a specific editor, its menus, or its keyboard shortcuts in
instructions.

Once it's merged, anyone with a clone pulls and asks the agent to install it —
no changes to their setup.
