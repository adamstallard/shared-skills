# prose: reference

Detail SKILL.md points to. Read the section SKILL.md names when you reach
that case.

## Goals from a file

`--goals-file` for `start` and `sign`, and `--message-goals-file` for
`check`, name a file holding one or more goals per line, separated by `;`,
with no `pattern:` prefix. Blank lines and `#` lines are skipped. Pass
`--goals` or the file, not both. `check`'s own `--goals-file` is a different
file: it gives per-file goals, as the next section says.

## Per-file goals: patterns and the goals file

Patterns are gitignore-style and relative to the repository root: `*` stays
in one directory, `**` spans any number, a pattern without a `/` matches at
any depth (`*.md`, `README.md`) and a leading `/` anchors it at the root
(`/README.md`). A pattern matching a directory, such as `docs`, covers every
file under it, and `\` escapes a glob character in a file's name. **The most
specific match wins:** an exact path beats any pattern, and between patterns
the one with more literal characters (not counting `*`, `?` or `[...]`), so
in SKILL.md's example command `docs/api.md` gets its own goals rather than
those of `docs/**`. Two equally specific matches with different goals are
refused.

For many docs, `check` takes the per-file goals from `--goals-file goals.txt`,
one `pattern: goal; goal` line each. Blank lines and `#` lines are skipped; the pattern ends at the first colon followed by a space, so a
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

The first call prints the message's goals; the prose in the change (the
message, each doc and spec, and the comments the diff touches), each under the
goals it gets and where they came from (`--goals`, its exact path, the pattern that
matched, or its kind's default); a warning for any pattern that matches no
listed file, usually a typo; history-language flags in those comments, as
warnings; the rules (the pass, rules 1 to 9 in full, the rest as a
checklist, and how agents cheat on the pass); and the pass token with the
command to run next.

Each `check` call first runs the repository's pre-commit hook, if any, so a
formatter rewrites the staged files before you read them and before they are
signed. If the hook fails, the call stops with its reason; fix that, restage,
and run the call again.

## Cold read: counts, refusals, reuse and hand-back

After a cold read, a commit's `Prose:` value ends with its counts, such as
`; cold read: 5 findings, 3 fixed, 2 kept; understood: 4 items, 1 fixed, 0 kept`,
or `; cold read: no findings; understood: 2 items, 0 fixed, 0 kept`. The
understood counts are the number of items, then how many of their understood
lines did not match and were fixed or kept. The script mints the counts;
pass the value as the result block prints it. A value with cold-read counts
but no understood counts, as earlier commits carry, still verifies. A commit
with no cold read keeps the plain value. A post's footer carries no counts.

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
recorded counts. So correcting only the message needs no new cold read. Any
staged change, other goals, or a read no signing call accepted brings the
full brief.

**Without subagents, hand the cold read back.** If something reads your
result, such as a caller or a workflow stage, do not read the brief
yourself, sign or commit. Leave the change staged and put in your result the
brief file's path, its token, and the paths of the message file and the
worktree. The brief file and the token live in the repository's git
directory, not your session, so any agent in the same repository can use
them. Whoever holds your result gives the brief file's path to a fresh
agent, then finishes steps 2 to 6 of SKILL.md's *The cold read*, or has an
agent finish them, within the token's 2 hours. As workflow stages, that is
three agents:
1. **The author** writes and stages the change, runs the signing call, and
   returns the brief file's path, the token and the other paths as fields
   of its structured output, without committing.
2. **The cold reader** gets, as its whole prompt, the instruction to read
   the brief file at that path, passed on exactly as returned, and follow it.
3. **The finisher**, in the same repository, with the token and the cold
   reader's report, first runs `prose.py start`, which prints the rules and
   lets the hook allow its first file edit. Then it does steps 2 to 6: it
   saves the report to a file, fixes, answers and signs. A finding it would
   keep goes to a person through its own picker, or is handed back as in
   SKILL.md's *When you cannot ask*.

Read the brief yourself only when nothing will read your result: read it as
if it were all you knew, open no other file, and write the report as it
asks.

## Committing with other skills' trailers, and amending

**When bug-hunter is installed,** the same commit carries bug-hunter's trailer
too ([the rule](../../lib/commit-trailer/DECISIONS.md#every-installed-skills-trailer-on-one-commit)).
While bug-hunter is running, its commit step runs prose's two calls (SKILL.md's *Two calls*) and
passes the `Prose:` value to its script: let it commit, once, with both
trailers. When you commit yourself, pass both in one command to the commit
script (`$C`, from SKILL.md's *Committing*), bug-hunter's with `--minted-by`
and its own minter. `B` is bug-hunter's directory: prose's base directory with
its last part, `prose`, replaced by `bug-hunter`.

```sh
$C --minted-by $B/scripts/mint-trailer.sh Bug-hunter "1 iteration, 1 bug fixed" \
   --verified-value $S/verify-staged.sh Prose "✓ 4d593e935186:9138830a72a2" \
   --co-authored-by "<co-author>" --message-file msg.txt --
```

**When spec-check is installed,** a commit that changes `openspec/` carries its
`Spec-check:` value too, as one more `--verified-value` family; spec-check's
SKILL.md (*Commit*) shows it.

**To amend,** run both calls with `--amend`, so the first lists the change
against the commit's parent; the `Prose:` value has the same form as for a
new commit. The commit
script cannot amend, so pass the block's whole `Prose:` line to git:

```sh
git commit --amend -F msg.txt --trailer "<the Prose: line>"
```

## Posting through gh

Run `gh` as the whole command, with the body as `--body-file <file>` or
`--body '<text>'`; a heredoc is not accepted. A hook blocks any other shape of
`gh` post, and any post whose footer does not match. A command that only
mentions a `gh` post, or a `gh` command that sends no text (a label edit), may
run inside a longer command; [README.md](README.md#posting-through-gh) says
what the hook reads. Any edit after signing breaks the footer, so sign again.

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

