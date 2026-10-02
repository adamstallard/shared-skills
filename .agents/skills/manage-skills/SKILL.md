---
name: manage-skills
description: >-
  Install, remove, and inspect skills from a clone of the shared-skills
  repo. Use when someone asks to install or add a skill, see which skills they
  have, remove or uninstall a skill, update their shared skills, or when a
  skill that should be available isn't showing up.
---

# Managing shared skills

Every shared skill is a symlink pointing back at a clone of `shared-skills`, so
`git pull` updates all of them at once. This skill is the exception: it's a real
copy, so it still works when the links it manages are broken.

Skills are installed into **every** target directory at once:

| Target             | Read by                                       |
| ------------------ | --------------------------------------------- |
| `~/.agents/skills` | agents that use the cross-tool skills location |
| `~/.claude/skills` | Claude Code (user-level skills)                |

One install writes a link into all of them, so the same clone serves every
platform. A skill present in one target but not another is invisible to
whichever agent reads the target that's missing it — `list` and `doctor` report
each target separately for exactly this reason.

## Locate the script

```bash
SK=~/.agents/skills/manage-skills/scripts/skills.py     # or
SK=~/.claude/skills/manage-skills/scripts/skills.py
```

Either copy works and both do the same thing — they're copies of the same
script, and each one installs into every target. If neither path exists, this
skill was loaded from a clone instead — use
`<clone>/.agents/skills/manage-skills/scripts/skills.py` and suggest running
`bootstrap` (see below).

## Commands

```bash
python3 $SK list                       # every skill, and its state in each target
python3 $SK install bug-hunter         # symlink one or more skills into every target
python3 $SK install --all              # symlink everything into every target
python3 $SK install --force <name>     # replace whatever is already there
python3 $SK install --no-hook <name>   # install without wiring up its hook
python3 $SK uninstall <name>           # remove the symlink from every target
python3 $SK doctor                     # find broken, missing, or stale installs
python3 $SK update                     # git pull the clone, refresh this skill
python3 $SK hooks                      # which skills ship hooks, and their state
python3 $SK enable-hook <name>         # wire a skill's hook into every platform
python3 $SK disable-hook <name>        # remove it from every platform
```

There are regression tests next to the script. Run them from the clone's root
after changing it:

```bash
python3 .agents/skills/manage-skills/scripts/test_skills.py
```

**Tell the user to try it in the current tab first.** A skill installed or
removed while a session is running can sometimes be picked up there without a
new tab — don't assume otherwise. If the agent doesn't see it, a new agent tab
is the reliable fallback: a fresh conversation always reflects whatever's
currently installed. That fallback is still the fix behind most "the install
didn't work" reports.

## Workflows

**"Install the X skill"** — run `list` first to confirm the real name, install
it, then tell them to try it right there — a new agent tab is the fallback only
if it isn't picked up. If the skill needs its own setup (a token, a CLI tool),
point them at that skill's README rather than walking them through it here.

**"What skills do I have?"** — `list`. It prints one column per target, so each
skill shows its state in each one: `installed`, `copy`, `-` (available, not
installed), or a problem state. A skill that reads `installed` in one column and
`-` in another is only half installed; the footer names those and gives the fix.

**When installed skills link into more than one clone** — say a public clone
and a team's private one — every command works on one clone at a time, so
answer for each. Find the clones from where the links in a target point
(`ls -l ~/.agents/skills`). Run the command as usual for the clone bootstrap
recorded, and again with `SHARED_SKILLS_REPO=<clone>` for each other clone.
Report the results together, saying which clone each skill comes from. This
holds for `list`, `doctor`, `install`, `uninstall` and `update`.

**"Skill X isn't working / isn't found"** — `doctor`. It reports per target:
dangling symlinks, skills linked to a different clone, real directories that
silently stop tracking `git pull`, and skills installed in one target but
missing from another. Each finding prints its own fix. Check which target is
missing it before anything else — a skill in `~/.agents/skills/` but not
`~/.claude/skills/` is invisible to Claude Code and nowhere else. If `doctor` is
clean, try it in the same tab first — it may already be picked up. If it's
still not seen, a new agent tab is the reliable fallback.

**"Update my skills"** — `update`. Symlinked skills track the clone with no
further action; the command only needs to re-copy this skill into every target.
With `SHARED_SKILLS_REPO` naming a second clone, `update` pulls that clone and
leaves this skill as it is: it is refreshed only from the clone bootstrap
recorded.

**"Turn off the hook" / "stop nagging me about commits"** — `disable-hook <name>`. It
removes the hook from every platform and *remembers the choice*, so a later
`install` won't quietly put it back. `enable-hook` clears that. Never hand-edit
`~/.claude/settings.json` or `~/.cursor/hooks.json` to do this — the manager
matches its own entries by script path and will lose track of a hand-made one.

**"Is the hook on?"** — `hooks`. It prints each hook-shipping skill and its state
per platform, and where each platform's config file lives.

**"Claude Code can't see my skills"** — most likely they were installed before
this script grew a second target. Run `doctor`, then `install --all` (or
`install <name>`) to fill in `~/.claude/skills/`, and `update` to re-copy this
skill there. Try the current tab first; open a new one only if it's still not
seen.

**First-time setup** — if neither `~/.agents/skills/manage-skills/` nor
`~/.claude/skills/manage-skills/` exists yet, run the installer in the clone:

```bash
<clone>/install.sh
```

That records the clone's location and copies this skill into every target.
Everything else is installed with `install` afterwards.

## Hooks

A skill may ship a `hook.json` next to its `SKILL.md`, declaring a script that
should run around agent events — for example, reporting any commit that lands
without having been checked. `install` wires it up automatically when the
manifest says `"default": "enabled"`, and always says so in its output.

```json
{
  "version": 1,
  "summary": "one line, printed when the hook is enabled",
  "command": "scripts/thing.sh",
  "default": "enabled",
  "events": {
    "claude": { "event": "PostToolUse", "matcher": "Bash" },
    "cursor": { "event": "postToolUse", "matcher": "Shell" }
  }
}
```

A skill that needs several hooks lists them under `"hooks"` instead, each entry
with its own `summary`, `command` and `events`; `default` stays top-level. Two
entries may share an event on one platform (say, two `PreToolUse` hooks with
different matchers) — both are wired.

```json
{
  "version": 1,
  "default": "enabled",
  "hooks": [
    { "summary": "...", "command": "scripts/a.sh",
      "events": { "claude": { "event": "PostToolUse", "matcher": "Bash" } } },
    { "summary": "...", "command": "scripts/b.sh",
      "events": { "claude": { "event": "PreToolUse", "matcher": "mcp__x__post" } } }
  ]
}
```

A skill's hooks are enabled, disabled and removed together; there is no
per-hook switch. A bad entry doesn't sink the rest: one with no `command` is
reported and ignored, and one whose script isn't executable is reported and
skipped — the others are enabled, and whatever it already had wired is left as
it is (`doctor` flags that as broken). A manifest with both `command` and
`hooks` wires the `hooks` list and ignores `command`, with a warning naming it:
move it into `hooks` or delete it. Wiring the ignored `command` already had is
treated like a dropped entry's. When an entry is dropped from the list, the
next `install` or `enable-hook` removes its wiring; until then `doctor` reports
it as `STRAY`. The same goes for everything a skill wired before when its
`hook.json` stops yielding any usable hook, including a one-hook manifest that
names no platform this manager knows.

Each platform has its own config file, event names and JSON shape, and the
manager owns all of that — a manifest only names the event it wants per platform.
Adding a platform is one entry in `HOOK_PLATFORMS` in `skills.py`, plus a case in
the hook script for how that host expects a decision reported back.

Things to know when working on this:

- **The hook script is wired by absolute path, with `--host <platform>`
  appended.** The host is passed in rather than guessed from the payload, so a
  script stays correct on a platform it has never seen.
- **Exit code 2 blocks** on every platform supported so far; every other exit
  code is non-blocking, so a crashing or missing hook script fails open.
- **Config files are merged, never rewritten.** Unrelated hooks and settings are
  preserved, a one-time `.shared-skills.bak` backup is kept beside the original,
  and a file that can't be parsed is reported and left untouched rather than
  clobbered.
- **`uninstall` removes the skill's hook too**, so nothing is left firing for a
  skill that isn't there.
- Sandboxed runs (`SHARED_SKILLS_TARGET` set without `SHARED_SKILLS_HOOK_HOME`)
  never touch real hook configs.

## Guardrails to respect

The script refuses to delete anything it didn't create, and you should not work
around it with `rm -rf`:

- `uninstall` removes symlinks only, from every target. If a real directory is
  in the way it says so and skips that target — that directory is somebody's own
  work, not a managed link.
- `install` won't overwrite a real directory or a link to another clone without
  `--force`. It decides target by target, so it can link the targets that are
  free and leave the one that isn't. Confirm with the user before passing
  `--force`.
- `uninstall manage-skills` is refused outright. To remove it, delete
  `~/.agents/skills/manage-skills/` and `~/.claude/skills/manage-skills/` by
  hand.
- Nothing is ever written inside the clone. `<clone>/.agents/skills/` is the
  source of truth; the targets are output only.

## Paths

- Skills are installed into every target at once: `~/.agents/skills/` (the
  cross-tool location agents read for every project) and `~/.claude/skills/`
  (Claude Code's user-level skills directory). The list lives in
  `DEFAULT_TARGET_PATHS` near the top of `skills.py`; adding a platform is one
  more line there.
- `SHARED_SKILLS_TARGET` *replaces* that list rather than adding to it — set it
  and the path it names becomes the only target. It's for tests and sandboxes.
  Separate several paths with `:`.
- The clone's location is recorded in `~/.config/shared-skills/config.json` at
  bootstrap. Override with `SHARED_SKILLS_REPO`.
- If the clone is moved, re-run `bootstrap` from its new location; every
  symlink needs recreating with `install --all --force`.
