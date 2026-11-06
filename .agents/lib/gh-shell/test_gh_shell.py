#!/usr/bin/env python3
"""Tests for gh_shell.py, the command reader prose's and spec-check's hooks
share. Its edge cases are tested through prose's posting hook
(.agents/skills/prose/scripts/test_hooks.py); these pin the interface both
hooks call.

    python3 test_gh_shell.py
"""

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import gh_shell  # noqa: E402


class CommandsTests(unittest.TestCase):
    def test_a_sequence_splits_into_simple_commands_with_text_and_source(self):
        commands, grouped = gh_shell._commands('cd /tmp && gh pr create --title "x y" -d')
        self.assertFalse(grouped)
        self.assertEqual([[text for text, _ in words] for words, _ in commands],
                         [["cd", "/tmp"], ["gh", "pr", "create", "--title", "x y", "-d"]])
        self.assertEqual(commands[1][0][4], ("x y", '"x y"'))

    def test_a_pipe_feeds_the_next_command(self):
        commands, _ = gh_shell._commands("gh pr view 5 | grep ready")
        self.assertEqual([fed for _, fed in commands], [False, True])

    def test_a_command_substitution_is_not_read(self):
        self.assertIsNone(gh_shell._commands('gh pr ready "$(git branch --show-current)"'))


class WordsTests(unittest.TestCase):
    def test_plain_words_keep_whether_they_were_quoted(self):
        self.assertEqual(gh_shell._words("gh pr edit -b 'a b'"),
                         [("gh", False), ("pr", False), ("edit", False), ("-b", False),
                          ("a b", True)])

    def test_an_expansion_is_not_a_plain_word(self):
        self.assertIsNone(gh_shell._words('gh pr create --body "$BODY"'))
        self.assertIsNone(gh_shell._words("cd ~/x"))


class GhArgsTests(unittest.TestCase):
    def test_a_leading_repo_flag_is_dropped(self):
        words = gh_shell._words("gh -R o/r pr ready 5")
        self.assertEqual([text for text, _ in gh_shell._gh_args(words)], ["pr", "ready", "5"])


class TablesTests(unittest.TestCase):
    def test_the_flag_tables_name_the_flags_both_hooks_read(self):
        self.assertIn("reviewer", gh_shell.LONG_FLAGS["pr"]["create"][0])
        self.assertIn("draft", gh_shell.LONG_FLAGS["pr"]["create"][1])
        self.assertIn("add-reviewer", gh_shell.LONG_FLAGS["pr"]["edit"][0])
        self.assertIn("r", gh_shell.SHORT_VALUES["pr"]["create"])
        self.assertIn("ready", gh_shell.NO_TEXT_VERBS["pr"])
        self.assertTrue(gh_shell.GITHUB_MCP.match("mcp__plugin_x_github__create_pull_request"))


if __name__ == "__main__":
    unittest.main()
