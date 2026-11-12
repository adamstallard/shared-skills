# manage-skills — decisions

Read before changing how `scripts/skills.py` wires hooks or refreshes itself.
Each entry: what was decided, why, what was rejected, and where it stops applying.

## Which wired entry is which declared hook: one rule

`hook_wiring` and `identifies` decide it; status, enable's sweep, `STRAY`,
auto-enable and `doctor` all ask them. `enable_plan` likewise decides, once,
which platforms enable rewrites and `STRAY` inspects.

- **Why:** one rule can't disagree with itself.
- **Rejected:** a separate matcher or path check at each caller. With the rule
  in four places (`owns_entry`, `runs_script`, the sweep's spare logic,
  `stray_wiring`'s claim), seven of the first eight bugs in the several-hooks
  work were two of them disagreeing.
- **Stops applying:** skill *ownership* — "did this skill wire it at all" — is a
  different question, answered by `owns` (the skill's directory in the path), so
  a renamed script stays removable.

## Whether a skill's hooks are on, and what follows

`hooks_switched_on` decides it, per skill. A skill's hooks are on when all
three hold:

- no opt-out is recorded for it. `disable-hook` and `install --no-hook` record
  the same one, through `switch_hook`;
- it is linked into some target;
- its `default` is `"enabled"`, or at least one of its hooks is wired on some
  platform, as after `enable-hook` on a default-off skill.

While a skill's hooks are on, `doctor` reports each declared hook that is
executable but not wired as `UNWIRED`, with the fix `enable-hook`, and `update`
wires it after the pull (`wire_new_hooks`). A sandboxed run, one with
`SHARED_SKILLS_TARGET` set and `SHARED_SKILLS_HOOK_HOME` unset, does neither:
`install` wires nothing in one.

- **Why:** an entry added to a `hook.json` was wired only by `install` or
  `enable-hook`, so it stayed unwired after `update`, and `doctor` said
  nothing. prose's handback-notice hook, added in commit 6096389, stayed
  unwired that way.
- **Why `--no-hook` records the opt-out:** without it, a default-enabled skill
  installed with `--no-hook` would read as on, so `doctor` would report its
  hooks `UNWIRED` and the next `update` would wire them.
- **Rejected:** "on" without the link condition. A skill in the clone that is
  not installed would read as on. So would a skill whose links are all gone
  but whose wiring was left behind; `doctor` reports that wiring as `ORPHAN`,
  with the fix `install` or `disable-hook`, and `update` would add to it.
- **Rejected:** reporting a hook whose script is not executable as `UNWIRED`.
  `enable-hook` skips such a hook, so the fix would not clear the report. Once
  it is wired, `doctor` reports it as `BROKEN`; while unwired, nothing reports
  it.
- **Stops applying:** if hooks gain a per-entry switch.

## Mods are linked only into `.claude/skills` targets

A folder with `.claude-plugin/plugin.json` and no `SKILL.md` is a mod, and
`targets_for` gives it only the targets whose path ends in `.claude/skills`
(`takes_mods`). `list` shows `n/a` for the others; `doctor`'s `MISSING` and
`ORPHAN` checks only look at the targets a name belongs in.

- **Why:** only Claude Code loads mods, from `.claude/skills/<name>`. A link in
  `~/.agents/skills` would do nothing for the agents that read it, and the
  per-target gap checks would flag the mod as half installed forever.
- **Rejected:** a `SKILL.md` in each mod so the manager needs no change. Every
  agent reading `~/.agents/skills` would list a skill that does nothing for it.
- **Stops applying:** if another agent starts loading Claude Code mods, or Claude
  Code loads them from another directory: change `takes_mods`.

## A mod left in a target that cannot load it: `rm`, reported by doctor

`doctor` reports any entry named like a mod, in a target that cannot load mods,
as `NOT HERE` with `fix: rm <path>` (`rm -r` for a real directory). That covers
a broken link, a link to another clone, and a valid link to this one. `list`
shows the entry's real state there, and `n/a` only when nothing is present.
`loads_here` exempts a target that is the same directory as one the mod belongs
in, comparing each pair separately (`same_dir`).

- **Why:** without the same-directory check, a `~/.agents/skills` linked to
  `~/.claude/skills` would get advice to delete the only working link; that
  happened once, when one missing target ended the whole comparison.
- **Rejected:** `uninstall <name>` as the fix (it walks every target and drops
  the working `.claude` link too); `install --force` as the fix (it never
  touches that target, so the problem never clears); `install --force`
  cleaning other targets (install would start deleting in targets it otherwise
  never touches).
- **Stops applying:** entries are still matched by exact name and regular files
  are still ignored, as everywhere else in doctor.

## Skill names and case

A name is written in the skill directory's own spelling (`skill_dir_name`), and
on a case-insensitive filesystem every read that compares a stored path or name
is case-blind (`fold`, decided once from the clone's skills directory):
ownership, hook identity, opt-outs, and whether a link is this skill's.

- **Why:** on macOS `Bug-Hunter` opens `bug-hunter`, and older versions
  recorded whatever spelling was typed, in links, wiring and opt-outs. Writing
  one spelling keeps new state consistent; reading case-blind still reaches the
  old state.
- **Rejected:** rewriting only the typed name (strands the old state: uninstall
  reported success while the hook kept firing); migrating stored state (writes
  users' config files to fix a read).
- **Stops applying:** on a case-sensitive filesystem, where `Bug-Hunter` and
  `bug-hunter` can be two skills, matching stays exact. `doctor` still lists
  target entries by exact name.

## A manifest with both `command` and `hooks`

The `hooks` list is wired and the top-level `command` is ignored, with a warning
that names it and says to move it into `hooks` or delete it. Wiring the ignored
`command` already had is treated like a dropped entry's: `doctor` reports it as
`STRAY`, and the next `install` or `enable-hook` removes it. That holds even
when the list has no usable entry (see the next section).

- **Why:** both forms together is most likely a half-finished move to the list,
  and the list is the new intent. One matching rule applies per skill (the
  list's), and a warning beats silently wiring nothing.
- **Rejected:** refusing the whole manifest. That left the skill with no hooks,
  and its message understated it.
- **Stops applying:** a manifest with only one of the two forms.

## A hook.json that loads no hook

When a skill's `hook.json` is there but yields no usable hook (unparseable,
invalid, an empty `hooks` list, only unusable entries, `command` beside such a
list, or a one-hook manifest that names no platform this manager knows), whatever
the skill wired before is leftover. `doctor` reports each
such command as `STRAY`, and `install` and `enable-hook` remove it, found by the
skill's directory in the path, as `disable-hook` and `uninstall` do.
The opt-out still follows the last command: `disable-hook` records it,
`enable-hook` clears it.

- **Why:** a hook that nothing declares any more must not keep firing unseen.
  Ownership needs no manifest, so the sweep needs none either.
- **Rejected:** leaving the wiring until `disable-hook` or `uninstall`. It keeps
  running, and nothing says so.
- **Stops applying:** a skill with no `hook.json` at all. It ships no hook, so
  its old wiring is left for `disable-hook` or `uninstall`.

## `update` refreshes manage-skills only from the recorded clone

`update` pulls whichever clone the command uses,
but copies `manage-skills` into the targets only from the clone `bootstrap`
recorded in the config. When `SHARED_SKILLS_REPO` names another clone, `update`
pulls it and says it left `manage-skills` as it is. When the variable names the
recorded clone, it refreshes as usual. When the variable is set and nothing is
recorded (bootstrap never ran), it refuses to refresh, because nothing says
which clone is the source; `bootstrap` records it. Without the variable and with
nothing recorded, it refreshes from the clone the script lives in.

`install_manager` checks the source has a `manage-skills` before touching any
target, and builds each new copy beside the target, swapping it in only once
it is complete. The swap moves the old copy aside, then moves the new one in;
the `finally` puts the old one back if the target is left empty, whatever
stopped it.

- **Why:** the variable lets people install from a second, private skills
  repository, and that clone's `manage-skills` may be older or missing.
- **Rejected:** replacing the installed `manage-skills` with the one in
  whichever clone `update` pulls. An older private copy replaces the public
  one, and a private repository with none leaves no `manage-skills` at all.
  Also rejected: telling people not to run `update` with the variable. The
  command they would naturally type stays destructive. And restoring the old
  copy only on `OSError`, since a Ctrl-C between the two renames then deletes
  it with the staging directory.
- **Stops applying:** `bootstrap`, which copies `manage-skills` from the clone it
  is run from and records that clone.

## Known gaps

### A process killed mid-swap leaves the target empty

If `update` is killed (SIGKILL, a crash) between moving the old copy aside and
moving the new one in, no `finally` runs: the target has no `manage-skills`,
and the old copy sits in a hidden `.manage-skills-*` directory beside it.
Re-running `bootstrap` from the clone restores it. Closing the gap needs an
atomic exchange (`renamex_np`/`renameat2`), which the standard library lacks.

### A hook script outside its skill's directory can't be swept

`"command": "../_shared/x.sh"`, or a symlink that resolves out of the skill,
is wired and shows as enabled, but `disable-hook` and `uninstall` leave it: the
sweep recognises the skill's entries by its directory (`hook_owner`), and the
resolved path isn't in it.

- **Why accepted:** sweeping by script path instead would also remove another
  skill's wiring of the same shared script.
- **Not done:** refusing such a manifest. That is the likely fix if it comes up.
- **Stops applying:** scripts inside the skill directory, which is every skill
  today.

### A repeat `enable-hook` counts a change

The sweep always removes the skill's entries before re-adding them, so the
"already enabled" branch is unreachable once a hook is wired: a second
`enable-hook` rewrites the file (same content, entries moved to the end),
counts a change and prints the Restart Cursor notice.

- **Why accepted:** counting a change only when the file's content changes
  would alter the single-hook output, which is kept stable.
- **Stops applying:** once the single-hook output may change.

### A case-sensitive clone with case-insensitive targets

With the clone on a case-sensitive volume and the target directories on a
case-insensitive one, `uninstall Bug-Hunter` removes the `bug-hunter` link (the
target filesystem finds it) but leaves its hook wired.

- **Why accepted:** case-blindness is decided from the clone's filesystem, where
  `Bug-Hunter` is not `bug-hunter`, so the name isn't rewritten and nothing is
  folded. It needs an unusual layout and the wrong case typed.
- **What would fix it:** deciding case-blindness per filesystem touched, or
  refusing a name that matches no skill directory exactly.
- **Stops applying:** clone and targets on filesystems that agree about case.

### Duplicate wiring left by two spellings

A version that recorded the typed spelling wired the hook twice for `install
Bug-Hunter` then `install bug-hunter`, once per spelling, so it runs twice. Neither `install` nor `doctor` flags it;
`enable-hook` collapses it to one, because its sweep ignores case.

- **Why accepted:** only such versions create it, and `enable-hook` repairs it.
- **What would fix it:** `doctor` reporting a skill wired more than once per
  event and matcher in the single-hook form, as it already does with `STRAY` in
  the list form.
- **Stops applying:** once no install made by such a version remains.

### Leftover wiring inside a config that doesn't parse

When a skill's `hook.json` loads no hook and its old wiring sits only in a
platform config that doesn't parse, neither `doctor` nor `install` mentions it:
both read only configs that parse. A sweep that reaches such a file refuses to
rewrite it and says so.

- **Why accepted:** the host most likely can't read that file either, so the
  entry isn't firing; the file itself needs repairing first.
- **What would fix it:** `doctor` naming each unparseable config once, for every
  skill that might have wiring there.
- **Stops applying:** once the config parses again, when `doctor` reports the
  leftover and `install` removes it.
