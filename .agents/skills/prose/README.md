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
  breaking the trailer. After a cold read (below), the value ends with its
  counts, such as `; cold read: 5 findings, 3 fixed, 2 kept; understood: 4
  items, 1 fixed, 0 kept`: the findings and how many were fixed or kept, then
  the items read and how many were misunderstood and then fixed or kept.
- **Pull request descriptions and comments** end with a short footer, such as
  `prose ✓ 3f2a91`. The hash covers the text above it, so it shows the pass ran
  over exactly what you are reading.

A missing trailer or footer means the agent skipped the pass. Tell it to run
`prose`.

**What it proves.** Each trailer or footer takes two calls: the first prints
the rules and a one-use pass token, the second takes the token and signs. So
the rules were on the agent's screen before it signed. Nothing proves the agent
followed them.

**A cold read.** Before it signs a changed comment, doc passage or post, the
agent has a fresh agent, one that never saw the conversation, read it and
report where it stopped, reread or guessed, quoting the words. For every item
it also says in one line what it understood: who does each thing, whether it
always happens, and whose doing it is. That line catches a confident
misreading, which makes no reader stop. The agent then answers every finding
and every understood line. A finding is fixed, which the script checks by its
item having changed since the brief, or kept, which a person decides. An
understood line matches what the agent meant, or else is fixed or kept in the
same way. The signing call refuses without
a report and those answers, both bound to that pass's token, and refuses a
kept one unless the agent says a person was asked. An agent that cannot ask
leaves the change unsigned, and hands each finding or understood line it would
keep back to its caller.
Nothing proves a fresh agent wrote the report, or that the person was asked.

To install it, ask your agent to install the `prose` skill; the
`manage-skills` skill does the rest, hooks included.

## Using it

It runs without being asked. To run it on existing text:

> Tighten this README
> This PR description is too long — rewrite it for a reviewer

The agent then drafts every section afresh, rather than choosing which to
fix, and keeps an original section only where its draft says the same thing.
It reports how many sections it redrafted, merged, kept and held back for an
open branch.

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

## Docs agents read before working stay compact

Agents reread docs such as `SKILL.md`, `AGENTS.md` and open OpenSpec
proposals before every task, so history, repetition and padding left in them
cost tokens on every read. When a commit changes a doc agents read often,
and the history, repetition and padding added since it was last compacted
make up a tenth of the doc and at least 1,000 bytes, or the doc has grown by
half since then, prose prints `compaction due for <file>`. The agent then
has a fresh subagent rewrite the file to what is current, answering for
every passage a script flagged, and runs a script that checks those answers
and that no link into the file broke. A second fresh subagent then checks
every removal against the old text and the code, and anything lost is put
back. The agent commits the result in a commit of its own, and asks you first
only when the rewrite would drop a conclusion.

You can ask your agent to:
- compact a specific file now, whether or not it is due;
- mark a file as read often, so it's checked for compaction;
- exempt a file from compaction;
- drop "who decided" credits, such as "(Adam, 2026-10-24)", when files are
  compacted;
- change when compaction is due.

For all but the first, the agent edits the repository's `.gitattributes`,
in a commit of its own. When you ask for one of them, it makes the edit
directly. It never adds such a line unasked: when it thinks one would help,
it proposes the line, and once you confirm, the agent makes the edit.

## What is enforced where

| What | Check |
|---|---|
| Commits | A hook after each shell command reports a commit whose `Prose: ✓ <tree>:<message>` trailer is missing, or whose tree or message changed after the check |
| GitHub posts, through MCP | A hook blocks the post unless its body ends with a valid footer |
| GitHub posts, through `gh` | The same hook, for a few exact command forms (see [Posting through `gh`](#posting-through-gh)) |
| A Claude Code session's first file write or GitHub post | A hook blocks it until prose's first call has printed the rules in that session |
| A changed comment or doc passage, or a post | The signing call signs it only with a cold reader's report for that pass, and an answer to each finding and understood line |

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
