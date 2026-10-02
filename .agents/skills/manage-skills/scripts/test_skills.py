#!/usr/bin/env python3
"""Regression tests for skills.py, focused on the hook wiring.

Standard library only, no fixtures to install:

    python3 test_skills.py

Every test runs skills.py as a subprocess against a throwaway clone, target
directory, hook home and config file, so nothing here can touch a real
~/.claude/settings.json, ~/.cursor/hooks.json or installed skill. The skill
under test is a synthetic one built in the temp directory — these tests cover
the manager, not any particular skill that happens to ship a hook.
"""

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parent / "skills.py"

SKILL = "demo-hooked"

CLAUDE_REL = pathlib.Path(".claude") / "settings.json"
CURSOR_REL = pathlib.Path(".cursor") / "hooks.json"

FOREIGN_HOOK = "/somebody/elses/hook.sh"


class HookTests(unittest.TestCase):
    def setUp(self):
        # resolve(): on macOS the temp root is itself a symlink (/var ->
        # /private/var), and skills.py stores resolved absolute paths. Comparing
        # an unresolved path against a resolved one silently never matches.
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="skills-test-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        self.clone = self.tmp / "clone"
        self.skill_dir = self.clone / ".agents" / "skills" / SKILL
        (self.skill_dir / "scripts").mkdir(parents=True)
        (self.skill_dir / "SKILL.md").write_text(
            "---\nname: demo-hooked\ndescription: A skill that ships a hook.\n---\n"
        )
        self.hook_sh = self.skill_dir / "scripts" / "demo.sh"
        self.hook_sh.write_text("#!/bin/sh\nexit 0\n")
        self.hook_sh.chmod(0o755)
        self.write_manifest(default="enabled")

        self.home = self.tmp / "home"
        self.targets = self.tmp / "targets"
        self.config = self.tmp / "config.json"
        self.home.mkdir()
        self.targets.mkdir()

    # -- helpers ----------------------------------------------------------

    def write_manifest(
        self, default="enabled", claude_event="PreToolUse", command="scripts/demo.sh",
        cursor_event="beforeShellExecution",
    ):
        (self.skill_dir / "hook.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "summary": "Demo hook.",
                    "command": command,
                    "default": default,
                    "events": {
                        "claude": {"event": claude_event, "matcher": "Bash"},
                        "cursor": {
                            "event": cursor_event,
                            "matcher": "git commit",
                        },
                    },
                }
            )
        )

    def run_cli(self, *args, hook_home=True):
        env = dict(os.environ)
        env["SHARED_SKILLS_REPO"] = str(self.clone)
        env["SHARED_SKILLS_TARGET"] = str(self.targets)
        env["SHARED_SKILLS_CONFIG"] = str(self.config)
        if hook_home:
            env["SHARED_SKILLS_HOOK_HOME"] = str(self.home)
        else:
            env.pop("SHARED_SKILLS_HOOK_HOME", None)
        result = subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def read(self, relpath):
        path = self.home / relpath
        return json.loads(path.read_text()) if path.is_file() else None

    def write(self, relpath, data):
        path = self.home / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data) if not isinstance(data, str) else data)

    def claude_entries(self):
        data = self.read(CLAUDE_REL) or {}
        return data.get("hooks", {}).get("PreToolUse", [])

    def cursor_entries(self):
        data = self.read(CURSOR_REL) or {}
        return data.get("hooks", {}).get("beforeShellExecution", [])

    def ours(self, entries):
        """Entries in either shape that point at our hook script."""
        found = []
        for entry in entries:
            if str(self.hook_sh) in str(entry.get("command", "")):
                found.append(entry)
            for inner in entry.get("hooks", []) or []:
                if str(self.hook_sh) in str(inner.get("command", "")):
                    found.append(inner)
        return found

    # -- install wiring ---------------------------------------------------

    def test_install_enables_hook_on_every_platform(self):
        self.run_cli("install", SKILL)

        claude = self.ours(self.claude_entries())
        self.assertEqual(len(claude), 1)
        self.assertEqual(claude[0]["type"], "command")
        self.assertIn("--host claude", claude[0]["command"])
        self.assertEqual(self.claude_entries()[0]["matcher"], "Bash")

        cursor = self.ours(self.cursor_entries())
        self.assertEqual(len(cursor), 1)
        self.assertIn("--host cursor", cursor[0]["command"])
        self.assertEqual(cursor[0]["matcher"], "git commit")
        # Cursor requires a schema version on the file.
        self.assertEqual(self.read(CURSOR_REL)["version"], 1)

    def test_hook_command_is_absolute(self):
        self.run_cli("install", SKILL)
        command = self.ours(self.claude_entries())[0]["command"]
        self.assertTrue(command.startswith(("/", '"/')), command)

    def test_install_preserves_unrelated_config(self):
        self.write(
            CLAUDE_REL,
            {
                "permissions": {"allow": ["Bash(ls:*)"]},
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Write",
                            "hooks": [{"type": "command", "command": FOREIGN_HOOK}],
                        }
                    ]
                },
            },
        )
        self.run_cli("install", SKILL)

        data = self.read(CLAUDE_REL)
        self.assertEqual(data["permissions"], {"allow": ["Bash(ls:*)"]})
        commands = [
            inner["command"]
            for entry in data["hooks"]["PreToolUse"]
            for inner in entry["hooks"]
        ]
        self.assertIn(FOREIGN_HOOK, commands)

    def test_enable_is_idempotent(self):
        self.run_cli("install", SKILL)
        self.run_cli("enable-hook", SKILL)
        self.run_cli("install", SKILL)
        self.assertEqual(len(self.ours(self.claude_entries())), 1)
        self.assertEqual(len(self.ours(self.cursor_entries())), 1)

    def test_default_off_is_not_wired_on_install(self):
        self.write_manifest(default="off")
        self.run_cli("install", SKILL)
        self.assertEqual(self.read(CLAUDE_REL), None)
        self.assertEqual(self.ours(self.cursor_entries()), [])

    def test_non_executable_script_is_not_wired(self):
        self.hook_sh.chmod(0o644)
        output = self.run_cli("enable-hook", SKILL)
        self.assertIn("not executable", output)
        self.assertEqual(self.read(CLAUDE_REL), None)

    def test_sandbox_install_does_not_touch_real_hook_configs(self):
        # No SHARED_SKILLS_HOOK_HOME means the paths would resolve under the
        # real $HOME, so auto-enable has to stay out of it entirely.
        output = self.run_cli("install", SKILL, hook_home=False)
        self.assertNotIn("ships a hook", output)

    # -- disable ----------------------------------------------------------

    def test_disable_removes_only_our_entries(self):
        self.write(
            CLAUDE_REL,
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Write",
                            "hooks": [{"type": "command", "command": FOREIGN_HOOK}],
                        }
                    ]
                }
            },
        )
        self.run_cli("install", SKILL)
        self.run_cli("disable-hook", SKILL)

        self.assertEqual(self.ours(self.claude_entries()), [])
        remaining = [
            inner["command"]
            for entry in self.claude_entries()
            for inner in entry["hooks"]
        ]
        self.assertEqual(remaining, [FOREIGN_HOOK])

    def test_disable_drops_the_event_key_when_nothing_is_left(self):
        self.run_cli("install", SKILL)
        self.run_cli("disable-hook", SKILL)
        self.assertNotIn("beforeShellExecution", self.read(CURSOR_REL).get("hooks", {}))

    def test_disable_recognises_an_entry_written_without_arguments(self):
        # Older versions wired the bare script path. It still has to be found.
        self.write(
            CURSOR_REL,
            {
                "version": 1,
                "hooks": {"beforeShellExecution": [{"command": str(self.hook_sh)}]},
            },
        )
        self.run_cli("disable-hook", SKILL)
        self.assertEqual(self.ours(self.cursor_entries()), [])

    def test_changing_the_hooked_event_leaves_nothing_behind(self):
        # A skill that moves from one event to another still owns what it wired
        # up under the old one. Orphaned there, it points at a script that may no
        # longer exist and errors on every command in every session.
        self.run_cli("install", SKILL)
        self.assertEqual(len(self.ours(self.claude_entries())), 1)

        self.write_manifest(default="enabled", claude_event="PostToolUse")
        self.run_cli("enable-hook", SKILL)

        data = self.read(CLAUDE_REL)
        self.assertEqual(self.ours(data["hooks"].get("PreToolUse", [])), [])
        self.assertEqual(len(self.ours(data["hooks"]["PostToolUse"])), 1)

    def test_disabling_after_an_event_change_clears_the_old_entry(self):
        self.run_cli("install", SKILL)
        self.write_manifest(default="enabled", claude_event="PostToolUse")
        self.run_cli("disable-hook", SKILL)

        data = self.read(CLAUDE_REL) or {}
        for entries in data.get("hooks", {}).values():
            self.assertEqual(self.ours(entries), [])

    def test_a_renamed_hook_script_is_still_recognised_as_ours(self):
        self.run_cli("install", SKILL)
        renamed = self.skill_dir / "scripts" / "renamed.sh"
        self.hook_sh.rename(renamed)
        self.hook_sh = renamed
        self.write_manifest(default="enabled", command="scripts/renamed.sh")

        self.run_cli("disable-hook", SKILL)
        data = self.read(CLAUDE_REL) or {}
        self.assertEqual(json.dumps(data).count("demo-hooked"), 0)

    def test_uninstall_removes_a_hook_left_under_an_old_event(self):
        # cmd_uninstall gated on hook_state, which only inspects the manifest's
        # *current* events — the pre-sweep predicate. An entry left under a
        # previous event reported OFF everywhere, so nothing removed it and it
        # kept firing after the skill was gone.
        self.run_cli("install", SKILL)
        # Both events must move: an unchanged one keeps the guard true, and the
        # sweep then cleans the orphan by accident rather than by design.
        self.write_manifest(default="enabled", claude_event="PostToolUse",
                            cursor_event="postToolUse")
        self.run_cli("uninstall", SKILL)

        for rel in (CLAUDE_REL, CURSOR_REL):
            data = self.read(rel) or {}
            for entries in data.get("hooks", {}).values():
                self.assertEqual(self.ours(entries), [], f"orphan left in {rel}")

    def test_uninstall_removes_a_hook_on_a_platform_the_manifest_dropped(self):
        # hook_present scans every platform; set_hook iterated hook_state, which
        # skips platforms the manifest no longer names. So uninstall detected an
        # orphan it could not remove, and told the user "not enabled" about a
        # hook that was very much enabled.
        self.run_cli("install", SKILL)
        manifest = json.loads((self.skill_dir / "hook.json").read_text())
        del manifest["events"]["cursor"]           # platform dropped
        (self.skill_dir / "hook.json").write_text(json.dumps(manifest))

        self.run_cli("uninstall", SKILL)
        data = self.read(CURSOR_REL) or {}
        for entries in data.get("hooks", {}).values():
            self.assertEqual(self.ours(entries), [], "orphan left on dropped platform")

    def test_uninstall_takes_the_hook_with_it(self):
        self.run_cli("install", SKILL)
        self.run_cli("uninstall", SKILL)
        self.assertEqual(self.ours(self.claude_entries()), [])
        self.assertEqual(self.ours(self.cursor_entries()), [])

    # -- the opt-out sticks -----------------------------------------------

    def test_install_does_not_undo_a_deliberate_disable(self):
        self.run_cli("install", SKILL)
        self.run_cli("disable-hook", SKILL)
        output = self.run_cli("install", SKILL)
        self.assertIn("you turned it off", output)
        self.assertEqual(self.ours(self.claude_entries()), [])

    def test_enable_clears_the_opt_out(self):
        self.run_cli("disable-hook", SKILL)
        self.run_cli("enable-hook", SKILL)
        self.assertEqual(json.loads(self.config.read_text()).get("hooks_off"), None)
        self.assertEqual(len(self.ours(self.claude_entries())), 1)

    def test_opt_out_preserves_the_recorded_clone(self):
        self.config.write_text(json.dumps({"repo": str(self.clone)}))
        self.run_cli("disable-hook", SKILL)
        config = json.loads(self.config.read_text())
        self.assertEqual(config["repo"], str(self.clone))
        self.assertEqual(config["hooks_off"], [SKILL])

    # -- damaged config ---------------------------------------------------

    def test_unparseable_config_is_refused_not_clobbered(self):
        broken = '{ "permissions": {},,, BROKEN'
        self.write(CLAUDE_REL, broken)
        output = self.run_cli("enable-hook", SKILL)

        self.assertIn("refusing to rewrite", output)
        self.assertEqual((self.home / CLAUDE_REL).read_text(), broken)
        # The platform it *could* reach is still wired up.
        self.assertEqual(len(self.ours(self.cursor_entries())), 1)

    def test_doctor_reports_an_unparseable_config_as_a_problem(self):
        self.write(CLAUDE_REL, "{ not json")
        output = self.run_cli("doctor")
        self.assertIn("UNREADABLE", output)
        self.assertIn("problem(s)", output)

    def test_doctor_flags_a_hook_whose_script_lost_its_exec_bit(self):
        self.run_cli("install", SKILL)
        self.hook_sh.chmod(0o644)
        output = self.run_cli("doctor")
        self.assertIn("BROKEN", output)
        self.assertIn("fails open", output)

    def test_first_write_keeps_a_backup_of_the_original(self):
        self.write(CLAUDE_REL, {"permissions": {"allow": []}})
        self.run_cli("install", SKILL)
        backup = self.home / CLAUDE_REL
        backup = backup.with_suffix(backup.suffix + ".shared-skills.bak")
        self.assertTrue(backup.is_file())
        self.assertEqual(json.loads(backup.read_text()), {"permissions": {"allow": []}})

    # -- reporting --------------------------------------------------------

    def test_hooks_command_reports_state_per_platform(self):
        self.run_cli("install", SKILL)
        output = self.run_cli("hooks")
        self.assertIn(SKILL, output)
        # Skip the "hook config files" preamble, whose lines also start with a
        # platform name, and read only this skill's own state rows.
        section = output.split(f"{SKILL}  (default")[1]
        for platform in ("claude", "cursor"):
            rows = [
                line
                for line in section.splitlines()
                if line.strip().startswith(platform)
            ]
            self.assertEqual(len(rows), 1, section)
            self.assertIn("enabled", rows[0])

    def test_list_mentions_the_hook(self):
        self.run_cli("install", SKILL)
        self.assertIn(f"Hook: {SKILL}", self.run_cli("list"))

    # -- several hooks in one manifest ------------------------------------

    MCP_MATCHER = "mcp__linear__save_comment|mcp__linear__save_issue"

    def add_script(self, filename):
        script = self.skill_dir / "scripts" / filename
        script.write_text("#!/bin/sh\nexit 0\n")
        script.chmod(0o755)
        return script

    def write_hook_list(self, hooks, default="enabled", **extra):
        (self.skill_dir / "hook.json").write_text(
            json.dumps({"version": 1, "default": default, "hooks": hooks, **extra})
        )

    def write_prose_like_manifest(self):
        """Three hooks, two of them sharing claude's PreToolUse."""
        self.post_sh = self.add_script("post.sh")
        self.pre_sh = self.add_script("pre.sh")
        self.write_hook_list(
            [
                {
                    "summary": "Commit check.",
                    "command": "scripts/demo.sh",
                    "events": {
                        "claude": {"event": "PostToolUse", "matcher": "Bash"},
                        "cursor": {"event": "postToolUse", "matcher": "Shell"},
                    },
                },
                {
                    "summary": "Pre-post check.",
                    "command": "scripts/post.sh",
                    "events": {
                        "claude": {"event": "PreToolUse", "matcher": self.MCP_MATCHER},
                    },
                },
                {
                    "summary": "Pre-shell check.",
                    "command": "scripts/pre.sh",
                    "events": {
                        "claude": {"event": "PreToolUse", "matcher": "Bash"},
                        "cursor": {"event": "beforeShellExecution", "matcher": "git"},
                    },
                },
            ]
        )

    def wired(self, relpath, event, script):
        """[(matcher, command)] for every entry under `event` running `script`."""
        data = self.read(relpath) or {}
        found = []
        for entry in data.get("hooks", {}).get(event, []):
            commands = [entry.get("command", "")] + [
                inner.get("command", "") for inner in entry.get("hooks", []) or []
            ]
            for command in commands:
                if str(script) in command:
                    found.append((entry.get("matcher"), command))
        return found

    def assert_nothing_of_ours(self):
        for rel in (CLAUDE_REL, CURSOR_REL):
            text = json.dumps(self.read(rel) or {})
            self.assertNotIn(str(self.skill_dir), text, f"left behind in {rel}")

    def test_list_form_wires_every_entry_on_every_declared_platform(self):
        self.write_prose_like_manifest()
        self.run_cli("install", SKILL)

        self.assertEqual(
            [m for m, _ in self.wired(CLAUDE_REL, "PostToolUse", self.hook_sh)], ["Bash"]
        )
        self.assertEqual(
            [m for m, _ in self.wired(CLAUDE_REL, "PreToolUse", self.post_sh)],
            [self.MCP_MATCHER],
        )
        self.assertEqual(
            [m for m, _ in self.wired(CLAUDE_REL, "PreToolUse", self.pre_sh)], ["Bash"]
        )
        self.assertEqual(
            [m for m, _ in self.wired(CURSOR_REL, "postToolUse", self.hook_sh)], ["Shell"]
        )
        self.assertEqual(
            [m for m, _ in self.wired(CURSOR_REL, "beforeShellExecution", self.pre_sh)],
            ["git"],
        )
        # post.sh declares no cursor event, so it must not appear there.
        self.assertNotIn(str(self.post_sh), json.dumps(self.read(CURSOR_REL)))
        for _, command in self.wired(CLAUDE_REL, "PreToolUse", self.pre_sh):
            self.assertIn("--host claude", command)

    def test_list_form_enable_is_idempotent(self):
        self.write_prose_like_manifest()
        self.run_cli("install", SKILL)
        self.run_cli("enable-hook", SKILL)
        self.run_cli("install", SKILL)
        self.assertEqual(len(self.wired(CLAUDE_REL, "PreToolUse", self.post_sh)), 1)
        self.assertEqual(len(self.wired(CLAUDE_REL, "PreToolUse", self.pre_sh)), 1)
        self.assertEqual(len(self.wired(CLAUDE_REL, "PostToolUse", self.hook_sh)), 1)

    def test_list_form_disable_removes_every_entry(self):
        self.write(
            CLAUDE_REL,
            {"hooks": {"PreToolUse": [
                {"matcher": "Write", "hooks": [{"type": "command", "command": FOREIGN_HOOK}]}
            ]}},
        )
        self.write_prose_like_manifest()
        self.run_cli("install", SKILL)
        output = self.run_cli("disable-hook", SKILL)

        self.assertIn("disabled on PostToolUse, PreToolUse", output)
        self.assert_nothing_of_ours()
        self.assertIn(FOREIGN_HOOK, json.dumps(self.read(CLAUDE_REL)))

    def test_list_form_uninstall_removes_every_entry(self):
        self.write_prose_like_manifest()
        self.run_cli("install", SKILL)
        self.run_cli("uninstall", SKILL)
        self.assert_nothing_of_ours()

    def test_list_form_opt_out_sticks_for_every_entry(self):
        self.write_prose_like_manifest()
        self.run_cli("install", SKILL)
        self.run_cli("disable-hook", SKILL)
        self.assertIn("you turned it off", self.run_cli("install", SKILL))
        self.assert_nothing_of_ours()

    def test_hooks_command_reports_each_list_entry(self):
        self.write_prose_like_manifest()
        self.run_cli("install", SKILL)
        output = self.run_cli("hooks")
        section = output.split(f"{SKILL}  (default")[1]
        for summary in ("Commit check.", "Pre-post check.", "Pre-shell check."):
            self.assertIn(summary, section)
        rows = [
            line.split()
            for line in section.splitlines()
            if line.strip().startswith(("claude", "cursor"))
        ]
        # Five rows, all enabled: demo.sh and pre.sh on two platforms each,
        # post.sh on one.
        self.assertEqual(len(rows), 5, section)
        self.assertTrue(all(row[1] == "enabled" for row in rows), section)
        self.assertIn(self.MCP_MATCHER, section)

    def test_one_script_under_one_event_twice_is_tracked_per_matcher(self):
        # If status can't tell the two entries apart, losing one still reads as
        # enabled, and install never puts it back.
        self.write_hook_list(
            [
                {"command": "scripts/demo.sh",
                 "events": {"claude": {"event": "PreToolUse", "matcher": "Bash"}}},
                {"command": "scripts/demo.sh",
                 "events": {"claude": {"event": "PreToolUse", "matcher": "Write"}}},
            ]
        )
        self.run_cli("install", SKILL)
        self.assertEqual(
            sorted(m for m, _ in self.wired(CLAUDE_REL, "PreToolUse", self.hook_sh)),
            ["Bash", "Write"],
        )

        data = self.read(CLAUDE_REL)
        data["hooks"]["PreToolUse"] = [
            e for e in data["hooks"]["PreToolUse"] if e["matcher"] != "Write"
        ]
        self.write(CLAUDE_REL, data)
        section = self.run_cli("hooks").split(f"{SKILL}  (default")[1]
        self.assertIn("off", section)

        self.run_cli("install", SKILL)
        self.assertEqual(
            sorted(m for m, _ in self.wired(CLAUDE_REL, "PreToolUse", self.hook_sh)),
            ["Bash", "Write"],
        )
        self.run_cli("disable-hook", SKILL)
        self.assert_nothing_of_ours()

    def test_list_entry_without_command_is_skipped_not_fatal(self):
        self.write_hook_list(
            [
                {"summary": "No command.",
                 "events": {"claude": {"event": "PreToolUse", "matcher": "Bash"}}},
                {"command": "scripts/demo.sh",
                 "events": {"claude": {"event": "PostToolUse", "matcher": "Bash"}}},
            ]
        )
        output = self.run_cli("install", SKILL)
        self.assertIn("hook 1 has no command", output)
        self.assertEqual(len(self.wired(CLAUDE_REL, "PostToolUse", self.hook_sh)), 1)
        self.assertNotIn("PreToolUse", self.read(CLAUDE_REL)["hooks"])

    def test_non_executable_list_entry_does_not_block_the_others(self):
        self.write_prose_like_manifest()
        self.post_sh.chmod(0o644)
        output = self.run_cli("install", SKILL)
        self.assertIn(f"{self.post_sh} is not executable", output)
        self.assertEqual(self.wired(CLAUDE_REL, "PreToolUse", self.post_sh), [])
        self.assertEqual(len(self.wired(CLAUDE_REL, "PreToolUse", self.pre_sh)), 1)
        self.assertEqual(len(self.wired(CLAUDE_REL, "PostToolUse", self.hook_sh)), 1)

    def test_doctor_flags_only_the_list_entry_that_lost_its_exec_bit(self):
        self.write_prose_like_manifest()
        self.run_cli("install", SKILL)
        self.pre_sh.chmod(0o644)
        output = self.run_cli("doctor")
        self.assertIn(f"not executable: {self.pre_sh}", output)
        self.assertNotIn(f"not executable: {self.post_sh}", output)
        self.assertNotIn(f"not executable: {self.hook_sh}", output)

    def test_a_script_named_as_a_prefix_of_another_is_not_read_as_wired(self):
        # scripts/lint is not executable, so it stays unwired. The lint-fix
        # command contains scripts/lint, and must not make it read as wired.
        self.add_script("lint").chmod(0o644)
        self.add_script("lint-fix")
        self.write_hook_list(
            [
                {"summary": "Lint.", "command": "scripts/lint",
                 "events": {"claude": {"event": "PreToolUse", "matcher": "Bash"}}},
                {"summary": "Fix.", "command": "scripts/lint-fix",
                 "events": {"claude": {"event": "PreToolUse", "matcher": "Bash"}}},
            ]
        )
        self.run_cli("enable-hook", SKILL)
        section = self.run_cli("hooks").split("Lint.")[1].split("Fix.")[0]
        self.assertIn("off", section)
        self.assertNotIn("BROKEN", self.run_cli("doctor"))

    def test_a_script_that_lost_its_exec_bit_is_left_as_it_is_on_a_shared_platform(self):
        # post.sh shares claude with working hooks; enable must still leave its
        # existing wiring as it is.
        self.write_prose_like_manifest()
        self.run_cli("install", SKILL)
        self.post_sh.chmod(0o644)
        self.run_cli("enable-hook", SKILL)
        self.assertEqual(len(self.wired(CLAUDE_REL, "PreToolUse", self.post_sh)), 1)
        self.assertEqual(len(self.wired(CLAUDE_REL, "PreToolUse", self.pre_sh)), 1)

    def test_an_empty_cursor_matcher_reads_as_enabled(self):
        self.write_hook_list(
            [{"command": "scripts/demo.sh",
              "events": {"cursor": {"event": "beforeShellExecution", "matcher": ""}}}]
        )
        self.run_cli("install", SKILL)
        self.assertIn("enabled (cursor)", self.run_cli("list"))
        self.assertIn("0 change(s)", self.run_cli("install", SKILL))

    def test_reinstall_with_a_permanently_broken_entry_changes_nothing(self):
        self.write_prose_like_manifest()
        self.post_sh.chmod(0o644)
        self.run_cli("install", SKILL)
        self.assertIn("0 change(s)", self.run_cli("install", SKILL))

    def test_single_form_reads_a_hand_quoted_entry_as_enabled(self):
        # The one-hook form recognises any entry containing its script path,
        # quoted or not.
        self.write(
            CLAUDE_REL,
            {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
                {"type": "command", "command": f"'{self.hook_sh}' --host claude"}
            ]}]}},
        )
        self.assertIn(f"Hook: {SKILL} — enabled (claude)", self.run_cli("list"))

    def test_a_broken_script_in_a_merged_group_does_not_shelter_its_sibling(self):
        self.write_prose_like_manifest()
        self.post_sh.chmod(0o644)
        # A hand-merged group: the broken post.sh beside pre.sh, under a
        # matcher pre.sh no longer declares.
        self.write(
            CLAUDE_REL,
            {"hooks": {"PreToolUse": [{"matcher": "Stale", "hooks": [
                {"type": "command", "command": f"{self.post_sh} --host claude"},
                {"type": "command", "command": f"{self.pre_sh} --host claude"},
            ]}]}},
        )
        self.run_cli("enable-hook", SKILL)
        self.assertEqual(
            [m for m, _ in self.wired(CLAUDE_REL, "PreToolUse", self.pre_sh)], ["Bash"]
        )
        self.assertEqual(len(self.wired(CLAUDE_REL, "PreToolUse", self.post_sh)), 1)

    def test_doctor_counts_a_broken_script_once_however_many_entries_use_it(self):
        self.write_hook_list(
            [
                {"command": "scripts/demo.sh",
                 "events": {"claude": {"event": "PreToolUse", "matcher": "Bash"}}},
                {"command": "scripts/demo.sh",
                 "events": {"claude": {"event": "PreToolUse", "matcher": "Write"}}},
            ]
        )
        self.run_cli("install", SKILL)
        self.hook_sh.chmod(0o644)
        output = self.run_cli("doctor")
        self.assertEqual(output.count(f"not executable: {self.hook_sh}"), 1)

    def test_install_clears_a_hook_the_list_no_longer_declares(self):
        self.write_prose_like_manifest()
        self.run_cli("install", SKILL)
        self.write_hook_list(
            [{"command": "scripts/demo.sh",
              "events": {"claude": {"event": "PostToolUse", "matcher": "Bash"},
                         "cursor": {"event": "postToolUse", "matcher": "Shell"}}}]
        )
        self.post_sh.unlink()
        self.run_cli("install", SKILL)
        self.assertNotIn(str(self.post_sh), json.dumps(self.read(CLAUDE_REL)))
        self.assertEqual(len(self.wired(CLAUDE_REL, "PostToolUse", self.hook_sh)), 1)

    def test_doctor_reports_wiring_of_a_hook_the_list_no_longer_declares(self):
        self.write_prose_like_manifest()
        self.run_cli("install", SKILL)
        # post.sh stays executable; it has only been dropped from the list.
        self.write_hook_list(
            [{"command": "scripts/demo.sh",
              "events": {"claude": {"event": "PostToolUse", "matcher": "Bash"},
                         "cursor": {"event": "postToolUse", "matcher": "Shell"}}},
             {"command": "scripts/pre.sh",
              "events": {"claude": {"event": "PreToolUse", "matcher": "Bash"},
                         "cursor": {"event": "beforeShellExecution", "matcher": "git"}}}]
        )
        output = self.run_cli("doctor")
        strays = [line for line in output.splitlines() if line.lstrip().startswith("STRAY")]
        self.assertEqual(len(strays), 1, output)
        self.assertIn(f"{self.post_sh} --host claude", strays[0])
        self.assertIn(f"fix: enable-hook {SKILL}", output)
        self.assertIn("1 problem(s)", output)

        self.run_cli("install", SKILL)
        self.assertNotIn("STRAY", self.run_cli("doctor"))

    def test_install_clears_dropped_hooks_on_a_platform_no_hook_names_any_more(self):
        self.write_prose_like_manifest()
        self.run_cli("install", SKILL)
        # Only post.sh is left, and it names claude alone.
        self.write_hook_list(
            [{"command": "scripts/post.sh",
              "events": {"claude": {"event": "PreToolUse", "matcher": self.MCP_MATCHER}}}]
        )
        self.run_cli("install", SKILL)
        self.assertNotIn(str(self.skill_dir), json.dumps(self.read(CURSOR_REL) or {}))
        self.assertEqual(len(self.wired(CLAUDE_REL, "PreToolUse", self.post_sh)), 1)
        self.assertIn("0 change(s)", self.run_cli("install", SKILL))
        self.assertNotIn("STRAY", self.run_cli("doctor"))

    def test_doctor_reports_dropped_hooks_on_a_platform_no_hook_names_any_more(self):
        self.write_prose_like_manifest()
        self.run_cli("install", SKILL)
        self.write_hook_list(
            [{"command": "scripts/post.sh",
              "events": {"claude": {"event": "PreToolUse", "matcher": self.MCP_MATCHER}}}]
        )
        output = self.run_cli("doctor")
        self.assertIn(f"{self.pre_sh} --host cursor", output)
        self.assertIn(f"{self.hook_sh} --host cursor", output)

    def test_enable_clears_a_dropped_platform_that_only_a_broken_hook_still_names(self):
        self.write_prose_like_manifest()
        self.run_cli("install", SKILL)
        # demo.sh no longer names cursor; pre.sh still does, but its script is
        # not executable.
        manifest = json.loads((self.skill_dir / "hook.json").read_text())
        del manifest["hooks"][0]["events"]["cursor"]
        self.write_hook_list(manifest["hooks"])
        self.pre_sh.chmod(0o644)
        self.run_cli("enable-hook", SKILL)
        self.assertEqual(self.wired(CURSOR_REL, "postToolUse", self.hook_sh), [])
        self.assertEqual(
            len(self.wired(CURSOR_REL, "beforeShellExecution", self.pre_sh)), 1
        )

    def test_enable_clears_a_dropped_hook_when_every_declared_hook_is_broken(self):
        self.write_prose_like_manifest()
        self.run_cli("install", SKILL)
        self.write_hook_list(
            [{"command": "scripts/post.sh",
              "events": {"claude": {"event": "PreToolUse", "matcher": self.MCP_MATCHER}}}]
        )
        self.post_sh.chmod(0o644)
        self.run_cli("enable-hook", SKILL)
        self.assertEqual(self.wired(CLAUDE_REL, "PreToolUse", self.pre_sh), [])
        self.assertEqual(len(self.wired(CLAUDE_REL, "PreToolUse", self.post_sh)), 1)

    def test_doctor_counts_an_unreadable_config_once_however_many_hooks_name_it(self):
        self.write_prose_like_manifest()
        self.write(CLAUDE_REL, "{bad")
        output = self.run_cli("doctor")
        self.assertEqual(output.count("UNREADABLE claude"), 1, output)

    def test_disable_clears_a_platform_the_manifest_set_to_null(self):
        hooks = [{"command": "scripts/demo.sh",
                  "events": {"claude": {"event": "PreToolUse", "matcher": "Bash"},
                             "cursor": {"event": "beforeShellExecution"}}}]
        self.write_hook_list(hooks)
        self.run_cli("install", SKILL)
        self.assertEqual(len(self.ours(self.cursor_entries())), 1)
        hooks[0]["events"]["cursor"] = None
        self.write_hook_list(hooks)
        self.run_cli("disable-hook", SKILL)
        self.assert_nothing_of_ours()

    def test_doctor_flags_a_broken_script_wired_away_from_its_declared_matcher(self):
        self.write_prose_like_manifest()
        self.run_cli("install", SKILL)
        # The manifest moves pre.sh to new matchers; its old wiring stays, and
        # the script then loses its exec bit.
        manifest = json.loads((self.skill_dir / "hook.json").read_text())
        manifest["hooks"][2]["events"]["claude"]["matcher"] = "Bash|Edit"
        manifest["hooks"][2]["events"]["cursor"]["matcher"] = "git push"
        self.write_hook_list(manifest["hooks"])
        self.pre_sh.chmod(0o644)
        self.assertEqual(len(self.wired(CLAUDE_REL, "PreToolUse", self.pre_sh)), 1)
        output = self.run_cli("doctor")
        self.assertIn(f"not executable: {self.pre_sh}", output)

    def test_uninstall_removes_the_hook_after_hook_json_is_deleted(self):
        self.run_cli("install", SKILL)
        self.assertEqual(len(self.ours(self.claude_entries())), 1)
        (self.skill_dir / "hook.json").unlink()
        self.run_cli("uninstall", SKILL)
        self.assert_nothing_of_ours()

    def test_disable_removes_the_hooks_after_hook_json_becomes_unreadable(self):
        self.write(
            CLAUDE_REL,
            {"hooks": {"PreToolUse": [
                {"matcher": "Write", "hooks": [{"type": "command", "command": FOREIGN_HOOK}]}
            ]}},
        )
        self.write_prose_like_manifest()
        self.run_cli("install", SKILL)
        (self.skill_dir / "hook.json").write_text("{not json")
        self.run_cli("disable-hook", SKILL)
        self.assert_nothing_of_ours()
        self.assertIn(FOREIGN_HOOK, json.dumps(self.read(CLAUDE_REL)))
        # The choice sticks once the manifest is readable again.
        self.write_prose_like_manifest()
        self.assertIn("you turned it off", self.run_cli("install", SKILL))
        self.assert_nothing_of_ours()

    def test_disable_with_an_unreadable_hook_json_sticks_even_with_nothing_wired(self):
        (self.skill_dir / "hook.json").write_text("<<<<<<< HEAD\n{")
        self.run_cli("install", SKILL)
        self.assertIsNone(self.read(CLAUDE_REL))
        output = self.run_cli("disable-hook", SKILL)
        self.assertNotIn("ships no hook", output)
        self.write_manifest(default="enabled")
        self.assertIn("you turned it off", self.run_cli("install", SKILL))
        self.assert_nothing_of_ours()

    def test_enable_with_an_unreadable_hook_json_clears_an_earlier_opt_out(self):
        self.run_cli("install", SKILL)
        self.run_cli("disable-hook", SKILL)
        (self.skill_dir / "hook.json").write_text("<<<<<<< HEAD\n{")
        output = self.run_cli("enable-hook", SKILL)
        self.assertNotIn("ships no hook", output)
        self.write_manifest(default="enabled")
        self.assertNotIn("you turned it off", self.run_cli("install", SKILL))
        self.assertEqual(len(self.ours(self.claude_entries())), 1)

    def test_a_trailing_slash_on_a_skill_name_is_ignored(self):
        self.run_cli("install", SKILL)
        self.run_cli("disable-hook", SKILL + "/")
        self.assert_nothing_of_ours()
        self.assertIn("you turned it off", self.run_cli("install", SKILL))
        self.assert_nothing_of_ours()
        self.run_cli("enable-hook", SKILL + "/")
        self.assertEqual(len(self.ours(self.claude_entries())), 1)
        self.run_cli("uninstall", SKILL + "/")
        self.assert_nothing_of_ours()
        self.assertEqual(json.loads(self.config.read_text()).get("hooks_off", []), [])

    def test_a_name_that_is_not_a_skill_touches_no_hooks(self):
        self.run_cli("install", SKILL)
        for name in ("./", ".", "", f"{SKILL}/scripts"):
            for command in ("disable-hook", "uninstall"):
                env = dict(os.environ, SHARED_SKILLS_REPO=str(self.clone),
                           SHARED_SKILLS_TARGET=str(self.targets),
                           SHARED_SKILLS_CONFIG=str(self.config),
                           SHARED_SKILLS_HOOK_HOME=str(self.home))
                subprocess.run([sys.executable, str(SCRIPT), command, name],
                               capture_output=True, text=True, env=env)
                self.assertEqual(
                    len(self.ours(self.claude_entries())), 1, f"{command} {name!r}"
                )

    def test_enable_undoes_a_disable_made_while_hook_json_was_missing(self):
        self.run_cli("install", SKILL)
        (self.skill_dir / "hook.json").unlink()
        self.run_cli("disable-hook", SKILL)
        self.run_cli("enable-hook", SKILL)
        self.write_manifest(default="enabled")
        self.assertNotIn("you turned it off", self.run_cli("install", SKILL))
        self.assertEqual(len(self.ours(self.claude_entries())), 1)

    def test_a_sweep_without_hook_json_says_when_it_cannot_parse_a_config(self):
        self.run_cli("install", SKILL)
        (self.skill_dir / "hook.json").write_text("{")
        path = self.home / CLAUDE_REL
        path.write_text(path.read_text() + "oops")
        output = self.run_cli("disable-hook", SKILL)
        self.assertIn("refusing to rewrite a file it cannot parse", output)

    def test_disable_says_nothing_about_a_platform_the_skill_does_not_declare(self):
        self.write_hook_list(
            [{"command": "scripts/demo.sh",
              "events": {"claude": {"event": "PreToolUse", "matcher": "Bash"}}}]
        )
        self.write(CURSOR_REL, '{"version": 1, oops')
        self.run_cli("install", SKILL)
        output = self.run_cli("disable-hook", SKILL)
        self.assertNotIn("cursor hook", output)
        self.assertNotIn(str(self.skill_dir), json.dumps(self.read(CLAUDE_REL) or {}))

    def test_a_list_entry_with_malformed_events_is_skipped_not_fatal(self):
        self.write_hook_list(
            [{"command": "scripts/demo.sh", "events": "x"},
             {"command": "scripts/demo.sh",
              "events": {"claude": {"event": "PostToolUse", "matcher": "Bash"}}}]
        )
        output = self.run_cli("enable-hook", SKILL)
        self.assertIn("hook 1", output)
        self.assertEqual(len(self.wired(CLAUDE_REL, "PostToolUse", self.hook_sh)), 1)
        self.run_cli("disable-hook", SKILL)
        self.assert_nothing_of_ours()

    def test_enable_with_an_unreadable_hook_json_promises_only_what_happens(self):
        (self.skill_dir / "hook.json").write_text("{")
        output = self.run_cli("enable-hook", SKILL)
        self.assertNotIn("stays on", output)
        self.assertIn("opt-out cleared", output)

    def test_uninstall_reports_an_unparseable_config_that_may_hold_the_hook(self):
        self.write_hook_list(
            [{"command": "scripts/demo.sh",
              "events": {"claude": {"event": "PreToolUse", "matcher": "Bash"}}}]
        )
        self.run_cli("install", SKILL)
        path = self.home / CLAUDE_REL
        path.write_text(path.read_text() + "oops")
        output = self.run_cli("uninstall", SKILL)
        self.assertIn("claude hook", output)
        self.assertIn("refusing to rewrite a file it cannot parse", output)

    def test_a_single_hook_with_the_wrong_types_is_ignored_not_fatal(self):
        for manifest in (
            {"version": 1, "command": 5, "default": "enabled",
             "events": {"claude": {"event": "PreToolUse", "matcher": "Bash"}}},
            {"version": 1, "command": "scripts/demo.sh", "default": "enabled",
             "events": [1]},
            {"version": 1, "command": "scripts/demo.sh", "default": "enabled",
             "events": {"claude": "x"}},
        ):
            (self.skill_dir / "hook.json").write_text(json.dumps(manifest))
            output = self.run_cli("install", SKILL)
            self.assertIn("ignoring its hook", output, manifest)
            self.run_cli("disable-hook", SKILL)
            self.run_cli("hooks")
            self.run_cli("doctor")
        self.assert_nothing_of_ours()

    def test_a_list_entry_with_a_non_string_command_is_ignored_not_fatal(self):
        self.write_hook_list(
            [{"command": 5,
              "events": {"claude": {"event": "PreToolUse", "matcher": "Bash"}}},
             {"command": "scripts/demo.sh",
              "events": {"claude": {"event": "PostToolUse", "matcher": "Bash"}}}]
        )
        output = self.run_cli("install", SKILL)
        self.assertIn("hook 1", output)
        self.assertEqual(len(self.wired(CLAUDE_REL, "PostToolUse", self.hook_sh)), 1)

    @unittest.skipUnless(
        os.path.exists(str(pathlib.Path(tempfile.gettempdir()).resolve()).upper()),
        "filesystem is case-sensitive",
    )
    def test_a_skill_name_in_the_wrong_case_acts_on_the_skill(self):
        self.run_cli("install", SKILL)
        self.run_cli("disable-hook", SKILL.upper())
        self.assert_nothing_of_ours()
        self.assertEqual(json.loads(self.config.read_text()).get("hooks_off"), [SKILL])
        self.assertIn("you turned it off", self.run_cli("install", SKILL))

    def legacy_case_state(self, opted_out=False):
        """Recreate what versions without case handling left after
        `install DEMO-HOOKED` on a case-insensitive filesystem: the typed
        spelling in the link name and the wiring, plus the opt-out when
        `opted_out` is set."""
        upper = str(self.skill_dir.parent / SKILL.upper())
        self.run_cli("install", SKILL)
        for rel in (CLAUDE_REL, CURSOR_REL):
            path = self.home / rel
            path.write_text(path.read_text().replace(str(self.skill_dir), upper))
        (self.targets / SKILL).unlink()
        (self.targets / SKILL.upper()).symlink_to(upper)
        if opted_out:
            self.config.write_text(json.dumps({"hooks_off": [SKILL.upper()]}))

    def wired_any_case(self):
        text = "".join(
            json.dumps(self.read(rel) or {}) for rel in (CLAUDE_REL, CURSOR_REL)
        ).lower()
        return text.count(SKILL.lower() + "/scripts/demo.sh")

    CASE_INSENSITIVE = os.path.exists(
        str(pathlib.Path(tempfile.gettempdir()).resolve()).upper()
    )

    @unittest.skipUnless(CASE_INSENSITIVE, "filesystem is case-sensitive")
    def test_uninstall_clears_wiring_recorded_under_another_case(self):
        self.legacy_case_state()
        self.run_cli("uninstall", SKILL.upper())
        self.assertEqual(self.wired_any_case(), 0)

    @unittest.skipUnless(CASE_INSENSITIVE, "filesystem is case-sensitive")
    def test_disable_clears_wiring_recorded_under_another_case(self):
        self.legacy_case_state()
        self.run_cli("disable-hook", SKILL.upper())
        self.assertEqual(self.wired_any_case(), 0)

    @unittest.skipUnless(CASE_INSENSITIVE, "filesystem is case-sensitive")
    def test_reinstall_over_another_case_wires_the_hook_once(self):
        self.legacy_case_state()
        output = self.run_cli("install", SKILL.upper())
        self.assertNotIn("different location", output)
        self.assertEqual(self.wired_any_case(), 2)  # one claude, one cursor

    @unittest.skipUnless(CASE_INSENSITIVE, "filesystem is case-sensitive")
    def test_an_opt_out_recorded_under_another_case_is_honoured_and_cleared(self):
        self.legacy_case_state(opted_out=True)
        self.run_cli("disable-hook", SKILL.upper())
        self.config.write_text(json.dumps({"hooks_off": [SKILL.upper()]}))
        self.assertIn("you turned it off", self.run_cli("install", SKILL))
        self.run_cli("enable-hook", SKILL)
        self.assertEqual(json.loads(self.config.read_text()).get("hooks_off", []), [])

    def test_a_hook_whose_event_is_not_a_string_is_ignored_not_fatal(self):
        for events in ({"claude": {"event": ["PostToolUse"], "matcher": "Bash"}},
                       {"claude": {"event": "PostToolUse", "matcher": 5}}):
            self.write_hook_list([{"command": "scripts/demo.sh", "events": events}])
            self.assertIn("malformed", self.run_cli("install", SKILL))
            (self.skill_dir / "hook.json").write_text(json.dumps(
                {"version": 1, "command": "scripts/demo.sh", "default": "enabled",
                 "events": events}))
            self.assertIn("malformed", self.run_cli("install", SKILL))

    def test_uninstall_reports_an_unparseable_config_once_for_all_names(self):
        self.write(CLAUDE_REL, "{bad")
        output = self.run_cli("uninstall", SKILL, "nosuch")
        self.assertEqual(output.count("refusing to rewrite a file it cannot parse"), 1, output)

    def test_an_unknown_platform_in_events_does_not_sink_the_hook(self):
        manifest = json.loads((self.skill_dir / "hook.json").read_text())
        manifest["events"]["codex"] = {"event": "PreToolUse", "matcher": ["Bash"]}
        (self.skill_dir / "hook.json").write_text(json.dumps(manifest))
        self.run_cli("install", SKILL)
        self.assertEqual(len(self.ours(self.claude_entries())), 1)
        self.write_hook_list([{"command": "scripts/demo.sh", "events": {
            "claude": {"event": "PostToolUse", "matcher": "Bash"},
            "codex": {"event": "PreToolUse", "matcher": 5}}}])
        self.run_cli("install", SKILL)
        self.assertEqual(len(self.wired(CLAUDE_REL, "PostToolUse", self.hook_sh)), 1)

    NO_USABLE_HOOK = {
        "unparseable": "{",
        "invalid": json.dumps({"version": 1}),
        "empty list": json.dumps({"version": 1, "default": "enabled", "hooks": []}),
        "only unusable": json.dumps(
            {"version": 1, "default": "enabled", "hooks": [{"summary": "todo"}]}),
        "command beside empty list": json.dumps(
            {"version": 1, "default": "enabled", "command": "scripts/demo.sh",
             "events": {"claude": {"event": "PreToolUse", "matcher": "Bash"}},
             "hooks": []}),
    }

    def leave_wiring_behind(self, text):
        self.write_manifest(default="enabled")
        self.run_cli("install", SKILL)
        self.assertEqual(len(self.ours(self.claude_entries())), 1)
        (self.skill_dir / "hook.json").write_text(text)

    def test_doctor_reports_wiring_left_by_a_hook_json_that_loads_no_hook(self):
        for shape, text in self.NO_USABLE_HOOK.items():
            with self.subTest(shape):
                self.leave_wiring_behind(text)
                output = self.run_cli("doctor")
                self.assertIn("STRAY", output)
                self.assertIn(str(self.hook_sh), output)
                self.run_cli("disable-hook", SKILL)
                self.run_cli("enable-hook", SKILL)

    def test_install_removes_wiring_left_by_a_hook_json_that_loads_no_hook(self):
        for shape, text in self.NO_USABLE_HOOK.items():
            with self.subTest(shape):
                self.leave_wiring_behind(text)
                self.run_cli("install", SKILL)
                self.assert_nothing_of_ours()
                self.assertNotIn("STRAY", self.run_cli("doctor"))

    def test_enable_removes_wiring_left_by_a_hook_json_that_loads_no_hook(self):
        for shape, text in self.NO_USABLE_HOOK.items():
            with self.subTest(shape):
                self.leave_wiring_behind(text)
                self.run_cli("enable-hook", SKILL)
                self.assert_nothing_of_ours()
                self.assertNotIn(SKILL, json.loads(self.config.read_text() or "{}").get("hooks_off", []))

    def test_doctor_advice_for_leftover_wiring_keeps_an_opt_out(self):
        self.leave_wiring_behind("{")
        self.config.write_text(json.dumps({"hooks_off": [SKILL]}))
        output = self.run_cli("doctor")
        advice = output.split("loads no hook")[1].splitlines()[1]
        # The advised command, run as given, must not undo the opt-out.
        command = advice.split(" or ")[-1].split(" to ")[0].split()
        self.run_cli(*command)
        self.assert_nothing_of_ours()
        self.assertEqual(json.loads(self.config.read_text()).get("hooks_off"), [SKILL])

    NO_KNOWN_PLATFORM = {
        "empty events": json.dumps(
            {"version": 1, "command": "scripts/demo.sh", "default": "enabled", "events": {}}),
        "unknown platform only": json.dumps(
            {"version": 1, "command": "scripts/demo.sh", "default": "enabled",
             "events": {"codex": {"event": "PreToolUse"}}}),
    }

    def test_a_single_hook_naming_no_known_platform_counts_as_loading_no_hook(self):
        for shape, text in self.NO_KNOWN_PLATFORM.items():
            with self.subTest(shape, step="doctor"):
                self.leave_wiring_behind(text)
                output = self.run_cli("doctor")
                self.assertIn("STRAY", output)
                self.assertIn(str(self.hook_sh), output)
            with self.subTest(shape, step="install"):
                self.run_cli("install", SKILL)
                self.assert_nothing_of_ours()
            with self.subTest(shape, step="enable-hook"):
                self.leave_wiring_behind(text)
                self.run_cli("enable-hook", SKILL)
                self.assert_nothing_of_ours()

    def test_disable_of_a_skill_with_no_hook_and_no_wiring_says_so(self):
        (self.skill_dir / "hook.json").unlink()
        output = self.run_cli("disable-hook", SKILL)
        self.assertIn(f"{SKILL}: ships no hook", output)
        self.assertIn("0 change(s)", output)

    def test_manifest_with_both_command_and_hooks_wires_the_list_and_ignores_command(self):
        # Adam's review decision: the list is wired, command is ignored with a
        # warning that names it. This replaces the earlier refusal.
        self.post_sh = self.add_script("post.sh")
        self.write_hook_list(
            [{"command": "scripts/post.sh",
              "events": {"claude": {"event": "PreToolUse", "matcher": "Bash"}}}],
            command="scripts/demo.sh",
        )
        output = self.run_cli("install", SKILL)
        self.assertIn("scripts/demo.sh", output)
        self.assertIn("move it into hooks or delete it", output)
        self.assertEqual(len(self.wired(CLAUDE_REL, "PreToolUse", self.post_sh)), 1)
        self.assertEqual(self.wired(CLAUDE_REL, "PreToolUse", self.hook_sh), [])

    def test_an_ignored_command_loses_the_wiring_it_had_like_any_dropped_hook(self):
        self.run_cli("install", SKILL)
        self.assertEqual(len(self.ours(self.claude_entries())), 1)
        self.post_sh = self.add_script("post.sh")
        self.write_hook_list(
            [{"command": "scripts/post.sh",
              "events": {"claude": {"event": "PostToolUse", "matcher": "Bash"}}}],
            command="scripts/demo.sh",
        )
        self.assertIn("STRAY", self.run_cli("doctor"))
        self.run_cli("install", SKILL)
        self.assertEqual(self.ours(self.claude_entries()), [])
        self.assertNotIn(str(self.hook_sh), json.dumps(self.read(CURSOR_REL) or {}))
        self.assertEqual(len(self.wired(CLAUDE_REL, "PostToolUse", self.post_sh)), 1)
        self.assertNotIn("STRAY", self.run_cli("doctor"))


MANAGER = "manage-skills"
MANAGER_SOURCE = SCRIPT.parent.parent
GIT_IDENTITY = ["-c", "user.name=test", "-c", "user.email=test@example.com", "-c", "commit.gpgsign=false"]


class UpdateTests(unittest.TestCase):
    """`update` and the copy of manage-skills it refreshes.

    Two git clones, each with its own origin: `public`, the one bootstrap
    recorded, and `private`, a second skills repository. Each clone's
    manage-skills carries a WHICH file naming the clone, so a test can tell
    where an installed copy came from."""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="skills-update-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.config = self.tmp / "config.json"
        self.targets = [self.tmp / "agents" / "skills", self.tmp / "claude" / "skills"]

        self.public = self.make_clone("public", manager=True)
        self.private = self.make_clone("private", manager=True)
        self.config.write_text(json.dumps({"repo": str(self.public)}))
        for target in self.targets:
            target.mkdir(parents=True)
            shutil.copytree(self.manager_in(self.public), target / MANAGER)

    # -- helpers ----------------------------------------------------------

    def git(self, *args, cwd=None):
        env = {**os.environ, "HOME": str(self.home), "GIT_CONFIG_NOSYSTEM": "1"}
        result = subprocess.run(
            ["git", *GIT_IDENTITY, *args], cwd=cwd, capture_output=True, text=True, env=env
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def manager_in(self, clone):
        return clone / ".agents" / "skills" / MANAGER

    def make_clone(self, name, manager):
        """A clone of a fresh origin, with one committed skill and optionally
        its own manage-skills."""
        origin = self.tmp / f"{name}-origin.git"
        clone = self.tmp / name
        self.git("init", "-q", "--bare", "-b", "main", str(origin))
        self.git("clone", "-q", str(origin), str(clone))
        skill = clone / ".agents" / "skills" / f"{name}-skill"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(f"---\nname: {name}-skill\ndescription: x\n---\n")
        if manager:
            shutil.copytree(
                MANAGER_SOURCE, self.manager_in(clone),
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
            (self.manager_in(clone) / "WHICH").write_text(name)
        self.git("add", "-A", cwd=clone)
        self.git("commit", "-q", "-m", "start", cwd=clone)
        self.git("push", "-q", "origin", "HEAD:main", cwd=clone)
        return clone

    def push_change(self, name, relpath, text):
        """Commit a change to `name`'s origin from a second clone, so the next
        pull of the first clone has something to fetch."""
        other = self.tmp / f"{name}-other"
        if other.is_dir():
            self.git("pull", "-q", "--ff-only", cwd=other)
        else:
            self.git("clone", "-q", str(self.tmp / f"{name}-origin.git"), str(other))
        path = other / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        self.git("add", "-A", cwd=other)
        self.git("commit", "-q", "-m", "change", cwd=other)
        self.git("push", "-q", "origin", "HEAD:main", cwd=other)

    def env(self, repo=None):
        env = dict(os.environ)
        env["SHARED_SKILLS_TARGET"] = os.pathsep.join(str(t) for t in self.targets)
        env["SHARED_SKILLS_CONFIG"] = str(self.config)
        env["SHARED_SKILLS_HOOK_HOME"] = str(self.home)
        env["HOME"] = str(self.home)
        env["GIT_CONFIG_NOSYSTEM"] = "1"
        env.pop("SHARED_SKILLS_REPO", None)
        if repo:
            env["SHARED_SKILLS_REPO"] = str(repo)
        return env

    def update(self, repo=None):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "update"],
            capture_output=True, text=True, env=self.env(repo),
        )

    def install_manager(self, repo):
        """Call install_manager(repo) directly, in a subprocess so TARGETS is
        read from this test's environment."""
        code = (
            "import pathlib, sys; sys.path.insert(0, sys.argv[1]); import skills; "
            "skills.install_manager(pathlib.Path(sys.argv[2]))"
        )
        return subprocess.run(
            [sys.executable, "-c", code, str(SCRIPT.parent), str(repo)],
            capture_output=True, text=True, env=self.env(),
        )

    def installed(self):
        """What WHICH says in each target's manage-skills, or None."""
        found = []
        for target in self.targets:
            which = target / MANAGER / "WHICH"
            found.append(which.read_text() if which.is_file() else None)
        return found

    def assert_complete(self):
        """Every target still has a whole manage-skills, and no staging left."""
        for target in self.targets:
            self.assertTrue((target / MANAGER / "scripts" / "skills.py").is_file(), target)
            self.assertEqual(sorted(p.name for p in target.iterdir()), [MANAGER], target)

    # -- update -----------------------------------------------------------

    def test_update_from_a_private_clone_keeps_the_recorded_manager(self):
        self.push_change("private", "pulled.txt", "yes")
        result = self.update(self.private)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.installed(), ["public", "public"])
        self.assertTrue((self.private / "pulled.txt").is_file(), "private clone not pulled")
        self.assertIn(f"Left {MANAGER} as it is", result.stdout)

    def test_update_from_a_private_clone_without_a_manager_leaves_it_untouched(self):
        shutil.rmtree(self.manager_in(self.private))
        self.git("add", "-A", cwd=self.private)
        self.git("commit", "-q", "-m", "export manage-skills", cwd=self.private)
        self.git("push", "-q", "origin", "HEAD:main", cwd=self.private)
        self.push_change("private", "pulled.txt", "yes")
        result = self.update(self.private)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.installed(), ["public", "public"])
        self.assert_complete()
        self.assertTrue((self.private / "pulled.txt").is_file())

    def test_update_without_the_variable_refreshes_from_the_recorded_clone(self):
        self.push_change("public", f".agents/skills/{MANAGER}/WHICH", "public-v2")
        result = self.update()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.installed(), ["public-v2", "public-v2"])
        self.assert_complete()

    def test_update_with_the_variable_naming_the_recorded_clone_refreshes(self):
        self.push_change("public", f".agents/skills/{MANAGER}/WHICH", "public-v2")
        result = self.update(self.public)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.installed(), ["public-v2", "public-v2"])

    def test_update_with_the_variable_and_no_recorded_clone_leaves_the_manager(self):
        self.config.unlink()
        self.push_change("private", "pulled.txt", "yes")
        result = self.update(self.private)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.installed(), ["public", "public"])
        self.assertTrue((self.private / "pulled.txt").is_file())
        self.assertIn("bootstrap", result.stdout)

    # -- install_manager --------------------------------------------------

    def test_install_manager_refuses_a_clone_without_a_manager(self):
        shutil.rmtree(self.manager_in(self.private))
        result = self.install_manager(self.private)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(f"has no {MANAGER}", result.stdout + result.stderr)
        self.assertEqual(self.installed(), ["public", "public"])
        self.assert_complete()

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root reads any file")
    def test_a_copy_that_fails_midway_keeps_the_previous_manager(self):
        unreadable = self.manager_in(self.private) / "scripts" / "unreadable.txt"
        unreadable.write_text("x")
        unreadable.chmod(0)
        self.addCleanup(unreadable.chmod, 0o644)
        result = self.install_manager(self.private)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.installed(), ["public", "public"])
        self.assert_complete()

    def test_update_with_the_recorded_clone_missing_says_to_rerun_bootstrap(self):
        self.config.write_text(json.dumps({"repo": str(self.tmp / "moved-away")}))
        result = self.update(self.private)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.installed(), ["public", "public"])
        self.assertIn("re-run bootstrap", result.stdout)
        self.assertNotIn("Run update without SHARED_SKILLS_REPO", result.stdout)

    def test_an_interrupt_between_the_two_renames_keeps_the_previous_manager(self):
        # Ctrl-C after the old copy is moved aside, before the new one is in.
        code = (
            "import os, pathlib, sys; sys.path.insert(0, sys.argv[1]); import skills\n"
            "real, calls = os.rename, []\n"
            "def rename(a, b):\n"
            "    calls.append(a)\n"
            "    if len(calls) == 2: raise KeyboardInterrupt\n"
            "    real(a, b)\n"
            "os.rename = rename\n"
            "skills.install_manager(pathlib.Path(sys.argv[2]))\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", code, str(SCRIPT.parent), str(self.private)],
            capture_output=True, text=True, env=self.env(),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("KeyboardInterrupt", result.stderr)
        self.assertEqual(self.installed(), ["public", "public"])
        self.assert_complete()



if __name__ == "__main__":
    unittest.main(verbosity=2)
