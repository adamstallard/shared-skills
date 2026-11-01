#!/usr/bin/env python3
"""Tests for prose's hooks, each of which runs prose.py: the posting hook
(check-post.sh), the commit hook (check-commit-trailer.sh) with the shared
commit script, and the gate on a session's first write or post
(require-first-call.sh).

Standard library only:

    python3 test_hooks.py
"""

import json
import os
import pathlib
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

from prose_test_support import (
    BUG_HUNTER_MINT,
    COMMIT_HOOK,
    COMMIT_SCRIPT,
    GATE,
    HERE,
    HOOK_REPORT,
    POST_HOOK,
    Repo,
    SCRIPT,
    VERIFY_STAGED,
    prose,
    run,
)


class PostingHook(unittest.TestCase):
    """The hook before a tool call, as Claude Code sends it."""

    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.good = prose.sign("A good body.\n")

    def hook(self, payload, host="claude"):
        raw = payload if isinstance(payload, str) else json.dumps(payload)
        return run(["sh", str(POST_HOOK), "--host", host], stdin=raw)

    def mcp(self, tool, tool_input):
        return {"hook_event_name": "PreToolUse", "cwd": str(self.dir),
                "tool_name": tool, "tool_input": tool_input}

    def bash(self, command):
        return self.mcp("Bash", {"command": command})

    def test_a_prose_command_whose_goals_mention_a_gh_post_is_not_a_post(self):
        for command in (
            "python3 $S/prose.py sign --goals 'check the gh pr create flow; approve it'",
            "python3 /x/prose.py sign --pass abc < body.md > signed.md",
        ):
            with self.subTest(command):
                result = self.hook(self.bash(command))
                self.assertEqual(result.returncode, 0, result.stderr)
        # Anything that could run a second command is still read as a post.
        for command in (
            "python3 /x/prose.py start --goals g; gh pr create --body x",
            "python3 /x/prose.py start --goals \"$(gh pr create --body x)\"",
            "python3 /x/prose.py start --goals g && gh issue comment 3 --body x",
        ):
            with self.subTest(command):
                self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_an_mcp_post_with_a_valid_footer_passes(self):
        result = self.hook(self.mcp("mcp__github__create_pull_request", {"title": "t", "body": self.good}))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_an_mcp_post_without_a_footer_is_blocked(self):
        result = self.hook(self.mcp("mcp__github__add_issue_comment", {"body": "Plain text."}))
        self.assertEqual(result.returncode, 2)
        self.assertIn("prose.py", result.stderr)
        self.assertIn("sign", result.stderr)

    def test_a_nested_review_comment_is_checked_too(self):
        tool_input = {"body": self.good, "comments": [{"path": "a", "body": "Unsigned."}]}
        result = self.hook(self.mcp("mcp__github__create_pull_request_review", tool_input))
        self.assertEqual(result.returncode, 2)
        self.assertIn("comments[0].body", result.stderr)

    def test_the_block_message_gives_the_two_calls_that_sign(self):
        result = self.hook(self.bash('gh pr comment 1 --body "$(cat x)"'))
        self.assertEqual(result.returncode, 2)
        self.assertIn("sign --pass", result.stderr)
        self.assertNotRegex(result.stderr, r"sign --goals '[^']*' < ")

    def test_a_github_tool_without_a_body_field_passes(self):
        result = self.hook(self.mcp("mcp__github__get_pull_request", {"pullNumber": 3}))
        self.assertEqual(result.returncode, 0)

    def test_a_plugin_bundled_github_server_is_checked(self):
        result = self.hook(self.mcp("mcp__plugin_gh_github__add_issue_comment", {"body": "x"}))
        self.assertEqual(result.returncode, 2)

    def test_another_server_is_not_checked(self):
        result = self.hook(self.mcp("mcp__linear__save_comment", {"body": "x"}))
        self.assertEqual(result.returncode, 0)

    def test_gh_with_an_inline_body(self):
        self.assertEqual(self.hook(self.bash("gh pr comment 3 --body 'Unsigned.'")).returncode, 2)
        command = "gh pr comment 3 --body " + shlex.quote(self.good)
        self.assertEqual(self.hook(self.bash(command)).returncode, 0)

    def test_the_heredoc_idiom_is_blocked(self):
        # Not on the allow-list (DECISIONS: the posting hook reads an allow-list).
        body = self.good.rstrip("\n")
        command = f"gh pr create --title T --body \"$(cat <<'EOF'\n{body}\nEOF\n)\""
        self.assertEqual(self.hook(self.bash(command)).returncode, 2)
        command = "gh pr create --title T --body \"$(cat <<'EOF'\nUnsigned, it's plain.\nEOF\n)\""
        self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_gh_with_a_body_file_relative_to_the_cwd(self):
        (self.dir / "body.md").write_text(self.good)
        self.assertEqual(self.hook(self.bash("gh pr edit 3 --body-file body.md")).returncode, 0)
        (self.dir / "bad.md").write_text("Unsigned.\n")
        self.assertEqual(self.hook(self.bash("gh issue create -t T -F bad.md")).returncode, 2)

    def test_gh_body_file_from_a_heredoc_is_not_an_accepted_form(self):
        command = f"gh pr comment 3 --body-file - <<'EOF'\n{self.good}EOF\n"
        # Not an accepted form (DECISIONS: the posting hook reads an allow-list), so blocked.
        self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_gh_body_from_a_pipe_cannot_be_read_and_is_blocked(self):
        result = self.hook(self.bash("cat body.md | gh pr comment 3 --body-file -"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("cannot be checked", result.stderr)

    def test_gh_commands_that_post_no_body_pass(self):
        for command in ("gh pr view 3", "gh pr edit 3 --add-label x", "gh issue list", "ls -la"):
            with self.subTest(command):
                self.assertEqual(self.hook(self.bash(command)).returncode, 0)

    def test_a_post_later_in_a_chain_is_found(self):
        command = "git push && gh pr comment 3 --body 'Unsigned.'"
        self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_a_double_quoted_body_with_escapes_is_not_an_accepted_form(self):
        signed = prose.sign("Use `make test` to run it.\n\nCosts $5.\n")
        escaped = signed.rstrip("\n").replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$")
        command = f'gh pr comment 12 --body "{escaped}"'
        result = self.hook(self.bash(command))
        # Not an accepted form (DECISIONS: the posting hook reads an allow-list), so blocked.
        self.assertEqual(result.returncode, 2, result.stderr)

    def test_a_body_built_by_the_shell_is_called_unreadable(self):
        (self.dir / "signed.md").write_text(self.good)
        result = self.hook(self.bash(f'gh pr create --title T --body "$(cat {self.dir}/signed.md)"'))
        self.assertEqual(result.returncode, 2)
        self.assertIn("cannot be checked", result.stderr)

    def test_a_body_file_rewritten_earlier_in_the_command_is_not_trusted(self):
        (self.dir / "pr.md").write_text(self.good)
        command = "printf 'new unsigned text\\n' > pr.md && gh pr edit 5 --body-file pr.md"
        self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_a_post_inside_a_command_substitution_is_checked(self):
        for command in (
            "url=$(gh pr create --title t --body 'no footer') && echo \"$url\"",
            "PR_URL=`gh pr create --title t --body 'no footer'`",
        ):
            with self.subTest(command):
                self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_a_command_the_hook_cannot_parse_does_not_let_a_post_through(self):
        for command in (
            "gh pr comment 1 --body 'no footer' && echo $'it\\'s posted'",
            "gh pr comment 1 --body $'Don\\'t merge yet'",
            "gh pr comment 1 --body-file - <<\\EOF\nDon't merge, no footer\nEOF\n",
        ):
            with self.subTest(command):
                self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_a_backslash_heredoc_delimiter_is_not_an_accepted_form(self):
        command = f"gh pr comment 3 --body-file - <<\\EOF\n{self.good}EOF\n"
        # Not an accepted form (DECISIONS: the posting hook reads an allow-list), so blocked.
        self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_gh_aliases_and_attached_short_flags_are_checked(self):
        for command in (
            "gh pr new --title t --body 'no footer'",
            "gh issue new --title t --body 'no footer'",
            "gh pr comment 1 -b'no footer'",
            "gh pr comment 1 -b='no footer'",
            "gh pr comment 1 --body-file <(echo no footer)",
        ):
            with self.subTest(command):
                self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_a_post_in_a_substitution_trusts_no_file_an_earlier_command_writes(self):
        (self.dir / "pr.md").write_text(self.good)
        # Not an accepted form (DECISIONS: the posting hook reads an allow-list), so blocked.
        self.assertEqual(self.hook(self.bash("url=$(gh pr edit 5 --body-file pr.md)")).returncode, 2)
        command = "printf 'unsigned\\n' > pr.md && url=$(gh pr edit 5 --body-file pr.md)"
        self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_a_signed_post_in_a_substitution_is_not_an_accepted_form(self):
        body = self.good.rstrip("\n")
        command = f"url=$(gh pr create --title T --body \"$(cat <<'EOF'\n{body}\nEOF\n)\")"
        # Not an accepted form (DECISIONS: the posting hook reads an allow-list), so blocked.
        self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_more_attached_flag_forms_are_read(self):
        (self.dir / "bad.md").write_text("Unsigned.\n")
        (self.dir / "good.md").write_text(self.good)
        for command, code in (
            ("gh pr comment 1 -Fbad.md", 2),
            ("gh pr comment 1 -F=bad.md", 2),
            ("gh pr comment 1 -Fgood.md", 0),
            ("gh -Rowner/repo pr comment 1 --body 'no footer'", 2),
            ("gh pr comment 1 --body " + shlex.quote(self.good), 0),
        ):
            with self.subTest(command):
                self.assertEqual(self.hook(self.bash(command)).returncode, code)

    def test_an_unparsable_command_without_a_gh_post_passes(self):
        self.assertEqual(self.hook(self.bash("echo 'unterminated gh")).returncode, 0)
        # Mentions a gh post verb and cannot be read to the end, so whether it
        # runs one is unknown: blocked.
        command = "cat > notes.md <<'EOF'\nrun gh pr create, it's easy\nEOF\necho 'x"
        self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_a_quoted_body_containing_a_heredoc_sample_passes(self):
        signed = prose.sign("Fixes the thing.\n\nRun:\n\n    cat <<EOF\n    hi\nEOF\n\nDone.\n")
        command = "gh pr comment 1 --body " + shlex.quote(signed)
        result = self.hook(self.bash(command))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_text_around_a_heredoc_substitution_is_not_ignored(self):
        body = self.good.rstrip("\n")
        command = f"gh pr create --title t --body \"Intro $(cat <<'EOF'\n{body}\nEOF\n)\""
        self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_close_with_a_comment_is_checked(self):
        for command in ("gh issue close 3 --comment 'unsigned text'", "gh pr close 3 -c 'unsigned text'"):
            with self.subTest(command):
                self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_reopen_and_revert_bodies_are_checked(self):
        for command in (
            "gh issue reopen 5 -c 'unsigned text'",
            "gh pr reopen 5 --comment 'unsigned text'",
            "gh pr revert 5 -b 'unsigned text'",
        ):
            with self.subTest(command):
                self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_an_unquoted_heredoc_with_backslashes_is_not_trusted(self):
        signed = prose.sign("Path is C:\\\\temp\\\\x\n").rstrip("\n")
        command = f'gh pr comment 5 -b "$(cat <<EOF\n{signed}\nEOF\n)"'
        self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_arithmetic_shift_is_not_a_heredoc(self):
        body = self.good.rstrip("\n")
        command = f"echo $((1<<x))\ngh pr comment 5 -b \"$(cat <<'EOF'\n{body}\nEOF\n)\""
        # Not an accepted form (DECISIONS: the posting hook reads an allow-list), so blocked.
        self.assertEqual(self.hook(self.bash(command)).returncode, 2)
        command = "echo $((1<<EOF))\ngh pr comment 5 -b 'unsigned'\nEOF\n"
        self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_a_heredoc_marker_inside_parameter_or_index_syntax_hides_nothing(self):
        for first in ("echo ${x:-<<EOF}", "echo $[1<<EOF]", "a[1<<EOF]=5"):
            command = f"{first}\ngh issue comment 1 --body 'unsigned'\nEOF\n"
            with self.subTest(first):
                self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_a_later_stdin_redirect_overrides_the_heredoc(self):
        signed = self.good.rstrip("\n")
        command = f"gh issue comment 1 -F - <<'EOF' <unsigned.txt\n{signed}\nEOF\n"
        self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_grouped_short_flags_do_not_hide_the_body(self):
        for command in (
            "gh pr close 1 -dc 'unsigned'",
            "gh pr review 1 -ab 'unsigned'",
            "gh pr create -db 'unsigned' -t t",
        ):
            with self.subTest(command):
                self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_shell_syntax_that_looks_like_a_heredoc_hides_no_post(self):
        for first in (
            "a=x[ # ] <<EOF",
            "echo ${x:-$'\\''} '}<<EOF' # '",
            'echo "${x:-"<<EOF"}"',
        ):
            command = f"{first}\ngh pr comment 1 --body 'unsigned'\nEOF\n"
            with self.subTest(first):
                self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_a_redirection_before_the_body_flag_does_not_end_the_arguments(self):
        for command in (
            "gh pr comment 1 >/dev/null --body 'unsigned'",
            "gh pr comment 1 2>&1 --body 'unsigned'",
        ):
            with self.subTest(command):
                self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_a_heredoc_after_an_operator_run_is_counted(self):
        signed = self.good.rstrip("\n")
        command = f"true;<<A; gh pr comment 1 --body-file - <<B\n{signed}\nA\nunsigned body\nB\n"
        self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_a_here_string_is_not_read_as_a_heredoc(self):
        command = "cat <<<x\ngh pr comment 1 --body 'unsigned'\nx\n"
        self.assertEqual(self.hook(self.bash(command)).returncode, 2)
        signed = self.good.rstrip("\n")
        command = f"cat <<<x; gh pr comment 1 -F - <<'EOF'\n{signed}\nEOF\n"
        # Not an accepted form (DECISIONS: the posting hook reads an allow-list), so blocked.
        self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_the_accepted_forms_pass_when_signed(self):
        (self.dir / "body.md").write_text(self.good)
        body = self.good.rstrip("\n")
        for command in (
            "gh pr comment 3 --body " + shlex.quote(self.good),
            'gh pr comment 3 --body "' + body + '"',
            "gh pr edit 3 --body-file body.md",
            "gh issue close 3 --comment " + shlex.quote(self.good),
            "gh -R owner/repo pr comment 3 -b " + shlex.quote(self.good),
        ):
            with self.subTest(command):
                result = self.hook(self.bash(command))
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_signed_heredoc_body_is_blocked_and_pointed_at_body_file(self):
        # The heredoc form is not accepted (DECISIONS: the posting hook reads an allow-list).
        body = self.good.rstrip("\n")
        command = f"gh pr create --title T --body \"$(cat <<'EOF'\n{body}\nEOF\n)\""
        result = self.hook(self.bash(command))
        self.assertEqual(result.returncode, 2)
        self.assertIn("--body-file signed.md", result.stderr)

    def test_any_other_shape_of_post_is_blocked_and_told_the_forms(self):
        for command in (
            "GH_REPO=o/r gh pr comment 3 --body " + shlex.quote(self.good),
            "/usr/local/bin/gh pr comment 3 --body " + shlex.quote(self.good),
            "cd sub && gh pr comment 3 --body " + shlex.quote(self.good),
            "gh pr comment 3 --body-file missing.md",
            "gh pr comment 3 --body *.md",
        ):
            with self.subTest(command):
                result = self.hook(self.bash(command))
                self.assertEqual(result.returncode, 2)
                self.assertIn("gh is the whole command", result.stderr)

    def test_a_long_value_flag_does_not_hide_the_body(self):
        for command in (
            "gh pr create --title -t --body 'UNSIGNED body'",
            "gh pr edit 5 --title -t --body 'UNSIGNED body'",
            "gh pr create -d=t --body 'UNSIGNED body' --title T",
        ):
            with self.subTest(command):
                self.assertEqual(self.hook(self.bash(command)).returncode, 2)
        command = "gh pr create --title '-bump deps' --body " + shlex.quote(self.good)
        self.assertEqual(self.hook(self.bash(command)).returncode, 0)

    def test_a_delimiter_line_inside_the_heredoc_body_ends_it(self):
        signed = prose.sign("Hello\nEOF\necho INJECTED unsigned\n").rstrip("\n")
        command = f"gh pr comment 5 --body \"$(cat <<'EOF'\n{signed}\nEOF\n)\""
        self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_a_typed_placeholder_is_never_read_as_a_heredoc(self):
        body = self.good.rstrip("\n")
        for command in (
            f"gh pr comment 5 --body \"$(cat <<'EOF'\n{body}\nEOF\n)\" --body __PROSE_HEREDOC_0__",
            "gh pr comment 5 --body __PROSE_HEREDOC_0__",
        ):
            with self.subTest(command):
                self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_an_unbalanced_paren_in_a_heredoc_body_is_not_trusted(self):
        signed = prose.sign('Done)"; echo INJECTED; echo "(\n').rstrip("\n")
        command = f"gh pr comment 5 --body \"$(cat <<'EOF'\n{signed}\nEOF\n)\""
        self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_a_quoted_tilde_path_is_read_literally(self):
        home = self.dir / "home"
        home.mkdir()
        (home / "body.md").write_text(self.good)
        (self.dir / "~").mkdir()
        (self.dir / "~" / "body.md").write_text("UNSIGNED\n")
        payload = self.bash("gh pr comment 5 --body-file '~/body.md'")
        env = dict(os.environ, HOME=str(home))
        result = run(["sh", str(POST_HOOK), "--host", "claude"], stdin=json.dumps(payload), env=env)
        self.assertEqual(result.returncode, 2)

    def test_flags_that_source_a_body_elsewhere_are_blocked(self):
        for command in (
            "gh pr create --fill",
            "gh pr create -f",
            "gh pr create -t x --fill-verbose",
            "gh pr create --recover state.json",
            "gh issue create -t x --recover state.json",
            "gh pr create -t x -T bug_report",
            "gh pr comment 1 -e",
        ):
            with self.subTest(command):
                self.assertEqual(self.hook(self.bash(command)).returncode, 2)
        for command in ("gh pr close 1", "gh pr review 1 --approve"):
            with self.subTest(command):
                self.assertEqual(self.hook(self.bash(command)).returncode, 0)

    def test_a_heredoc_body_bash_3_would_cut_or_join_is_not_trusted(self):
        for text in (
            "'(' x.# )\" --body 'UNSIGNED' ; : \"\nharmless words\n",
            "# x \\\n(\nmore\n",
            "Run:\n    make build \\\n      FLAGS=1\n",
        ):
            signed = prose.sign(text).rstrip("\n")
            command = f"gh pr comment 1 --body \"$(cat <<'EOF'\n{signed}\nEOF\n)\""
            with self.subTest(text):
                self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_a_word_zsh_would_expand_is_not_read(self):
        (self.dir / "=notes").write_text(self.good)
        self.assertEqual(self.hook(self.bash("gh pr comment 1 --body-file =notes")).returncode, 2)

    def test_a_heredoc_body_with_ansi_c_or_locale_quoting_is_not_trusted(self):
        for text in ("Split on tabs with IFS=$'\\t' here.\n", 'Say $"hello" here.\n'):
            signed = prose.sign(text).rstrip("\n")
            command = f"gh pr comment 1 --body \"$(cat <<'EOF'\n{signed}\nEOF\n)\""
            with self.subTest(text):
                self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_an_empty_quoted_prefix_does_not_hide_a_zsh_equals_word(self):
        (self.dir / "=post").write_text(self.good)
        self.assertEqual(self.hook(self.bash("gh pr comment 1 --body-file ''=post")).returncode, 2)

    def test_an_unreadable_payload_fails_open(self):
        self.assertEqual(self.hook("not json gh").returncode, 0)

    def test_cursor_gets_json_either_way(self):
        allow = self.hook({"command": "ls", "cwd": str(self.dir)}, host="cursor")
        self.assertEqual(json.loads(allow.stdout), {"permission": "allow"})
        deny = self.hook({"tool_name": "add_issue_comment", "mcp_server_name": "github",
                          "tool_input": json.dumps({"body": "x"})}, host="cursor")
        self.assertEqual(deny.returncode, 0)
        self.assertEqual(json.loads(deny.stdout)["permission"], "deny")
        passing = self.hook({"command": "gh pr view 3", "cwd": str(self.dir)}, host="cursor")
        self.assertEqual(json.loads(passing.stdout), {"permission": "allow"})

    def test_a_command_that_only_mentions_a_gh_post_passes(self):
        for command in (
            # A script whose text names a gh post, as data, in a quoted heredoc.
            "python3 - <<'EOF'\n# then run gh issue edit 5 --add-label x\n"
            "open('notes.md', 'w').write('Claim it with `gh issue edit 5 --add-label claimed`.')\nEOF\n",
            "cat > notes.md <<'EOF'\nrun gh pr create, it's easy\nEOF",
            "cat > notes.md <<-EOF\n\tgh pr comment 1 --body 'x'\n\tEOF\necho done",
            'grep -rn "gh pr create" .',
            "git commit -m 'docs: explain gh issue comment' && git push",
            "ls # later: gh pr create --fill",
            "python3 /x/prose.py sign --goals 'gh pr create' && echo ok",
        ):
            with self.subTest(command):
                result = self.hook(self.bash(command))
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_gh_command_that_posts_no_prose_passes_in_a_compound_command(self):
        for command in (
            "cd /tmp && gh issue edit 12 --add-label claimed",
            "gh issue edit 12 --add-label claimed 2>&1",
            "gh issue edit 12 --add-label claimed --remove-label ready && gh issue view 12",
            "gh pr ready 3 && gh pr edit 3 --add-reviewer x --milestone v1 >/dev/null",
            "gh issue close 3; gh issue reopen 4",
            "(cd sub && gh pr edit 3 --add-assignee @me)",
            "git push -u origin HEAD\ngh pr edit 3 --remove-label wip",
        ):
            with self.subTest(command):
                result = self.hook(self.bash(command))
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_post_in_a_compound_command_is_still_blocked(self):
        (self.dir / "body.md").write_text(self.good)
        for command in (
            "cd /tmp && gh issue edit 12 --add-label x --body 'unsigned'",
            "gh issue edit 12 --add-label x && gh issue comment 12 --body 'unsigned'",
            "gh issue comment 1 --body 'unsigned' 2>&1",
            "cd sub && gh pr comment 3 --body-file body.md",
            "gh issue edit 12 --add-label x < body.md",
            "cat body.md | gh issue edit 12 --add-label x",
            "cat > a.md <<'EOF'\ngh pr create\nEOF\ngh pr comment 1 --body 'unsigned'",
            "python3 - <<'EOF' && gh pr comment 1 --body 'unsigned'\nprint(1)\nEOF\n",
            "gh --verbose pr comment 1 --body 'unsigned' && true",
            "GH_REPO=o/r gh issue edit 1 --add-label x; true",
        ):
            with self.subTest(command):
                self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_text_a_shell_would_run_is_not_read_as_data(self):
        for command in (
            "bash <<'EOF'\ngh pr comment 1 --body 'unsigned'\nEOF",
            "sh -c 'gh pr comment 1 --body unsigned'",
            "echo 'gh issue comment 1 --body x' | /bin/bash",
            "eval 'gh pr create --body x'",
            "ssh host 'gh pr comment 1 --body x'",
            "xargs -n1 gh pr comment --body x < list",
            "env gh pr comment 1 --body x",
            "cat <<EOF\n$(gh pr comment 1 --body x)\nEOF",
            "cat <<EOF\n`gh pr comment 1 --body x`\nEOF",
            "cat <<EOF\nend \\\nEOF\ngh pr comment 1 --body x\nEOF",
            "# it's\ngh pr comment 1 --body x\n# '",
            "echo x # ; gh pr comment 1 --body x",
            "cat <<'EOF'\ngh pr comment 1 --body x\n",
            "(cat <<'EOF'\ngh pr create\nEOF\n); gh pr comment 1 --body x",
            "[ -f x ] || gh pr comment 1 --body x",
        ):
            with self.subTest(command):
                self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_text_another_command_may_run_is_not_read_as_data(self):
        for command in (
            "xargs gh <<< 'pr comment 1 --body hi'",
            "xargs gh pr <<'EOF'\ncomment 1 --body hi\nEOF",
            "echo comment 1 --body hi | xargs gh pr # then gh pr comment",
            "trap 'gh pr comment 1 --body hi' EXIT",
            "env -S 'gh pr comment 1 --body hi'",
            "echo 'gh pr comment 1 --body hi' | xargs env -S",
            "echo 'gh pr comment 1 --body hi' |\nsh",
            "echo 'gh pr comment 1 --body hi' | # run it\nsh",
            "echo 'gh pr comment 1 --body hi' | (true; sh)",
            "(sh) <<< 'gh pr comment 1 --body hi'",
            "(sh) <<'EOF'\ngh pr comment 1 --body hi\nEOF",
            'cat <<"E\\OF"\nx\nE\\OF\ngh pr comment 1 --body hi\nEOF',
        ):
            with self.subTest(command):
                self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_a_heredoc_body_after_an_open_substitution_is_not_skipped(self):
        # bash and zsh run the $( … ) first and read the heredoc body after
        # its closing line, so the lines below the operator are code.
        for command in (
            "cat <<echo $(\ngh pr comment 1 -b hello\necho\n)\necho",
            'cat <<true >/dev/null "$x" $(\ngh pr comment 1 -b hello\ntrue\n)\ntrue',
        ):
            with self.subTest(command):
                self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_only_a_single_ascii_digit_before_a_redirection_is_a_descriptor(self):
        # zsh reads `12>` as the argument 12 and a redirection; neither shell
        # reads a non-ASCII digit as a descriptor. Either way gh gets the word.
        for command in (
            "gh pr comment 1 -F 12>/dev/stderr",
            "cd . && gh pr comment 1 -b 12>/dev/stderr",
            "gh pr comment 1 -b ١>/dev/stderr",
        ):
            with self.subTest(command):
                self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_a_gh_post_split_by_quotes_in_a_longer_command_is_read(self):
        for command in (
            "echo 'gh pr comment' ; gh p''r comment 1 -b hello",
            "gh pr edit 5 --add-label x && gh p''r comment 5 -b hello",
        ):
            with self.subTest(command):
                self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_a_body_file_path_with_a_nul_byte_is_blocked(self):
        result = self.hook(self.bash("cd /tmp && gh pr comment 5 --body-file 'a\x00b'"))
        self.assertEqual(result.returncode, 2, result.stderr)

    def test_a_command_after_a_reserved_word_is_read_as_that_command(self):
        for command in (
            'if grep -q "gh pr create" README.md; then echo yes; fi',
            "! grep -q 'gh pr create' README.md",
            "time grep -rn 'gh pr create' .",
            "while false; do grep -n 'gh pr create' a.md; done",
            "{ echo 'gh pr create'; echo x; } > notes.md",
            'if [ -n "$x" ]; then gh issue edit 3 --add-label claimed; fi',
            "if gh pr view 3 >/dev/null 2>&1; then gh pr ready 3; "
            "else gh issue edit 3 --add-label blocked; fi",
            "for n in 3 4; do gh issue edit 3 --add-label x; done",
            "{ gh issue edit 3 --add-label x; }",
        ):
            with self.subTest(command):
                result = self.hook(self.bash(command))
                self.assertEqual(result.returncode, 0, result.stderr)
        for command in (
            "if true; then gh pr comment 1 --body x; fi",
            "{ gh pr comment 1 --body x; }",
            "! time gh issue comment 1 --body x",
            "if sh -c 'gh pr comment 1 --body x'; then true; fi",
            # A reserved word alone on a line leaves no command to read.
            "if true\nthen\ngh pr comment 1 --body x\nfi",
            "{\ngh pr comment 1 --body x\n}",
        ):
            with self.subTest(command):
                self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_a_word_that_only_contains_gh_does_not_name_it(self):
        for command in (
            "make gh-pages && gh issue edit 3 --add-label deployed",
            "npm run deploy:gh-pages && gh issue edit 3 --add-label deployed",
            "chmod +x scripts/gh-post.sh && gh issue edit 3 --add-label x",
        ):
            with self.subTest(command):
                result = self.hook(self.bash(command))
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_line_continuation_is_not_a_word(self):
        for command in (
            "cd repo && \\\n  grep -rn 'gh pr create' .",
            "cd repo && \\\n  gh issue edit 3 --add-label x",
            "cd repo && gh issue edit 3 \\\n  --add-label a \\\n  --add-label b",
            "git push && gh pr edit 3 \\\n  --add-reviewer alice",
        ):
            with self.subTest(command):
                result = self.hook(self.bash(command))
                self.assertEqual(result.returncode, 0, result.stderr)
        for command in (
            "cd repo && \\\n  gh pr comment 3 --body x",
            "cd repo && gh pr comment 3 \\\n  --body x",
            "cd repo && \\\ngh pr comment 3 --body x",
            # The shell removes the continuation first, so the delimiter is
            # unquoted and the body's $( … ) runs.
            "cat <<\\\nEOF\n$(gh pr comment 3 --body x)\nEOF\n",
            "cat <<E\\\nOF\n$(gh pr comment 3 --body x)\nEOF\n",
        ):
            with self.subTest(command):
                self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_a_closing_reserved_word_is_no_command_beside_a_pipe(self):
        for command in (
            "if git log --oneline | grep -q 'gh pr create'; then echo found; fi",
            "{ echo '# Notes'; echo 'Run gh pr create'; } | tee notes.md",
            "if grep -q 'gh pr create' a.md < /dev/null; then echo yes; fi",
            "while false; do echo 'gh pr create'; done | cat",
        ):
            with self.subTest(command):
                result = self.hook(self.bash(command))
                self.assertEqual(result.returncode, 0, result.stderr)
        for command in (
            "echo 'gh pr comment 1 --body x' | { sh; }",
            "echo 'gh pr comment 1 --body x' | if true; then sh; fi",
        ):
            with self.subTest(command):
                self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_a_pipe_matters_only_to_the_command_it_feeds(self):
        # Issue #14: a gh read, a pipe and a quoted post verb used as data,
        # in one command that posts nothing.
        for command in (
            'gh pr view 1\necho "review" | head -1',
            'gh pr view 1\necho "comment" | head -1',
            'gh pr view 1; echo "create" | head -1',
            'gh pr view 1\necho "hello" | head -1',
            'gh pr view 1\npython3 p.py --goals "review"',
            'python3 p.py --goals "review" | head -1',
            "gh pr view 156 --json body > body.md\n"
            'python3 prose.py sign --goals "review PR #156; know where it stands" 2>&1'
            " | grep -v '^$' | head -1",
            "gh pr list --search 'review-requested:@me' | head -5",
            "gh issue view 3 --comments |& grep -n 'gh pr create'",
            "cat body.md | gh pr view 3",
            "gh pr view 3 < /dev/null",
            "gh issue edit 3 --add-label x; grep -c 'gh pr comment' < notes.md",
            "gh pr view 3 > a.md\ncat <<'EOF' | tee b.md\ngh pr create\nEOF",
            "gh pr checks 3 | grep fail |\n  head -3; gh issue edit 3 --add-label ci",
        ):
            with self.subTest(command):
                result = self.hook(self.bash(command))
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_command_fed_by_a_pipe_or_redirection_must_be_a_data_command(self):
        (self.dir / "body.md").write_text(self.good)
        for command in (
            # gh fed text it could post.
            "cat body.md | gh pr comment 1 --body-file -",
            "cat body.md |& gh pr comment 1 -F -",
            "gh pr view 1; cat body.md | gh pr comment 1 -F -",
            "gh pr comment 1 -F - < body.md",
            "gh pr comment 1 -F - <<< 'unsigned'",
            "gh pr comment 1 -F - <<'EOF'\nunsigned\nEOF",
            "cat <<'EOF' |\nunsigned\nEOF\ngh pr comment 1 -F -",
            "echo x |\n\ngh pr comment 1 -F -",
            "echo x | # c\ngh pr comment 1 -F -",
            "echo x | time gh pr comment 1 -F -",
            "echo x | ! gh pr comment 1 -F -",
            "echo x | gh issue edit 1 --add-label y",
            # A command that may run what it reads.
            "gh pr view 1; echo 'gh pr comment 1 --body hi' | sh",
            "gh pr view 1; echo 'gh pr comment 1 --body hi' | xargs -I{} sh -c {}",
            "gh pr view 1; sh < comment.sh",
            "gh pr view 1\nsh <<'EOF'\ngh pr comment 1 --body hi\nEOF",
            "gh pr view 1; echo 'gh pr comment 1 --body hi' | cat $(sh)",
            "gh pr view 1; echo 'gh pr comment 1 --body hi' | $(echo sh)",
            # stdin that reaches a group, loop or subshell.
            "gh pr view 1; echo 'gh pr comment 1 --body hi' | (sh)",
            "gh pr view 1; echo 'gh pr comment 1 --body hi' | { sh; }",
            "gh pr view 1; echo 'gh pr comment 1 --body hi' | while read l; do sh; done",
            "gh pr view 1; { sh; cat; } < comment.txt",
            "gh pr view 1; (sh; cat) < comment.txt",
            "gh pr view 1; while read l; do sh; done < comment.txt",
            "gh pr view 1; { sh; cat } < comment.txt",
            "gh pr view 1; x=$(sh) <<< 'gh pr comment 1 --body hi'",
        ):
            with self.subTest(command):
                self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_the_block_names_the_command_a_pipe_feeds(self):
        result = self.hook(self.bash("gh pr view 1; echo 'gh pr comment 1 --body hi' | sh"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("`sh` reads", result.stderr)

    def test_a_gh_read_command_naming_a_post_verb_passes_in_a_longer_command(self):
        for command in (
            "cd repo && gh pr list --search 'review-requested:@me'",
            "cd repo && gh issue list --label new",
        ):
            with self.subTest(command):
                result = self.hook(self.bash(command))
                self.assertEqual(result.returncode, 0, result.stderr)
        for command in (
            "cd repo && gh pr -R o/r comment 1 --body x",
            "cd repo && gh pr --repo=o/r comment 1 --body x",
        ):
            with self.subTest(command):
                self.assertEqual(self.hook(self.bash(command)).returncode, 2)

    def test_printf_and_test_may_run_a_subscript_so_their_text_is_not_data(self):
        # bash 4+ evaluates an array subscript in `printf -v` and `test -v`,
        # command substitution included, so the quoted text can run gh.
        for command in (
            "printf -v 'a[$(gh pr comment 1 --body hi)]' x",
            "test -v 'a[$(gh pr comment 1 --body hi)]'",
            "[ -v 'a[$(gh pr comment 1 --body hi)]' ]",
        ):
            with self.subTest(command):
                self.assertEqual(self.hook(self.bash(command)).returncode, 2)


class CommitHookBase(unittest.TestCase):
    """A repository with one commit, and the hook's cursor set past it."""

    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)
        self.repo.write("a.py", "x = 1\n")
        self.repo.commit("base\n")
        self.hook()  # sets the cursor, so later runs judge only new commits

    def hook(self, script=COMMIT_HOOK, env=None):
        payload = json.dumps({"cwd": str(self.repo.path)})
        full = dict(os.environ, TMPDIR=tempfile.gettempdir(), **(env or {}))
        return run(["sh", str(script), "--host", "claude"], stdin=payload, env=full)

    def callback(self, sha="HEAD"):
        """commit_trailer_verify, as the library calls it."""
        env = dict(os.environ, PROSE_SCRIPTS=str(HERE))
        return run(["sh", "-c", '. "$0" && commit_trailer_verify "$1" ignored', str(HOOK_REPORT), sha],
                   cwd=self.repo.path, env=env)


class CommitHook(CommitHookBase):
    """prose's commit hook: the shared library's report, and the callback
    prose gives it, called directly by sourcing hook-report.sh. The library
    calling it is tested in CommitHookThroughTheLibrary."""

    def test_a_checked_commit_passes_the_callback(self):
        self.repo.write("README.md", "# Hi\n")
        message = "DOCS(x): add a readme\n"
        self.repo.commit(message, self.repo.trailers(message))
        result = self.callback()
        self.assertEqual((result.returncode, result.stdout), (0, "checked\n"))

    def test_a_commit_without_the_trailer_is_reported(self):
        self.repo.write("README.md", "# Hi\n")
        self.repo.commit("DOCS(x): add a readme\n")
        result = self.hook()
        self.assertEqual(result.returncode, 2)
        self.assertIn("without a Prose: trailer", result.stderr)
        self.assertIn("Ask before rewriting a pushed commit.", result.stderr)
        self.assertIn("Fix it with the prose skill's *Committing* steps.", result.stderr)
        self.assertIn("A person who does not want this check can turn it off:", result.stderr)
        self.assertIn("skills.py disable-hook prose", result.stderr)

    def test_a_prose_line_git_does_not_read_is_reported_as_such(self):
        self.repo.write("README.md", "# Hi\n")
        self.repo.commit("DOCS(x): add a readme\n\nProse: ✓ 0123:4567\n\nmore body\n")
        result = self.hook()
        self.assertEqual(result.returncode, 2)
        self.assertIn("without a Prose: trailer", result.stderr)
        self.assertIn("There is a Prose: line in there, but git does not read it as a trailer.",
                      result.stderr)

    def test_an_edited_message_fails_the_callback(self):
        self.repo.write("README.md", "# Hi\n")
        trailer = self.repo.trailers("DOCS(x): add a readme\n")
        self.repo.commit("DOCS(x): add a readme, edited\n", trailer)
        result = self.callback()
        self.assertEqual(result.returncode, 1)
        self.assertTrue(result.stdout.startswith("mismatch:"), result.stdout)

    def test_a_change_staged_after_the_check_fails_the_callback(self):
        self.repo.write("README.md", "# Hi\n")
        trailer = self.repo.trailers("DOCS(x): add a readme\n")
        self.repo.write("b.py", "y = 2\n")
        self.repo.commit("DOCS(x): add a readme\n", trailer)
        result = self.callback()
        self.assertEqual(result.returncode, 1)
        self.assertTrue(result.stdout.startswith("tree:"), result.stdout)

    def test_a_skip_value_fails_the_callback(self):
        self.repo.write("README.md", "# Hi\n")
        self.repo.commit("DOCS(x): add a readme\n", "Prose: skipped (no prose)")
        result = self.callback()
        self.assertEqual(result.returncode, 1)
        self.assertTrue(result.stdout.startswith("unrecognised:"), result.stdout)

    def test_a_commit_the_callback_cannot_read_exits_3(self):
        self.assertEqual(self.callback("nope").returncode, 3)

    def test_a_cherry_pick_carrying_a_valid_trailer_is_not_reported(self):
        self.repo.git("checkout", "-q", "-b", "side")
        self.repo.write("README.md", "# Hi\n")
        message = "DOCS(x): add a readme\n"
        self.repo.commit(message, self.repo.trailers(message))
        self.repo.git("checkout", "-q", "-")
        self.repo.write("b.py", "y = 2\n")
        self.repo.commit("other\n", self.repo.trailers("other\n"))
        self.hook()
        self.repo.git("cherry-pick", "side")
        result = self.hook()
        self.assertEqual((result.returncode, result.stderr), (0, ""))
class HookReportText(unittest.TestCase):
    def test_the_rejected_trailer_report_names_the_section_and_no_path(self):
        # The report names SKILL.md's section rather than restating its
        # commands, and names none of prose's files: the section gives each
        # path from the skill's base directory.
        result = run(["sh", "-c", f'. "{HOOK_REPORT}"; rejected="abc123 x -- mismatch: y"; '
                                  'commit_trailer_report; printf "%s\\n" "$REPORT"'])
        self.assertIn("carry a Prose: trailer that does not hold", result.stdout)
        self.assertIn("abc123 x -- mismatch: y", result.stdout)
        self.assertIn("Fix it with the prose skill's *Committing* steps.", result.stdout)
        self.assertNotIn("prose check", result.stdout)
        self.assertNotIn(".sh", result.stdout)

    def test_the_first_block_names_the_repository_and_the_second_follows_a_blank_line(self):
        # The library sets repo_label to the repository's top, which matters
        # most for a commit in a submodule. One batch can hold a commit with no
        # trailer and another whose trailer fails verification.
        result = run(["sh", "-c", f'. "{HOOK_REPORT}"; repo_label=/r/sub; count_unchecked=1; '
                                  'unchecked="abc1234 a"; rejected="def5678 b -- tree: x"; '
                                  'commit_trailer_report; printf "%s\\n" "$REPORT"'])
        self.assertIn("landed without a Prose: trailer in /r/sub.", result.stdout)
        self.assertIn("abc1234 a\n\nprose: 1 commit(s) carry", result.stdout)


class CommitHookThroughTheLibrary(CommitHookBase):
    """The hook end to end: the shared library finds each new commit and calls
    prose's commit_trailer_verify, and reports what it returns."""

    def test_a_commit_made_through_the_commit_script_is_quiet(self):
        self.repo.write("README.md", "# Hi\n")
        trailer = self.repo.trailers("DOCS(x): add a readme\n")
        made = self.repo.commit_script("DOCS(x): add a readme", "", "--verified-value",
                                       str(VERIFY_STAGED), "Prose", trailer[len("Prose: "):])
        self.assertEqual(made.returncode, 0, made.stderr)
        result = self.hook()
        self.assertEqual((result.returncode, result.stderr), (0, ""))

    def test_an_edited_message_is_reported(self):
        self.repo.write("README.md", "# Hi\n")
        trailer = self.repo.trailers("DOCS(x): add a readme\n")
        self.repo.commit("DOCS(x): add a readme, edited\n", trailer)
        result = self.hook()
        self.assertEqual(result.returncode, 2)
        self.assertIn("carry a Prose: trailer that does not hold", result.stderr)
        self.assertIn("DOCS(x): add a readme, edited -- mismatch:", result.stderr)

    def test_a_change_staged_after_the_check_is_reported(self):
        self.repo.write("README.md", "# Hi\n")
        trailer = self.repo.trailers("DOCS(x): add a readme\n")
        self.repo.write("b.py", "y = 2\n")
        self.repo.commit("DOCS(x): add a readme\n", trailer)
        result = self.hook()
        self.assertEqual(result.returncode, 2)
        self.assertIn("DOCS(x): add a readme -- tree:", result.stderr)

    def test_a_skip_note_passed_to_the_commit_script_is_reported(self):
        # The commit script runs no verifier for a value starting "skipped";
        # prose has no skip value, so the hook reports the commit.
        self.repo.write("README.md", "# Hi\n")
        made = self.repo.commit_script("DOCS(x): add a readme", "", "--verified-value",
                                       str(VERIFY_STAGED), "Prose", "skipped (no prose)")
        self.assertEqual(made.returncode, 0, made.stderr)
        result = self.hook()
        self.assertEqual(result.returncode, 2)
        self.assertIn("-- unrecognised: Prose: skipped (no prose)", result.stderr)
class CommitScript(unittest.TestCase):
    """The commit path SKILL.md gives: the shared commit script, with prose's
    --verified-value option, alone or beside bug-hunter's."""

    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)
        self.repo.write("a.py", "x = 1\n")
        self.repo.commit("base\n")
        self.base = self.head()

    def head(self):
        return self.repo.git("rev-parse", "HEAD").strip()

    def prose_family(self, trailer):
        return ["--verified-value", str(VERIFY_STAGED), "Prose", trailer[len("Prose: "):]]

    def test_a_checked_commit_lands_and_verifies(self):
        self.repo.write("README.md", "# Hi\n")
        trailer = self.repo.trailers("DOCS(x): add a readme\n\nWhy it is needed.\n")
        made = self.repo.commit_script("DOCS(x): add a readme", "Why it is needed.",
                                       *self.prose_family(trailer),
                                       "--co-authored-by", "A <a@example.com>")
        self.assertEqual(made.returncode, 0, made.stderr)
        self.assertEqual(self.repo.git("log", "-1", "--format=%(trailers:key=Prose,valueonly)").strip(),
                         trailer[len("Prose: "):])
        verified = self.repo.verify()
        self.assertEqual((verified.returncode, verified.stdout), (0, "checked\n"))

    def test_a_message_signed_from_a_file_commits_from_that_file(self):
        self.repo.write("README.md", "# Hi\n")
        message = "DOCS(x): add a readme\n\nWhy it's needed: \"quotes\", $HOME and `ticks`.\n"
        trailer = self.repo.trailers(message)  # signs the file .msg
        made = run(["sh", str(COMMIT_SCRIPT), *self.prose_family(trailer),
                    "--message-file", ".msg", "--"], cwd=self.repo.path)
        self.assertEqual(made.returncode, 0, made.stderr)
        self.assertEqual(self.repo.git("log", "-1", "--format=%s").strip(), "DOCS(x): add a readme")
        verified = self.repo.verify()
        self.assertEqual((verified.returncode, verified.stdout), (0, "checked\n"))

    def test_an_edited_message_is_refused_before_the_commit(self):
        self.repo.write("README.md", "# Hi\n")
        trailer = self.repo.trailers("DOCS(x): add a readme\n")
        made = self.repo.commit_script("DOCS(x): add a readme, edited", "", *self.prose_family(trailer))
        self.assertEqual(made.returncode, 1)
        self.assertIn("mismatch:", made.stderr)
        self.assertEqual(self.head(), self.base)

    def test_a_change_staged_after_the_check_is_refused_before_the_commit(self):
        self.repo.write("README.md", "# Hi\n")
        trailer = self.repo.trailers("DOCS(x): add a readme\n")
        self.repo.write("b.py", "y = 2\n")
        made = self.repo.commit_script("DOCS(x): add a readme", "", *self.prose_family(trailer))
        self.assertEqual(made.returncode, 1)
        self.assertIn("tree:", made.stderr)
        self.assertEqual(self.head(), self.base)

    def test_it_composes_with_bug_hunter_in_one_commit(self):
        self.repo.write("b.py", "y = 2\n")
        trailer = self.repo.trailers("FIX(x): set y\n")
        made = self.repo.commit_script(
            "FIX(x): set y", "",
            "--minted-by", str(BUG_HUNTER_MINT), "Bug-hunter", "1 iteration, 1 bug fixed",
            *self.prose_family(trailer))
        self.assertEqual(made.returncode, 0, made.stderr)
        trailers = self.repo.git("log", "-1", "--format=%(trailers:only,unfold)").split("\n")
        tree = self.repo.git("rev-parse", "HEAD^{tree}").strip()
        self.assertEqual([t for t in trailers if t], [
            "Bug-hunter: 1 iteration, 1 bug fixed", f"Bug-hunter-Tree: {tree}", trailer])
        self.assertEqual(self.repo.verify().returncode, 0, self.repo.verify().stdout)

    def test_check_with_amend_says_how_to_amend(self):
        self.repo.write("README.md", "# Hi\n")
        self.repo.commit("DOCS(x): add a readme\n")
        self.repo.write("README.md", "# Hello\n")
        result = self.repo.prose("check", "-F", "-", "--goals", "g", "--amend",
                                 stdin="DOCS(x): add a readme\n")
        self.assertEqual(result.returncode, 4, result.stderr)
        self.assertNotIn("Commit through the commit script", result.stdout)
        self.assertIn("git commit --amend", result.stdout)

    def test_the_amend_instruction_names_the_file_that_was_checked(self):
        self.repo.write("README.md", "# Hi\n")
        self.repo.commit("DOCS(x): add a readme\n")
        self.repo.write("README.md", "# Hello\n")
        (self.repo.path / "final msg.txt").write_text("DOCS(x): add a readme\n")
        result = self.repo.prose("check", "-F", "final msg.txt", "--goals", "g", "--amend")
        self.assertEqual(result.returncode, 4, result.stderr)
        self.assertIn("git commit --amend -F 'final msg.txt' --trailer", result.stdout)
        from_stdin = self.repo.prose("check", "-F", "-", "--goals", "g", "--amend",
                                     stdin="DOCS(x): add a readme\n")
        self.assertNotIn("msg.txt", from_stdin.stdout)
        self.assertIn("-F <a file holding exactly the text checked>", from_stdin.stdout)

    def test_verify_staged_refuses_a_line_that_is_not_a_prose_trailer(self):
        result = run([str(VERIFY_STAGED), "Prose: checked"], cwd=self.repo.path, stdin="Title")
        self.assertEqual(result.returncode, 1)
        self.assertTrue(result.stdout.startswith("unrecognised:"), result.stdout)


class Gate(unittest.TestCase):
    """The hook that blocks a session's first file write or post until a first call ran."""

    def setUp(self):
        self.state = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.state, True)
        self.env = dict(os.environ, XDG_STATE_HOME=str(self.state / "missing" / "state"))

    def gate(self, tool, tool_input, session="s-1", env=None, cwd=None):
        payload = {"session_id": session, "hook_event_name": "PreToolUse", "cwd": str(cwd or self.state),
                   "tool_name": tool, "tool_input": tool_input}
        return run(["/bin/sh", str(GATE), "--host", "claude"], stdin=json.dumps(payload),
                   env=env or self.env)

    def start(self, *extra, env=None):
        result = run([sys.executable, str(SCRIPT), "start", "--goals", "g", *extra],
                     cwd=self.state, env=env or self.env)
        self.assertEqual(result.returncode, 0, result.stderr)

    def assertBlocked(self, result, what):
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn(what, result.stderr)
        self.assertIn("start --goals", result.stderr)

    def assertAllowed(self, result):
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))

    def test_a_write_without_a_path_key_still_reaches_the_gate(self):
        # The wrapper skips only Bash commands that name no gh; every other
        # matched tool goes to prose.py, whatever its input's keys are called.
        for tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
            with self.subTest(tool):
                self.assertBlocked(self.gate(tool, {"path": "/w/a.md", "content": "x"}), f"this {tool}")
        self.assertAllowed(self.gate("Bash", {"command": "ls"}))

    def test_it_blocks_the_first_file_edit_until_a_first_call_then_stays_silent(self):
        edit = {"file_path": "/w/docs/guide.md", "old_string": "a", "new_string": "b"}
        blocked = self.gate("Edit", edit)
        self.assertBlocked(blocked, "this Edit of /w/docs/guide.md")
        self.assertIn("--session s-1", blocked.stderr)
        self.start("--session", "s-1")
        self.assertAllowed(self.gate("Edit", edit))
        self.assertAllowed(self.gate("Write", {"file_path": "/w/README", "content": "x"}))
        self.assertBlocked(self.gate("Edit", edit, session="s-2"), "guide.md")

    def test_the_session_id_from_the_environment_opens_it(self):
        self.start(env=dict(self.env, CLAUDE_CODE_SESSION_ID="s-1"))
        self.assertAllowed(self.gate("Write", {"file_path": "/w/openspec/x/spec.yaml", "content": "k: v"}))

    def test_an_edit_that_is_neither_a_doc_nor_a_comment_is_blocked(self):
        self.assertBlocked(self.gate("Edit", {"file_path": "/w/a.py", "old_string": "x = 1",
                                              "new_string": "x = 2"}), "this Edit of /w/a.py")

    def test_a_write_to_any_path_is_blocked(self):
        for tool, tool_input in (
                ("Write", {"file_path": "/w/data.json", "content": "{}"}),
                ("Write", {"file_path": "/w/node_modules/d/README.md", "content": "x"}),
                ("Write", {"file_path": "/w/build/out/a.py", "content": "x = 1\n"}),
                ("Write", {"file_path": "rel/Dockerfile", "content": "FROM alpine\n"}),
                ("MultiEdit", {"file_path": "/w/a.ts", "edits": [{"old_string": "a", "new_string": "b"}]}),
                ("NotebookEdit", {"notebook_path": "/w/n.ipynb", "cell_type": "code", "new_source": "x = 1"}),
                ("NotebookEdit", {"notebook_path": "/w/n.ipynb", "edit_mode": "delete", "cell_id": "c1"})):
            with self.subTest(tool=tool, path=tool_input.get("file_path") or tool_input.get("notebook_path")):
                path = tool_input.get("file_path") or tool_input.get("notebook_path")
                self.assertBlocked(self.gate(tool, tool_input), f"this {tool} of {path}")

    def test_after_start_every_call_passes(self):
        self.start("--session", "s-1")
        for tool, tool_input in (
                ("Write", {"file_path": "/w/data.json", "content": "{}"}),
                ("Edit", {"file_path": "/w/a.py", "old_string": "x", "new_string": "# why\nx"}),
                ("MultiEdit", {"file_path": "/w/a.ts", "edits": [{"old_string": "a", "new_string": "b"}]}),
                ("NotebookEdit", {"notebook_path": "/w/n.ipynb", "cell_type": "markdown", "new_source": "# N"}),
                ("Bash", {"command": "gh pr create --body-file signed.md"}),
                ("mcp__github__add_issue_comment", {"body": "Hi."})):
            with self.subTest(tool):
                self.assertAllowed(self.gate(tool, tool_input))

    def test_tools_that_write_nothing_pass(self):
        self.assertAllowed(self.gate("Read", {"file_path": "/w/README.md"}))
        self.assertAllowed(self.gate("Grep", {"pattern": "x", "path": "/w"}))

    def test_it_blocks_a_gh_post_but_not_other_commands(self):
        self.assertBlocked(self.gate("Bash", {"command": "gh pr create --body-file signed.md"}),
                           "this gh post")
        self.assertBlocked(self.gate("mcp__github__add_issue_comment", {"body": "Hi."}), "mcp__github__")
        for command in ("ls", "gh pr view 3", "git commit -m x",
                        "cd /tmp && gh issue edit 1 --add-label y",
                        "cat > a.md <<'EOF'\nrun gh pr create\nEOF"):
            with self.subTest(command):
                self.assertAllowed(self.gate("Bash", {"command": command}))
        self.assertAllowed(self.gate("mcp__github__get_pull_request", {"pullNumber": 3}))

    def test_it_does_not_block_its_own_start_command(self):
        command = "python3 /x/prose.py start --goals 'review the gh pr create flow' --session s"
        self.assertAllowed(self.gate("Bash", {"command": command}))
        self.assertBlocked(self.gate("Bash", {"command": "python3 /x/prose.py start --goals g | gh pr create --body x"}),
                           "this gh post")

    def test_the_block_message_does_not_promise_a_token_from_start(self):
        blocked = self.gate("Write", {"file_path": "/w/README.md", "content": "x"})
        self.assertNotIn("pass token", blocked.stderr)

    def test_a_marked_session_does_not_read_the_file(self):
        self.start("--session", "s-1")
        fifo = self.state / "big.py"
        os.mkfifo(fifo)
        payload = {"session_id": "s-1", "cwd": str(self.state), "tool_name": "Edit",
                   "tool_input": {"file_path": str(fifo), "old_string": "a", "new_string": "# b"}}
        try:
            # Reading a FIFO with no writer blocks, so a gate that reads the
            # file before checking the session times out here.
            result = subprocess.run([sys.executable, str(SCRIPT), "hook-gate"], input=json.dumps(payload),
                                    capture_output=True, text=True, env=self.env, timeout=10)
        except subprocess.TimeoutExpired:
            self.fail("the gate read the file in a session whose first call already ran")
        self.assertEqual(result.returncode, 0, result.stderr)


    def test_it_fails_open(self):
        edit = {"file_path": "/w/README.md", "old_string": "a", "new_string": "b"}
        not_a_dir = self.state / "file"
        not_a_dir.write_text("")
        self.assertAllowed(self.gate("Edit", edit, env=dict(self.env, XDG_STATE_HOME=str(not_a_dir))))
        bin_dir = self.state / "bin"
        bin_dir.mkdir()
        for tool in ("cat", "dirname"):
            os.symlink(shutil.which(tool), bin_dir / tool)
        self.assertAllowed(self.gate("Edit", edit, env=dict(self.env, PATH=str(bin_dir))))
        for raw in ("not json", "[]", json.dumps({"tool_name": "Edit", "tool_input": edit})):
            with self.subTest(raw):
                self.assertAllowed(run(["/bin/sh", str(GATE)], stdin=raw, env=self.env))

    def test_it_fails_open_on_an_unreadable_state_directory(self):
        if os.geteuid() == 0:
            self.skipTest("root reads any directory")
        sessions = self.state / "home" / "prose" / "sessions"
        sessions.mkdir(parents=True)
        sessions.chmod(0)
        self.addCleanup(sessions.chmod, 0o700)
        env = dict(self.env, XDG_STATE_HOME=str(self.state / "home"))
        self.assertAllowed(self.gate("Edit", {"file_path": "/w/README.md", "old_string": "a",
                                              "new_string": "b"}, env=env))


if __name__ == "__main__":
    unittest.main(verbosity=2)

