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
- **On request**, over text you did not write, as the next section says.

## Revising existing text

When someone asks you to improve, fix or tighten existing text with prose (a
file's comments, a doc, a spec, a PR description), write every section of it
again as its author. Don't choose which sections need work, by searching for
patterns or by any test of your own: editing keeps the existing framing, and a
sentence that sounds reasoned passes "is this wrong?" far more easily than
"would a fresh draft be better?".

For each section, such as a comment block, a doc section or a paragraph:

1. **Write a draft before you reread it,** from its reader's goals and from
   what it describes. The goals are the reader table's row in rules.md unless
   you have a reason to differ, which you state. For a comment, read the code
   it sits on and write the draft for that code. Write the draft out, even for
   a section you end up keeping: a draft held in your head can't be checked.
2. **Compare the draft with the existing text,** and carry over every fact,
   measurement, decision and warning the draft lacks. Comments often hold what
   the code can't show: a measured value, a rejected alternative, a past
   failure written as a warning.
3. **Keep the existing text only where your draft converges on it:** the
   draft, written without it, says the same things in essentially the same
   way. Otherwise the draft goes in, or a merge of the two. When you can't
   tell, the draft goes in.

A section whose lines an open branch also changes is held: leave it as it is,
and revise it after that branch merges. A held section is not kept; the reason
for leaving it is the other branch, not its reader.

Go through the text in order, each section with what it describes in view;
never read comments without their code. Split a text too long for one pass
into chunks, and give whoever takes a chunk, such as a subagent, this
procedure and all the code the chunk's comments sit on.

Then report how many sections you redrafted, merged, kept and held. Show each
kept section's draft beside the original, so a reviewer can check that the two
converge, and name the branch each held section waits for. `prose check` lists
only the sections your change touches, so your report is the only record that
you read the rest.

## Compaction

Agents read some docs before every task, so each sentence there that no longer
serves them is paid for on every read. Those docs stay compact, and a doc that
describes the current state holds no history. `prose compact` applies rule 8
of [rules.md](rules.md), *What is, not how it got here*, to a whole file, not
only to the lines a change touched. `$S` below is this skill's scripts
directory, as *Two calls* defines it.

**When it is due.** `prose check`'s first call measures each changed
current-state file. By default that is every `DECISIONS.md`, `SKILL.md`,
`AGENTS.md` and `CLAUDE.md`, every `architecture*.md`, and every OpenSpec
`spec.md`, `proposal.md` and `design.md` outside `openspec/changes/archive/`.
A `prose-compact` declaration in `.gitattributes` adds any other text file,
of any type; a file git treats as binary (`-diff`, `binary`, or a NUL byte)
is skipped. For each one due, it prints `compaction due for <file>: <why>`.
A file is due when either holds:
- **Size:** it is over its budget, 40,000 bytes by default, and either was
  never compacted or has grown by half since it was. Its last compaction is
  the newest commit behind HEAD, merged branches included, that shrank it by
  a tenth or more.
- **History markers,** at any size: a dated revision note such as
  "Revised 2026-09-30" or "dropped on 2026-09-28", a "History:" or "Update:"
  label, "previously", "originally", "formerly", or "was changed to".

**On that line, just compact.** Don't ask first. Commit the change you were
making, then compact in a commit of its own in the same pull request, so a
reviewer can read the compaction's diff apart from your change. Removing
history, wording or repetition needs no question. A reviewer's verdicts decide
what is restored. Ask the person only where restoring, or dropping, is itself
a judgement call.

Inside a git repository each step reads the file as staged, so stage it
before every step that checks it: what is checked is what will be committed.
Outside one, skip the staging and name the file by any path to it; each step
reads the working file.

1. Run `python3 $S/prose.py compact <file>`. Inside a repository, run it on
   the committed file, with nothing staged or unstaged in it; staging starts
   with step 3. Running it again on the unchanged file replaces the saved
   copy and is harmless. Add the files that might refer to it, as *Which
   files refer to the doc* below says; files you already know of can be
   named directly, with no search. It saves the file as staged, prints a
   brief between `=== compaction brief ===` lines, and exits 4.
2. Start a new subagent and give it the brief, exactly as printed. The brief
   is [compact.md](compact.md), then the file's path, the history markers
   found, and the headings other files link to or name. The subagent rewrites
   the file in place and replies `Would drop: none`, or one `Would drop:` line
   for each conclusion it left in place but believes is no longer true.
3. Stage the file (`git add <file>`), then run
   `python3 $S/prose.py compact <file> --verify`, with the same referrers as
   step 1. It compares the staged file with the saved copy. It prints the
   size before and after, what it searched, the headings removed, and the
   names that are gone. It fails, exiting 1, when:
   - a removed heading is still referenced: its `#anchor` appears in the
     file itself or in a file searched, or its text (16 characters or more)
     appears in another file searched, in any context. Text is compared with
     case, backticks, `*` and `_` ignored, and with line breaks and the
     comment or quote markers (`#`, `//`, `*`, `>`) starting a line read as
     one space, so a citation wrapped in a comment counts;
   - a history marker is left;
   - the file grew, or is empty.

   Have the compactor fix what it names, stage it, and run `--verify` again
   until it exits 0. It exits 2 when the file has unstaged changes, or when
   it could not read a file it was to search; fix that, or narrow the paths,
   and run it again.
4. Run `python3 $S/prose.py compact <file> --review`, with the file staged.
   It writes every change to a file, removed and rewritten text side by side,
   headed by the code spans, flags, constants, paths and headings the new
   file no longer has. It prints a brief between `=== compaction review
   brief ===` lines that names that file, and exits 4.
5. Start another new subagent, on the same model as the compactor, never a
   cheaper one, and give it that brief exactly as printed. The brief is
   [compact-review.md](compact-review.md). For each removal, the reviewer
   answers superseded, folded in (and where) or lost. It checks that every
   decision the new text keeps still carries its reason. For each rewritten
   or added sentence, it answers whether the claim holds against the code and
   docs. It ends with `Totals: <n> lost, <m> false`. Save its reply to a
   file.
6. Send each `lost` and `false` line back to the compactor, which restores
   the conclusion or corrects the claim. Stage the file and run `--verify`
   again. When the first review found anything, run steps 4 and 5 once more
   with a fresh reviewer, and fix what it finds. Never run more than two
   reviews. Report whatever the second one still finds.
7. Record the last review as complete:
   `python3 $S/prose.py compact <file> --reviewed <reply file> --dispositions <answers file>`.
   It checks that the reply gives every change a verdict and that its
   `Totals:` line matches them. The answers file holds one line for each
   change with a `lost` or `false` finding: `Change <n>: fixed` when the
   compactor fixed it, which needs the staged file to differ from the one
   reviewed, or `Change <n>: kept: <reason>`. With nothing fixed, the staged
   file must be the one reviewed. A reply with no findings needs no answers
   file. It exits 0, or 2 with what is missing.
8. Ask the person, through your host's picker, about each reviewer line
   whose text starts `ask:` and each `Would drop:` line from the compactor,
   and act on the answer. When you cannot ask, leave the conclusion in, and
   put the line in your result for your caller. If the answer changes the
   file, stage it and run steps 3 to 7 again: the commit gate needs a
   review of the file as staged, so this review runs even after two.
9. Commit as usual, with both calls of `prose check`.

**The commit gate.** A passing `--verify` and a completed review (step 7)
are each recorded for the file's staged content. Once step 1 has run on a
file, for 7 days after it and while the base (HEAD, or HEAD's parent with
`--amend`) still holds the copy step 1 started from, `prose check` refuses
to sign while that file is staged with other content and lacks either
record, whatever kind of file it is. Nothing else is gated: always compact
with `prose compact`, never by hand. Each refusal names the step:
- `<file> was compacted but not verified; run prose compact --verify <file>`
- `<file> was compacted but its review was not completed; ...`

Either refusal means the content staged is not the content that passed that
step: the file changed after it, or the step never ran. Run the named step
on the file as staged and sign again. Never change the file after its last
`--verify` and `--reviewed`. Each refusal also names `prose compact
--abandon <file>`, for a compaction you will not finish (see below). Step 1 refuses a file whose staged copy
differs from HEAD's, so every compaction starts from the committed file:
commit the change you were making first. A symlink holds no prose and is
not gated. A file renamed and shrunk in the same commit is not gated
either. Outside git there is no commit to gate, so running `--verify` is up
to you; the brief names it as the required last step.

**Abandoning a compaction.** Run `python3 $S/prose.py compact --abandon
<file>` when you started step 1 on a file and decided not to compact it,
or to discard the attempt and start again from step 1. It deletes the saved
copy, the review file and the file's `--verify` and review records, so the
commit gate treats the file as an ordinary one again; without it, the gate
refuses that file's commits for the 7 days the saved copy lasts. It leaves
the file itself as it is: restore the committed copy yourself if you mean
to discard the edits too. It exits 0, or 2 when no compaction was started
on the file.

**Name every compaction** in your report and in the pull request body, with
the file's size before and after, as `--verify` prints it: for example,
"Compacted DECISIONS.md: 107,341 -> 61,020 bytes (-43%)".

**Settings** go in `.gitattributes`, one line each:

```text
* prose-compact-budget=60000
docs/runbook.md prose-compact
CHANGELOG.md -prose-compact
docs/architecture.md prose-compact-budget=150000 prose-compact-growth=30
```

- `prose-compact-budget=<bytes>` replaces the budget.
- `prose-compact-growth=<percent>` replaces the growth share, 50 by default.
- `prose-compact` declares a file current-state.
- `-prose-compact` exempts a file.

Declarations reach the triggers only. Prose's writing rules still apply
only to docs.

A doc that is meant to stay over budget gets its own budget. `--verify`
suggests one when a compaction cut less than a tenth of a doc that is still
over its budget.

**Called by another skill.** A skill that keeps docs of its own compact, such
as spec-check for a change's `proposal.md` and `design.md`, runs the same
commands and may then run its own checks on the result:
- `prose.py compact <file> [--paths-from <file|-> [-0]] [-- <path>...]` exits
  4 and prints the brief on stdout between `=== compaction brief ===` and
  `=== end compaction brief ===`. The caller may add its own instructions
  after the brief.
- `prose.py compact <file> --verify [--paths-from <file|-> [-0]] [-- <path>...]`
  exits 0 when the result passes and 1 when it fails, with the report on
  stdout.
- `prose.py compact <file> --review` exits 4 and prints the reviewer's brief
  between `=== compaction review brief ===` and `=== end compaction review
  brief ===`.
- `prose.py compact <file> --reviewed <reply> [--dispositions <file>]` exits 0
  when the review is complete, recording it for the commit gate.
- `prose.py compact <file> --abandon` exits 0 when it discarded a started
  compaction, and 2 when none was started.
- Each call exits 2, with the reason on stderr, when the file is missing or
  has unstaged changes, when a later step has no saved copy, or when a file
  to search cannot be read. Step 1, `prose.py compact <file>`, saves that
  copy in the repository's git directory, and the later steps refuse a copy
  older than 7 days, so any agent in the same work tree can finish within
  that time.

### Which files refer to the doc

`--verify` searches for removed headings in the files you name, beside the
file itself. Inside a git repository it also searches every tracked file.
Outside one it searches only what you name. Each name is a file: a
directory is refused, and the refusal shows how to list its files.

**Find the candidates** before step 1, when you cannot yet know which
headings will go. Search every place a referrer could live (sibling folders,
other repositories, notes) for the doc's file name, every heading's
`#anchor`, and a distinctive word from each heading whose text is 16
characters or more, ignoring case. `--verify` fails where a heading's
anchor or text appears, even when a citation wraps the text or drops its
formatting, so search for one word of it, which neither can break. A file that has none of them cannot refer to the doc. A shorter
heading needs only its anchor searched. A broad term only adds candidates,
which costs nothing. `rg` skips hidden, gitignored and binary files; add
`--hidden --no-ignore -a` unless you know no referrer is one. The title
heading counts like any other.

```sh
rg -l -i -F -e 'DECISIONS.md' -e '#snapshot-lifetime-policy' -e 'lifetime' ~/notes ~/other-repo
```

Give step 1 and every `--verify` the same files: save the search's list
once to a file outside the repository, such as one in `$TMPDIR`, so it is
never staged or searched as a tracked file, and pass `--paths-from <that
file>` (with `-0` if the list is NUL-separated), or run the identical
search again from the same directory. Every relative path, the doc's and
the referrers', is read from the current directory, so run the search from
where you run prose.py. Inside a repository, spell and case the doc's path
as `git ls-files` lists it.

**A few known files: list them after `--`.** Give the same list to step 1
and to every `--verify`. A file named this way is read whatever its type
or size.

```sh
python3 $S/prose.py compact DECISIONS.md --verify -- ../README.md ../notes/plan.md
```

**Many files, or files a search found: `--paths-from`.** It reads one path
per line from a file, or from stdin with `-`:

```sh
rg -l -i -F -e 'DECISIONS.md' -e 'lifetime' ~/notes | python3 $S/prose.py compact DECISIONS.md --paths-from -
rg -l -i -F -e 'DECISIONS.md' -e 'lifetime' ~/notes | python3 $S/prose.py compact DECISIONS.md --verify --paths-from -
```

The first line is step 1 and the second is step 3, each fed the same search.
To read every Markdown file in a folder, list them with `find`.

Add `-0` when the list is NUL-separated, as `rg -l0` and `find -print0`
write it, and use those forms whenever the tool can write them. In a list of
one path per line, a name holding a newline splits in two and its file is
missed, and a tool that quotes odd names, spaces among them, gives paths
that match no file. A NUL-separated list keeps every name exactly.

```sh
rg -l0 -i -F -e 'DECISIONS.md' -e 'lifetime' ~/notes | python3 $S/prose.py compact DECISIONS.md --verify --paths-from - -0
find ~/notes -name '*.md' -print0 | python3 $S/prose.py compact DECISIONS.md --verify --paths-from - -0
```

The two forms combine: `--paths-from list.txt -- ../README.md`. In a
pipeline the exit code is prose.py's, the last command's: 1 still means a
reference broke.

**Read the report's `Searched for references:` line** before trusting a
pass. Inside a repository it names the tracked files, and the given files and
where they came from. Outside one, it names only the given files and says
`only these were read`. With no paths outside a repository it says
`references from other files were not checked`. Then a pass proves only
that the file's own links still work; give the referrers and run it again.
`0 given files (the list was empty)` means the search found nothing, which
is a real answer only if the search was right.

## Two calls: the rules, then the signature

Each commit and each post takes two calls. The first takes the goals of that
text's reader, prints the rules and a pass token, and exits 4. You do the pass;
then the second call takes the token and signs. A token signs one text, once,
within 2 hours, and only of the kind that issued it: `check` for a commit,
`sign` for a post.

`S` below is the `scripts/` directory in this skill's base directory: the
directory that holds this SKILL.md, which Claude Code names on the "Base
directory for this skill:" line above it. Write the path out in full, as that
line gives it; don't swap in a home-directory install path, which may be
missing or hold a different copy.

**Before a session's first file edit or post,** put the rules in front of you:

```sh
python3 $S/prose.py start --goals "review the fix; check it is safe to merge"
```

`--goals` lists the most probable reasons a reader opens this text, most
probable first. To keep them off the command line, which other users of the
machine can read, write them to a file instead and pass `--goals-file
goals.txt`: one or more goals per line, separated by `;`. Unlike `check`'s
goals file, below, a line holds goals only and names no file. Blank lines and
`#` lines are skipped. Pass `--goals` or the file, not both.
`start` prints the goals and the rules and signs nothing. In
Claude Code, until `start` or one of the first calls below has run in the
session, a hook blocks the session's first file write and its first `gh` or
GitHub MCP post.

**Before a commit**, stage the change, write the final message to a file, and
run the first call:

```sh
python3 $S/prose.py check -F msg.txt --goals "review the fix; check it is safe to merge"
```

Its `--goals` are the commit message's reader's: the reviewer's. To keep them
off the command line, pass `--message-goals-file goals.txt` instead, a file
written like `start`'s: one or more goals per line, separated by `;`, naming
no file. Pass `--goals` or the file, not both. Each changed
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
- the rules: the pass, rules 1 to 9 in full, the rest as a checklist, and how
  agents cheat on the pass;
- the pass token, and the command to run next.

In a repository with a pre-commit hook, each `check` call runs it first, so a
formatter rewrites the staged files before you read them and before they are
signed. If the hook fails, the call stops with its reason; fix that, restage,
and run the call again.

Do the pass over each listed item against the goals above it, rereading each
changed doc passage inside its section, and restage. Then run that command on
the final text, with the token. When the change holds a comment or doc
passage, it first asks for a cold read; see [The cold read](#the-cold-read). The token holds the per-file goals, so the
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
stderr for `sign`. The brief is [cold-read.md](cold-read.md), then the line the
report must start with, then each text with its reader's goals: a comment or
doc by its file and lines, a post quoted in full.

1. Start a new subagent, and give it the brief exactly as printed. Add
   nothing: not the conversation, not what the text is meant to say, not a
   summary of the change.
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
   the understood line describes.
   `matches` means the understood line says what you meant: who acts,
   whether it always happens, and whose doing it is.
5. **A person decides every kept finding and understood line.** To keep one
   is to leave its item as it is: for an understood line, although it shows
   a meaning other than yours. For each one you would keep, ask a person one
   question, through your host's interactive picker (in Claude
   Code, the `AskUserQuestion` tool): show the quoted words and the cold
   reader's note, or its understood line beside what you meant, and your
   reason, with two options, "Keep as is" and "Fix it". "Fix it": rewrite the
   passage, restage it, and make its line `fixed`. "Keep as is": make its
   line `kept (asked): <reason>`. Neither answer needs a new cold read. The
   token is still unspent after you ask, and a fixed line is checked by its
   item having changed, not read cold again. `(asked)` is your statement that a
   person answered; the script cannot check it.
6. Run the signing call again, adding `--cold-read cold-read.txt
   --dispositions dispositions.txt`.

**When you cannot ask** (you are a subagent or a background job, or your host
has no picker), don't sign and don't commit. Write the line of each one you
would keep without `(asked)`, as `<n>. kept: <reason>` or `Item <n>: kept:
<reason>`, and run the signing call anyway. It
refuses and keeps the token. Its message names each one you kept: a finding
with its quote and the cold reader's note, an understood line with its text,
and your reason for each. It ends with the paths of the report and the
dispositions file. Leave the change staged and put that message, whole, in
your result. Whoever receives your result asks the person, edits the
dispositions file and runs the signing call before the token's 2 hours are
up.

A commit's `Prose:` value then ends with the cold read's counts, such as
`; cold read: 5 findings, 3 fixed, 2 kept; understood: 4 items, 1 fixed, 0 kept`,
or `; cold read: no findings; understood: 2 items, 0 fixed, 0 kept`. The
understood counts are the number of items, then how many of their understood
lines did not match and were fixed or kept. A value from before the understood lines,
without them, still verifies.
The script mints them; pass the value as the result block prints it. A commit
with no cold read keeps the plain value. A post's footer carries no counts.

The signing call refuses (exit 2), signs nothing and keeps the token when:
- the report or the dispositions file does not start with this token's line;
- the report has a line not in the brief's form, says nothing about an
  item, or has no understood line for one;
- a finding or understood line is unanswered, answered twice, or not in the
  report, or is kept without a reason;
- a finding or understood line is marked `fixed`, but its item has not
  changed since the brief;
- a finding or understood line is kept without `(asked)`;
- a file the brief did not name now has a changed comment or doc passage:
  run the signing call without `--cold-read` for a new brief, and have that
  read cold.

Each token takes one cold read; the fixes are not read cold again. The script
checks `fixed` instead, by the item having changed.

**Without subagents, hand the cold read back.** If you were started by
something that reads your result, such as a caller or a workflow stage, do
not read the brief yourself, sign or commit. Leave the change staged and put
in your result the brief, whole and as printed, its token, and the paths of
the message file and the worktree. The token is stored in the repository's
git directory, not in your session, so any agent working in the same
repository can spend it. Whoever holds your result gives the brief to a fresh
agent. Then they, or an agent they start, fix the findings, write the
dispositions and run the signing call before the token's 2 hours are up.

As workflow stages, that is three agents:
1. **The author** writes and stages the change, runs the signing call, and
   returns the brief, the token and the paths as fields of its structured
   output, without committing.
2. **The cold reader** gets the brief as its whole prompt. The workflow
   script passes the author's brief field on exactly as returned, never
   summarised or reworded.
3. **The finisher** works in the same repository with the report and the
   token. It first runs `prose.py start`, which prints the rules and lets
   the hook allow its first file edit; then it fixes, answers each finding
   and understood line, and signs. One it would keep goes to a person:
   through its own picker if it has one, or else handed back as in *When you
   cannot ask*.

Read the brief yourself only when nothing will read your result: read it as
if it were all you knew, open only what it names, and write the report as it
asks.

## Committing

Every commit carries `Prose: ✓ <tree>:<message>`, because every commit has a
message a reviewer reads. The two hashes bind it to the staged files and the
final message as they were when the signing `prose check` ran. After a cold
read, the value ends with its counts (see [The cold read](#the-cold-read)).

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
uses `--minted-by` with its own minter. `B` below is bug-hunter's directory,
beside this skill's: the base directory with its last part, `prose`, replaced
by `bug-hunter`.

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
exactly as `sign` printed it. The first call prints the rules and the token on stderr, and nothing on stdout:

```sh
python3 $S/prose.py sign --goals "approve the change"
python3 $S/prose.py sign --pass <token> < body.md > signed.md
gh pr create --title "..." --body-file signed.md
```

`sign`'s first call takes `--goals-file` in place of `--goals`, as `start`
does. The second call, with `--pass`, may pass the same goals or none, and
refuses other goals.

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
- Change the cold-read brief, or add to it, before giving it to the cold
  reader.
