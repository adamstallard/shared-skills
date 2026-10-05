# manage-skills

Installs and removes the skills in this repository for you, so you don't have
to think about symlinks.

This is the one skill you install by hand. Once it's in place, you install
everything else by asking the agent.

---

## One-time setup (about 1 minute)

```bash
git clone https://github.com/adamstallard/shared-skills.git ~/shared-skills
~/shared-skills/install.sh
```

Then open a new agent tab.

The clone can live anywhere, not just `~/shared-skills`. `install.sh` runs
`bootstrap`, which records where the clone is and copies this skill
into both places agents look for skills:

- `~/.agents/skills/` — the cross-tool location, read for every project
- `~/.claude/skills/` — Claude Code's user-level skills directory

Everything you install afterwards lands in both, so it doesn't matter which
agent you're using.

Don't move the clone afterwards — the installed skills point back at it. If you
do move it, re-run `bootstrap` from the new location and then ask the agent to
reinstall your skills.

---

## Using it

Just ask the agent:

- "What skills do I have?"
- "Install the bug-hunter skill"
- "Install all the shared skills"
- "Remove the prose skill"
- "Update my shared skills"
- "The bug-hunter skill isn't showing up"

**After anything is installed or removed, try asking in the same tab first** —
it can already see the change. **If it doesn't, open a new agent tab** — a
fresh conversation always picks up whatever's currently installed, and that's
the most common fix when an install seems not to have worked.

Some skills need their own setup on top of this — an API token, a CLI tool.
The agent will point you at the right README when that applies.

---

## Running it yourself

```bash
SK=~/.agents/skills/manage-skills/scripts/skills.py

python3 $SK list                    # what exists, and where each one is installed
python3 $SK install bug-hunter      # install one (or several, space separated)
python3 $SK install --all           # install everything
python3 $SK uninstall bug-hunter    # remove one
python3 $SK doctor                  # diagnose anything odd
python3 $SK update                  # git pull the clone and refresh this skill
python3 $SK hooks                   # which skills have hooks, and whether they're on
python3 $SK disable-hook <name>     # turn a skill's hook off (and keep it off)
python3 $SK enable-hook <name>      # turn it back on
```

`~/.claude/skills/manage-skills/scripts/skills.py` is the same script; either
copy works, and both install into both locations.

`list` prints one column per location, so you can see at a glance if something
landed in one and not the other:

```
  agents      claude      skill        what it does
  installed   installed   bug-hunter   Catch bugs in code that was just written, …
```

---

## Claude Code mods

A mod changes Claude Code itself: a line it draws, a command it adds, a tool
call it checks. It isn't a skill, so there's nothing to ask the agent; once
installed, it just runs. `usage-hint` is one.

You install and remove a mod like a skill, but only Claude Code runs mods, so
it's linked into `~/.claude/skills/` alone. `list` shows `n/a` in the other
column, tags the description `(mod)`, and doesn't count the mod as half
installed:

```
  agents      claude      skill        what it does
  n/a         installed   usage-hint   (mod) Your Claude subscription usage …
```

A new Claude Code session loads a newly installed mod.

---

## Using a private skills repository too

`manage-skills` can install skills from a second clone, such as your own
private skills repository laid out like this one. Point `SHARED_SKILLS_REPO` at
that clone for the one command:

```bash
SHARED_SKILLS_REPO=~/my-skills python3 $SK install my-skill
```

The installed symlinks point into `~/my-skills`. To update those skills, run
`update` the same way:

```bash
SHARED_SKILLS_REPO=~/my-skills python3 $SK update
```

That pulls `~/my-skills` and leaves `manage-skills` as it is, because
`manage-skills` is refreshed only from the clone `bootstrap` recorded. Run
`update` without the variable to pull that clone and refresh it.

Each command works on one clone: the one `SHARED_SKILLS_REPO` names, or else
the recorded one. So `list` and `doctor` without the variable don't show the
private skills; run them with it to check those. If both clones have a skill
with the same name, installing the second one leaves the first in place. Keep
the names apart: when a skill moves from your private repository into this
one, delete it from yours.

---

## Skills that come with a hook

A few skills do more than sit there waiting to be asked — they ship a **hook**
that fires around what your agent does. `bug-hunter`, for example, reports any
commit that lands without having been checked for bugs.

Installing such a skill turns its hook on, and says so:

```
bug-hunter ships a hook, enabled by default:
  Reports any commit that lands without having been through bug-hunter.
  bug-hunter [claude hook]: enabled on PostToolUse
  bug-hunter [cursor hook]: enabled on postToolUse
  turn it off with:  skills.py disable-hook bug-hunter
```

To turn it off, ask the agent to "turn off the bug-hunter hook", or run
`python3 $SK disable-hook bug-hunter`. **The choice sticks** — installing or
reinstalling skills later won't switch it back on. `python3 $SK hooks` shows what
is on right now.

This writes to `~/.claude/settings.json` and `~/.cursor/hooks.json`. Your existing
settings and any other hooks in those files are left alone, and the first time
either file is changed a copy is saved next to it as
`<file>.shared-skills.bak`. Restart Cursor after a change; Claude Code picks it up
in the next session.

Hooks fail open by design: if the hook script is missing or broken, your work
carries on rather than locking you out of your own repo. That means a silently
broken hook checks nothing, which is what `python3 $SK doctor` looks for.

## How it works

Every skill except this one is a **symlink** to `<clone>/.agents/skills/<name>`,
created in `~/.agents/skills/<name>` *and* `~/.claude/skills/<name>`. So a `git
pull` updates every installed skill at once, in every project and every agent,
with no reinstall. Nothing is written inside the clone — it stays the source of
truth.

This skill is a real copy instead, for two reasons: it has to keep working when
the symlinks it manages are broken, and it can't be allowed to delete itself
partway through an uninstall. `update` re-copies it only from the clone
`bootstrap` recorded.

The script will not delete anything it didn't create. If a real directory sits
where a symlink belongs, it says so and stops rather than removing your work.

---

## Troubleshooting

**A skill I installed doesn't show up.** Ask for it in the same tab first — it
can already be there. If not, open a new agent tab. If it still
doesn't appear, run `python3 $SK doctor` — it checks each location separately
and tells you which one is missing the skill. If your agent has a settings
screen listing available skills, check whether it's there.

**Claude Code can't see my skills, but my other agent can.** They were probably
installed before this script started writing to `~/.claude/skills/`. Run
`python3 $SK install --all` (or name just the ones you want) and `python3 $SK
update` to bring that location up to date. Try the current tab first; open a
new one only if it's still not seen.

**"Can't find the shared-skills clone."** The clone was moved or deleted.
Re-run `bootstrap` from wherever it lives now, or set `SHARED_SKILLS_REPO` to
its path.