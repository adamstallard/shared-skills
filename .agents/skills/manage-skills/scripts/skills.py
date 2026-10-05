#!/usr/bin/env python3
"""Install shared skills by symlinking them into your user skills directories.

Standard library only. Every skill except this one is installed as a symlink
back to the clone, so `git pull` updates them everywhere at once. This skill
is installed as a real copy instead, so it keeps working even when the links
it manages are broken, and so it can never delete itself mid-operation.

Skills are installed into *every* target directory listed in TARGETS, so one
clone serves several agent platforms at the same time.

Before changing how hooks are wired, read ../DECISIONS.md.
"""

import argparse
import collections
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

MANAGER = "manage-skills"

# Where skill folders live inside the clone. This is the repo's canonical
# layout and is deliberately not the same thing as the install targets below.
SKILLS_SUBDIR = pathlib.Path(".agents") / "skills"

# Every install target gets its own copy of the symlink, so the same clone is
# visible to every agent platform at once. Adding a platform is one more line.
#   ~/.agents/skills  — the cross-tool location several agents read
#   ~/.claude/skills  — where Claude Code discovers user-level skills
DEFAULT_TARGET_PATHS = (
    pathlib.Path.home() / ".agents" / "skills",
    pathlib.Path.home() / ".claude" / "skills",
)

# SHARED_SKILLS_TARGET replaces the whole list rather than adding to it: when it
# is set, that path is the only target. Useful for tests and sandboxes, which
# want one throwaway directory and nothing touching the real home directory.
# Several paths may be given, separated by os.pathsep (":" on macOS/Linux).
TARGET_ENV = "SHARED_SKILLS_TARGET"

CONFIG_FILE = pathlib.Path(
    os.environ.get("SHARED_SKILLS_CONFIG")
    or pathlib.Path.home() / ".config" / "shared-skills" / "config.json"
).expanduser()

# ---------------------------------------------------------------------------
# Hooks
#
# A skill may ship a hook.json describing hooks that should fire around agent
# events — see read_hook_manifest() for the format. Every platform has its own
# config file, event names and JSON shape, so the *platform* knowledge lives here and a
# skill's manifest only names the event it wants on each one.
#
# Hook scripts are always wired by absolute path. Both platforms resolve
# relative paths against a working directory that differs between project and
# user scope, and getting that wrong is the most common reason a hook silently
# never fires.
HOOK_MANIFEST = "hook.json"

# Rewrites where hook config files are looked for. Tests and sandboxes set it so
# nothing touches the real home directory.
HOOK_HOME_ENV = "SHARED_SKILLS_HOOK_HOME"

HookPlatform = collections.namedtuple("HookPlatform", "name relpath shape")

HOOK_PLATFORMS = (
    # Claude Code: hooks live alongside the rest of its settings.
    #   {"hooks": {"PreToolUse": [{"matcher": ..., "hooks": [{"type": "command",
    #    "command": ...}]}]}}
    HookPlatform("claude", pathlib.Path(".claude") / "settings.json", "claude"),
    # Cursor: a dedicated file, flatter shape, schema version 1.
    #   {"version": 1, "hooks": {"beforeShellExecution": [{"command": ...,
    #    "matcher": ...}]}}
    HookPlatform("cursor", pathlib.Path(".cursor") / "hooks.json", "cursor"),
)

HOOK_ENABLED = "enabled"
HOOK_OFF = "off"

LINKED = "linked"
COPY = "copy"
FOREIGN = "other"
BROKEN = "broken"
ABSENT = "-"
NOT_HERE = "n/a"

MARKERS = {
    LINKED: "installed",
    COPY: "copy",
    FOREIGN: "other",
    BROKEN: "broken",
    ABSENT: "-",
    NOT_HERE: "n/a",
}

# A Claude Code mod is a plugin folder: .claude-plugin/plugin.json and a hooks
# module, no SKILL.md. Claude Code loads one from a `.claude/skills/<name>`
# directory, and no other agent runs it, so a mod is linked only into targets
# that are such a directory (see takes_mods).
MOD_MANIFEST = pathlib.Path(".claude-plugin") / "plugin.json"

PRESENT = (LINKED, COPY, FOREIGN, BROKEN)

Target = collections.namedtuple("Target", "label path")


def label_for(path):
    """A short name for a target, taken from the directory it sits in."""
    stem = path.parent.name.lstrip(".") or path.name.lstrip(".")
    return stem or str(path)


def make_targets(paths):
    targets = []
    used = set()
    for path in paths:
        path = pathlib.Path(path).expanduser()
        label = label_for(path)
        if label in used:
            label = f"{label}-{len(targets) + 1}"
        used.add(label)
        targets.append(Target(label, path))
    return tuple(targets)


def resolve_targets():
    override = os.environ.get(TARGET_ENV, "").strip()
    if override:
        paths = [part for part in override.split(os.pathsep) if part.strip()]
        if paths:
            return make_targets(paths)
    return make_targets(DEFAULT_TARGET_PATHS)


TARGETS = resolve_targets()
LABEL_WIDTH = max([10] + [len(target.label) for target in TARGETS])


def infer_repo_from_script():
    """The clone this script physically lives in, if it lives in one."""
    here = pathlib.Path(__file__).resolve()
    if len(here.parents) > 4:
        candidate = here.parents[4]
        if (candidate / SKILLS_SUBDIR).is_dir():
            return candidate
    return None


def find_repo(required=True):
    global CASE_BLIND
    repo = locate_repo(required)
    if repo:
        CASE_BLIND = case_blind(repo / SKILLS_SUBDIR)
    return repo


# Whether the clone's filesystem ignores case; find_repo sets it.
CASE_BLIND = False


def case_blind(path):
    """Does the filesystem at `path` ignore case?"""
    path = str(path.resolve())
    try:
        return path != path.swapcase() and os.path.samefile(path, path.swapcase())
    except OSError:
        return False


def fold(text):
    """`text` as the clone's filesystem compares it: lowercased when the
    filesystem ignores case, unchanged otherwise.

    Every case-insensitive comparison of a path or skill name goes through
    here, so they all agree."""
    return text.lower() if CASE_BLIND else text


def locate_repo(required):
    override = os.environ.get("SHARED_SKILLS_REPO", "").strip()
    if override:
        path = pathlib.Path(override).expanduser()
        if (path / SKILLS_SUBDIR).is_dir():
            return path
        sys.exit(f"SHARED_SKILLS_REPO points at {path}, which has no {SKILLS_SUBDIR}/.")

    if CONFIG_FILE.is_file():
        try:
            stored = json.loads(CONFIG_FILE.read_text()).get("repo", "")
        except (json.JSONDecodeError, OSError):
            stored = ""
        if stored:
            path = pathlib.Path(stored).expanduser()
            if (path / SKILLS_SUBDIR).is_dir():
                return path
            sys.exit(
                f"The clone recorded in {CONFIG_FILE} is missing:\n  {path}\n"
                "Move the clone back, or re-run bootstrap from its new location."
            )

    inferred = infer_repo_from_script()
    if inferred:
        return inferred
    if required:
        sys.exit(
            "Can't find the shared-skills clone.\n"
            "Run bootstrap from inside the clone:\n"
            "  python3 <clone>/.agents/skills/manage-skills/scripts/skills.py bootstrap\n"
            "Or set SHARED_SKILLS_REPO=/path/to/shared-skills."
        )
    return None


def load_config():
    if not CONFIG_FILE.is_file():
        return {}
    try:
        data = json.loads(CONFIG_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def save_config(data):
    """Write the whole config back, preserving keys this command didn't touch."""
    try:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(data, indent=2) + "\n")
    except OSError as err:
        sys.exit(
            f"Could not write {CONFIG_FILE}: {err}\n"
            "Fix the permissions, or set SHARED_SKILLS_REPO in your shell instead."
        )


def save_repo(repo):
    config = load_config()
    config["repo"] = str(repo)
    save_config(config)


def hook_opt_outs():
    """Skills whose hook the user turned off on purpose.

    Without this, the next `install` would quietly undo a `disable-hook` —
    installing is not consent to re-enable something you switched off.
    """
    values = load_config().get("hooks_off", [])
    return set(values) if isinstance(values, list) else set()


def opted_out_of_hook(name):
    return fold(name) in {fold(str(value)) for value in hook_opt_outs()}


def set_hook_opt_out(name, opted_out):
    config = load_config()
    current = config.get("hooks_off", [])
    current = set(current) if isinstance(current, list) else set()
    # Drop the name in every case first: older versions recorded it as typed.
    current = {value for value in current if fold(str(value)) != fold(name)}
    if opted_out:
        current.add(name)
    else:
        current.discard(name)
    if current:
        config["hooks_off"] = sorted(current)
    else:
        config.pop("hooks_off", None)
    save_config(config)


def skill_dir_name(repo, name):
    """The skill directory's own spelling of `name`.

    On a case-insensitive filesystem `Bug-Hunter` opens `bug-hunter`, but every
    string the manager keeps — opt-outs, owner paths, link names — must use the
    directory's spelling. Where the filesystem is case-sensitive the wrong case
    finds nothing, and the name is left as typed.
    """
    root = repo / SKILLS_SUBDIR
    if not (root / name).is_dir():
        return name
    for entry in root.iterdir():
        if entry.name == name:
            return name
    for entry in root.iterdir():
        if entry.name.lower() == name.lower() and entry.is_dir() and os.path.samefile(entry, root / name):
            return entry.name
    return name


def is_mod(repo, name):
    source = repo / SKILLS_SUBDIR / name
    return not (source / "SKILL.md").is_file() and (source / MOD_MANIFEST).is_file()


def available(repo):
    root = repo / SKILLS_SUBDIR
    return sorted(
        entry.name
        for entry in root.iterdir()
        if (entry / "SKILL.md").is_file() or (entry / MOD_MANIFEST).is_file()
    )


def takes_mods(target):
    """Whether Claude Code loads mods from this target: a `.claude/skills` dir."""
    return target.path.parts[-2:] == (".claude", "skills")


def targets_for(repo, name):
    """The targets a skill or mod belongs in: every one for a skill."""
    if is_mod(repo, name):
        return tuple(target for target in TARGETS if takes_mods(target))
    return TARGETS


def describe(repo, name):
    """A skill's description from its YAML frontmatter; a mod's from plugin.json."""
    if is_mod(repo, name):
        try:
            manifest = json.loads((repo / SKILLS_SUBDIR / name / MOD_MANIFEST).read_text())
        except (OSError, ValueError):
            return ""
        description = manifest.get("description") if isinstance(manifest, dict) else None
        return "(mod) " + description if isinstance(description, str) else "(mod)"
    try:
        lines = (repo / SKILLS_SUBDIR / name / "SKILL.md").read_text().splitlines()
    except OSError:
        return ""
    if not lines or lines[0].strip() != "---":
        return ""
    collected = []
    capturing = False
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if capturing:
            if line.startswith((" ", "\t")):
                collected.append(line.strip())
                continue
            break
        if line.startswith("description:"):
            first = line.split(":", 1)[1].strip()
            if first and first not in (">", ">-", "|", "|-"):
                collected.append(first)
            capturing = True
    return " ".join(collected)


def status(repo, name, target):
    """State of one skill in one target directory."""
    link = target.path / name
    expected = (repo / SKILLS_SUBDIR / name).resolve()
    if link.is_symlink():
        try:
            actual = link.resolve(strict=True)
        except OSError:
            return BROKEN
        try:
            # samefile rather than ==: on a case-insensitive filesystem, a link
            # spelt in another case still points at this skill.
            return LINKED if os.path.samefile(actual, expected) else FOREIGN
        except OSError:
            return FOREIGN
    if link.is_dir():
        return COPY
    return ABSENT


def statuses(repo, name):
    """[(target, state), ...] across every target, in TARGETS order."""
    return [(target, status(repo, name, target)) for target in TARGETS]


def print_header(repo):
    print(f"Clone:  {repo}")
    print("Targets:")
    for target in TARGETS:
        print(f"  {target.label:<{LABEL_WIDTH}}  {target.path}")
    print()


def install_into(repo, name, target, force=False):
    source = repo / SKILLS_SUBDIR / name
    link = target.path / name
    state = status(repo, name, target)

    if state == LINKED:
        print(f"  {name} [{target.label}]: already installed")
        return False
    if state == COPY and not force:
        print(
            f"  {name} [{target.label}]: a real directory is already there; "
            "not touching it (--force to replace)"
        )
        return False
    if state == FOREIGN and not force:
        print(
            f"  {name} [{target.label}]: linked to a different location; "
            "leaving it (--force to relink)"
        )
        return False

    target.path.mkdir(parents=True, exist_ok=True)
    if link.is_symlink():
        link.unlink()
    elif link.is_dir():
        shutil.rmtree(link)
    link.symlink_to(source, target_is_directory=True)
    print(f"  {name} [{target.label}]: installed")
    return True


def install_one(repo, name, force=False):
    """Install one skill into every target. Returns how many targets changed."""
    if name == MANAGER:
        print(f"  {name}: installed as a copy by bootstrap; use 'update' to refresh it")
        return 0

    source = repo / SKILLS_SUBDIR / name
    if not (source / "SKILL.md").is_file() and not (source / MOD_MANIFEST).is_file():
        print(f"  {name}: not a skill or mod in this repo")
        return 0

    targets = targets_for(repo, name)
    if not targets:
        print(f"  {name}: a Claude Code mod, and no target is a .claude/skills directory")
        return 0
    return sum(install_into(repo, name, target, force) for target in targets)


def uninstall_from(repo, name, target):
    link = target.path / name
    if link.is_symlink():
        link.unlink()
        print(f"  {name} [{target.label}]: removed")
        return True
    if link.is_dir():
        print(
            f"  {name} [{target.label}]: a real directory, not a symlink — "
            "remove it by hand if you meant to"
        )
        return False
    print(f"  {name} [{target.label}]: not installed")
    return False


def uninstall_one(repo, name):
    """Remove one skill from every target. Returns how many targets changed."""
    if name == MANAGER:
        print(f"  {name}: refusing to remove the manager itself")
        return 0
    return sum(uninstall_from(repo, name, target) for target in TARGETS)


def hook_home():
    override = os.environ.get(HOOK_HOME_ENV, "").strip()
    return pathlib.Path(override).expanduser() if override else pathlib.Path.home()


def hook_config_path(platform):
    return hook_home() / platform.relpath


def read_hook_manifest(repo, name):
    """A skill's hook.json, or None when it doesn't declare a hook.

    Format, one hook:
      {"version": 1,
       "summary": "one line, shown when the hook is enabled",
       "command": "scripts/thing.sh",          # relative to the skill directory
       "default": "enabled" | "off",           # wire it up on install?
       "events": {"<platform>": {"event": ..., "matcher": ...}}}

    Several hooks: "hooks" replaces summary/command/events with a list of
    objects holding those three keys. "default" stays top-level and covers them
    all. An entry with no command is reported and dropped; the rest still load.
    A top-level command beside "hooks" is reported and ignored.
    """
    path = repo / SKILLS_SUBDIR / name / HOOK_MANIFEST
    if not path.is_file():
        return None
    try:
        manifest = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as err:
        print(f"  {name}: {HOOK_MANIFEST} is unreadable ({err}); ignoring its hook")
        return None
    if isinstance(manifest, dict) and "hooks" in manifest:
        return read_hook_list(name, manifest)
    if not isinstance(manifest, dict) or not manifest.get("command"):
        print(f"  {name}: {HOOK_MANIFEST} has no command; ignoring its hook")
        return None
    if not hook_well_formed(manifest):
        print(f"  {name}: {HOOK_MANIFEST} has a malformed command or events; ignoring its hook")
        return None
    if not any(manifest.get("events", {}).get(platform.name) for platform in HOOK_PLATFORMS):
        # It would wire nothing, so it counts as loading no hook and what the
        # skill wired before is leftover.
        print(f"  {name}: {HOOK_MANIFEST} names no known platform; ignoring its hook")
        return None
    return manifest


def read_hook_list(name, manifest):
    """Validate the several-hooks form, keeping whichever entries are usable.

    A top-level command beside the list is ignored with a warning, and the list
    is wired. Refusing the whole manifest would leave the skill with no hooks.
    """
    if manifest.get("command"):
        print(
            f"  {name}: {HOOK_MANIFEST} has both command ({manifest['command']}) and hooks;"
            " ignoring command — move it into hooks or delete it"
        )
        manifest = {key: value for key, value in manifest.items() if key != "command"}
    entries = manifest["hooks"] if isinstance(manifest["hooks"], list) else []
    kept = []
    for number, entry in enumerate(entries, 1):
        if not (isinstance(entry, dict) and entry.get("command")):
            print(f"  {name}: {HOOK_MANIFEST} hook {number} has no command; ignoring that hook")
        elif not hook_well_formed(entry):
            print(f"  {name}: {HOOK_MANIFEST} hook {number} has a malformed command or events; ignoring that hook")
        else:
            kept.append(entry)
    if not kept:
        print(f"  {name}: {HOOK_MANIFEST} has no usable hook; ignoring it")
        return None
    return {**manifest, "hooks": kept}


def hook_well_formed(hook):
    """Can the rest of this file read `hook` without crashing? Requires a
    string command, and events that are an object whose entry for each known
    platform is empty or names an event. Both hook.json forms are checked here.

    Unknown platform keys are not checked: a newer manager may have added them,
    and nothing here reads them."""
    events = hook.get("events", {})
    return (
        isinstance(hook.get("command"), str)
        and isinstance(events, dict)
        and all(
            not events.get(platform.name) or event_well_formed(events[platform.name])
            for platform in HOOK_PLATFORMS
        )
    )


def event_well_formed(wanted):
    """A non-empty string event, and a string matcher or none."""
    return (
        isinstance(wanted, dict)
        and isinstance(wanted.get("event"), str)
        and bool(wanted["event"])
        and isinstance(wanted.get("matcher"), (str, type(None)))
    )


def manifest_hooks(manifest):
    """Every hook a manifest declares. The one-hook form is a list of one."""
    return manifest["hooks"] if "hooks" in manifest else [manifest]


def hook_script(repo, name, hook):
    """Absolute path to one hook's script."""
    return str((repo / SKILLS_SUBDIR / name / hook["command"]).resolve())


def hook_owner(repo, name):
    """What marks a config entry as belonging to this skill.

    The skill's directory, not the script path: a skill that renames or replaces
    its hook script still owns whatever it wired up under the old name, and has
    to be able to clean it out.
    """
    return str((repo / SKILLS_SUBDIR / name).resolve()) + os.sep


def wired_command(script, platform):
    """What actually goes in the config file.

    The platform is passed to the script rather than sniffed from the payload:
    every host has its own way of reporting a decision back, and guessing from
    the shape of stdin breaks the moment a new host shows up. A script that is
    told who it is talking to can stay correct on hosts it has never seen.
    """
    quoted = f'"{script}"' if " " in script else script
    return f"{quoted} --host {platform.name}"


def load_hook_config(platform):
    """(data, error). Missing file is an empty config, not an error."""
    path = hook_config_path(platform)
    if not path.is_file():
        return {}, None
    try:
        text = path.read_text().strip()
    except OSError as err:
        return None, f"cannot read {path}: {err}"
    if not text:
        return {}, None
    try:
        data = json.loads(text)
    except json.JSONDecodeError as err:
        return None, f"{path} is not valid JSON ({err})"
    if not isinstance(data, dict):
        return None, f"{path} is not a JSON object"
    return data, None


def save_hook_config(platform, data):
    """Write a hook config back, keeping a one-time backup of the original."""
    path = hook_config_path(platform)
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = path.with_suffix(path.suffix + ".shared-skills.bak")
    if path.is_file() and not backup.exists():
        shutil.copy2(path, backup)
    path.write_text(json.dumps(data, indent=2) + "\n")
    return backup if backup.exists() else None


# Matching wired config entries to declared hooks.
#
# Status, enable's sweep and doctor's STRAY report all match through
# identifies(). Don't give any of them its own copy of the rule: copies drift
# apart.

ANYWHERE = object()

Wiring = collections.namedtuple("Wiring", "script event matcher loose")


def hook_wiring(repo, name, manifest, hook, platform=None):
    """The Wiring that recognises one declared hook in a config, or None when
    the hook names no event on `platform`.

    With no platform, event and matcher are ANYWHERE, so the script matches under
    any event and matcher. Callers use this to find a broken script's wiring and
    leave it alone.

    How strictly a command is matched:
    - One-hook form (loose): the script path anywhere in the command, under any
      matcher. This still recognises entries written by hand or by older
      versions of this manager.
    - List form: the path must appear as a whole script path (see
      command_runs), and the matcher must match. A list can put one script
      under one event twice, or name a script that is a prefix of another.
    """
    script = hook_script(repo, name, hook)
    loose = "hooks" not in manifest
    if platform is None:
        return Wiring(script, ANYWHERE, ANYWHERE, loose)
    wanted = hook.get("events", {}).get(platform.name)
    if not wanted:
        return None
    return Wiring(script, wanted["event"], wanted.get("matcher"), loose)


def identifies(wiring, event, matcher, command):
    """Is this wired command, under this event and matcher, the declared hook?"""
    if wiring.event is not ANYWHERE and event != wiring.event:
        return False
    if wiring.loose:
        return fold(wiring.script) in fold(command)
    # A missing matcher and "" both mean "match everything".
    if wiring.matcher is not ANYWHERE and (matcher or None) != (wiring.matcher or None):
        return False
    return command_runs(fold(command), fold(wiring.script))


def command_runs(command, script):
    """Does `command` contain `script` followed by the end of the command, a
    space or a double quote?

    This keeps scripts/lint from matching inside scripts/lint-fix.
    """
    start = command.find(script)
    while start != -1:
        after = command[start + len(script):start + len(script) + 1]
        if after in ("", " ", '"'):
            return True
        start = command.find(script, start + 1)
    return False


def owns(command, owner):
    """Did this skill wire this command? See hook_owner for why ownership is
    judged by the skill's directory, not a script path."""
    return fold(owner) in fold(command)


def item_command(item):
    return str(item.get("command", "")) if isinstance(item, dict) else ""


def wired_items(data):
    """(event, matcher, command) for every command wired in a config.

    A claude matcher group holds the matcher and its inner hooks hold the
    commands; a cursor entry holds both. Either way, each command is yielded
    separately, so a match on one never counts for another in the same group.
    """
    hooks = data.get("hooks") if isinstance(data, dict) else None
    if not isinstance(hooks, dict):
        return
    for name, entries in hooks.items():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            inner = entry.get("hooks")
            for item in inner if isinstance(inner, list) else [entry]:
                yield name, entry.get("matcher"), item_command(item)


def hook_installed(data, wiring):
    return any(
        identifies(wiring, event, matcher, command)
        for event, matcher, command in wired_items(data)
    )


def add_hook_entry(data, platform, event, matcher, command):
    if platform.shape == "cursor":
        # Schema version leads the file, before "hooks" is created.
        data.setdefault("version", 1)
    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        return False
    entries = hooks.setdefault(event, [])
    if not isinstance(entries, list):
        return False
    if platform.shape == "claude":
        entry = {"matcher": matcher, "hooks": [{"type": "command", "command": command}]}
    else:
        data.setdefault("version", 1)
        entry = {"command": command}
        if matcher:
            entry["matcher"] = matcher
    entries.append(entry)
    return True


def drop_hook_entries(data, owner, keep=()):
    """Remove every entry belonging to this skill, under *any* event, except
    those a Wiring in `keep` identifies.

    Sweeping all events rather than the one the manifest currently names is the
    whole point: when a skill changes which event it hooks, the entry it wrote
    under the old event is still out there, and only the skill that wrote it
    knows to remove it. Left behind, it points at a script that may no longer
    exist and errors on every command in every session.
    """
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return False
    # Build a list: with a generator, any() would stop at the first event it
    # cleared and leave the other events uncleared.
    removed = [
        drop_hook_entry(data, event, owner, keep) for event in list(hooks.keys())
    ]
    return any(removed)


def drop_hook_entry(data, event, owner, keep=()):
    """Remove our entries from one event, and any matcher group we just emptied.

    Anything that isn't ours stays, including anything that doesn't look like a
    hook entry at all.
    """
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return False
    entries = hooks.get(event)
    if not isinstance(entries, list):
        return False

    def doomed(item, matcher):
        command = item_command(item)
        return owns(command, owner) and not any(
            identifies(wiring, event, matcher, command) for wiring in keep
        )

    kept = []
    removed = False
    for entry in entries:
        if not isinstance(entry, dict):
            kept.append(entry)
            continue
        matcher = entry.get("matcher")
        inner = entry.get("hooks")
        if isinstance(inner, list):
            survivors = [item for item in inner if not doomed(item, matcher)]
            if len(survivors) == len(inner):
                kept.append(entry)
                continue
            removed = True
            if survivors:
                kept.append({**entry, "hooks": survivors})
            continue
        if doomed(entry, matcher):
            removed = True
            continue
        kept.append(entry)

    if not removed:
        return False
    if kept:
        hooks[event] = kept
    else:
        hooks.pop(event, None)
        if not hooks:
            data.pop("hooks", None)
    return True


def hook_rows(repo, name, manifest):
    """[(hook, platform, state, detail), ...] — one row per hook per platform it
    names; state is enabled / off / a problem."""
    listed = "hooks" in manifest
    configs = {}
    rows = []
    for hook in manifest_hooks(manifest):
        for platform in HOOK_PLATFORMS:
            wiring = hook_wiring(repo, name, manifest, hook, platform)
            if not wiring:
                continue
            if platform.name not in configs:
                configs[platform.name] = load_hook_config(platform)
            data, error = configs[platform.name]
            if error:
                rows.append((hook, platform, "unreadable", error))
                continue
            installed = hook_installed(data, wiring)
            detail = wiring.event
            if listed and wiring.matcher:
                # Without the matcher, two entries on one event print identical rows.
                detail += f"  {wiring.matcher}"
            rows.append((hook, platform, HOOK_ENABLED if installed else HOOK_OFF, detail))
    return rows


def enable_plan(repo, name, manifest):
    """What set_hook(enable) does, as (usable, broken, plan):
    - usable: hooks whose script is executable; these get wired.
    - broken: Wirings of the hooks whose script is not; their existing wiring
      is kept.
    - plan: {platform: [Wiring, ...]}, the platforms to rewrite and what to wire
      on each. stray_wiring inspects the same platforms.

    Which platforms are rewritten:
    - List form: every platform, so wiring left by a hook dropped from the list
      is swept wherever it is. If a platform were skipped because no usable
      hook names it, a dropped hook would keep firing there, unreported.
    - One-hook form: the platforms its hook names, and none when that hook is
      broken.
    """
    hooks = manifest_hooks(manifest)
    usable, broken = [], []
    for hook in hooks:
        if os.access(hook_script(repo, name, hook), os.X_OK):
            usable.append(hook)
        else:
            broken.append(hook_wiring(repo, name, manifest, hook))
    listed = "hooks" in manifest
    plan = {}
    if not usable and not listed:
        return usable, broken, plan
    for platform in HOOK_PLATFORMS:
        wanted = [
            wiring
            for wiring in (hook_wiring(repo, name, manifest, hook, platform) for hook in usable)
            if wiring
        ]
        if wanted or listed:
            plan[platform] = wanted
    return usable, broken, plan


def stray_wiring(repo, name, manifest):
    """Commands this skill has wired that no declared hook accounts for.

    Needed because hook_rows lists only declared hooks: without this report, a
    hook dropped from the list stays wired and shows up nowhere.

    Looks only where set_hook(enable) rewrites, and skips the wiring of
    non-executable scripts, which enable deliberately keeps.
    """
    owner = hook_owner(repo, name)
    _, broken, plan = enable_plan(repo, name, manifest)
    strays = []
    for platform, wanted in plan.items():
        data, error = load_hook_config(platform)
        if error:
            continue
        # Each declared hook accounts for one wired command, so a duplicate is
        # a stray too.
        unclaimed = list(wanted)
        for event, matcher, command in wired_items(data):
            if not owns(command, owner) or any(
                identifies(wiring, event, matcher, command) for wiring in broken
            ):
                continue
            claim = next(
                (w for w in unclaimed if identifies(w, event, matcher, command)), None
            )
            if claim:
                unclaimed.remove(claim)
            else:
                strays.append(command)
    return strays


def hook_state(repo, name, manifest):
    """[(platform, state, detail), ...] across every hook the skill declares."""
    return [row[1:] for row in hook_rows(repo, name, manifest)]


def refuse_unparseable(label, error):
    """Print why a config file is left untouched. Every writer calls this, so
    the wording is the same everywhere."""
    print(f"{label}: {error}")
    print(f"{label}: refusing to rewrite a file it cannot parse")


def sweep_owned(repo, name, platforms, why, report=True):
    """Remove everything this skill has wired on `platforms`, and return how
    many config files changed.

    Needs no manifest: ownership is decided by the skill's directory (see
    hook_owner). With `report`, prints a message for each config it cannot
    parse."""
    owner = hook_owner(repo, name)
    changed = 0
    for platform in platforms:
        data, error = load_hook_config(platform)
        if error:
            if report:
                refuse_unparseable(f"  {name} [{platform.name} hook]", error)
            continue
        if drop_hook_entries(data, owner):
            try:
                save_hook_config(platform, data)
            except OSError as err:
                print(f"  {name} [{platform.name} hook]: could not write: {err}")
                continue
            print(f"  {name} [{platform.name} hook]: removed ({why})")
            changed += 1
    return changed


NO_MANIFEST = "no usable hook declared"


def set_hook(repo, name, manifest, enable, report_undeclared=False):
    """Wire every hook a skill declares into (or out of) the platforms it names.

    Removal is platform-blind, on purpose: `hook_present` reports an entry on any
    platform, so if removal only visited the platforms the manifest names *today*
    it would detect orphans it could not clear — and tell the user "not enabled"
    about a hook that is enabled. Writing stays scoped to the named platforms.

    Each platform's config is loaded once, swept of everything the skill owns,
    given every entry that names it (when enabling), and saved once. Doing it in
    one pass means several entries on one event are all wired, or all removed.
    """
    hooks = manifest_hooks(manifest)
    owner = hook_owner(repo, name)
    declared = {
        platform.name
        for hook in hooks
        for platform in HOOK_PLATFORMS
        if hook_wiring(repo, name, manifest, hook, platform)
    }

    swept_undeclared = 0
    if not enable:
        # Sweep everywhere first, including platforms this manifest has dropped.
        swept_undeclared = sweep_owned(
            repo,
            name,
            [p for p in HOOK_PLATFORMS if p.name not in declared],
            "platform no longer declared",
            # Stay quiet about an unparseable config on a platform the skill
            # doesn't name, except during uninstall, which must say what it may
            # have left behind.
            report=report_undeclared,
        )

    broken = []
    if enable:
        # A hook whose script is not executable is skipped, not fatal: the
        # other hooks are still wired, and the skipped hook's existing wiring
        # is left in place.
        usable, broken, plan = enable_plan(repo, name, manifest)
        for wiring in broken:
            print(f"  {name}: {wiring.script} is not executable; not enabling the hook")
        if not plan:
            return 0
    else:
        plan = {}
        for platform in HOOK_PLATFORMS:
            wanted = [
                wiring
                for wiring in (hook_wiring(repo, name, manifest, hook, platform) for hook in hooks)
                if wiring
            ]
            if wanted:
                plan[platform] = wanted

    changed = swept_undeclared
    for platform, wanted in plan.items():
        label = f"  {name} [{platform.name} hook]"

        data, error = load_hook_config(platform)
        if error and not wanted:
            # Nothing to wire here, so don't report a file that would only be
            # swept.
            continue
        if error:
            refuse_unparseable(label, error)
            continue

        present = [hook_installed(data, wiring) for wiring in wanted]
        # Always sweep first, whichever direction we are going. Enabling has to
        # clear a stale entry left under an event this skill used to hook, or the
        # config ends up wired twice; disabling has to clear it because nothing
        # else ever will.
        swept = drop_hook_entries(data, owner, keep=broken)

        if not wanted:
            # No usable hook names this platform: only a sweep can change it.
            if not swept:
                continue
            try:
                save_hook_config(platform, data)
            except OSError as err:
                print(f"{label}: could not write {hook_config_path(platform)}: {err}")
                continue
            print(f"{label}: removed (no usable hook names this platform)")
            changed += 1
            continue
        if enable and all(present) and not swept:
            print(f"{label}: already enabled")
            continue
        if not enable and not any(present) and not swept:
            print(f"{label}: not enabled")
            continue

        if enable:
            ok = all(
                [
                    add_hook_entry(
                        data,
                        platform,
                        wiring.event,
                        wiring.matcher,
                        wired_command(wiring.script, platform),
                    )
                    for wiring in wanted
                ]
            )
        else:
            ok = swept
        if not ok:
            print(f"{label}: unexpected shape in {hook_config_path(platform)}; skipped")
            continue

        try:
            save_hook_config(platform, data)
        except OSError as err:
            print(f"{label}: could not write {hook_config_path(platform)}: {err}")
            continue
        if enable:
            for wiring in wanted:
                print(f"{label}: enabled on {wiring.event}")
        else:
            events = list(dict.fromkeys(wiring.event for wiring in wanted))
            print(f"{label}: disabled on {', '.join(events)}")
        changed += 1
    return changed


def owned_wiring(repo, name):
    """Every command this skill has wired, in every config that parses."""
    owner = hook_owner(repo, name)
    found = []
    for platform in HOOK_PLATFORMS:
        data, error = load_hook_config(platform)
        if not error:
            found += [command for _, _, command in wired_items(data) if owns(command, owner)]
    return found


def hook_present(repo, name):
    """Is anything this skill wired up still in any config, under any event?

    Deliberately not `hook_state`: that inspects the events the manifest names
    *today*, so a hook left behind by an earlier manifest reads as absent. That
    is the question `uninstall` needs answered, and asking the narrower one left
    orphans firing for a skill that was no longer installed.
    """
    return bool(owned_wiring(repo, name))


def hooked_skills(repo):
    """[(name, manifest), ...] for every skill in the clone that ships a hook."""
    found = []
    for name in available(repo):
        manifest = read_hook_manifest(repo, name)
        if manifest:
            found.append((name, manifest))
    return found


def install_manager(repo):
    """Copy (not symlink) this skill into every target.

    Each target's new copy is built beside it and swapped in only when complete,
    so a failed copy leaves the previous one in place."""
    source = repo / SKILLS_SUBDIR / MANAGER
    if not (source / "SKILL.md").is_file():
        sys.exit(f"{repo} has no {MANAGER}; every installed copy is left as it is.")
    for target in TARGETS:
        dest = target.path / MANAGER
        target.path.mkdir(parents=True, exist_ok=True)
        staging = pathlib.Path(tempfile.mkdtemp(prefix=f".{MANAGER}-", dir=target.path))
        fresh = staging / MANAGER
        previous = staging / "previous"
        try:
            try:
                shutil.copytree(
                    source, fresh, ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
                )
            except OSError as err:
                sys.exit(
                    f"Could not copy {MANAGER} into {target.path}: {err}\n"
                    f"The {MANAGER} already there is left as it was."
                )
            if dest.is_symlink() or dest.exists():
                os.rename(dest, previous)
            os.rename(fresh, dest)
        finally:
            # Whatever stopped the swap, put the previous copy back before
            # the staging directory, which holds it, is deleted.
            if not (dest.is_symlink() or dest.exists()) and (
                previous.is_symlink() or previous.exists()
            ):
                os.rename(previous, dest)
            shutil.rmtree(staging, ignore_errors=True)


def cmd_bootstrap(args):
    repo = infer_repo_from_script() or find_repo()
    save_repo(repo)
    install_manager(repo)
    print(f"Recorded clone {repo}. Installed {MANAGER} into:")
    for target in TARGETS:
        print(f"  {target.path}")
    print("\nNext: open a new agent tab, then ask the agent to install the")
    print("skills you want.")


def cell(repo, name, target, belongs):
    """A name's state in one target, for `list`: `n/a` where the name does not
    belong and nothing is there, otherwise the real state, so `list` shows
    whatever `doctor` reports on."""
    state = status(repo, name, target)
    return NOT_HERE if target not in belongs and state == ABSENT else state


def cmd_list(args):
    repo = find_repo()
    names = available(repo)
    width = max((len(n) for n in names), default=10)
    print_header(repo)

    columns = "  ".join(f"{target.label:<{LABEL_WIDTH}}" for target in TARGETS)
    print(f"  {columns}  {'skill':<{width}}  what it does")

    gaps = []
    for name in names:
        belongs = targets_for(repo, name)
        states = [(target, state) for target, state in statuses(repo, name) if target in belongs]
        cells = "  ".join(
            f"{MARKERS[cell(repo, name, target, belongs)]:<{LABEL_WIDTH}}"
            for target in TARGETS
        )
        summary = describe(repo, name)
        if len(summary) > 60:
            summary = summary[:59].rstrip() + "…"
        print(f"  {cells}  {name:<{width}}  {summary}")
        present = [state for _, state in states if state in PRESENT]
        if present and len(present) != len(states):
            gaps.append(name)

    print(f"\n{MANAGER} is a copy by design; everything else is a symlink.")
    if any(is_mod(repo, name) for name in names):
        print("A mod runs only in Claude Code, so it is linked only where Claude Code loads it (n/a elsewhere).")

    for name, manifest in hooked_skills(repo):
        states = hook_state(repo, name, manifest)
        on = list(
            dict.fromkeys(
                platform.name for platform, state, _ in states if state == HOOK_ENABLED
            )
        )
        print(
            f"Hook: {name} — "
            + (f"enabled ({', '.join(on)})" if on else "available, not enabled")
            + "   see 'hooks'"
        )

    if gaps:
        print("Installed in some targets but not all: " + ", ".join(gaps))
        linkable = [name for name in gaps if name != MANAGER]
        if linkable:
            print("  fix: install " + " ".join(linkable))
        if MANAGER in gaps:
            print(f"  fix: update   (re-copies {MANAGER} into every target)")


def auto_enable_hooks(repo, names, skip):
    """Wire up hooks for freshly installed skills that ask for it by default.

    Sandboxes (SHARED_SKILLS_TARGET without SHARED_SKILLS_HOOK_HOME) are left
    alone: a throwaway install should never touch real agent config files.
    """
    if skip:
        return 0
    if os.environ.get(TARGET_ENV, "").strip() and not os.environ.get(HOOK_HOME_ENV, "").strip():
        return 0

    changed = 0
    for name in names:
        manifest = read_hook_manifest(repo, name)
        if not manifest:
            # A hook.json that loads no hook leaves nothing to wire, so what the
            # skill wired before is only leftover.
            if (repo / SKILLS_SUBDIR / name / HOOK_MANIFEST).is_file() and hook_present(repo, name):
                changed += sweep_owned(repo, name, HOOK_PLATFORMS, NO_MANIFEST)
            continue
        if manifest.get("default") != HOOK_ENABLED:
            continue
        if opted_out_of_hook(name):
            print()
            print(f"{name} ships a hook, but you turned it off — leaving it off.")
            print(f"  re-enable with:  skills.py enable-hook {name}")
            continue
        # Check only hooks whose script is executable. A broken hook that isn't
        # wired stays off (enable never wires it); without this filter, every
        # install would rewrite the config. If none is executable, keep every
        # row, so set_hook runs and says why.
        rows = hook_rows(repo, name, manifest)
        live = [
            hook
            for hook in manifest_hooks(manifest)
            if os.access(hook_script(repo, name, hook), os.X_OK)
        ]
        if live:
            rows = [row for row in rows if any(row[0] is hook for hook in live)]
        # List form: a hook dropped from the list may still be wired; set_hook
        # sweeps it.
        if all(state != HOOK_OFF for _, _, state, _ in rows) and not (
            "hooks" in manifest and stray_wiring(repo, name, manifest)
        ):
            continue
        print()
        print(f"{name} ships a hook, enabled by default:")
        for hook in manifest_hooks(manifest):
            summary = hook.get("summary")
            if summary:
                print(f"  {summary}")
        changed += set_hook(repo, name, manifest, enable=True)
        print(f"  turn it off with:  skills.py disable-hook {name}")
    return changed


def cmd_install(args):
    repo = find_repo()
    names = available(repo) if args.all_skills else args.names
    if not names:
        sys.exit("Name at least one skill, or pass --all. See 'list' for what exists.")
    print("Installing into:")
    for target in TARGETS:
        print(f"  {target.label:<{LABEL_WIDTH}}  {target.path}")
    print()
    changed = sum(install_one(repo, name, args.force) for name in names)
    changed += auto_enable_hooks(repo, names, args.no_hook)
    print(f"\n{changed} change(s). Open a new agent tab to pick them up.")


def cmd_uninstall(args):
    repo = find_repo()
    if not args.names:
        sys.exit("Name at least one skill to remove.")
    print("Removing from:")
    for target in TARGETS:
        print(f"  {target.label:<{LABEL_WIDTH}}  {target.path}")
    print()
    changed = sum(uninstall_one(repo, name) for name in args.names)
    # A hook left pointing at an uninstalled skill would fire on every commit
    # for no reason, so take it out with the skill.
    unseen = []
    for name in args.names:
        manifest = read_hook_manifest(repo, name)
        if not hook_present(repo, name):
            unseen.append(name)
            continue
        if manifest:
            changed += set_hook(repo, name, manifest, enable=False, report_undeclared=True)
        else:
            changed += sweep_owned(repo, name, HOOK_PLATFORMS, NO_MANIFEST)
    if unseen:
        # A config that cannot be parsed may still hold these skills' hooks.
        # Print one message per such file, naming all of them.
        for platform in HOOK_PLATFORMS:
            _, error = load_hook_config(platform)
            if error:
                refuse_unparseable(f"  {', '.join(unseen)} [{platform.name} hook]", error)
    print(f"\n{changed} change(s). Open a new agent tab to pick them up.")


def cmd_enable_hook(args):
    repo = find_repo()
    if not args.names:
        sys.exit("Name at least one skill. See 'hooks' for which ones ship one.")
    changed = 0
    for name in args.names:
        manifest = read_hook_manifest(repo, name)
        if not manifest:
            # No manifest loads. Wiring can outlive a deleted or broken
            # hook.json, and removal doesn't need a manifest, so disable still
            # sweeps. A hook.json that exists but won't load still counts as a
            # hook: record the choice either way, so it applies once the file
            # loads again.
            broken = (repo / SKILLS_SUBDIR / name / HOOK_MANIFEST).is_file()
            if broken:
                # Nothing loads to wire, so whatever is wired is leftover, in
                # either direction.
                changed += sweep_owned(repo, name, HOOK_PLATFORMS, NO_MANIFEST)
                set_hook_opt_out(name, not args.enable)
                if args.enable:
                    print(
                        f"  {name}: opt-out cleared; once {HOOK_MANIFEST} declares a usable hook,"
                        " install wires it if its default is enabled, else run enable-hook again"
                    )
                else:
                    print(
                        f"  {name}: hook turned off; it stays off once {HOOK_MANIFEST}"
                        " declares a usable hook"
                    )
                continue
            if args.enable and opted_out_of_hook(name):
                # Undoes a disable made while hook.json was missing.
                set_hook_opt_out(name, False)
            if args.enable or not hook_present(repo, name):
                print(f"  {name}: ships no hook")
                continue
            changed += sweep_owned(repo, name, HOOK_PLATFORMS, NO_MANIFEST)
            set_hook_opt_out(name, True)
            continue
        changed += set_hook(repo, name, manifest, enable=args.enable)
        # Remember the choice, so a later install doesn't undo it.
        set_hook_opt_out(name, not args.enable)
    print(f"\n{changed} change(s).")
    if changed and args.enable:
        print("Restart Cursor to pick up hooks.json; Claude Code reads settings.json")
        print("on the next session.")


def cmd_hooks(args):
    repo = find_repo()
    print(f"Clone:  {repo}")
    print("Hook config files:")
    for platform in HOOK_PLATFORMS:
        path = hook_config_path(platform)
        print(f"  {platform.name:<8}  {path}{'' if path.is_file() else '  (none yet)'}")
    print()

    hooked = hooked_skills(repo)
    if not hooked:
        print("No skill in this clone ships a hook.")
        return

    for name, manifest in hooked:
        default = manifest.get("default", HOOK_OFF)
        print(f"{name}  (default: {default})")
        rows = hook_rows(repo, name, manifest)
        for hook in manifest_hooks(manifest):
            summary = hook.get("summary")
            if summary:
                print(f"  {summary}")
            for owner, platform, state, detail in rows:
                if owner is hook:
                    print(f"  {platform.name:<8}  {state:<10}  {detail}")
        print(f"  enable-hook {name} / disable-hook {name}")
        print()


def loads_here(repo, name, target):
    """Does `name` belong in `target`? Also true when `target` is the same
    directory as one it belongs in (~/.agents/skills linked to ~/.claude/skills),
    so doctor never advises removing the one link that works."""
    belongs = targets_for(repo, name)
    return target in belongs or any(same_dir(target.path, other.path) for other in belongs)


def same_dir(a, b):
    """Are `a` and `b` the same directory? False when either is missing, so one
    target not created yet cannot hide a match with another."""
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def check_target(repo, target, known):
    """Report on one target directory. Returns a list of problem lines."""
    lines = []

    if not target.path.is_dir():
        lines.append(("note", "EMPTY      directory does not exist yet — nothing installed here"))
    else:
        for entry in sorted(target.path.iterdir()):
            name = entry.name
            if name in known:
                state = status(repo, name, target)
                if not loads_here(repo, name, target):
                    # A mod in a target that cannot load it. install skips this
                    # target, so install --force would not clear it.
                    lines.append(
                        ("problem", f"NOT HERE   {name}: a Claude Code mod; nothing loads it from here")
                    )
                    remove = "rm" if entry.is_symlink() else "rm -r"
                    lines.append(("cont", f"           fix: {remove} {entry}"))
                elif state == BROKEN:
                    lines.append(
                        ("problem", f"BROKEN     {name}: points at something missing")
                    )
                    lines.append(("cont", f"           fix: install --force {name}"))
                elif state == FOREIGN:
                    lines.append(
                        (
                            "problem",
                            f"OTHER      {name}: links outside this clone, "
                            f"to {os.readlink(entry)}",
                        )
                    )
                    lines.append(("cont", f"           fix: install --force {name}"))
                elif state == COPY and name != MANAGER:
                    lines.append(
                        (
                            "problem",
                            f"COPY       {name}: real directory, so git pull "
                            "won't update it",
                        )
                    )
                    lines.append(("cont", f"           fix: install --force {name}"))
            elif entry.is_symlink() and not entry.exists():
                lines.append(
                    (
                        "problem",
                        f"BROKEN     {name}: dangling symlink, not a skill from this clone",
                    )
                )
                lines.append(("cont", f"           fix: rm {entry}"))

    # A skill installed in one target but missing from another is invisible to
    # whichever agent reads that target — the most likely reason a skill that
    # "is installed" still isn't found.
    others = [other for other in TARGETS if other.path != target.path]
    for name in sorted(known):
        if target not in targets_for(repo, name):
            continue
        if status(repo, name, target) != ABSENT:
            continue
        if any(status(repo, name, other) in PRESENT for other in others):
            lines.append(
                (
                    "problem",
                    f"MISSING    {name}: installed in another target but not here",
                )
            )
            fix = "update" if name == MANAGER else f"install {name}"
            lines.append(("cont", f"           fix: {fix}"))

    return lines


def cmd_doctor(args):
    repo = find_repo()
    print_header(repo)

    known = set(available(repo))
    problems = 0
    for target in TARGETS:
        print(f"{target.label}  ({target.path})")
        lines = check_target(repo, target, known)
        problems += sum(1 for kind, _ in lines if kind == "problem")
        if not lines:
            print("  No problems found.")
        for _, text in lines:
            print(f"  {text}")
        print()

    hooked = hooked_skills(repo)
    loaded = {name for name, _ in hooked}
    for name in sorted(known - loaded):
        if not (repo / SKILLS_SUBDIR / name / HOOK_MANIFEST).is_file():
            continue
        leftover = owned_wiring(repo, name)
        if not leftover:
            continue
        # Both commands remove it; advise the one that keeps the opt-out as it is.
        remover = "disable-hook" if opted_out_of_hook(name) else "enable-hook"
        print(f"{name} hook")
        for command in leftover:
            problems += 1
            print(f"  STRAY      wired, but its {HOOK_MANIFEST} loads no hook: {command}")
            print(f"             fix: correct {HOOK_MANIFEST}, or {remover} {name} to remove it")
        print()

    for name, manifest in hooked:
        rows = hook_rows(repo, name, manifest)
        on = [platform for _, platform, state, _ in rows if state == HOOK_ENABLED]
        print(f"{name} hook")
        unreadable = set()
        for _, platform, state, detail in rows:
            if state == "unreadable":
                # Several hooks can share one unreadable file; report it once.
                if platform.name in unreadable:
                    continue
                unreadable.add(platform.name)
                problems += 1
                print(f"  UNREADABLE {platform.name}: {detail}")
                print(f"             fix: repair or delete that file, then enable-hook {name}")
            else:
                print(f"  {state:<10} {platform.name}  ({detail})")
        # Report a broken script wherever it is wired, not only where the
        # manifest declares it: enable leaves a broken hook's old wiring in
        # place. One report per script.
        configs = [load_hook_config(platform) for platform in HOOK_PLATFORMS]
        broken = {}
        for hook in manifest_hooks(manifest):
            wiring = hook_wiring(repo, name, manifest, hook)
            if not os.access(wiring.script, os.X_OK):
                broken.setdefault(wiring.script, wiring)
        for script, wiring in broken.items():
            if any(
                hook_installed(data, wiring) for data, error in configs if not error
            ):
                problems += 1
                print(f"  BROKEN     hook script missing or not executable: {script}")
                print(f"             it fails open, so commits are not being checked")
                print(f"             fix: chmod +x {script}")
        if "hooks" in manifest:
            for command in stray_wiring(repo, name, manifest):
                problems += 1
                print(f"  STRAY      wired, but no declared hook accounts for it: {command}")
                print(f"             fix: enable-hook {name}   (or disable-hook {name})")
        if on and any(status(repo, name, t) == ABSENT for t in targets_for(repo, name)):
            problems += 1
            print(f"  ORPHAN     hook is enabled but {name} is not installed everywhere")
            print(f"             fix: install {name}   (or disable-hook {name})")
        print()

    if problems:
        print(f"{problems} problem(s); each line above says how to fix it.")
    else:
        print("No problems found in any target.")


def manager_source(repo):
    """(clone to refresh manage-skills from, or None; why not).

    Only the clone bootstrap recorded supplies manage-skills. SHARED_SKILLS_REPO
    may name a second skills repository, whose manage-skills is someone else's
    copy, or missing."""
    if not os.environ.get("SHARED_SKILLS_REPO", "").strip():
        # find_repo already chose the recorded clone, or before bootstrap, the
        # clone this script lives in.
        return repo, None
    stored = load_config().get("repo")
    if not stored or not isinstance(stored, str):
        return None, (
            "bootstrap has not recorded a clone, so update can't tell which\n"
            "clone it comes from. Run bootstrap from that clone first."
        )
    recorded = pathlib.Path(stored).expanduser()
    # The same test locate_repo applies to the recorded clone.
    if not (recorded / SKILLS_SUBDIR).is_dir():
        return None, (
            f"the clone recorded in {CONFIG_FILE} is missing:\n  {recorded}\n"
            "Move the clone back, or re-run bootstrap from its new location."
        )
    if os.path.samefile(recorded, repo):
        return repo, None
    return None, (
        f"it comes only from the clone bootstrap recorded ({recorded}).\n"
        "Run update without SHARED_SKILLS_REPO to refresh it."
    )


def cmd_update(args):
    repo = find_repo()
    print(f"Pulling {repo} ...")
    result = subprocess.run(
        ["git", "-C", str(repo), "pull", "--ff-only"], capture_output=True, text=True
    )
    sys.stdout.write(result.stdout)
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        sys.exit("git pull failed; resolve it in the clone and try again.")
    source, why_not = manager_source(repo)
    if source:
        install_manager(source)
        print(f"Refreshed {MANAGER} in every target.")
    else:
        print(f"Left {MANAGER} as it is: {why_not}")
    print("Symlinked skills track the clone automatically. Open a new agent tab")
    print("to pick up changes.")


def main():
    parser = argparse.ArgumentParser(
        prog="skills.py", description="Install shared skills as symlinks."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("bootstrap", help="First-time setup; run from inside the clone")
    sub.add_parser("list", help="Show every skill and where it is installed")
    sub.add_parser("doctor", help="Report broken, foreign, missing, or stale installs")
    sub.add_parser("update", help="git pull the clone and refresh this manager")
    sub.add_parser("hooks", help="Show which skills ship hooks, and their state")

    add = sub.add_parser("install", help="Symlink one or more skills into every target")
    add.add_argument("names", nargs="*")
    add.add_argument("--all", dest="all_skills", action="store_true", help="Install everything")
    add.add_argument("--force", action="store_true", help="Replace what's already there")
    add.add_argument(
        "--no-hook",
        action="store_true",
        help="Install without wiring up hooks the skill enables by default",
    )

    remove = sub.add_parser("uninstall", help="Remove one or more symlinked skills")
    remove.add_argument("names", nargs="*")

    on = sub.add_parser("enable-hook", help="Wire a skill's hook into every platform")
    on.add_argument("names", nargs="*")
    on.set_defaults(enable=True)

    off = sub.add_parser("disable-hook", help="Remove a skill's hook from every platform")
    off.add_argument("names", nargs="*")
    off.set_defaults(enable=False)

    args = parser.parse_args()
    if getattr(args, "names", None):
        # Tab completion adds a slash to a directory name.
        args.names = [name.rstrip("/") or name for name in args.names]
    for name in getattr(args, "names", None) or []:
        # A skill name must be a single directory under the skills folder.
        # Without this check, hook_owner could be a prefix of other skills'
        # wiring, and removing this skill's hooks would remove theirs too.
        if name in ("", ".", "..") or "/" in name or os.sep in name:
            sys.exit(f"not a skill name: {name!r}")
    if getattr(args, "names", None):
        repo = find_repo(required=False)
        if repo:
            args.names = [skill_dir_name(repo, name) for name in args.names]
    {
        "bootstrap": cmd_bootstrap,
        "list": cmd_list,
        "install": cmd_install,
        "uninstall": cmd_uninstall,
        "doctor": cmd_doctor,
        "update": cmd_update,
        "hooks": cmd_hooks,
        "enable-hook": cmd_enable_hook,
        "disable-hook": cmd_enable_hook,
    }[args.command](args)


if __name__ == "__main__":
    main()
