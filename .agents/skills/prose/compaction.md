# Compaction

Agents read some docs before every task, so each sentence there that no longer
serves them is paid for on every read. Those docs stay compact, and a doc that
describes the current state holds no history. `prose compact` applies rule 8
of [rules.md](rules.md), *What is, not how it got here*, to a whole file, not
only to the lines a change touched. `$S` is prose's scripts directory, as
[SKILL.md](SKILL.md)'s *Two calls* defines it.

**When it is due.** `prose check`'s first call prints
`compaction due for <file>: <why>` for each changed doc that agents read often
and that is due. A doc is read often when it is:
- a `CLAUDE.md`, `AGENTS.md` or `SKILL.md`;
- a file a `SKILL.md` or `AGENTS.md` links in a paragraph that asks for it to
  be read first, or read before some task. A link to be read only before
  changing the skill does not count, as with SKILL.md's link to DECISIONS.md:
  that file is read only when the skill changes;
- an open OpenSpec change's `proposal.md`, `design.md` or delta specs
  (`openspec/changes/<change>/specs/<capability>/spec.md`): spec-check's
  consistency read, run for every commit that changes `openspec/`, opens each of
  them in every open change;
- declared with `prose-compact` in `.gitattributes`;
- or a `DECISIONS.md`, `architecture*.md` or OpenSpec `spec.md` that none of
  the above covers, read at least 20 times since its last compaction,
  counting only the last 300 commits behind HEAD. Each such commit counts as
  one read of the docs it implies: a change in a skill's directory implies its `SKILL.md` and
  read-first files; a `Bug-hunter:`, `Prose:` or `Spec-check:` trailer
  implies that skill's `SKILL.md`, and `Spec-check:` also the main specs
  (`openspec/specs/**/spec.md`) and open OpenSpec changes. Commits imply a
  `DECISIONS.md` or architecture doc only as a read-first file, which the
  second bullet already covers, so only a main spec is read often this way.

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
2. Give a new subagent only the brief file's path, as SKILL.md's *The cold
   read* says.
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
     searched; the text's mentions in the file itself do not count. The text of a heading of
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
   run `prose check`'s first call for it (SKILL.md's *Two calls*), then its signing
   call (`--pass <token>`) without `--cold-read`. That call does not sign
   yet: the commit gate refuses until steps 5 to 8 are done, so it lists the
   compaction steps still missing, then prints the cold-read brief. It signs
   at step 10. Follow SKILL.md's *The cold read* in full: a new subagent writes a
   report, you send its findings back to the compactor to fix, and you
   answer every finding and understood line in the cold read's dispositions
   file, asking a person about any you would keep. Stage the file and run `--verify` again. Keep the
   token, the report and that dispositions file for step 10. A compaction
   that only removed lines has nothing to read cold: its signing call prints
   no brief and refuses, listing the steps left; go on to step 5.

   The token lasts 2 hours from the first call. If it expires before step
   10, redo step 4 with a new first call. Step 4's cold read cannot be
   reused: a cold read is reused only for a tree a signing call signed, and
   step 4's signing call refused. If the new
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
   sentence holds against the code and docs, answering `false` where one
   does not, and that each flagged passage
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
   staged. Step 4's cold read still counts: fixes are not read cold again.
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
as a plain `git commit` can be, keeps gating until you abandon it. Nothing else is gated: a compaction made by
hand escapes `--verify` and the review, so always compact with
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

A line setting any of these attributes affects only the triggers and the
compactor's brief:
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

## Which files refer to the doc

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
