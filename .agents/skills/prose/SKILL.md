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

Agents read some docs before every task, so each sentence there that no longer
serves them is paid for on every read. Those docs stay compact, and a doc that
describes the current state holds no history. `prose compact` applies rule 8
of [rules.md](rules.md), *What is, not how it got here*, to a whole file, not
only to the lines a change touched. `$S` is this skill's scripts directory, as
*Two calls* defines it.

**When it is due.** `prose check`'s first call prints
`compaction due for <file>: <why>` for each changed doc that agents read often
and that is due. A doc is read often when it is:
- a `CLAUDE.md`, `AGENTS.md` or `SKILL.md`;
- a file a `SKILL.md` or `AGENTS.md` links in a paragraph that asks for it to
  be read first, or read before some task. Read before changing the skill
  does not count, as for this file's link to DECISIONS.md: that file is read
  only when the skill changes;
- an open OpenSpec change's `proposal.md` or `design.md`;
- declared with `prose-compact` in `.gitattributes`;
- or a `DECISIONS.md`, `architecture*.md` or OpenSpec `spec.md` that none of
  the above covers, read at least 20 times since its last compaction. Each of
  the last 300 commits behind HEAD counts as one read of the docs it
  implies: a change in a skill's directory implies its `SKILL.md` and
  read-first files; a `Bug-hunter:`, `Prose:` or `Spec-check:` trailer
  implies that skill's `SKILL.md`, and `Spec-check:` also the main specs
  (`openspec/specs/**/spec.md`) and open OpenSpec changes. A read-first file
  is already covered above, so of the files this bullet names, only a main
  spec gains reads: a `DECISIONS.md` or architecture doc is read often only
  when linked to be read first, or declared.

A doc read often is due when either holds:
- **Flagged text:** the text the detectors (below) flag holds at least 1,000
  bytes more than at its last compaction, and those added bytes are at least
  10% of the file's current size. For a doc never compacted, all its flagged
  text counts.
- **Growth:** it has grown by half, and by 2,000 bytes or more, since its
  last compaction. A doc never compacted has no growth to measure.

Its last compaction is the newest commit behind HEAD, merged branches
included, whose `Prose:` trailer lists it after `compacted:`, or that shrank
it by a tenth or more. The signing call adds `; compacted: <path>` to the
trailer for each staged file whose `--verify` and `--reviewed` passed, so
every clone sees even a compaction that cut little.

The detectors flag sentences and paragraphs outside code and quotations:
- history: a dated revision note such as "Revised 2026-09-30", a
  "History:" or "Update:" label, "previously", "originally", "formerly" or
  "was changed to";
- repetition: a sentence of 10 or more words stated twice, or 8 words in a
  row that two sentences share;
- amendment notes: "Amended by", "Superseded by", "Withdrawn", "as first
  written";
- long rejected alternatives: a "Rejected" paragraph or list item longer
  than the sentence naming the alternative and one sentence of reason, or a
  "Rejected" section longer than one sentence;
- stale references: a path, flag or function in a code span that the
  repository no longer has. A path counts only when its first directory is
  one the repository has, at its root or beside the doc;
- narrative: "initially", "at first", "we tried", "turned out", "ended up";
- filler: a "Note:" line, "it is worth noting", "note that", "as mentioned
  above", "basically".

**When a doc is due, compact it without asking.** Commit the change you were
making, then compact in a commit of its own in the same pull request, so a
reviewer reads the compaction's diff apart from your change. Removing history,
wordiness or repetition needs no question, and the review subagent's verdicts
(steps 6 to 8) decide what is restored. Ask the person only where restoring, or dropping, is itself a
judgement call.

Inside a git repository each step reads the file as staged, so stage it
before every step that checks it: what is checked is what will be committed.
Outside one, skip the staging and name the file by any path; each step reads
the working file.

1. Run this on the committed file, with nothing staged or unstaged in it,
   naming the files that might refer to the doc (*Which files refer to the
   doc*):
   `python3 $S/prose.py compact <file> [--paths-from <file|-> [-0]] [-- <path>...]`.
   It refuses a file whose staged copy differs from HEAD's. Running it again
   on the unchanged file replaces the saved copy and is harmless. It saves
   a copy of the committed file for later steps to compare against, prints
   a brief between `=== compaction brief ===` and
   `=== end compaction brief ===`, saves the brief to the file named on the
   `Brief file: <path>` line after them, and exits 4.
2. Give a new subagent only the brief file's path, as *The cold read* says.
   The brief is [compact.md](compact.md), then the doc's path, the headings
   other files link to or name, whether to keep "who decided" credits, the
   answers file, and every flagged passage with its lines, kind and text.
   The answers file is in a folder of the system's temporary directory that
   only your operating-system account can use, so the subagent never writes
   inside `.git`. The subagent rewrites the file in place, answers each
   passage in the answers file (`removed`, `rewritten`, or `kept: <reason>`),
   and replies `Would drop: none` or one `Would drop:` line per conclusion it
   left in place but believes is no longer true. If it could not write the
   answers file, it adds `Answers: <file>`, naming where it wrote them.
3. Stage the file (`git add <file>`) and run
   `python3 $S/prose.py compact <file> --verify [--answers <file>] [--paths-from <file|-> [-0]] [-- <path>...]`,
   with the same referrers as step 1, adding `--answers` when the
   compactor's reply named a file. It compares the staged file with the saved copy, and prints the
   size before and after, what it searched, the headings removed, the code
   spans, flags, constants and paths that are gone, and the answers to the
   flagged passages. It fails, exiting 1, when:
   - a removed heading is still referenced: its `#anchor` appears in the
     file itself or in a file searched, or its text appears in another file
     searched (the file's own text is not checked). The text of a heading of
     16 characters or more is a reference wherever it appears, compared with
     case, backticks, `*` and `_` ignored, and with line breaks and the
     comment or quote markers (`#`, `//`, `*`, `>`) starting a line read as
     one space, so a citation wrapped in a comment counts. A shorter
     heading's whole text, matched case-sensitively but with backticks and
     emphasis markers ignored, is a reference only on the same line or in the same sentence
     as a name for the doc: its path, its file name, or, for a doc in a
     skill, the skill's name as "<skill>'s" or "the <skill> skill"
     ("prose's", "the prose skill");
   - a flagged passage has no answer, or, without a `kept:` answer, is still
     in the file as many times as before (case, markup and line breaks
     ignored), so it was neither removed nor shortened;
   - a history marker is left, outside a passage answered `kept:`;
   - the file grew, or is empty.

   Have the compactor fix what it names, stage it, and run `--verify` again
   until it exits 0. On exit 2 (unstaged changes, a file to search it could
   not read, or a missing `--answers` file), fix that or narrow the paths,
   and run it again. A passing `--verify` stores the answers it checked for
   the staged file, and the later steps and the commit gate read only that
   copy: an edit to the answers file counts only once `--verify` runs again.
4. Have the compacted file read cold before any review, so the reviews check
   the cold read's fixes too. Write the compaction commit's message file and
   run `prose check`'s first call for it (*Two calls*), then its signing
   call (`--pass <token>`) without `--cold-read`. That call does not sign
   yet: the commit gate refuses until steps 5 to 8 are done, so it lists the
   compaction steps still missing, then prints the cold-read brief. It signs
   at step 10. Follow *The cold read* in full: a new subagent writes a
   report, you send its findings back to the compactor to fix, and you
   answer every finding and understood line in the cold read's dispositions
   file, asking a person about any you would keep. Stage the file and run `--verify` again. Keep the
   token, the report and that dispositions file for step 10. A compaction
   that only removed lines has nothing to read cold: its signing call prints
   no brief and refuses, listing the steps left; go on to step 5.

   The token lasts 2 hours from the first call. If it expires before step
   10, redo step 4 with a new first call. Step 4's cold read cannot be
   reused, because its signing call refused and signed nothing. If the new
   cold read's fixes change the file, run steps 5 to 8 again on it, even if
   you ran them before. After step 10 signs, a new token for a changed
   message signs without a new cold read.
5. Run `python3 $S/prose.py compact <file> --review`, with the file staged.
   It writes every change to a file, removed and rewritten text side by side,
   headed by the code spans, flags, constants, paths and headings the new
   file no longer has. It prints a brief naming that file between
   `=== compaction review brief ===` and `=== end compaction review brief ===`,
   saves the brief as step 1 does, and exits 4.
6. Give another new subagent, on the same model as the compactor and never a
   cheaper one, only the brief file's path. The brief is
   [compact-review.md](compact-review.md). The reviewer answers superseded,
   folded in (and where) or lost for each removal, and checks that every
   decision kept still carries its reason, that each rewritten or added
   sentence holds against the code and docs, and that each flagged passage
   kept has a justified reason. It ends with `Totals: <n> lost, <m> false`,
   which counts only `lost` and `false` lines, not `unjustified` ones. Save
   its reply to a file.
7. Send each `lost`, `false` and `unjustified` line back to the compactor,
   which restores the conclusion, corrects the claim, or removes or shortens
   the passage and updates its answer. Stage the file and run `--verify`
   again. When the first review found anything, run steps 5 and 6 once more
   with a fresh reviewer, and fix what it finds. Never run more than two
   reviews, except as step 9 says. Report whatever the second one still
   finds.
8. Record the last review as complete:
   `python3 $S/prose.py compact <file> --reviewed <reply file> --dispositions <dispositions file>`.
   It checks that the reply gives every change and every kept passage a
   verdict and that its `Totals:` line matches them. You write the
   dispositions file, separate from the compactor's answers file, with a
   line for each change found `lost` or `false` and each passage found
   `unjustified`: `Change <n>: fixed` or `Passage <n>: fixed`, which needs
   the staged file to differ from the one reviewed, or
   `Change <n>: kept: <reason>` or `Passage <n>: kept: <reason>`. With
   nothing fixed, the staged file must be the one reviewed. With a `fixed`
   line, `--reviewed` records the review for the file as now staged, so
   those fixes need no further review. A reply with no findings needs no
   dispositions file. It exits 0, recording the review for the commit gate,
   or 2 with what is missing.
9. Ask the person, through your host's picker, about each reviewer line
   whose text starts `ask:` and each `Would drop:` line from the compactor,
   and act on the answer. When you cannot ask, leave the conclusion in and
   put the line in your result for your caller. An answer that changes the
   file means staging it and running step 3 and steps 5 to 8 again, even
   after two reviews, because the commit gate needs a review of the file as
   staged.
10. Run step 4's signing call again and commit. Add `--cold-read <report>`
    and `--dispositions <file>`, giving the cold read's report and
    dispositions file from step 4, not step 8's dispositions file. With
    nothing read cold, add neither.

**The commit gate.** A passing `--verify` and a completed review (step 8)
are each recorded for the file's staged content. Once step 1 has run on a
file of any kind, `prose check` refuses to sign while that file is staged
with content other than the base's (HEAD's, or HEAD's parent's with
`--amend`) and lacks either record. The gate does not lapse with time. It
retires at the first `prose check` once the base commit holds exactly the
content this compaction's own `--verify` and `--reviewed` passed, with
both records still standing; that run deletes the saved copy, so
a later revert is not gated. A compaction committed without both records,
as a plain `git commit` can be, keeps gating until you abandon it. Nothing else is gated, so always compact with
`prose compact`, never by hand. Each refusal names the step to run on the
file as staged, then `prose compact --abandon <file>` as the way out:
- `<file> was compacted but not verified; run prose compact --verify <file>`
- `<file> was compacted but its review was not completed; run prose compact --review <file>, answer the reviewer's findings, then prose compact --reviewed <reply> <file>`

`--reviewed` still needs `--dispositions <file>` when the reply has findings
(step 8).

Never change the file after its last `--verify` and `--reviewed`. A symlink
holds no prose and is not gated. A file renamed and changed in the same
commit is not gated either, a known gap: its saved copy names the old path,
which the commit deletes. Outside git there is no commit to gate, so running `--verify`
is up to you; the brief names it as the required last step.

**Abandoning a compaction.** `python3 $S/prose.py compact --abandon <file>`
discards a compaction you will not finish, or one to restart from step 1.
It deletes the saved copy, the review file and the file's `--verify` and
review records, so the gate stops refusing the file's commits. It leaves the
file itself as it is: restore the committed copy yourself to discard the
edits too. It exits 0, or 2 when no compaction was started on the file.
Abandon before removing a work tree you compacted in: the saved copy is kept
with the repository's other git data, and a new work tree at the same path
would inherit it and its gate.

**Name every compaction** in your report and in the pull request body, with
the file's size before and after, as `--verify` prints it: for example,
"Compacted DECISIONS.md: 107,341 -> 61,020 bytes (-43%)".

**A person's request works on any file.** `prose compact <file>` runs on a
file whether or not it is due, read often or a doc at all. The detectors
always run in step 1, with no threshold, and `--verify` requires an answer to
every flagged passage, however few. The thresholds only decide when
`prose check` prints `compaction due`.

**Settings** go in `.gitattributes`, one line each. Patterns are git's own,
read through `git check-attr`: `*` stays within one directory, `**/` spans
directories, a pattern without a slash matches that name anywhere, and a
later line overrides an earlier one.

```text
docs/runbook.md prose-compact
CHANGELOG.md -prose-compact
docs/architecture.md prose-compact-growth=30 prose-compact-flagged=2000
openspec/specs/**/spec.md prose-compact-reads=10
.agents/skills/*/DECISIONS.md prose-compact-attribution=drop
```

- `prose-compact` declares a file read often, of any type; a file git treats
  as binary (`-diff`, `binary`, or a NUL byte) is skipped.
- `-prose-compact` exempts a file from the triggers.
- `prose-compact-growth=<percent>` replaces the growth share, 50 by default.
- `prose-compact-growth-bytes=<bytes>` replaces the bytes of growth also
  needed, 2,000 by default.
- `prose-compact-flagged=<bytes>` replaces the flagged bytes that make a doc
  due, 1,000 by default.
- `prose-compact-flagged-share=<percent>` replaces the share of the file
  those bytes must also be, 10 by default.
- `prose-compact-reads=<n>` replaces the reads that make a doc read often,
  20 by default.
- `prose-compact-attribution=drop` has the compactor drop "who decided"
  credits, such as "(Adam, 2026-10-24)". Without it, they are kept.

A `prose-compact` line affects only the triggers and the compactor's brief:
it does not put a file that is not a doc under prose's writing rules.

Never add or change a setting on your own initiative: each changes when the
trigger fires or what a compaction keeps, and one added among other edits
would do so unnoticed. Propose the line and let the person decide; when they
ask for a setting or confirm your line, make the edit yourself, and commit
it on its own so it stays visible. Propose:
- `-prose-compact` for a doc that comes up due but shouldn't be rewritten,
  such as a changelog or a generated or vendored file;
- `prose-compact` for a doc agents read often that *When it is due* misses;
- `prose-compact-attribution=drop` when the person doesn't want "who
  decided" credits kept;
- a higher `prose-compact-flagged`, `prose-compact-flagged-share`,
  `prose-compact-growth` or `prose-compact-growth-bytes` for a doc that
  keeps coming up due while its
  compactions cut little, or a higher `prose-compact-reads` when such a doc
  counts as read often only by its reads.

**Called by another skill.** A skill that keeps its own docs compact, such
as spec-check for a change's `proposal.md` and `design.md`, runs the same
steps, may add its own instructions to the compactor's prompt after the
instruction to read the brief file, and may then run its own checks on the
result. The reviewer and the cold reader still get nothing but the brief
file's path. `prose compact` prints its briefs and reports on stdout. Each call exits 2, with the reason
on stderr, when the file is missing or has unstaged changes, when a later
step has no saved copy, when a file to search cannot be read, or when a file
given with `--answers` is missing.

Step 1's saved copy stays in the repository's git directory, however long the
compaction takes, until the compaction retires on commit, `--abandon` deletes
it, or the next step 1 on the file replaces it, so any agent in the same work
tree can finish it. Steps run at once on one file are safe only where Python
has `fcntl` (macOS, Linux); on Windows, run one at a time.

### Which files refer to the doc

`--verify` searches for removed headings in the file itself and in the files
you name, whatever their type. Inside a git repository it also searches every
tracked file that git does not treat as binary; to have a misjudged text file
searched, give it the `diff` attribute. Outside a repository it searches only
what you name. Each name is a file: a directory is refused,
and the refusal shows how to list its files.

**Find the candidates** before step 1, when you cannot yet know which
headings will go. Search every place a referrer could live (sibling folders,
other repositories, notes), ignoring case, for the doc's file name, its
skill's name for a doc in a skill, every heading's `#anchor`, the title's
included, and one distinctive word from each heading whose text is 16
characters or more: `--verify` matches that text even wrapped or stripped of formatting,
and one word survives both. A shorter heading counts only beside the doc's
name or by its anchor, which those searches find. A file with none of these
terms cannot refer to the doc; a broad term only adds candidates, which
costs nothing. `rg` skips hidden, gitignored and binary files; add
`--hidden --no-ignore -a` unless you know no referrer is one.

```sh
rg -l -i -F -e 'DECISIONS.md' -e '#snapshot-lifetime-policy' -e 'lifetime' ~/notes ~/other-repo
```

Give step 1 and every `--verify` the same files: save the search's list once
to a file outside the repository, such as in `$TMPDIR`, so it is never staged
or searched as a tracked file, and pass `--paths-from <that file>`; or run
the identical search again from the same directory. Relative paths, the
doc's and the referrers', are read from the current directory, so search
from where you run prose.py. Inside a repository, spell and case the doc's
path as `git ls-files` lists it.

**A few known files: list them after `--`.** A file named this way is read
whatever its type or size.

```sh
python3 $S/prose.py compact DECISIONS.md --verify -- ../README.md ../notes/plan.md
```

**Many files, or files a search found: `--paths-from`.** It reads one path
per line from a file, or from stdin with `-`. Prefer a NUL-separated list,
as `rg -l0` and `find -print0` write it, with `-0`: in a list of one path
per line, a name holding a newline splits in two and its file is missed, and
a tool that quotes odd names, spaces among them, gives paths that match no
file. Below, the first two lines are step 1 and step 3, fed the same search;
the third reads every Markdown file in a folder.

```sh
rg -l0 -i -F -e 'DECISIONS.md' -e 'lifetime' ~/notes | python3 $S/prose.py compact DECISIONS.md --paths-from - -0
rg -l0 -i -F -e 'DECISIONS.md' -e 'lifetime' ~/notes | python3 $S/prose.py compact DECISIONS.md --verify --paths-from - -0
find ~/notes -name '*.md' -print0 | python3 $S/prose.py compact DECISIONS.md --verify --paths-from - -0
```

The two forms combine: `--paths-from list.txt -- ../README.md`. In a
pipeline the exit code is prose.py's, the last command's: 1 still means a
reference broke.

**Read the report's `Searched for references:` line** before trusting a
pass. Inside a repository it names the tracked files, and the given files and
where they came from. Outside one it says `only these were read`, or, with no
paths, `references from other files were not checked`: that pass proves only
the file's own links, so give the referrers and run it again.
`0 given files (the list was empty)` means the search found nothing, which
is a real answer only if the search was right.

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
and, for a compaction, with the files compacted (see *Compaction*).

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
