---
name: prose
description: >-
  Rewrite any text a human will review so it is quick to read, then prove the
  pass ran. Applies by default, unasked, before every commit that adds or
  changes prose — READMEs and other docs, code comments, architecture docs,
  specs, the commit message itself — and before posting a pull request
  description, review reply, or GitHub, Linear or Discord comment. Also use when
  the user says "tighten this", "this is too long", "make this readable", or
  "rewrite this for a reviewer". Commits carry a Prose: trailer; posted text
  ends with a signed prose footer.
---

# Prose

**A reviewer should get what they need from the text in one read.** Text that is
true but slow to read has failed.

Prose's first call prints the rules from [rules.md](rules.md), their only
copy. Work from that printout, not from memory of an earlier session.

- **Why each rule and mechanism is the way it is:** [DECISIONS.md](DECISIONS.md).
  Read it before changing this file.

## What counts as prose

Anything a human reviews: READMEs and other docs, code comments, architecture
docs, specs, commit messages, pull request descriptions, and posts to GitHub,
Linear and Discord. **Short kinds are not exempt.** Commit subjects and ticket
comments bloat too.

## When the pass runs

- **Before every commit that contains prose**, on the staged change and the
  commit message. Write the code first, then do the pass as one read of the
  finished text, then commit.
- **Before posting** any pull request description or comment.
- **On request**, over text you did not write.

## Two calls: the rules, then the signature

Each commit and each post takes two calls. The first takes the goals of that
text's reader, prints the rules and a pass token, and exits 4. You do the pass;
then the second call takes the token and signs. A token signs one text, once,
within 2 hours, and only of the kind that issued it: `check` for a commit,
`sign` for a post.

`S` below is this skill's `scripts/` directory: `~/.agents/skills/prose/scripts`,
or `~/.claude/skills/prose/scripts` if only that one is installed.

**Before a session's first file edit or post,** put the rules in front of you:

```sh
python3 $S/prose.py start --goals "review the fix; check it is safe to merge"
```

`--goals` lists the most probable reasons a reader opens this text, most
probable first. `start` prints the goals and the rules and signs nothing. In
Claude Code, until `start` or one of the first calls below has run in the
session, a hook blocks the session's first file write and its first `gh` or
GitHub MCP post.

**Before a commit**, stage the change, write the final message to a file, and
run the first call:

```sh
python3 $S/prose.py check -F msg.txt --goals "review the fix; check it is safe to merge"
```

Its `--goals` are the commit message's reader's: the reviewer's. Each changed
doc and spec has a reader of its own, who is not the reviewer and was not in
the conversation behind the change. Name that reader's goals for each file
with `--goals-for <path or pattern> '<goal; goal>'`, repeated as needed:

```sh
python3 $S/prose.py check -F msg.txt --goals "review the fix; check it is safe to merge" \
  --goals-for 'docs/**' "learn how sync works; find what to run when it fails" \
  --goals-for docs/api.md "call the API correctly; see what each error means"
```

Patterns are gitignore-style and relative to the repository root: `*` stays
in one directory, `**` spans any number, a pattern without a `/` matches at any
depth (`*.md`, `README.md`) and a leading `/` anchors it at the root
(`/README.md`). A pattern that matches a directory, such as `docs`, covers
every file under it, and `\` escapes a glob character in a file's name.
**The most specific match wins:** an exact path beats any pattern, and between
patterns the one with more literal characters (not counting `*`, `?` or
`[...]`) wins. Above, `docs/api.md` gets its own goals and every other file
under `docs/` gets the pattern's. Two equally specific matches with different
goals are refused.

For a change with many docs, put the goals in a file, one `pattern: goal; goal`
line each, and pass `--goals-file goals.txt`. Blank lines and `#` lines are
skipped; the pattern ends at the first colon followed by a space, so a colon
in a file's name is written `\:`. The file needs no shell quoting, so
apostrophes are safe. Keep it out of the commit.

```text
# Reader goals for this change
docs/**: learn how sync works; find what to run when it fails
docs/api.md: call the API correctly; see what each error means
/README.md: what it's for; how to start
```

Every changed doc and spec must get goals, except a deleted one. Without them
the call refuses, naming each file and its kind's default from the reader
table in [rules.md](rules.md) for you to adjust. A code comment may go
without, and then gets the table's code-comment row, labelled as a default.

It prints:

- the message's goals, echoed back;
- the prose in the change: the message, each doc and spec, and the comments
  the diff touches, each under the goals it gets and where they came from
  (`--goals`, its exact path, the pattern that matched, or its kind's default);
- a warning for any pattern that matches no listed file, which is usually a
  typo;
- history-language flags in those comments, as warnings;
- the rules: the pass, rules 1 to 8 in full, the rest as a checklist, and how
  agents cheat on the pass;
- the pass token, and the command to run next.

In a repository with a pre-commit hook, each `check` call runs it first, so a
formatter rewrites the staged files before you read them and before they are
signed. If the hook fails, the call stops with its reason; fix that, restage,
and run the call again.

Do the pass over each listed item against the goals above it, rereading each
changed doc passage inside its section, and restage. Then run that command on
the final text, with the token. The token holds the per-file goals, so the
second call needs no `--goals-for`; it refuses other ones, and a doc staged
since the first call that they don't cover.

```sh
python3 $S/prose.py check -F msg.txt --pass <token>
```

It prints only the result block, holding the trailer for this commit:

```text
=== prose result ===
Prose: ✓ 4d593e935186:9138830a72a2
=== prose open decisions: 0 ===
=== end prose ===
```

## Committing

Every commit carries `Prose: ✓ <tree>:<message>`, because every commit has a
message a reviewer reads. The two hashes bind it to the staged files and the
final message as they were when the signing `prose check` ran.

Commit through the shared commit script, with nothing staged or edited
between the signing call and the commit. Pass the block's `Prose:` value (the text
after `Prose: `) with `--verified-value`, and the message as the file you signed,
`msg.txt`, with `--message-file`:

```sh
C=$S/../../../lib/commit-trailer/commit-with-trailers.sh
$C --verified-value $S/verify-staged.sh Prose "✓ 4d593e935186:9138830a72a2" \
   --co-authored-by "<co-author>" --message-file msg.txt --
```

The file keeps the message off the command line, so it never needs quoting:
apostrophes, quotes and `$` in it are safe. Its first line is the subject, the
next line must be blank, and the rest is the body. Passing the message as two
words instead, `-- "<subject>" "<body>"`, still works.

Just before it commits, the script runs `verify-staged.sh`, which refuses the
commit if the staged files or the message no longer match the trailer. If it
refuses, run both calls again and pass the new value.

**When bug-hunter is installed,** the same commit carries bug-hunter's trailer
too ([the rule](../../lib/commit-trailer/DECISIONS.md#every-installed-skills-trailer-on-one-commit)).
While bug-hunter is running, its commit step runs the two calls above and
passes the `Prose:` value to its script: let it commit, once, with both
trailers. When you commit yourself, pass both in one command; bug-hunter's
uses `--minted-by` with its own minter:

```sh
$C --minted-by ~/.agents/skills/bug-hunter/scripts/mint-trailer.sh Bug-hunter "1 iteration, 1 bug fixed" \
   --verified-value $S/verify-staged.sh Prose "✓ 4d593e935186:9138830a72a2" \
   --co-authored-by "<co-author>" --message-file msg.txt --
```

**To amend,** run both calls with `--amend`, so the first lists the change
against the commit's parent; the trailer is the same either way. The commit
script cannot amend, so pass the block's whole `Prose:` line to git:

```sh
git commit --amend -F msg.txt --trailer "<the Prose: line>"
```

**When the hook reports a commit,** it names the commit and the reason:

- no `Prose:` trailer, or one that is not `✓ <tree>:<message>`: the pass did
  not run through `prose check`;
- `mismatch:`: the message changed after the check;
- `tree:`: the staged files changed after the check.

Run the pass and both calls again, and ask before rewriting a pushed commit.

## Posting

Posted text ends with a signed footer, such as `prose ✓ 3f2a91`, which a hook
checks before the post goes out. Post only text that went through `sign`,
exactly as `sign` printed it. The first call prints the rules and the token on stderr, and nothing on stdout:

```sh
python3 $S/prose.py sign --goals "approve the change"
python3 $S/prose.py sign --pass <token> < body.md > signed.md
gh pr create --title "..." --body-file signed.md
```

Run `gh` as the whole command, with the body as `--body-file <file>` or
`--body '<text>'`; a heredoc is not accepted. A hook blocks any other shape of
`gh` post, and any post whose footer does not match. A command that only
mentions a `gh` post, or a `gh` command that sends no text (a label edit), may
run inside a longer command; [README.md](README.md#posting-through-gh) says
what the hook reads. Any edit after signing breaks the footer; sign again after
editing.

## Never

- Skip the pass because the text is short.
- Type a trailer or footer by hand. It is valid only when a script produces
  it.
- Run the signing call before the pass is done. The rules are printed for the
  rewrite between the two calls.
