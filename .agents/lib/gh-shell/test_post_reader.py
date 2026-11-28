#!/usr/bin/env python3
"""Tests for post_reader.py, the shared post reader, which prose's posting
hook and the inquisitor's post hook call. Each test checks one scenario of the
gh-post spec (openspec/changes/inquisitor/specs/gh-post/spec.md).

    python3 test_post_reader.py
"""

import json
import pathlib
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import post_reader  # noqa: E402
from post_reader import NoPost, Post, Unreadable  # noqa: E402


class Reader(unittest.TestCase):
    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        for name in ("c.md", "body.md", "b.md", "tmpl.md"):
            (self.dir / name).write_text(f"text of {name}\n")
        (self.dir / "m.md").write_text("User says: yes")
        (self.dir / "c.json").write_text(json.dumps({"body": "Done."}))
        (self.dir / "r.json").write_text(json.dumps(
            {"body": "ok", "comments": [{"path": "a.py", "body": "Why?"}]}))

    def read(self, command):
        return post_reader.read_command(command, str(self.dir))

    def bodies(self, command):
        found = self.read(command)
        self.assertIsInstance(found, list, f"{command!r} gave {found!r}")
        assert isinstance(found, list)
        return [post.body for post in found]

    def assert_no_post(self, *commands):
        for command in commands:
            with self.subTest(command=command):
                self.assertEqual(self.read(command), NoPost())

    def assert_unreadable(self, *commands):
        for command in commands:
            with self.subTest(command=command):
                found = self.read(command)
                self.assertIsInstance(found, Unreadable)
                assert isinstance(found, Unreadable)
                self.assertIn(post_reader.CANONICAL_FORMS, found.why)

    def payload(self, tool, tool_input):
        return post_reader.read_posts({"tool_name": tool, "tool_input": tool_input}, "claude")


class ReadPosts(Reader):
    # @scenario gh-post: Both post hooks read a post through the shared reader
    def test_a_hook_payload_s_post_is_read_from_its_file(self):
        payload = {"tool_name": "Bash", "cwd": str(self.dir),
                   "tool_input": {"command": "gh pr comment 5 --body-file c.md"}}
        self.assertEqual(post_reader.read_posts(payload, "claude"),
                         [Post("gh pr comment --body-file c.md", "text of c.md\n")])
        cursor = {"command": "gh pr comment 5 --body-file c.md", "cwd": str(self.dir)}
        self.assertEqual(post_reader.read_posts(cursor, "cursor"),
                         [Post("gh pr comment --body-file c.md", "text of c.md\n")])

    # @scenario gh-post: An MCP comment field is read
    def test_mcp_body_and_comment_keys_are_read_at_any_depth(self):
        for tool in ("mcp__github__add_issue_comment", "mcp__plugin_gh_github__review"):
            with self.subTest(tool=tool):
                self.assertEqual(self.payload(tool, {"comment": "ok"}), [Post("comment", "ok")])
        self.assertEqual(
            self.payload("mcp__github__create_review",
                         {"comments": [{"path": "a", "body": "nested"}]}),
            [Post("comments[0].body", "nested")])
        cursor = {"tool_name": "add_issue_comment", "mcp_server_name": "github",
                  "tool_input": json.dumps({"body": "x"})}
        self.assertEqual(post_reader.read_posts(cursor, "cursor"), [Post("body", "x")])
        self.assertEqual(self.payload("mcp__github__add_issue_comment", {"body": " "}),
                         NoPost())


class Linear(Reader):
    # @scenario gh-post: A Linear MCP comment and description are read
    def test_a_comment_and_a_description(self):
        for tool in ("mcp__linear__save_comment", "mcp__plugin_x_linear__save_comment"):
            with self.subTest(tool=tool):
                self.assertEqual(self.payload(tool, {"issueId": "A-1", "body": "User says: yes"}),
                                 [Post("body", "User says: yes", "linear")])
        self.assertEqual(
            self.payload("mcp__linear__save_issue",
                         {"title": "Retries?", "description": "Should retries back off?"}),
            [Post("description", "Should retries back off?", "linear")])
        for given in ({"id": "A-1", "patch": [{"op": "append", "text": "x"}]},
                      {"id": "A-1", "patch": [], "description": "x"},
                      {"team": "T", "template": "Bug"},
                      {"team": "T", "template": "Bug", "description": ""}):
            with self.subTest(given=given):
                self.assertIsInstance(self.payload("mcp__linear__save_issue", given),
                                      Unreadable)
        self.assertEqual(
            self.payload("mcp__linear__save_issue",
                         {"team": "T", "template": "Bug", "description": "mine"}),
            [Post("description", "mine", "linear")])
        cursor = {"tool_name": "save_comment", "mcp_server_name": "linear",
                  "tool_input": json.dumps({"body": "x"})}
        self.assertEqual(post_reader.read_posts(cursor, "cursor"),
                         [Post("body", "x", "linear")])

    # @scenario gh-post: A Linear MCP call with no text is no post
    def test_a_call_with_no_text(self):
        self.assertEqual(self.payload("mcp__linear__save_issue", {"id": "A-1", "state": "Done"}),
                         NoPost())
        self.assertEqual(self.payload("mcp__linear__get_issue", {"id": "A-1"}), NoPost())


class PostVerbs(Reader):
    # @scenario gh-post: The gh post verbs are a closed list
    def test_the_post_verbs_and_whole_words(self):
        for noun, verbs in (("pr", post_reader.PR_VERBS), ("issue", post_reader.ISSUE_VERBS)):
            for verb in verbs:
                with self.subTest(noun=noun, verb=verb):
                    # Each mentions a post verb, and a pipe into sh is no
                    # canonical form, so each is unreadable.
                    self.assert_unreadable(f"echo x | gh {noun} {verb} 5 | sh",
                                           f"gh {noun} {verb} 5 | sh")
        self.assert_unreadable("gh api -X DELETE repos/o/r/x | sh",
                               "python3 /abs/discord_bot.py post --message-file m.md | sh",
                               "echo /abs/discord_bot.py edit | sh")
        # Whole words only: --comments is not the word comment, --comment is.
        self.assert_no_post("gh pr view 5 --comments | sh", "gh issue review 5 | sh",
                            "gh pr view 5 | sh # comment-x", "gh prx comment | sh",
                            "gh repo view o/api | sh", "gh api repos/o/r/pulls/5 | sh",
                            "python3 /abs/discord_bot.py read | sh",
                            "echo /abs/discord_bot.py posted | sh")
        self.assert_unreadable("gh pr view 5 --comment | sh")

    # @scenario gh-post: A gh command off the list passes unread
    def test_gh_commands_off_the_list_send_no_post(self):
        self.assert_no_post(
            "gh release create v1.2 --notes 'Ready?'",
            "gh project item-create 1 --owner o --body 'Should retries back off?'",
            "gh agent-task create 'Should retries back off?'",
            "gh c 5 -b 'Should retries back off?'")

    # @scenario gh-post: A gh api read piped into a script is no post
    def test_a_gh_api_read_piped_into_python_is_no_post(self):
        script = "python3 -c 'import json, sys; print(json.load(sys.stdin)[\"title\"])'"
        self.assert_no_post(f"gh api repos/o/r/pulls/5 | {script}",
                            f"python3 /abs/github_app.py gh api repos/o/r/pulls/5 | {script}")

    # @scenario gh-post: A command that only runs prose is no post
    def test_a_command_that_only_runs_prose(self):
        self.assert_no_post("/abs/prose.py sign --goals 'approve the gh pr create body'",
                            "python3 /x/prose.py sign --pass abc < body.md > signed.md")
        self.assert_unreadable("/abs/prose.py sign --goals g; gh pr create --body x")


class Canonical(Reader):
    # @scenario gh-post: A post chained to another command is unreadable and the block names the forms
    def test_a_chained_post_is_unreadable(self):
        self.assert_unreadable("cd /x && gh pr comment 5 --body-file c.md",
                               "gh pr comment 5 --body-file c.md > out.txt")
        found = self.read("cd /x && gh pr comment 5 --body-file c.md")
        assert isinstance(found, Unreadable)
        self.assertIn("gh pr comment <number> --body-file <file>", found.why)

    # @scenario gh-post: A gh post run through another shell is unreadable
    def test_another_shell(self):
        self.assert_unreadable("sh -c 'gh pr comment 5 --body-file c.md'",
                               "bash -c 'gh issue create --body x'",
                               "eval 'gh pr comment 5 --body x'")

    # @scenario gh-post: A command the reader can't read exactly is unreadable
    def test_a_command_it_cannot_read(self):
        self.assert_unreadable("gh pr comment 5 --body `cat c.md`", "gh pr comment 5 --body $'x'",
                               'gh pr comment 5 --body "a$X"', "gh pr comment 5 $FLAGS",
                               'gh $N comment 5 --body "see issue, then edit"')

    # @scenario gh-post: Only a word the shell leaves alone is literal
    def test_literal_words(self):
        for word in ("'a $b'", '"a b"', "hi"):
            with self.subTest(word=word):
                self.assertTrue(post_reader.literal(word))
        for word in ('"$X"', "hi*", "~/notes", "'open", "=x", "''=x"):
            with self.subTest(word=word):
                self.assertFalse(post_reader.literal(word))

    # @scenario gh-post: A canonical gh post is read
    def test_canonical_gh_posts(self):
        self.assertEqual(self.read("gh pr create --title t --body-file body.md --base main"),
                         [Post("gh pr create --body-file body.md", "text of body.md\n")])
        self.assertEqual(self.bodies("gh issue comment 5 --body '$(not run)'"), ["$(not run)"])
        self.assertEqual(self.read("gh issue comment 5 --body 'Done.'"),
                         [Post("gh issue comment --body", "Done.")])
        self.assertEqual(self.read("gh issue close 5 --comment 'done'"),
                         [Post("gh issue close --comment", "done")])
        for command in (
                "gh pr create --title t --body x --repo o/r --base main --head f --draft "
                "--label a --assignee @me --reviewer b --milestone v1",
                "gh pr edit 5 --body x --title t", "gh issue edit 5 --body x",
                "gh pr review 5 --comment --body x", "gh pr review 5 --approve --body x",
                "gh pr review 5 --request-changes --body x", "gh pr reopen 5 --comment x",
                "gh issue reopen 5 --comment x", "gh pr close 5 --comment x"):
            with self.subTest(command=command):
                self.assertEqual(self.bodies(command), ["x"])

    # @scenario gh-post: A gh post in any other form is unreadable
    def test_other_gh_forms(self):
        self.assert_unreadable(
            "gh pr comment 5 -b hi", "gh pr comment 5 --body=hi", "gh pr comment 5 -F c.md",
            'gh pr comment 5 --body "$(cat c.md)"', "cat c.md | gh pr comment 5 --body-file -",
            "gh pr comment 5 --body-file -", "gh pr comment 5 --body-file missing.md",
            "gh pr comment 5 --body-file .",
            "gh pr create --title t --template tmpl.md", "gh pr create --fill",
            "gh pr revert 5 --body x", "gh pr comment 5 --body a --body b",
            "gh pr comment 5 --body a --body-file c.md", "gh pr comment --body x",
            "gh pr comment x5 --body x", "gh issue close 5 --body x",
            "gh pr review 5 --body x", "gh pr review 5 --comment",
            "gh pr review 5 --approve --comment --body x",
            "gh pr comment 5 --body x --edit-last", "gh -R o/r pr comment 5 --body x",
            "gh pr -R o/r comment 5 --body x", "gh pr comment 5 --body", "gh pr new --body x",
            "gh pr comment 5 --body hi*", "gh pr create --title t --body x --draft=true",
            "gh issue close 5 -c done", "gh pr create -t x -T tmpl.md",
            "gh pr merge 5 --body 'will comment'")


class Splitting(Reader):
    # @scenario gh-post: A command line splits into simple commands
    def test_operators_reserved_words_and_whole_words(self):
        self.assert_no_post(
            "gh pr view 1 | grep x || true && echo y; ls & wc -l; gh pr edit 1 --add-label x",
            "gh pr view 1 |& head -1; gh pr edit 1 --add-label x\ngh pr ready 1",
            "if gh pr view 3; then gh pr ready 3; else gh issue edit 3 --add-label x; fi",
            "while false; do echo 'gh pr create'; done; { gh pr edit 1 --add-label x; }",
            "! time grep -q 'gh pr create' a.md",
            "make gh-pages && gh issue edit 3 --add-label deployed")
        self.assert_unreadable("if true; then gh pr comment 1 --body x; fi",
                               "gh pr view 1 | gh pr comment 1 --body-file -")

    # @scenario gh-post: A subshell's and an unquoted substitution's commands are read
    def test_subshells_and_substitutions(self):
        self.assert_no_post("(cd sub && gh pr edit 3 --add-assignee @me)",
                            "echo $(gh pr edit 5 --add-assignee @me)")
        self.assert_unreadable("(cd sub && gh pr comment 3 --body hi)",
                               "echo $(gh pr comment 5 --body yo)",
                               "(gh pr comment 3 --body hi)")

    # @scenario gh-post: A backslash-newline and a comment are read as nothing
    def test_a_continuation_and_a_comment(self):
        found = self.read("gh pr comment 5 \\\n--body-file b.md # reply")
        self.assertEqual(found, [Post("gh pr comment --body-file b.md", "text of b.md\n")])

    # @scenario gh-post: A form the reader can't split exactly is unreadable
    def test_forms_it_cannot_split(self):
        post = "gh pr edit 1 --add-label x"
        self.assert_unreadable(
            f"echo `date`; {post}", f"cat <(echo); {post}", f"echo $'a'; {post}",
            f"echo ${{x:-y}}; {post}", f'echo "$(date)"; {post}', f"echo 'open; {post}",
            f"(cat <<'EOF'\nx\nEOF\n); {post}", f"cat <<EOF\n$(date)\nEOF\n{post}",
            f"{post} 12>/dev/null", f"{post} # it's", f"{post} # a; b")


class NoPostLines(Reader):
    # @scenario gh-post: A command that sends no body is no post
    def test_commands_that_send_no_body(self):
        self.assert_no_post(
            "gh pr edit 5 --add-label spec", "gh issue edit 5 --title 'Rename it?'",
            "gh pr edit 5 --add-assignee @me --add-reviewer bob --milestone v1",
            "gh pr ready", "gh issue close 5", "gh pr list", "gh pr review 5 --approve",
            "gh pr view 5 -c", "python3 /abs/github_app.py gh pr edit 5 --add-label spec")
        self.assert_unreadable("cd x && gh api -X DELETE repos/o/r/issues/comments/9",
                               "cd x && gh api -X POST repos/o/r/releases --input c.json",
                               "gh pr edit 5 --add-label $L --body x")

    # @scenario gh-post: A gh post quoted as data is no post
    def test_data_commands(self):
        self.assert_no_post("echo 'run gh pr create next'",
                            *[f"{name} 'gh pr create'" for name in sorted(
                                post_reader.DATA_COMMANDS)])
        self.assertEqual(post_reader.DATA_COMMANDS, {
            "echo", "cat", "tee", "grep", "egrep", "fgrep", "rg", "git", "python", "python3",
            "node", "jq", "head", "tail", "wc", "sort", "uniq", "cut", "tr", "ls", "cd", "true",
            "false"})

    # A word only ending in gh, pr or a verb is not that word.
    # @scenario gh-post: The gh post verbs are a closed list
    def test_a_word_ending_in_a_post_word(self):
        self.assert_no_post("xgh pr create -b hi", "echo gh pr xcreate",
                            "echo gh xpr create")

    # @scenario gh-post: gh named as another command's argument is unreadable
    def test_gh_as_an_argument(self):
        self.assert_unreadable("xargs gh pr comment 5 -b x", "echo gh pr create")

    # @scenario gh-post: Code given to a data command passes unread
    def test_code_given_to_a_data_command(self):
        self.assert_no_post("python3 -c 'import os; os.system(\"gh pr comment 5 -b x\")'",
                            "git -c 'alias.p=!gh pr comment 5 -b x' p",
                            "echo 'gh pr comment 5 -b x' | python3")


class Input(Reader):
    # @scenario gh-post: A gh post piped into a shell is unreadable
    def test_input_into_a_shell(self):
        self.assert_unreadable("echo 'gh pr comment 5 -b x' | sh",
                               "echo 'gh pr comment 5 -b x' |& sh",
                               "sh < c.md # gh pr create", "sh <> c.md # gh pr create",
                               "sh <&0 # gh pr create",
                               "sh <<'EOF'\ngh pr comment 5 -b x\nEOF",
                               "sh <<< 'gh pr comment 5 -b x'")

    # @scenario gh-post: Input that reaches several commands needs data commands only
    def test_input_into_a_group(self):
        self.assert_unreadable("echo 'gh pr comment 5 -b x' | { cat; gh pr view 5; }",
                               "echo 'gh pr comment 5 -b x' | (cat; gh pr view 5)",
                               "echo 'gh pr comment 5 -b x' | cat $(gh pr view 5)",
                               "echo 'gh pr comment 5 -b x' | while read l; do gh pr view; done",
                               "echo x | { cat; gh release view v1; }")
        self.assert_no_post("echo 'gh pr comment 5 -b x' | { cat; wc -l; }")

    # @scenario gh-post: Input may reach one gh command that uses no post verb
    def test_input_into_one_gh_command(self):
        self.assert_no_post("cat c.md | gh pr view 5 && gh pr edit 5 --add-label spec")
        self.assert_unreadable("cat c.md | gh pr edit 5 --add-label spec")

    # The scenario also has input into a gh api read send no post.
    # @scenario gh-post: Input that reaches another gh command is unreadable
    def test_input_into_another_gh_command(self):
        self.assert_unreadable("cat notes.md | gh release create v1 --notes-file -",
                               "gh release create v1 --notes-file - < notes.md")
        self.assert_no_post("cat q.json | gh api repos/o/r/pulls/5",
                            "cat q.json | gh pr view 5")


class GithubApp(Reader):
    # @scenario gh-post: A post sent through the github-app skill is read
    def test_the_script_s_forms(self):
        for command in (
                "python3 /abs/github_app.py gh pr create --title t --body-file body.md",
                'G="$HOME/github_app.py"; python3 "$G" --identity bot gh pr comment 5 '
                "--body-file body.md",
                "python3 $D/github_app.py --identity=bot run -- gh pr comment 5 "
                "--body-file body.md"):
            with self.subTest(command=command):
                self.assertEqual(self.bodies(command), ["text of body.md\n"])
        # prose reads a create's flags, such as --dry-run, from the gh call
        # github-app's script runs.
        self.assertEqual(post_reader.gh_command(
            "G=/s/github_app.py; python3 $G gh pr create --dry-run -b x"),
            ["pr", "create", "--dry-run", "-b", "x"])
        self.assertIsNone(post_reader.gh_command("cd x && gh pr create -b x"))

    # @scenario gh-post: A github-app post is told from a plain gh post
    def test_via_github_app(self):
        app = self.read("python3 /abs/github_app.py --identity bot gh pr comment 5 "
                        "--body-file c.md")
        plain = self.read("gh pr comment 5 --body-file c.md")
        assert isinstance(app, list) and isinstance(plain, list)
        self.assertEqual([p.via_github_app for p in app], [True])
        self.assertEqual([p.via_github_app for p in plain], [False])
        api = self.read("python3 /abs/github_app.py gh api repos/o/r/issues/5/comments "
                        "-X POST --input c.json")
        assert isinstance(api, list)
        self.assertEqual([p.via_github_app for p in api], [True])

    # @scenario gh-post: Another script given gh's arguments is unreadable
    def test_another_script(self):
        self.assert_unreadable("python3 /tmp/other.py gh pr comment 5 --body-file c.md")

    # @scenario gh-post: The github-app script after another command is unreadable where a direct gh call is
    def test_the_script_after_another_command(self):
        self.assert_unreadable(
            "cd x && python3 /abs/github_app.py gh pr comment 5 --body-file c.md",
            "cd x && gh pr comment 5 --body-file c.md")

    # @scenario gh-post: The github-app script through an unassigned variable is unreadable
    def test_an_unassigned_variable(self):
        for command in ('python3 "$G" gh pr comment 5 --body-file c.md',
                        'G=/abs/github_app.py; unset G; python3 "$G" gh pr comment 5 '
                        "--body-file c.md",
                        "G=/abs/github_app.py; G=/tmp/x.py; python3 $G gh pr comment 5 "
                        "--body-file c.md"):
            with self.subTest(command=command):
                found = self.read(command)
                self.assertIsInstance(found, Unreadable)
                assert isinstance(found, Unreadable)
                self.assertIn("Assign the variable in the same command", found.why)
                self.assertIn("write the script's path", found.why)

    # @scenario gh-post: A gh read through an unset G is no post
    def test_a_read_through_an_unset_variable(self):
        self.assert_no_post('python3 "$G" gh pr view 12 --comments')
        self.assert_unreadable('python3 "$G" gh api repos/o/r/pulls/5')

    # @scenario gh-post: A gh api call through the github-app script is judged as a direct one
    def test_gh_api_through_the_script(self):
        self.assertEqual(self.bodies(
            "python3 /abs/github_app.py gh api repos/o/r/issues/5/comments -X POST "
            "--input c.json"), ["Done."])
        self.assert_unreadable("python3 /abs/github_app.py --identity bot gh api -X DELETE "
                               "repos/o/r/issues/comments/9")


class Discord(Reader):
    # @scenario gh-post: A Discord post or edit is read from its file
    def test_post_and_edit(self):
        for verb in ("post --channel ops", "edit --message-id 9"):
            with self.subTest(verb=verb):
                found = self.read(f"python3 /abs/discord_bot.py --identity relay {verb} "
                                  "--message-file m.md")
                self.assertEqual(found, [Post(
                    f"discord-bot {verb.split()[0]} --message-file m.md", "User says: yes",
                    "discord")])
        self.assertEqual(self.bodies(
            "D=/abs/discord_bot.py; python3 $D post --message-file m.md --reply-to 5"),
            ["User says: yes"])
        self.assert_unreadable("cd x && python3 /abs/discord_bot.py --identity relay post "
                               "--channel ops --message-file m.md")

    # Any way but one --message-file naming a file that exists.
    # @scenario gh-post: A Discord message given any other way is unreadable
    def test_other_ways(self):
        self.assert_unreadable(
            "python3 /abs/discord_bot.py post --message yes",
            "printf 'User says: yes' | python3 /abs/discord_bot.py post --message -",
            "python3 /abs/discord_bot.py post --message=yes",
            "python3 /abs/discord_bot.py post --message-file -",
            "python3 /abs/discord_bot.py post --message-file=m.md",
            "python3 /abs/discord_bot.py post --message-file m.md --message-file c.md",
            "python3 /abs/discord_bot.py post --message-file m.md --message x",
            "python3 /abs/discord_bot.py post --message-file missing.md",
            "python3 /abs/discord_bot.py post --message-file 'm$X.md'",
            "python3 /abs/discord_bot.py post --message-file m.md < c.md",
            "python3 -I /abs/discord_bot.py post --message-file m.md",
            'D=/abs/discord_bot.py; unset D; python3 "$D" post --message-file m.md',
            "python3 /abs/discord_bot.py --ident relay post --message-file m.md")

    # @scenario gh-post: A Discord delete, read or thread is no post
    def test_calls_that_post_no_text(self):
        self.assert_no_post("python3 /abs/discord_bot.py delete --message-id 9",
                            "python3 /abs/discord_bot.py read --limit 5",
                            "python3 /abs/discord_bot.py thread --message-id 9 --name Retries",
                            "cd x && python3 /abs/discord_bot.py read --limit 5")

    # @scenario gh-post: A discord-bot post outside the reader's form is unreadable
    def test_outside_the_form(self):
        self.assert_unreadable("sh -c 'python3 /abs/discord_bot.py post --message-file m.md'",
                               "/abs/discord_bot.py post --message-file m.md")


class GhApiReads(Reader):
    # A gh api call in the form _api_read accepts.
    # @scenario gh-post: A plain read is a read
    def test_reads(self):
        self.assert_no_post(
            "gh api repos/{owner}/{repo}/pulls/5", "gh api 'search/issues?q=x'",
            "gh api search/issues?q=x", "gh api -X GET search/issues -f q=x",
            "gh api graphql -f query='{ viewer { login } }'",
            "gh api graphql -f query='query($n: Int) { viewer { login } }' -f n=1",
            'G=/abs/github_app.py && python3 "$G" gh api repos/o/r/pulls/5',
            "gh api repos/o/r/pulls --paginate --jq '.[].title'",
            "cd x && gh api repos/o/r/pulls/5 | jq .title")

    # @scenario gh-post: A gh api call in any other form is no read
    def test_other_forms(self):
        self.assert_unreadable(
            "gh api search/issues -f q=x", "gh api repos/o/r/issues/5/comments $F",
            'gh api -X "$M" repos/o/r/issues/5', "gh api graphql -f query='mutation { x }'",
            "gh api graphql -F query=@q.graphql", "gh api -X get search/issues -f q=x",
            "gh api -XGET search/issues", "gh api --method GET search/issues",
            "gh api -X 'GET' search/issues", "gh api -H 'Accept: x' repos/o/r/pulls/5",
            "gh api --header=x repos/o/r", "gh api repos/o/r --input q.json",
            "gh api repos/o/r -F a=b", "gh api repos/o/r --field a=b",
            "gh api repos/o/r --raw-field a=b", "gh api repos/o/r/pulls/$N",
            "gh api --unknown x repos/o/r", "gh api repos/o/r repos/o/s",
            "gh api /graphql -f query='{ viewer { login } }'",
            "gh api graphql -f query='{ a }' -f query='mutation { b }'",
            "gh api graphql -f query='{ a }' -F x=1", "gh api graphql",
            "cat a | xargs gh api repos/o/r/issues/5/comments")


class GhApiPosts(Reader):
    # @scenario gh-post: A canonical gh api post is read
    def test_canonical_posts(self):
        self.assertEqual(self.read("gh api repos/o/r/issues/5/comments -X POST --input c.json"),
                         [Post("gh api repos/o/r/issues/5/comments --input c.json body",
                               "Done.")])
        self.assertEqual(self.bodies("gh api repos/o/r/pulls/5/reviews -X POST --input r.json"),
                         ["ok", "Why?"])
        self.assertEqual(self.bodies("gh api -X POST --input c.json repos/o/r/issues"),
                         ["Done."])
        for endpoint, method in (
                ("issues", "POST"), ("issues/5", "PATCH"), ("issues/5/comments", "POST"),
                ("issues/comments/7", "PATCH"), ("pulls", "POST"), ("pulls/5", "PATCH"),
                ("pulls/5/comments", "POST"), ("pulls/comments/7", "PATCH"),
                ("pulls/5/reviews", "POST")):
            with self.subTest(endpoint=endpoint):
                self.assertEqual(self.bodies(
                    f"gh api repos/my-org/my.repo_1/{endpoint} -X {method} --input c.json"),
                    ["Done."])
                other = "PATCH" if method == "POST" else "POST"
                self.assert_unreadable(
                    f"gh api repos/o/r/{endpoint} -X {other} --input c.json")

    # @scenario gh-post: A gh api write in any other form is unreadable
    def test_other_writes(self):
        files = {"list.json": "[1]", "num.json": json.dumps({"body": 5}),
                 "none.json": json.dumps({"title": "x"}), "bad.json": "{",
                 "dup.json": '{"body": "ok", "body": "other"}',
                 "rc.json": json.dumps({"body": "ok", "comments": [{"path": "a"}]}),
                 "rcs.json": json.dumps({"body": "ok", "comments": "x"})}
        for name, text in files.items():
            (self.dir / name).write_text(text)
        self.assert_unreadable(
            "gh api repos/o/r/issues/5/comments -f body=hi",
            "gh api /repos/o/r/issues/5/comments -X POST --input c.json",
            "gh api repos/{owner}/{repo}/issues/5/comments -X POST --input c.json",
            "gh api repos/o/r/issues/5/comments?x=1 -X POST --input c.json",
            "gh api repositories/1/issues/5/comments -X POST --input c.json",
            "gh api repos/o/r/issues/5/comments -X POST --input c.json -f x=1",
            "gh api -X POST repos/o/r/releases --input c.json",
            "gh api -X DELETE repos/o/r/issues/comments/9",
            "gh api repos/o/../issues/5/comments -X POST --input c.json",
            "gh api repos/o/r/ISSUES/5/comments -X POST --input c.json",
            "gh api repos/o/r/issues/5/comments -X post --input c.json",
            "gh api repos/o/r/issues/5/comments --method POST --input c.json",
            "gh api repos/o/r/issues/5/comments -X POST --input=c.json",
            "gh api repos/o/r/issues/5/comments -X POST --input -",
            "gh api repos/o/r/issues/5/comments -X POST --input missing.json",
            "gh api repos/o/r/issues/5/comments -X POST -X POST --input c.json",
            *[f"gh api repos/o/r/pulls/5/reviews -X POST --input {name}" for name in files])
        # An issue edit with no body is unreadable, whatever else it changes.
        self.assert_unreadable("gh api repos/o/r/issues/5 -X PATCH --input none.json")


class Regressions(Reader):
    # @scenario gh-post: A canonical gh api post is read
    # @scenario gh-post: A gh api write in any other form is unreadable
    def test_a_quoted_api_is_still_gh_api(self):
        self.assert_unreadable("gh 'api' repos/o/r/issues/5/comments -f body=x",
                               'cd x && gh "api" repos/o/r/issues/5/comments -f body=x',
                               "python3 /abs/github_app.py gh 'api' repos/o/r/issues/5/comments "
                               "-f body=x")
        self.assertEqual(self.bodies(
            'gh "api" -X POST repos/o/r/issues/5/comments --input c.json'), ["Done."])

    # *A line whose simple commands send no text is no post* allows no gh
    # command but gh pr and gh issue, so any other in a line that mentions a
    # post verb is unreadable.
    # @scenario gh-post: A command that sends no body is no post
    def test_another_gh_command_in_a_line_that_mentions_a_post_verb(self):
        self.assert_unreadable("gh alias set c 'pr comment' && gh c 5 -b hi",
                               "gh alias set --clobber c 'pr comment 5 --body hi' ; gh c",
                               "gh release create v1 --notes 'see gh pr comment'")

    # The scenario counts a word whether quoted or not.
    # @scenario gh-post: The gh post verbs are a closed list
    def test_a_word_split_by_quotes_or_a_backslash_still_counts(self):
        self.assert_unreadable(
            "g\\h pr comment 5 --body hi",
            "gh pr co\\mment 5 --body hi", "gh a''pi repos/o/r/issues/5/comments -f body=hi",
            "python3 /abs/discord_bot.py p''ost --message yes",
            "python3 /abs/discord_bot.p''y post --message yes")
        # Every word literal, so the canonical form is read, as the shell joins it.
        for command in ("g''h pr comment 5 --body hi", "gh p''r comment 5 --body hi",
                        "gh pr com''ment 5 --body hi"):
            with self.subTest(command=command):
                self.assertEqual(self.bodies(command), ["hi"])

    # The mention check the scenario defines must finish within a hook's
    # time limit.
    # @scenario gh-post: The gh post verbs are a closed list
    def test_a_long_line_is_judged_quickly(self):
        import time
        for line in ("echo '" + "gh pr " * 700 + "'", "echo '" + "gh issue " * 700 + "'",
                     "echo '" + "gh " * 1400 + "'",
                     "echo '" + "discord_bot.py " * 700 + "'"):
            start = time.monotonic()
            self.read(line)
            self.assertLess(time.monotonic() - start, 1.0, line[:30])


class Pinned(Reader):
    """Behaviour no other test checks, found by mutation testing."""

    # @scenario gh-post: A post chained to another command is unreadable and the block names the forms
    def test_a_post_followed_by_another_command(self):
        self.assert_unreadable("gh pr comment 5 --body-file c.md && gh pr comment 6 --body x",
                               "gh pr comment 5 --body-file c.md && cd y")

    # The reader returns a result for a bare gh pr rather than raising.
    # @scenario gh-post: Input may reach one gh command that uses no post verb
    def test_input_into_a_bare_gh_pr(self):
        self.assertIsInstance(self.read("echo x | gh pr"), (NoPost, Unreadable))

    # @scenario gh-post: A command that sends no body is no post
    def test_an_attached_repo_before_the_noun(self):
        self.assert_no_post("gh --repo=o/r pr edit 5 --add-label spec",
                            "gh -Ro/r pr edit 5 --add-label spec",
                            "gh pr view 5 -c; echo 'next: gh pr comment'")
        self.assert_unreadable("gh --body hi pr comment 5")

    # @scenario gh-post: A gh post in any other form is unreadable
    def test_a_number_and_a_file_named_dash(self):
        (self.dir / "-").write_text("not what gh reads")
        self.assert_unreadable("gh pr comment \u0665 --body x", "gh pr comment 5 --body-file -")

    # @scenario gh-post: A canonical gh api post is read
    def test_comments_count_only_on_a_review(self):
        (self.dir / "f.json").write_text(json.dumps({"body": "ok", "comments": [{"body": "x"}]}))
        (self.dir / "g.json").write_text(json.dumps({"body": "ok", "comments": "x"}))
        for name in ("f.json", "g.json"):
            with self.subTest(name=name):
                self.assertEqual(self.bodies(
                    f"gh api repos/o/r/issues/5/comments -X POST --input {name}"), ["ok"])

    # @scenario gh-post: A gh api write in any other form is unreadable
    def test_input_that_is_a_json_string(self):
        (self.dir / "s.json").write_text(json.dumps("nobody"))
        self.assert_unreadable("gh api repos/o/r/issues/5/comments -X POST --input s.json")

    # @scenario gh-post: A Discord post or edit is read from its file
    def test_an_attached_message_id(self):
        self.assertEqual(self.bodies("python3 /abs/discord_bot.py edit --message-id=9 "
                                     "--message-file m.md"), ["User says: yes"])

    # @scenario gh-post: A Discord message given any other way is unreadable
    def test_a_message_file_with_no_file(self):
        self.assert_unreadable("python3 /abs/discord_bot.py post --message-file")

    # @scenario gh-post: A form the reader can't split exactly is unreadable
    def test_an_unsplittable_gh_api_line(self):
        self.assert_unreadable('gh api repos/o/r/issues/5/comments -f body="$(cat c.md)"',
                               "sh <<'EOF'\ngh api repos/o/r/issues/5/comments -f body=hi\nEOF")

    # @scenario gh-post: Input that reaches several commands needs data commands only
    def test_input_into_a_group_with_a_quiet_gh_command(self):
        self.assert_unreadable("echo x | { cat; gh pr view 5; }")

    # @scenario gh-post: A plain read is a read
    def test_a_read_whose_query_names_a_post_verb(self):
        self.assert_no_post("gh api 'search/issues?q=gh pr comment'")

    # @scenario gh-post: An MCP comment field is read
    def test_a_cursor_mcp_payload_with_a_launch_command(self):
        payload = {"tool_name": "add_issue_comment", "mcp_server_name": "github",
                   "command": "npx github-mcp", "tool_input": {"body": "x"}}
        self.assertEqual(post_reader.read_posts(payload, "cursor"), [Post("body", "x")])

    # @scenario gh-post: A Linear MCP comment and description are read
    def test_a_linear_body_that_is_not_text(self):
        self.assertIsInstance(self.payload("mcp__linear__save_comment", {"body": 123}),
                              Unreadable)


class Regressions2(Reader):
    # @scenario gh-post: A gh api call in any other form is no read
    def test_an_expansion_glued_to_api(self):
        self.assert_unreadable(
            "E=' -X POST -f body=hello'; gh api$E repos/o/r/issues/5/comments",
            "gh api$E repos/o/r/issues/comments/9", "gh api${E} repos/o/r/pulls/5",
            'gh "api"$E repos/o/r/pulls/5',
            "python3 /abs/github_app.py gh api$E repos/o/r/issues/5/comments",
            "cat c.json | gh api$E repos/o/r/issues/5/comments")

    # @scenario gh-post: A form the reader can't split exactly is unreadable
    def test_a_word_split_by_ansi_c_quoting(self):
        self.assert_unreadable(
            "gh pr co$'mment' 5 --body x", "g$'h' pr comment 5 --body x",
            'g$"h" pr comment 5 --body x', "gh p$'r' comment 5 --body x",
            "gh a$'pi' -X DELETE repos/o/r/issues/comments/9",
            "python3 /abs/discord_bot.py po$'st' --message yes",
            "python3 /abs/discord_bot$'.py' post --message yes")

    # @scenario gh-post: A canonical gh post is read
    def test_a_quoted_gh(self):
        self.assertEqual(self.bodies('"gh" pr comment 5 --body-file c.md'), ["text of c.md\n"])
        self.assert_unreadable("\\gh pr comment 5 --body x")


class Regressions3(Reader):
    # The scenario makes unreadable only a line that mentions a post verb.
    # These mention none, so they send no post.
    # @scenario gh-post: A form the reader can't split exactly is unreadable
    def test_ansi_c_quoting_beside_a_gh_read(self):
        self.assert_no_post("gh pr view 5 --json body --jq .body | tr $'\\n' ' '",
                            "gh pr list --search $'is:open'",
                            "gh pr view 5 && echo $'a\\tb'")


class Continuations(Reader):
    # A line continuation inside a word joins it; an escaped backslash or a
    # comment before a newline does not, so the next line is a command.
    # @scenario gh-post: A backslash-newline and a comment are read as nothing
    def test_a_continuation_inside_a_post_verb(self):
        self.assertEqual(self.bodies("gh pr co\\\nmment 5 --body x"), ["x"])
        self.assert_unreadable("gh pr co\\\nmment 5 --body `cat c.md`")

    # After each string's newline comes a post of its own, its verb split
    # by quotes.
    # @scenario gh-post: A backslash-newline and a comment are read as nothing
    def test_a_newline_that_ends_a_line_still_splits_words(self):
        self.assert_unreadable("echo x\\\\\ngh pr co\"\"mment 5 --body hi",
                               "# reply to foo\\\ngh pr co\"\"mment 5 --body hi",
                               "echo x\\\\\ngh pr co\"\"mment 5 --body `cat c.md`")


    # A real continuation and a line end that does not continue, in one line.
    # @scenario gh-post: A backslash-newline and a comment are read as nothing
    def test_a_continuation_beside_a_line_end(self):
        self.assert_unreadable("echo x\\\\\ng\\\nh pr comment 5 --body hi",
                               "echo x\\\\\ngh pr co\\\nmment 5 --body hi",
                               "#c\\\ng\\\nh pr comment 5 --body hi",
                               "true #c\\\ng\\\nh pr comment 5 --body hi",
                               "true;#c\\\ng\\\nh pr comment 5 --body hi",
                               "(#c\\\ngh pr co\\\nmment 5 --body hi)")

    # The same mix on a line gh_shell cannot split: $(…) in quotes, a
    # comment holding a quote, a backtick.
    # @scenario gh-post: A backslash-newline and a comment are read as nothing
    def test_a_continuation_beside_a_line_end_on_an_unsplittable_line(self):
        self.assert_unreadable('echo x\\\\\ng\\\nh pr comment 5 --body "$(cat b.md)"',
                               "echo x\\\\\ngh pr co\\\nmment 5 --body hi # it's",
                               '#c\\\necho x\\\\\ng\\\nh pr comment 5 --body hi',
                               'echo x\\\\\ng\\\nh pr comment 5 --body hi; echo `date`',
                               "echo x\\\\\ng\\\nh api -X POST repos/o/r/issues/1/comments -f body=hi # it's",
                               "echo x\\\\\n'g'h pr comment 5 --body hi # it's",
                               'echo x\\\\\n"g"h pr comment 5 --body hi # it\'s',
                               "echo x\\\\\n$'g'h pr comment 5 --body hi # it's",
                               "echo x\\\\\n#c\\\ng\\\nh pr comment 5 --body hi # it's")

    # An apostrophe in a heredoc body is no quote to the shell, so the line
    # after it must still join across its backslash-newline.
    # @scenario gh-post: A backslash-newline and a comment are read as nothing
    def test_a_continuation_after_a_heredoc_apostrophe(self):
        self.assert_unreadable("cat <<EOF\nit's\nEOF\ng\\\nh pr comment 5 --body hi",
                               "cat <<'EOF'\nit's\nEOF\necho x\\\\\ng\\h pr comment 5 --body hi")

    # An empty command substitution joins the letters on either side.
    # @scenario gh-post: A backslash-newline and a comment are read as nothing
    def test_an_empty_substitution_inside_a_word(self):
        self.assert_unreadable("g``h pr comment 5 --body hi", "g$()h pr comment 5 --body hi",
                               "gh pr co`#x`mment 5 --body hi",
                               "gh ap$( )i -X POST repos/o/r/issues/1/comments -f body=hi",
                               "python3 x/discord_bot.py po``st --channel 1 --message-file m",
                               "gh pr view 5 && g$()h pr comment 5 --body hi",
                               "g$(gh pr view 1 >/dev/null)h pr comment 5 --body hi",
                               "g$()h api -X POST repos/o/r/issues/1/comments -f body=hi # gh api",
                               "g$($(true))h pr comment 5 --body hi",
                               "g$(: ')')h pr comment 5 --body hi",
                               "g`echo \\`true\\``h pr comment 5 --body hi")

    # A single-quoted backslash does not hide a later substitution.
    # @scenario gh-post: A backslash-newline and a comment are read as nothing
    def test_a_single_quoted_backslash_before_a_substitution(self):
        self.assert_unreadable("echo 'a\\'; g$()h pr comment 5 --body x",
                               "echo 'a\\'; gh pr co``mment 5 --body x",
                               "echo 'a\\' && gh a$()pi repos/o/r/issues/1/comments -f body=x")

    # A `)` in a heredoc, comment or case pattern need not close $(…).
    # @scenario gh-post: A backslash-newline and a comment are read as nothing
    def test_a_parenthesis_that_does_not_close_a_substitution(self):
        self.assert_unreadable("gh pr co$(true <<'E'\n)\nE\n)mment 5 --body x",
                               "gh pr co$(case a in a) ;; esac)mment 5 --body x",
                               "gh pr co$(# )\n)mment 5 --body x")

    # An apostrophe in a comment or heredoc, or an escaped one in $'…', is no
    # quote to the shell.
    # @scenario gh-post: A backslash-newline and a comment are read as nothing
    def test_an_apostrophe_the_shell_does_not_pair(self):
        self.assert_unreadable("echo # don't\ng$()h pr comment 1 --body x",
                               "echo # it's\ng``h pr comment 1 --body x",
                               "cat <<'E'\nit's\nE\ng$()h pr comment 1 --body x",
                               "cat <<E\nit's\nE\ng$()h pr comment 1 --body x",
                               "echo $'\\''; g$()h pr comment 1 --body x",
                               "echo $'it\\'s'; g``h pr comment 1 --body x",
                               "a=$'\\''\ng$()h pr comment 1 --body x",
                               "g$(: $'\\')')h pr comment 1 --body x",
                               "g$(: $'\\'')h pr comment 1 --body x")

    # A substitution only inside quotes, or beside no letter, joins no
    # letters, whatever it holds.
    # @scenario gh-post: The gh post verbs are a closed list
    def test_a_quoted_substitution_holding_a_heredoc(self):
        self.assert_no_post(
            "git commit -m \"$(cat <<'EOF'\nFix the thing\n\nCo-Authored-By: X <x@y>\nEOF\n)\"",
            "git commit -m \"$(printf 'Fix #12\\n')\"",
            "echo \"$(git log -1 --format='%h # %s')\"",
            "x=$(git rev-parse HEAD#)")

    # A substitution that prints nothing, in quotes beside letters, joins
    # them, whatever the line holds before it. One beside a letter on a line
    # that mentions no post verb is no post.
    # @scenario gh-post: A backslash-newline and a comment are read as nothing
    def test_a_quoted_substitution_beside_letters(self):
        post = 'g"$(true)"h pr comment 1 --body hi'
        self.assert_unreadable(*(lead + post for lead in (
            "x=$(true)#; ", "cat <<<x\n", "cat <<E\"O\"F\nbody\nEOF\n",
            "cat <<\\EOF\nbody\nEOF\n", "cat <<EOF\r\nbody\r\nEOF\r\n",
            "(( y = 1<<3 ))\n", "x=\"$(cat <<EOF\ndon't\nEOF\n)\"\n",
            "git commit -m \"$(cat <<'EOF'\nIt's fixed\nEOF\n)\"; ")),
            'g"$(# )\n)"h pr comment 1 --body hi')
        self.assert_no_post("echo 'a$(b # c)d'",
                            "git commit -m \"$(cat <<'EOF'\nSupport the 2)nd form\nEOF\n)\"",
                            "git tag v$(node -p \"require('./package.json').version\")",
                            "echo v$(echo '" + "(x) " * 100 + "')")

    # A substitution that prints nothing, touching a word on one side only,
    # still joins it to that side.
    # @scenario gh-post: A backslash-newline and a comment are read as nothing
    def test_an_empty_substitution_beside_a_word(self):
        self.assert_unreadable("/abs/discord_bot.py $(true)post --message-file m.md",
                               "python3 /abs/discord_bot.py$(true) post --message-file m.md")

    # A quote the shell pairs differently from any rewrite of the line: an
    # escaped quote in $'...', or a comment inside backticks.
    # @scenario gh-post: A backslash-newline and a comment are read as nothing
    def test_a_quote_the_shell_pairs_its_own_way(self):
        self.assert_unreadable("echo $'it\\'s'; echo x\\\\\ng\\h pr comment 5 --body hi",
                               "echo `#it's`; echo x\\\\\ng\\h pr comment 5 --body hi",
                               "echo $'it\\'s'; echo x\\\\\ng\\h api -X POST "
                               "repos/o/r/issues/1/comments -f body=hi")



class Round5(Reader):
    # @scenario gh-post: A canonical gh post is read
    def test_edit_options_that_add_or_remove(self):
        self.assertEqual(self.bodies("gh pr edit 5 --add-reviewer alice --remove-label wip "
                                     "--title t --body-file body.md"), ["text of body.md\n"])
        self.assertEqual(self.bodies("gh issue edit 5 --add-assignee bob --remove-project P "
                                     "--remove-milestone --body hi"), ["hi"])
        # --remove-milestone takes no value, so the --body-file after it is an
        # option; it takes --body as its file, and the stray x is unreadable.
        self.assert_unreadable("gh pr edit 5 --remove-milestone --body-file --body x")
        # Reviewer options belong to pull requests, and the --add-… and
        # --remove-… options only to edit.
        self.assert_unreadable("gh issue edit 5 --add-reviewer alice --body hi",
                               "gh pr comment 5 --add-label x --body hi")

    # @scenario gh-post: A gh post in any other form is unreadable
    def test_new_is_no_canonical_verb(self):
        self.assert_unreadable("gh pr new --body x", "gh issue new --body x")

    # @scenario gh-post: An MCP comment field is read
    def test_the_claude_ai_github_prefix(self):
        self.assertEqual(self.payload("mcp__claude_ai_GitHub__add_issue_comment", {"body": "ok"}),
                         [Post("body", "ok")])

    # @scenario gh-post: A Linear MCP comment and description are read
    def test_the_claude_ai_linear_prefix(self):
        self.assertEqual(self.payload("mcp__claude_ai_Linear__save_comment", {"body": "ok"}),
                         [Post("body", "ok", "linear")])

    # @scenario gh-post: The text options are a closed list
    def test_a_short_group_holding_a_text_letter(self):
        self.assert_unreadable("cd x && gh pr edit 5 -db x")
        self.assertEqual(post_reader.TEXT_LONG, {
            "body", "body-file", "fill", "fill-first", "fill-verbose", "template", "recover",
            "comment", "editor", "web"})
        self.assertEqual(post_reader.TEXT_SHORT, set("bFcfTew"))

    # @scenario gh-post: Input may reach one gh command that uses no post verb
    def test_input_into_a_verb_off_the_no_text_list(self):
        self.assert_unreadable("cat c.md | gh pr merge 5")
        self.assert_no_post("cat c.md | gh pr view 5", "cat c.md | gh issue view 5")

    # A command run through a variable names no gh, so it passes unread.
    # @scenario gh-post: A gh command off the list passes unread
    def test_gh_held_in_a_variable(self):
        self.assert_no_post("$X pr comment 5 --body 'Should retries back off?'")

    # @scenario gh-post: A Discord message given any other way is unreadable
    def test_a_message_file_given_another_way(self):
        self.assert_unreadable("python3 /abs/discord_bot.py post --message-file=m.md",
                               "python3 /abs/discord_bot.py post --message-file m.md "
                               "--message-file b.md",
                               "python3 -m discord_bot post --message-file m.md")

    # @scenario gh-post: A discord-bot post outside the reader's form is unreadable
    def test_discord_bot_as_a_word_counts_as_gh(self):
        self.assert_unreadable("echo hi && python3 -m discord_bot post --message-file m.md",
                               "true; cat discord_bot post")
        # The post word must be a word of its own in the same simple command;
        # a quoted string is one word.
        self.assert_no_post("echo 'python3 -m discord_bot post'", "ls discord_bot",
                            "cat discord_bot.py; echo post")


class LinearWrites(Reader):
    # @scenario gh-post: A Linear write call holding no text sends no post
    def test_a_write_holding_no_text(self):
        for tool, given in (
                ("mcp__linear__save_project",
                 {"id": "P-ENG-12", "state": "completed", "targetDate": "2026-12-01"}),
                ("mcp__linear__update_diff",
                 {"urlOrId": "ENG-5", "statusAction": "markReadyForReview",
                  "addedReviewRequests": [{"user": "alice"}]}),
                ("mcp__linear__submit_diff_review", {"urlOrId": "ENG-5", "decision": "approved"}),
                ("mcp__linear__save_project", {"id": "P-1", "priority": 2, "archived": None}),
                ("mcp__linear__get_issue", {"id": "A-1", "query": "Should retries back off?"})):
            with self.subTest(tool=tool, given=given):
                self.assertEqual(self.payload(tool, given), NoPost())

    # @scenario gh-post: A Linear write call holding text is unreadable
    def test_a_write_holding_text(self):
        for tool, given in (
                ("mcp__linear__save_document", {"content": "Done?"}),
                ("mcp__linear__save_status_update", {"body": "Done?"}),
                ("mcp__linear__save_project", {"id": "P-1", "summary": "Done?"}),
                ("mcp__linear__update_diff", {"urlOrId": "ENG-5", "title": "Done?"}),
                ("mcp__linear__save_milestone", {"project": "P-1", "name": "Done?"}),
                ("mcp__linear__save_release_note",
                 {"id": "R-1", "patch": [{"op": "append", "text": "Done?"}]}),
                ("mcp__linear__create_attachment_from_upload",
                 {"issue": "A-1", "assetUrl": "https://x/y"}),
                ("mcp__linear__submit_diff_review", {"urlOrId": "ENG-5", "body": "Done?"}),
                ("mcp__claude_ai_Linear__save_document", {"content": "Done?"})):
            with self.subTest(tool=tool):
                self.assertIsInstance(self.payload(tool, given), Unreadable)

    # @scenario gh-post: The no-text list names keys that hold no text
    def test_the_key_a_string_sits_under(self):
        self.assertEqual(post_reader._text_keys(  # pyright: ignore[reportPrivateUsage]
            {"addTeams": ["a", "b"], "addedIssueLinks": [{"issue": "A-1"}],
             "patch": [{"text": "x"}]}), {"text"})
        self.assertEqual(len(post_reader.NO_TEXT_KEYS), 45)
        self.assertIn("removedIssueLinks", post_reader.NO_TEXT_KEYS)
        self.assertNotIn("assetUrl", post_reader.NO_TEXT_KEYS)

if __name__ == "__main__":
    unittest.main()
