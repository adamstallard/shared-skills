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

The rules live only in [rules.md](rules.md). This skill's script, `prose.py`,
prints them at `prose.py start` and at the first call of `prose.py check`
(before a commit) or `prose.py sign` (before a post); *Two calls* says how.
Work from that printout, not from memory of an earlier session. Before
changing this file, read [DECISIONS.md](DECISIONS.md), which says why each rule
and mechanism is the way it is.

## What counts as prose

Anything a human reviews: READMEs and other docs, code comments, architecture
docs, specs, commit messages, pull request descriptions, and posts to GitHub,
Linear and Discord. **Short kinds are not exempt.** Commit subjects and ticket
comments bloat too.

## When the pass runs

- **Before every commit that contains prose**, on the staged change and the
  commit message. Write the code first, do the pass as one read of the
  finished text, then commit.
- **Before posting** any pull request description or comment.
- **On request**, over text you did not write, as the next section says.

## Revising existing text

When asked to improve, fix or tighten existing text (a file's comments, a doc,
a spec, a PR description), rewrite every section of it as its author. Don't
pick out sections that seem to need work, by searching for patterns or by any
test of your own. Picking leads to editing the rest in place, and editing
keeps the existing framing: a sentence that sounds reasoned passes "is this
wrong?" far more easily than "would a fresh draft be better?".

For each section, such as a comment block, a doc section or a paragraph:

1. **Write a draft before you reread it,** from its reader's goals and from
   what it describes. The goals are the reader table's row in rules.md unless
   you state a reason to differ. For a comment, draft from the code it sits
   on. Write the draft out even for a section you keep: a draft held in your
   head can't be checked.
2. **Compare the draft with the existing text,** and carry over every fact,
   measurement, decision and warning the draft lacks. Comments often hold what
   the code can't show: a measured value, a rejected alternative, a past
   failure written as a warning.
3. **Keep the existing text only where the draft, written without it, says
   the same things in essentially the same way.** Otherwise the draft goes
   in, or a merge of the two. When you can't tell, the draft goes in.

A section whose lines an open branch also changes is held: leave it as it is,
and revise it after that branch merges. Held is not kept: the reason for
leaving it is the other branch, not its reader.

Go through the text in order, each section with what it describes in view;
never read comments without their code. Split a text too long for one pass
into chunks, and give whoever takes a chunk, such as a subagent, this
procedure and all the code its comments sit on.

Then report how many sections you redrafted, merged, kept and held. Show each
kept section's draft beside the original, so a reviewer can check that they
converge, and name the branch each held section waits for. `prose check` lists
only the sections your change touches, so your report is the only record that
you read the rest.

## Compaction

Agents read some docs before every task, so those docs stay compact. When
`prose check` prints `compaction due for <file>`, or a person asks you to
compact a file, read [compaction.md](compaction.md) and follow it before
compacting. Never compact by hand: only `prose compact` runs the checks and
the review, and only a compaction it started is gated. A file with a
compaction started and not finished makes `prose check` refuse to sign while
it is staged; each refusal names the step to run, or
`prose compact --abandon <file>`.

## Two calls: the rules, then the signature

Each commit and each post takes two calls. The first takes the goals of that
text's reader, prints the rules and a pass token, and exits 4. You do the
pass; then the second call takes the token and signs. A token signs one text,
once, within 2 hours, and only of the kind that issued it: `check` for a
commit, `sign` for a post.

`S` is the `scripts/` directory beside this SKILL.md, in the directory Claude
Code names on the "Base directory for this skill:" line it shows above this
file's text when the skill loads. Write the
path out in full, as that line gives it; a home-directory install path may be
missing or hold a different copy.

**Before a session's first file edit or post,** put the rules in front of you:

```sh
python3 $S/prose.py start --goals "review the fix; check it is safe to merge"
```

`--goals` lists the most probable reasons a reader opens this text, most
probable first. Other users of the machine can read the command line, so a
first call may take the goals from a file instead: `--goals-file` for `start`
and `sign`, `--message-goals-file` for `check`. That file holds one or more
goals per line, separated by `;`, with no `pattern:` prefix (unlike
`check`'s `--goals-file`, below, which gives per-file goals), and skips
blank lines and `#` lines. Pass `--goals` or the file, not both. `start` prints the goals and
the rules and signs nothing. In Claude Code, until `start` or one of the
first calls below has run in the session, a hook blocks the session's first
file write and its first `gh` or GitHub MCP post.

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
in one directory, `**` spans any number, a pattern without a `/` matches at
any depth (`*.md`, `README.md`) and a leading `/` anchors it at the root
(`/README.md`). A pattern matching a directory, such as `docs`, covers every
file under it, and `\` escapes a glob character in a file's name. **The most
specific match wins:** an exact path beats any pattern, and between patterns
the one with more literal characters (not counting `*`, `?` or `[...]`), so
in the command above `docs/api.md` gets its own goals. Two equally specific matches with
different goals are refused.

For many docs, `check` takes the per-file goals from
`--goals-file goals.txt`, one `pattern: goal; goal` line each. Blank lines and `#` lines
are skipped; the pattern ends at the first colon followed by a space, so a
colon in a file's name is written `\:`. The file needs no shell quoting, so
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

It prints the message's goals; the prose in the change (the message, each
doc and spec, and the comments the diff touches), each under the goals it
gets and where they came from (`--goals`, its exact path, the pattern that
matched, or its kind's default); a warning for any pattern that matches no
listed file, usually a typo; history-language flags in those comments, as
warnings; the rules (the pass, rules 1 to 9 in full, the rest as a
checklist, and how agents cheat on the pass); and the pass token with the
command to run next.

Each `check` call first runs the repository's pre-commit hook, if any, so a
formatter rewrites the staged files before you read them and before they are
signed. If the hook fails, the call stops with its reason; fix that, restage,
and run the call again.

Do the pass over each listed item against the goals above it, rereading each
changed doc passage inside its section, and restage. Then run that command on
the final text, with the token. When the change holds a comment or doc
passage, it first asks for a [cold read](#the-cold-read). The token holds the
per-file goals, so the second call needs no `--goals-for`. It refuses
per-file goals other than the token's, and a doc staged since the first
call that the token's goals don't cover.

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

## The cold read

You read your own text knowing what you meant, so you fill its gaps without
seeing them. Before a text is signed, an agent that has never seen the
conversation reads it and reports every place it stopped, reread or guessed.
For every item it also says in one line what it understood the item to state,
because a reader who misreads with confidence never stops. The line says:
- who or what does each thing;
- whether it always happens, or only in some case;
- whether the code does it, or someone else could make it happen.

**What gets one:** every comment block the change adds to or edits, read
whole even when one line changed; every doc or spec passage it adds to; and
every post, whatever its length. The commit message gets none, so a commit
that changes no comment or doc signs without one. A doc that git diffs as
binary is skipped, since prose cannot read it.

**How.** Run the signing call as usual. When it has something to read cold and
you pass no report, it signs nothing, keeps the token and exits 5. It prints a
brief between `=== cold-read brief ===` lines, on stdout for `check` and on
stderr for `sign`, and then a `Brief file:` line naming the file it saved the
brief in. The brief is [cold-read.md](cold-read.md), then the line the
report must start with, then each text with its reader's goals: a comment or
doc by its file and lines, a post quoted in full.

1. Give a new subagent only the brief file's path, telling it to read the
   file and follow it. Don't copy the brief into its prompt: a retyped brief
   can drop or repeat lines. Add nothing: not the conversation, not what the
   text is meant to say, not a summary of the change.
2. Save its report, as it wrote it, to a file outside the commit, such as
   `cold-read.txt` beside `msg.txt`. The brief asks for one line per
   finding, quoting the words that stopped the reader, one line for each
   item read straight through, and one understood line for every item:

   ```text
   cold-read <token>
   Finding 1, item 1, guessed: «It runs there» What runs, and where?
   Item 1, understood: The worker runs each command in its own clone.
   Item 2: read straight through.
   Item 2, understood: A person may rerun a failed upload; nothing retries it.
   ```

3. Fix the places the report names, by the rules, and restage. Compare each
   understood line with what you meant, and fix the item where they differ.
4. Answer every finding and every understood line in a dispositions file
   beside the report, such as `dispositions.txt`. Its first line binds it to
   the same token; then one line per finding, and one per item:

   ```text
   dispositions <token>
   1. fixed
   Item 1: matches
   Item 2: fixed
   ```

   `fixed` means you changed the item: the one the finding is in, or the one
   the understood line describes. `matches` means the understood line says
   what you meant on all three points above.
5. **A person decides every kept finding and understood line.** To keep one
   is to leave its item as it is: for an understood line, although it shows
   a meaning other than yours. For each one you would keep, ask a person one
   question through your host's interactive picker (in Claude Code, the
   `AskUserQuestion` tool): show the quoted words and the cold reader's note,
   or its understood line beside what you meant, and your reason, with two
   options. "Fix it": rewrite the passage, restage it, and make its line
   `fixed`. "Keep as is": make its line `kept (asked): <reason>`. The token
   stays unspent. `(asked)` is your statement that a person answered; the
   script cannot check it.
6. Run the signing call again, adding `--cold-read cold-read.txt
   --dispositions dispositions.txt`.

**When you cannot ask** (you are a subagent or a background job, or your host
has no picker), don't sign or commit. Write each line you would keep
without `(asked)`, as `<n>. kept: <reason>` or `Item <n>: kept: <reason>`,
and run the signing call anyway. It refuses, keeps the token, and names each
kept line (a finding with its quote and the cold reader's note, an
understood line with its text) with your reason, then the paths of the
report and the dispositions file. Leave the change staged and put that
message, whole, in your result. Whoever receives it asks the person, edits
the dispositions file and runs the signing call before the token's 2 hours
are up.

A commit's `Prose:` value then ends with the cold read's counts, such as
`; cold read: 5 findings, 3 fixed, 2 kept; understood: 4 items, 1 fixed, 0 kept`,
or `; cold read: no findings; understood: 2 items, 0 fixed, 0 kept`. The
understood counts are the number of items, then how many of their understood
lines did not match and were fixed or kept. The script mints the counts;
pass the value as the result block prints it. A value with cold-read counts
but no understood counts, as earlier commits carry, still verifies. A commit with no cold read keeps the plain value. A post's
footer carries no counts.

The signing call refuses (exit 2), signs nothing and keeps the token when:
- the report or the dispositions file does not start with this token's line;
- the report has a line not in the brief's form, says nothing about an
  item, or has no understood line for one;
- a finding or understood line is unanswered, answered twice, or not in the
  report, or is kept without a reason or without `(asked)`;
- a finding or understood line is marked `fixed`, but its item has not
  changed since the brief;
- a file the brief did not name now has a changed comment or doc passage:
  run the signing call without `--cold-read` for a new brief, and have that
  read cold.

Each token takes one cold read. Fixes, including those a person chose, are
not read cold again: the script checks `fixed` by the item having changed.

**A re-sign of the same tree reuses its cold read.** A signing call that
checks a cold read and signs records the staged tree's hash with the read's
counts. A signing call with a new token, from a new first call, whose
staged tree has that exact hash, listed with the same items and goals,
signs without a brief, and the `Prose:` value it prints carries the
recorded counts. So correcting only the message needs no new
cold read. Any staged change, other goals, or a read no signing call
accepted brings the full brief.

**Without subagents, hand the cold read back.** If something reads your
result, such as a caller or a workflow stage, do not read the brief
yourself, sign or commit. Leave the change staged and put in your result the
brief file's path, its token, and the paths of the message file and the
worktree. The brief file and the token live in the repository's git
directory, not your session, so any agent in the same repository can use
them. Whoever holds your result gives the brief file's path to a fresh
agent, then finishes steps 2 to 6, or has an agent finish them, within the
token's 2 hours. As workflow stages, that is three agents:
1. **The author** writes and stages the change, runs the signing call, and
   returns the brief file's path, the token and the other paths as fields
   of its structured output, without committing.
2. **The cold reader** gets, as its whole prompt, the instruction to read
   the brief file at that path, passed on exactly as returned, and follow it.
3. **The finisher**, in the same repository with the report and the token,
   first runs `prose.py start`, which prints the rules and lets the hook
   allow its first file edit; then it does steps 3 to 6, a finding it would
   keep going to a person through its own picker, or handed back as in
   *When you cannot ask*.

Read the brief yourself only when nothing will read your result: read it as
if it were all you knew, open only what it names, and write the report as it
asks.

## Committing

Every commit carries `Prose: ✓ <tree>:<message>`, because every commit has a
message a reviewer reads. The two hashes bind it to the staged files and the
final message as they were when the signing `prose check` ran. After a cold
read, the value ends with its counts (see [The cold read](#the-cold-read)),
and, for a compaction, with the files compacted (see
[compaction.md](compaction.md)).

Commit through the shared commit script, with nothing staged or edited
between the signing call and the commit. Pass the block's `Prose:` value (the
text after `Prose: `) with `--verified-value`, and the message file you
signed with `--message-file`:

```sh
C=$S/../../../lib/commit-trailer/commit-with-trailers.sh
$C --verified-value $S/verify-staged.sh Prose "✓ 4d593e935186:9138830a72a2" \
   --co-authored-by "<co-author>" --message-file msg.txt --
```

The file keeps the message off the command line, so apostrophes, quotes and
`$` in it are safe. Its first line is the subject, the next line must be
blank, and the rest is the body. Passing the message as two words instead,
`-- "<subject>" "<body>"`, still works.

Just before it commits, the script runs `verify-staged.sh`, which refuses the
commit if the staged files or the message no longer match the trailer. If it
refuses, run both calls again and pass the new value. When only the message
changed, the new signing call reuses the cold read (*The cold read*).

**When bug-hunter is installed,** the same commit carries bug-hunter's trailer
too ([the rule](../../lib/commit-trailer/DECISIONS.md#every-installed-skills-trailer-on-one-commit)).
While bug-hunter is running, its commit step runs the two calls above and
passes the `Prose:` value to its script: let it commit, once, with both
trailers. When you commit yourself, pass both in one command, bug-hunter's
with `--minted-by` and its own minter. `B` is bug-hunter's directory: the
base directory with its last part, `prose`, replaced by `bug-hunter`.

```sh
$C --minted-by $B/scripts/mint-trailer.sh Bug-hunter "1 iteration, 1 bug fixed" \
   --verified-value $S/verify-staged.sh Prose "✓ 4d593e935186:9138830a72a2" \
   --co-authored-by "<co-author>" --message-file msg.txt --
```

**When spec-check is installed,** a commit that changes `openspec/` carries its
`Spec-check:` value too, as one more `--verified-value` family; spec-check's
SKILL.md (*Commit*) shows it.

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
exactly as `sign` printed it. The first call prints the rules and the token on
stderr, and nothing on stdout:

```sh
python3 $S/prose.py sign --goals "approve the change"
python3 $S/prose.py sign --pass <token> < body.md > signed.md
gh pr create --title "..." --body-file signed.md
```

The second call, with `--pass`, may pass the same goals or none, and refuses
other goals.

Run `gh` as the whole command, with the body as `--body-file <file>` or
`--body '<text>'`; a heredoc is not accepted. A hook blocks any other shape of
`gh` post, and any post whose footer does not match. A command that only
mentions a `gh` post, or a `gh` command that sends no text (a label edit), may
run inside a longer command; [README.md](README.md#posting-through-gh) says
what the hook reads. Any edit after signing breaks the footer, so sign again.

## Never

- Skip the pass because the text is short.
- Type a trailer or footer by hand. It is valid only when a script produces
  it.
- Run the signing call before the pass is done. The rules are printed for the
  rewrite between the two calls.
- Change the cold-read brief, or add to it, before giving it to the cold
  reader.
