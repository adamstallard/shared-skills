# Prose

Prose makes agents rewrite what they write for you (docs, code comments, specs,
commit messages, pull request descriptions, ticket comments) so you can review
it in one read, and makes every commit and post carry proof that the rewrite
ran.

> Agent instructions: [SKILL.md](SKILL.md). Why it works this way:
> [DECISIONS.md](DECISIONS.md).

## What you get

- **Commits** carry a `Prose: ✓ <tree>:<message>` trailer. Its two hashes cover
  the staged files and the final message when the agent signed, so an edit
  after signing breaks it. In a repository with a pre-commit hook, prose runs
  the hook before signing, so a formatter's changes are signed instead of
  breaking the trailer.
- **Pull request descriptions and comments** end with a short footer, such as
  `prose ✓ 3f2a91`. The hash covers the text above it, so it shows the pass ran
  over exactly what you are reading.

A missing trailer or footer means the agent skipped the pass. Tell it to run
`prose`.

**What it proves.** Each trailer or footer takes two calls: the first prints
the rules and a one-use pass token, the second takes the token and signs. So
the rules were on the agent's screen before it signed. Nothing proves the agent
followed them.

To install it, ask your agent to install the `prose` skill; the
`manage-skills` skill does the rest, hooks included.

## Using it

It runs without being asked. To run it on existing text:

> Tighten this README
> This PR description is too long — rewrite it for a reviewer

## Each document is checked for its own reader

A commit's reviewer is not the reader of the docs it changes. So before it
signs a commit, the agent names the reader goals of each changed doc and spec,
apart from the reviewer's, and does the pass on each file against its own.
Prose will not sign while a changed doc or spec has none. A code comment
without goals gets a default reader: someone about to change the code.

The agent passes them as gitignore-style patterns, where the most specific
match wins: an exact path beats any pattern, and a pattern with more literal
characters beats one with fewer.

```sh
prose.py check -F msg.txt --goals "review the fix; check it is safe to merge" \
  --goals-for 'docs/**' "learn how sync works; find what to run when it fails" \
  --goals-for docs/api.md "call the API correctly"
```

For many files, the same goes in a file passed as `--goals-file goals.txt`:

```text
docs/**: learn how sync works; find what to run when it fails
docs/api.md: call the API correctly
```

[SKILL.md](SKILL.md) has the details.

## What is enforced where

| What | Check |
|---|---|
| Commits | A hook after each shell command reports a commit whose `Prose: ✓ <tree>:<message>` trailer is missing, or whose tree or message changed after the check |
| GitHub posts, through MCP | A hook blocks the post unless its body ends with a valid footer |
| GitHub posts, through `gh` | The same hook, for a few exact command forms (see [Posting through `gh`](#posting-through-gh)) |
| A Claude Code session's first file write or GitHub post | A hook blocks it until prose's first call has printed the rules in that session |

To turn the hooks off, run
`python3 ~/.agents/skills/manage-skills/scripts/skills.py disable-hook prose`;
`enable-hook prose` turns them back on. While they are off, nothing is checked.

There is no GitHub Action: installing the skill installs these hooks, so every
agent that uses it is checked where it works. See
[DECISIONS.md](DECISIONS.md#rejected-a-github-action).

## Using it in Cursor: unverified

The posting hook is wired for Cursor as a best guess, on
`beforeShellExecution` and `beforeMCPExecution`. It follows Cursor's documented
hook contract but has not been run in a real Cursor, so it may need fixing. If
it blocks every shell command, or never blocks an unsigned post, turn it off
with `python3 ~/.agents/skills/manage-skills/scripts/skills.py disable-hook
prose` and report it. See
[DECISIONS.md](DECISIONS.md#cursors-posting-hook-is-wired-as-a-best-guess).

## Posting through `gh`

The posting hook reads the body only when `gh` is the whole command and the
body is `--body '<text>'` or `--body-file <existing file>`. For longer text,
sign it into a file and pass that. `gh api` calls are not checked.

A `gh` post in any other shape is blocked: inside a longer command, after `cd`,
in a heredoc, or through `bash -c`. So are `--fill`, `--editor`, `--web` and
`--template`, since the hook cannot read the text they post. The block message
lists the forms that work.

A command passes when the shell runs no `gh` post in it:

- one that only mentions a post: in a comment with no quotes or `;&|()<>`
  in it, or in quotes or a quoted heredoc given to a command that treats them
  as data (`echo`, `cat`, `grep`, `git`, `python3` and a few others), such as
  `grep "gh pr create"` or a Python script that writes the phrase to a file;
- a `gh` command that sends no text, anywhere in a longer command: a label,
  assignee or milestone edit, `gh pr ready`, a close without `--comment`. A
  `--title` is not checked. An edit or close fed by a pipe or `<` is still
  blocked, since those verbs can take a body.

The hook still blocks a command it cannot read to the end, such as one with
backticks or an unterminated quote. It also blocks a mention given to any other
command, since that command might run it (`sh -c`, `eval`, `xargs`). A command
that reads a pipe or an input redirection must be one of those data commands
or a `gh` subcommand that takes no body, such as `gh pr view`; when the input reaches a group, loop or
subshell, every command in it must be a data command. To run one that only
mentions a post, put it in a script file,
run it in your own terminal, or, as a last resort, turn the hooks off as in
[What is enforced where](#what-is-enforced-where).

## Tests

From the root of your clone:

```sh
python3 .agents/skills/prose/scripts/test_prose.py
python3 .agents/skills/prose/scripts/test_comment_scan.py
```
