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
        for name in ("c.md", "body.md", "b.md"):
            (self.dir / name).write_text(f"text of {name}\n")
        (self.dir / "c.json").write_text(json.dumps({"body": "json body"}))
        (self.dir / "r.json").write_text(json.dumps(
            {"body": "review", "comments": [{"path": "a.py", "body": "first"},
                                            {"path": "b.py", "body": "second"}]}))

    def read(self, command):
        return post_reader.read_command(command, str(self.dir))

    def bodies(self, command):
        found = self.read(command)
        self.assertIsInstance(found, list, f"{command!r} gave {found!r}")
        return [post.body for post in found]

    def assert_no_post(self, *commands):
        for command in commands:
            with self.subTest(command=command):
                self.assertEqual(self.read(command), NoPost())

    def assert_unreadable(self, *commands):
        for command in commands:
            with self.subTest(command=command):
                self.assertIsInstance(self.read(command), Unreadable)

    def writes(self, call):
        """Whether a gh api call writes. The reader counts a write as
        mentioning a gh post verb, so piped into sh it is unreadable; a read mentions none, and the line
        passes unread."""
        found = self.read(call + " | sh")
        if found == NoPost():
            return False
        self.assertIsInstance(found, Unreadable)
        return True


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
                payload = {"tool_name": tool, "tool_input": {"comment": "ok"}}
                self.assertEqual(post_reader.read_posts(payload, "claude"),
                                 [Post("comment", "ok")])
        payload = {"tool_name": "mcp__github__create_review",
                   "tool_input": {"comments": [{"path": "a", "body": "nested"}]}}
        self.assertEqual(post_reader.read_posts(payload, "claude"),
                         [Post("comments[0].body", "nested")])
        other = {"tool_name": "mcp__linear__save_comment", "tool_input": {"body": "x"}}
        self.assertEqual(post_reader.read_posts(other, "claude"), NoPost())
        cursor = {"tool_name": "add_issue_comment", "mcp_server_name": "github",
                  "tool_input": json.dumps({"body": "x"})}
        self.assertEqual(post_reader.read_posts(cursor, "cursor"), [Post("body", "x")])


class PostVerbs(Reader):
    # @scenario gh-post: The gh post verbs are a closed list
    def test_the_post_verbs_and_whole_words(self):
        for noun, verbs in (("pr", ("create", "new", "edit", "comment", "review", "revert")),
                            ("issue", ("create", "new", "edit", "comment"))):
            for verb in verbs:
                with self.subTest(noun=noun, verb=verb):
                    self.assertEqual(self.bodies(f"gh {noun} {verb} 5 --body hi"), ["hi"])
        for noun in ("pr", "issue"):
            for verb in ("close", "reopen"):
                with self.subTest(noun=noun, verb=verb):
                    self.assertEqual(self.bodies(f"gh {noun} {verb} 5 --comment hi"), ["hi"])
                    # Without a comment it still mentions a post verb, so a
                    # pipe into sh is unreadable, but it sends no text.
                    self.assert_no_post(f"gh {noun} {verb} 5")
                    self.assert_unreadable(f"gh {noun} {verb} 5 | sh")
        # Whole words only: --comments is not the word comment, --comment is.
        self.assert_no_post("gh pr view 5 --comments | sh", "gh issue review 5 | sh",
                            "gh pr view 5 | sh # comment-x", "gh prx comment | sh")
        self.assert_unreadable("gh pr view 5 --comment | sh")
        # discord-bot's post and edit are post verbs, though they hold no gh.
        for verb in ("post", "edit"):
            with self.subTest(verb=verb):
                self.assert_unreadable(f"python3 /abs/discord_bot.py {verb} --message x | sh",
                                       f"echo /abs/discord_bot.py {verb} | sh")
        self.assert_no_post("python3 /abs/discord_bot.py read | sh",
                            "echo /abs/discord_bot.py posted | sh")

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


class GhPrAndIssue(Reader):
    # @scenario gh-post: A gh post chained to another command is unreadable
    def test_a_chained_post_is_unreadable(self):
        # A redirection, like a chained command, stops gh being the whole line.
        self.assert_unreadable("cd /x && gh pr comment 5 --body-file c.md",
                               "gh pr comment 5 --body-file c.md > out.txt")

    # @scenario gh-post: Only a word the shell leaves alone is literal
    def test_literal_words(self):
        for word in ("'a $b'", '"a b"', "hi"):
            with self.subTest(word=word):
                self.assertTrue(post_reader.literal(word))
        for word in ('"$X"', "hi*", "~/notes"):
            with self.subTest(word=word):
                self.assertFalse(post_reader.literal(word))

    # @scenario gh-post: A whole-command post with a body file is read
    def test_a_body_file(self):
        for command in ("gh pr create --title t --body-file body.md",
                        "gh pr create --title t -F body.md"):
            with self.subTest(command=command):
                self.assertEqual(self.bodies(command), ["text of body.md\n"])

    # @scenario gh-post: A one-word unquoted body is read
    def test_a_one_word_body(self):
        for command in ("gh pr comment 5 --body hi", "gh pr comment 5 -bhi",
                        "gh pr comment 5 --body=hi"):
            with self.subTest(command=command):
                self.assertEqual(self.bodies(command), ["hi"])

    # @scenario gh-post: A body from the shell, a pipe or a missing file is unreadable
    def test_bodies_it_cannot_read(self):
        self.assert_unreadable(
            'gh pr comment 5 --body "$(cat body.md)"', "gh pr comment 5 --body hi*",
            "gh pr comment 5 --body ~/notes", "cat c.md | gh pr comment 5 -F -",
            "gh pr comment 5 --body-file missing.md", "gh pr create -t x -T tmpl.md",
            *[f"gh pr create -t x {flag}" for flag in
              ("--fill", "--fill-first", "--fill-verbose", "--recover s.json", "--editor",
               "--web")])

    # @scenario gh-post: A close with a comment is read
    def test_a_close_or_reopen_comment(self):
        for command in ("gh issue close 5 --comment 'done'", "gh issue close 5 -c 'done'",
                        "gh issue reopen 5 -c done", "gh pr reopen 5 --comment done"):
            with self.subTest(command=command):
                self.assertEqual(self.bodies(command), ["done"])


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
                               "gh pr view 1 | gh pr comment 1 -F -")

    # @scenario gh-post: A subshell's and an unquoted substitution's commands are read
    def test_subshells_and_substitutions(self):
        self.assert_no_post("(cd sub && gh pr edit 3 --add-assignee @me)",
                            "echo $(gh pr edit 5 --add-assignee @me)")
        self.assert_unreadable("(cd sub && gh pr comment 3 --body hi)",
                               "echo $(gh pr comment 5 --body yo)")

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
            "gh pr ready", "gh issue close 5", "gh pr list",
            "python3 /abs/github_app.py gh pr edit 5 --add-label spec",
            "cd x && gh api -X DELETE repos/o/r/issues/comments/9",
            "cd x && gh api -X POST repos/o/r/releases -f body=notes")

    # @scenario gh-post: A gh post quoted as data is no post
    def test_data_commands(self):
        self.assert_no_post("echo 'run gh pr create next'",
                            *[f"{name} 'gh pr create'" for name in sorted(
                                post_reader.DATA_COMMANDS)])
        self.assertEqual(post_reader.DATA_COMMANDS, {
            "echo", "cat", "tee", "grep", "egrep", "fgrep", "rg", "git", "python", "python3",
            "node", "jq", "head", "tail", "wc", "sort", "uniq", "cut", "tr", "ls", "cd", "true",
            "false"})

    # @scenario gh-post: gh named as another command's argument is unreadable
    def test_gh_as_an_argument(self):
        # Unquoted, gh is a word of its own; quoted, as in `echo 'gh pr
        # create'`, it is data.
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
                               "echo 'gh pr comment 5 -b x' | while read l; do gh pr view; done")
        self.assert_no_post("echo 'gh pr comment 5 -b x' | { cat; wc -l; }")

    # @scenario gh-post: Input may reach one gh command that uses no post verb
    def test_input_into_one_gh_command(self):
        self.assert_no_post("cat c.md | gh pr view 5 && gh pr edit 5 --add-label spec")
        self.assert_unreadable("cat c.md | gh pr edit 5 --add-label spec")


class OtherLines(Reader):
    # @scenario gh-post: A gh post run through another shell is unreadable
    def test_another_shell(self):
        self.assert_unreadable("sh -c 'gh pr comment 5 --body-file c.md'",
                               "bash -c 'gh issue create -b x'", "eval 'gh pr comment 5 -b x'")

    # @scenario gh-post: A command the reader can't read exactly is unreadable
    def test_a_command_it_cannot_read(self):
        self.assert_unreadable("gh pr comment 5 -b `cat c.md`", "gh pr comment 5 -b $'x'")


class GithubApp(Reader):
    # @scenario gh-post: A post sent through the github-app skill is read
    def test_the_script_s_forms(self):
        for command in (
                "python3 /abs/github_app.py gh pr create --body-file body.md",
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

    # @scenario gh-post: Another script given gh's arguments is unreadable
    def test_another_script(self):
        self.assert_unreadable("python3 /tmp/other.py gh pr comment 5 --body-file c.md")

    # @scenario gh-post: The github-app script after another command is unreadable where a direct gh call is
    def test_the_script_after_another_command(self):
        self.assert_unreadable(
            "cd x && python3 /abs/github_app.py gh pr comment 5 --body-file c.md",
            "cd x && python3 /abs/github_app.py gh api repos/o/r/issues/5/comments "
            "-F body=@c.md")

    # @scenario gh-post: The github-app script through an unassigned variable is unreadable
    def test_an_unassigned_variable(self):
        for command in ('python3 "$G" gh pr comment 5 --body-file c.md',
                        'G=/abs/github_app.py; unset G; python3 "$G" gh pr comment 5 '
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
        # An unassigned $G is not github-app's form, so the gh api call is no
        # read.
        self.assert_unreadable('python3 "$G" gh api repos/o/r/pulls/5')

    # @scenario gh-post: A gh api call through the github-app script is judged as a direct one
    def test_gh_api_through_the_script(self):
        self.assertEqual(self.bodies(
            "python3 /abs/github_app.py gh api repos/o/r/issues/5/comments -f body=hi"), ["hi"])
        self.assert_no_post("python3 /abs/github_app.py --identity bot gh api -X DELETE "
                            "repos/o/r/issues/comments/9")


class Discord(Reader):
    # @scenario gh-post: A Discord post or edit is read from its file
    def test_post_and_edit(self):
        (self.dir / "m.md").write_text("User says: yes")
        for verb in ("post --channel ops", "edit --message-id 9"):
            with self.subTest(verb=verb):
                found = self.read(f"python3 /abs/discord_bot.py --identity relay {verb} "
                                  "--message-file m.md")
                self.assertIsInstance(found, list)
                assert isinstance(found, list)
                self.assertEqual([(p.body, p.surface) for p in found],
                                 [("User says: yes", "discord")])
        self.assertEqual(self.bodies("python3 /abs/discord_bot.py post --message yes"), ["yes"])
        self.assertEqual(self.bodies(
            "D=~/.agents/skills/discord-bot/scripts/discord_bot.py; "
            "python3 $D post --message=hi --reply-to 5"), ["hi"])
        self.assert_unreadable("cd x && python3 /abs/discord_bot.py post --message yes",
                               "python3 /abs/discord_bot.py post --message-file missing.md",
                               "python3 -I /abs/discord_bot.py post --message hi",
                               'D=/abs/discord_bot.py; unset D; python3 "$D" post --message hi',
                               "sh -c 'python3 /abs/discord_bot.py post --message hi'")

    # @scenario gh-post: A Discord post or edit is read from its file
    def test_option_forms_discord_bot_accepts(self):
        (self.dir / "m.md").write_text("from file")
        for command, body in (
                ("python3 /abs/discord_bot.py post --message=x", "x"),
                ("python3 /abs/discord_bot.py post --message-file=m.md", "from file"),
                ("python3 /abs/discord_bot.py post --message first --message last", "last"),
                ("python3 /abs/discord_bot.py edit --message-id 9 --message-file missing.md "
                 "--message-file m.md", "from file")):
            with self.subTest(command=command):
                self.assertEqual(self.bodies(command), [body])
        self.assert_unreadable('python3 /abs/discord_bot.py post --message "$X"',
                               "python3 /abs/discord_bot.py post --message-f m.md",
                               "python3 /abs/discord_bot.py post --mess x")

    # @scenario gh-post: A Discord message from standard input is unreadable
    def test_a_message_from_stdin(self):
        self.assert_unreadable(
            "printf 'User says: yes' | python3 /abs/discord_bot.py post --message -",
            "python3 /abs/discord_bot.py post --message - < m.md",
            "python3 /abs/discord_bot.py post --message-file -",
            "python3 /abs/discord_bot.py post --message-file=-")

    # @scenario gh-post: A Discord delete, read or thread is no post
    def test_calls_that_post_no_text(self):
        self.assert_no_post("python3 /abs/discord_bot.py delete --message-id 9",
                            "python3 /abs/discord_bot.py read --limit 5",
                            "python3 /abs/discord_bot.py thread --message-id 9 --name Retries",
                            "cd x && python3 /abs/discord_bot.py read --limit 5")


class GhApiReads(Reader):
    # @scenario gh-post: A read with placeholders or a query string is a read
    def test_reads(self):
        for call in ("gh api repos/{owner}/{repo}/pulls/5", "gh api search/issues?q=x",
                     'G=/abs/github_app.py && python3 "$G" gh api repos/o/r/pulls/5'):
            with self.subTest(call=call):
                self.assertEqual(self.read(call), NoPost())
                self.assertFalse(self.writes(call))

    # @scenario gh-post: A gh api call the reader cannot see whole is unreadable
    def test_words_the_shell_builds(self):
        self.assert_unreadable("gh api repos/o/r/issues/5/comments $F",
                               'gh api -X "$M" repos/o/r/issues/5',
                               "cat a | xargs gh api repos/o/r/issues/5/comments",
                               "sh -c 'gh api repos/o/r/issues/5/comments \"$@\"' _ -f body=x",
                               "gh api repos/o/r/pulls/$N", "gh api --unknown x repos/o/r")

    # @scenario gh-post: A method other than GET writes
    def test_methods(self):
        for call in ("gh api -X DELETE repos/o/r/issues/comments/9",
                     "gh api --method=patch repos/o/r/issues/5 -f state=closed",
                     "gh api -XPOST repos/o/r/issues/5/labels -f 'labels[]=x'",
                     "gh api --method put repos/o/r/x", "gh api -X=post repos/o/r/x",
                     "gh api -iXPOST repos/o/r/x",
                     "gh api -X GET -X POST repos/o/r/labels -f name=x"):
            with self.subTest(call=call):
                self.assertTrue(self.writes(call))
        self.assertFalse(self.writes("gh api -X get search/issues -f q=x"))

    # @scenario gh-post: Fields or input with no method write
    def test_fields_and_input(self):
        for call in ("gh api repos/o/r/labels -f name=x", "gh api repos/o/r/labels -fname=x",
                     "gh api repos/o/r/labels --raw-field=name=x",
                     "gh api repos/o/r/labels -F name=x", "gh api repos/o/r/labels --field name=x",
                     "gh api repos/o/r/labels --input l.json"):
            with self.subTest(call=call):
                self.assertTrue(self.writes(call))
        self.assertFalse(self.writes("gh api -X GET search/issues -f q=x"))
        self.assertFalse(self.writes("gh api repos/o/r/pulls/5"))

    # @scenario gh-post: A method override header writes
    def test_an_override_header(self):
        self.assertTrue(self.writes(
            "gh api -H 'X-HTTP-Method-Override: DELETE' repos/o/r/issues/comments/9"))
        self.assertTrue(self.writes(
            "gh api -X GET --header 'x-http-method-override: PUT' repos/o/r/x"))

    # @scenario gh-post: A GraphQL call writes only as a mutation or an unread query
    def test_graphql_writes(self):
        self.assertFalse(self.writes("gh api graphql -f query='{ viewer { login } }'"))
        self.assertTrue(self.writes(
            "gh api graphql -f query='mutation { addStar(input: {starrableId: \"R_1\"}) "
            "{ clientMutationId } }'"))
        self.assert_unreadable("cat q.graphql | gh api graphql -F query=@-")
        self.assertTrue(self.writes("gh api graphql -F query=@-"))


class GhApiPosts(Reader):
    # @scenario gh-post: Each gh api body form is read
    def test_each_body_form(self):
        endpoint = "gh api repos/o/r/issues/5/comments"
        for form, body in (("-f body=hi", "hi"), ("--raw-field body=hi", "hi"),
                           ("-F body=hi", "hi"), ("--field body=hi", "hi"),
                           ("--raw-field=body=hi", "hi"), ("-fbody=hi", "hi"),
                           ("-F body=@c.md", "text of c.md\n"), ("--input c.json", "json body")):
            with self.subTest(form=form):
                self.assertEqual(self.bodies(f"{endpoint} {form}"), [body])

    # @scenario gh-post: gh api placeholders count as an owner and a repository
    def test_placeholders(self):
        for endpoint in ("/repos/{owner}/{repo}/issues/5/comments",
                         "repos/{owner}/{repo}/issues/5/comments",
                         "https://api.github.com/repos/o/r/pulls/5"):
            with self.subTest(endpoint=endpoint):
                self.assertEqual(self.bodies(f"gh api {endpoint} -f body=hi"), ["hi"])

    # @scenario gh-post: A gh api review's nested comments are read
    def test_a_review_s_comments(self):
        self.assertEqual(self.bodies(
            "gh api repos/o/r/pulls/5/reviews -f body=ok -f 'comments[][path]=a.py' "
            "-f 'comments[][body]=Why?'"), ["ok", "Why?"])
        self.assertEqual(self.bodies("gh api repos/o/r/pulls/5/reviews --input r.json"),
                         ["review", "first", "second"])

    # @scenario gh-post: A gh api body file after another command is unreadable
    def test_a_file_beside_another_command(self):
        self.assert_unreadable(
            "printf 'unsigned' > c.md && gh api repos/o/r/issues/5/comments -F body=@c.md",
            "printf 'unsigned' > c.json && gh api repos/o/r/issues/5/comments --input c.json",
            "printf q > q.graphql && gh api graphql -F query=@q.graphql")

    # @scenario gh-post: A gh api body given in the command is read in a longer line
    def test_a_body_in_a_longer_line(self):
        line = "cd /x && gh api repos/o/r/issues/5/comments -f body='done'"
        self.assertEqual(self.bodies(line), ["done"])
        self.assert_unreadable(f"{line} && gh api repos/o/r/issues/6/comments -f body='b'",
                               f"{line} && gh pr comment 6 -b x",
                               f"{line}; sh -c 'gh issue create -b x'")


class GraphQL(Reader):
    MUTATION = ("mutation($b: String!) { addComment(input: {subjectId: \"I_1\", body: $b}) "
                "{ clientMutationId } }")

    # @scenario gh-post: A GraphQL comment's body is read
    def test_a_comment_s_body(self):
        query = f"gh api graphql -f query='{self.MUTATION}'"
        self.assertEqual(self.bodies(f"{query} -f b=hello"), ["hello"])
        for form in ("-F b=hello", "--raw-field b=hello", "--field=b=hello"):
            with self.subTest(form=form):
                self.assertEqual(self.bodies(f"{query} {form}"), ["hello"])
        self.assertEqual(self.bodies(
            "gh api graphql -f query='mutation { addComment(input: {subjectId: \"I\", "
            "body: \"literal\"}) { clientMutationId } }'"), ["literal"])
        (self.dir / "q.json").write_text(json.dumps({
            "query": "mutation($t: [DraftPullRequestReviewThread]) { addPullRequestReview("
                     "input: {pullRequestId: \"P\", body: \"top\", threads: $t}) "
                     "{ clientMutationId } }",
            "variables": {"t": [{"path": "a", "body": "one"}, {"path": "b", "body": "two"}]}}))
        self.assertEqual(self.bodies("gh api graphql --input q.json"), ["top", "one", "two"])
        (self.dir / "q.graphql").write_text(self.MUTATION)
        self.assertEqual(self.bodies("gh api graphql -F query=@q.graphql -f b=filed"),
                         ["filed"])
        # A block string's value drops its common indent and blank end lines.
        self.assertEqual(self.bodies(
            "gh api graphql -f query='mutation { addComment(input: {body: \"\"\"\n"
            "    a\n      b\n  \"\"\"}) { clientMutationId } }'"), ["a\n  b"])

    # @scenario gh-post: The GraphQL mutations that post text are a closed list
    def test_the_mutations(self):
        self.assertEqual(len(post_reader.MUTATIONS), 13)
        for name in sorted(post_reader.MUTATIONS):
            with self.subTest(name=name):
                self.assertEqual(self.bodies(
                    f"gh api graphql -f query='mutation {{ {name}(input: {{body: \"x\"}}) "
                    "{ clientMutationId } }'"), ["x"])
        self.assert_no_post("gh api graphql -f query='mutation { addDiscussionComment("
                            "input: {discussionId: \"D\", body: \"x\"}) { clientMutationId } }'")

    # @scenario gh-post: A write with no body sends no post
    def test_writes_with_no_body(self):
        self.assert_no_post(
            "gh api --method=patch repos/o/r/issues/5 -f state=closed",
            "gh api graphql -f query='mutation { addLabelsToLabelable(input: "
            "{labelableId: \"x\", labelIds: [\"y\"]}) { clientMutationId } }'",
            "gh api graphql -f query='mutation { addComment(input: {subjectId: \"x\"}) "
            "{ clientMutationId } }'")

    # @scenario gh-post: A GraphQL mutation that can't be read is unreadable
    def test_a_mutation_it_cannot_read(self):
        self.assert_unreadable("gh api graphql -f query='mutation { … }'",
                               f"gh api graphql -f query='{self.MUTATION}'",
                               "gh api graphql -f query='mutation { addComment(input: "
                               "{body: 5}) { clientMutationId } }'")

    # @scenario gh-post: A gh api body from a missing file is unreadable
    def test_a_missing_body_file(self):
        self.assert_unreadable("gh api repos/o/r/issues/5/comments -F body=@missing.md",
                               "gh api repos/o/r/pulls/5/reviews -f body=ok "
                               "-F 'comments[][body]=@missing.md'",
                               "gh api repos/o/r/issues/5/comments --input missing.json")

    # @scenario gh-post: A gh api write to an endpoint the reader does not read passes unread
    def test_endpoints_it_does_not_read(self):
        self.assert_no_post("gh api -X POST repos/o/r/releases -F body=@missing.md",
                            "gh api graphql -f query='mutation { addDiscussionComment("
                            "input: {discussionId: \"D\", body: \"x\"}) { clientMutationId } }'")
        self.assert_unreadable("gh api -X POST repos/o/r/releases -f body=$B")


class Regressions(Reader):
    """Forms the tagged scenario does not name: they look like it, but the
    reader cannot read their body exactly, or reads it only after
    normalising the endpoint as GitHub does."""

    # @scenario gh-post: A GraphQL comment's body is read
    def test_fields_beside_input_are_unreadable(self):
        (self.dir / "q.json").write_text(json.dumps({
            "query": "mutation { addComment(input: {subjectId: \"I\", body: \"from file\"}) "
                     "{ clientMutationId } }"}))
        self.assert_unreadable("gh api graphql --input q.json -f query='{ viewer { login } }'")
        (self.dir / "v.json").write_text(json.dumps({
            "query": "mutation($b: String!) { addComment(input: {subjectId: \"I\", body: $b}) "
                     "{ clientMutationId } }", "variables": {"b": "from file"}}))
        self.assert_unreadable("gh api graphql --input v.json -f b=clean")
        self.assertEqual(self.bodies("gh api graphql --input v.json"), ["from file"])

    # @scenario gh-post: Each gh api body form is read
    def test_an_endpoint_gh_sends_to_an_issue_is_read_however_it_is_spelled(self):
        for endpoint in ("'repos/o/r/./issues/5/comments'", "'repos/o/x/../r/issues/5/comments'",
                         "repos/o/r/%69ssues/5/comments", "repositories/123/issues/5/comments",
                         "'repos/o/r/issues/5/comments#x'"):
            with self.subTest(endpoint=endpoint):
                self.assertEqual(self.bodies(f"gh api {endpoint} -f body=hi"), ["hi"])
        for endpoint in ("'graphql#x'", "graphql/"):
            with self.subTest(endpoint=endpoint):
                self.assertEqual(self.bodies(
                    f"gh api {endpoint} -f query='mutation {{ addComment(input: {{body: \"x\"}}) "
                    "{ clientMutationId } }'"), ["x"])

    # @scenario gh-post: Each gh api body form is read
    def test_a_typed_field_gh_fills_a_placeholder_in_is_unreadable(self):
        self.assert_unreadable(
            "gh api repos/o/r/issues/5/comments -F 'body=see {owner}'",
            "gh api repos/o/r/issues/5/comments -F 'body=see {repo}'",
            "gh api repos/o/r/issues/5/comments -F 'body=see {branch}'",
            "gh api repos/o/r/issues/5/comments -F 'body=see :owner and :repo'",
            "gh api repos/o/r/pulls/1/reviews -F 'comments[][body]=at :branch-x'",
            "gh api graphql -F 'query=mutation { addComment(input: {body: \"by :owner\"}) "
            "{ clientMutationId } }'",
            "gh api repos/o/r/issues/5/comments -F body=+5")

    # @scenario gh-post: Each gh api body form is read
    def test_a_field_beside_input_on_an_issue_endpoint_is_unreadable(self):
        (self.dir / "empty.json").write_text("{}")
        self.assert_unreadable("gh api repos/o/r/issues/1/comments --input empty.json -f body=x")

    # @scenario gh-post: Each gh api body form is read
    def test_a_placeholder_before_a_non_ascii_letter_is_still_filled(self):
        self.assert_unreadable("gh api repos/o/r/issues/1/comments -F 'body=hi :owneré'",
                               "gh api repos/o/r/issues/1/comments -F 'body=hi :owner٣'")
        self.assertEqual(self.bodies("gh api repos/o/r/issues/1/comments -F 'body=hi :owner_x'"),
                         ["hi :owner_x"])

    # @scenario gh-post: A GraphQL comment's body is read
    def test_fields_beside_the_query_are_unreadable_unless_the_endpoint_is_graphql(self):
        query = ("-f query='mutation($b: String = \"default\") { addComment(input: "
                 "{body: $b}) { clientMutationId } }' -f b=hello")
        self.assertEqual(self.bodies(f"gh api graphql {query}"), ["hello"])
        for endpoint in ("/graphql", "https://api.github.com/graphql"):
            with self.subTest(endpoint=endpoint):
                # gh sends the fields beside the query, where a field named
                # variables[…] sets the variables GitHub runs.
                self.assert_unreadable(
                    f"gh api {endpoint} {query}",
                    f"gh api {endpoint} -f query='mutation($b: String = \"default\") {{ "
                    "addComment(input: {body: $b}) { clientMutationId } }' "
                    "-f 'variables[b]=other'",
                    f"gh api {endpoint} -f query='mutation($i: AddCommentInput!) {{ "
                    "addComment(input: $i) { clientMutationId } }' -f 'variables[i][body]=x'")
                self.assertEqual(self.bodies(
                    f"gh api {endpoint} -f query='mutation($b: String = \"default\") {{ "
                    "addComment(input: {body: $b}) { clientMutationId } }'"), ["default"])

    # @scenario gh-post: Each gh api body form is read
    def test_a_write_with_a_query_string_on_an_issue_endpoint_is_unreadable(self):
        self.assert_unreadable("gh api -X POST 'repos/o/r/issues/1/comments?body=hello'",
                               "gh api 'repos/o/r/issues/1/comments?body=b' -f body=a")


class Pinned(Reader):
    """Behaviour no test checked until mutation testing showed it."""

    # @scenario gh-post: A gh post chained to another command is unreadable
    def test_a_subshell_after_a_comment_line_is_not_a_whole_command(self):
        self.assert_unreadable("# c\n(gh pr comment 5 --body hi)")

    # @scenario gh-post: The github-app script through an unassigned variable is unreadable
    def test_a_script_variable_set_again_no_longer_names_the_script(self):
        # discord-bot's script is found in github-app's forms, so this
        # scenario covers it.
        self.assert_unreadable(
            "D=/abs/discord_bot.py; D=/tmp/other.py; python3 $D post --channel ops --message hi",
            'D=/abs/discord_bot.py; export D=/tmp/other.py; python3 "$D" post --message hi')

    # @scenario gh-post: A Discord message from standard input is unreadable
    def test_input_into_a_discord_call_is_unreadable(self):
        self.assert_unreadable(
            "echo x | python3 /abs/discord_bot.py delete --message-id 9 --channel post")

    # @scenario gh-post: A gh api call the reader cannot see whole is unreadable
    def test_a_flag_missing_its_value_is_unreadable(self):
        self.assert_unreadable("gh api repos/o/r/issues/1/comments -f body=x --field",
                               "gh api repos/o/r/issues/1/comments -f body=x -f",
                               "python3 /abs/discord_bot.py post --message")

    # @scenario gh-post: Each gh api body form is read
    def test_gh_api_flag_forms(self):
        self.assertEqual(self.bodies("gh api -f body=x -- repos/o/r/issues/1/comments"), ["x"])
        self.assertEqual(self.bodies("gh api -i=true repos/o/r/issues/1/comments -f body=x"),
                         ["x"])

    # @scenario gh-post: A GraphQL comment's body is read
    def test_a_block_string_s_first_line_and_a_default_variable(self):
        self.assertEqual(self.bodies(
            "gh api graphql -f query='mutation { addComment(input: {body: "
            "\"\"\"  first\n    second\"\"\"}) { clientMutationId } }'"), ["  first\nsecond"])
        self.assertEqual(self.bodies(
            "gh api graphql -f query='mutation($b: String = \"text\") { addComment(input: "
            "{body: $b}) { clientMutationId } }'"), ["text"])

    # @scenario gh-post: Only a word the shell leaves alone is literal
    def test_an_unterminated_quote_is_not_literal(self):
        self.assertFalse(post_reader.literal("'open"))

    # @scenario gh-post: An MCP comment field is read
    def test_blank_bodies_and_other_cursor_servers_send_no_post(self):
        payload = {"tool_name": "mcp__github__add_issue_comment", "tool_input": {"body": "  "}}
        self.assertEqual(post_reader.read_posts(payload, "claude"), NoPost())
        cursor = {"tool_name": "save_comment", "mcp_server_name": "linear",
                  "tool_input": json.dumps({"body": "x"})}
        self.assertEqual(post_reader.read_posts(cursor, "cursor"), NoPost())

    # @scenario gh-post: A one-word unquoted body is read
    def test_short_and_long_flag_values(self):
        self.assertEqual(self.bodies("gh pr comment 5 -b=hi"), ["hi"])
        self.assertEqual(self.bodies("gh pr comment 5 --body -F missing.md"), ["-F"])
        self.assertEqual(self.bodies(
            "python3 /abs/discord_bot.py post --channel=ops --message hi"), ["hi"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
