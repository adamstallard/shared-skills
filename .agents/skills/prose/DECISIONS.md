# prose — decisions

`prose` makes agents rewrite what they write for human reviewers, and proves
they did. The rules are in [rules.md](rules.md); this file is why they, and the
mechanisms around them, are the way they are. Each entry gives the decision,
why it holds, and the alternatives an editor might propose again, with why
each was rejected. Entries give the rules' current numbers.

**Terms used throughout.**
- **The pass:** the agent rewrites its own text by rules.md before signing it.
- **First call and signing call:** each commit or post takes two runs of
  `prose.py`. The first (`check` or `sign` without `--pass`) prints the rules
  and a **pass token**; the signing call passes that token back and gets the
  trailer or footer.
- **Cold read:** before signing, a fresh agent reads the changed text and
  reports where it stopped; the author answers each finding.
- **The gate:** a Claude Code hook that blocks a session's first file write
  until a first call has run.
- **Igor** (adamstallard/igor) is an agent pipeline that runs prose in its
  workers; most examples come from it.

---

## Why the skill exists

Agent-written code is usually easy to read; the text around it is not: long,
ambiguous and switching topics, because agents rank completeness and
defensibility above being understood.

**Its value is enforcement.** `sharper-comments`, `CLAUDE.md` rules and
memories all failed the same way: agents treat advisory text as optional. A
rule no script checks is the thing that already failed.

**Scope: anything a human reviews.** READMEs and other docs, code comments,
architecture docs, specs, commit messages, pull request descriptions, and
posts to GitHub, Linear and Discord. Short kinds are not exempt: agents bloat
commit subjects and ticket comments too.

**Rejected.**
- **Readability scores** (Flesch and similar), even as a flag. They count
  syllables and sentence length, not whether a reviewer finds what they need,
  and text rewritten to raise them is no easier to understand.
- **Length budgets per kind**, beyond the 72-character commit subject. A number
  reads as a target: short text gets padded, long text loses a needed
  sentence. If bloat still gets through, measure word counts before and after
  the pass first, and set limits from that.

---

## The rules

**Rules 1 to 3 cut claims; nothing checks them.** Rule 1 keeps a sentence
only if the reader needs it, rule 2 puts the conclusion first, and rule 3
removes rereads. None asks the agent to verify its claims. Every claim is
something a reviewer can attack, and an agent answers each attack
with a hedge, which is another claim; a few rounds produce the unreadable
block. Re-verifying claims inside this skill would rebuild that loop. One
explicit scope line ("Checked: X. Not checked: Y.") narrows rather than hedges:
vague hedges lower trust while a stated limit raises it (van der Bles 2020,
Jensen 2008).

**Rule 3 names a pointer whose one referent is far back** as a cause of a
reread: "it" or "these commands" a paragraph after the one
thing it points at. Before, the rule named only a pointer with two possible
referents.

**Rule 4, a hypothetical reads as one.** A case that happens only by accident,
rarely, or by someone else's choice is marked three ways together: lead with
what is always true, say the case is unusual and whose doing it would be, and
put its consequences in "would" or "might". This comment, which passed three
cold reads, was read as "spec-trace saves a log of its output":

```
# A log of this output saved in the repository is searched by the next run.
```

It meant: if a person saved the output in the repository, the next run would
search it. The condition hid in the subject, so the writer saw no condition to
label, and a reader sure of the wrong meaning never stops. "If" alone is not
enough: with the case still the topic and its consequences in the plain
present, the reader takes away a normal workflow with a condition attached.
Rule 4 comes right after rule 3, among the rules printed in full (*New
failures fold into an existing rule*, below), because a misreading costs more
than a reread.

**Rule 5, say when and whether, sits beside rule 4.** Both are about a claim's
status (past, present or future; actual or conditional), and both prevent a
reader who leaves misinformed without stopping, the goal rules.md names
*Read as meant*. Further apart, someone applying one would read past the
other.

**Rule 6, each sentence follows from the last.** Abrupt switches to a subject
the reader wasn't expecting kept slowing reading after the pass existed. It
also says a "so", "because" or "therefore" points at what the reader just read: a "so" whose cause is two
sentences back makes the reader search.

**Rule 7, a claim is stated once, with its reason.** In Igor's PR #156 one
catchphrase appeared nine times across six documents, restating a rule in a
form that sounded like a reason, so the reasons were never written down. The
pass greps the repository for a phrase a changed passage repeats and fixes it
at its source. rules.md's *Scope* limits the pass to text the change wrote, and names this
fix as one of its two exceptions; the other is text someone asked to have
revised. A
term defined once and used as a name is vocabulary, not a catchphrase.

**Rule 8, what is, not how it got here,** covers docs as well as comments. A
passage that labelled its past ("the argument once made … does not apply")
passed the pass: it satisfied rule 5, which only asks that the past be
labelled. Rule 8 is what says whether the past belongs in the text at all.

**Rule 9, spend words where they save reading time,** has *one claim per
sentence* as its point. Its sentence "a longer sentence that reads once beats a
shorter one read twice" now says what may make a sentence longer: words that serve
its one claim, not a second claim.

**New failures fold into an existing rule when they fit its question;** a new
rule is inserted only when none fits, as rule 4 was. Renumbering breaks
citations by number, and rules past `RULES_IN_FULL` (9) reach the agent as
headings without their reasons or examples.

**Rejected.**
- **A word or clause limit per sentence.** A count of words does not see
  claims, and reads as a target.
- **Merging rule 8 (*What is*) into rule 5 (*Say when*).** They answer
  different questions: whether the past belongs in the text, and how to mark
  it when it does. Kept apart, rule 5 can say outright that labelling the past does not
  justify keeping it: that is rule 8's call.
- **Merging rule 6 into rule 11 (*One topic per block*).** Rule 11 is about
  how text is divided; rule 6 is about whether one sentence leads to the next.
- **A mechanical lint for passives** such as "is searched" with no "by". It
  would flag far more harmless sentences than harmful ones, and prose's checks
  are worth reading because they don't cry wolf.

---

## The rules live only in rules.md

`rules.md` holds the full rules text: scope, the pass with its reader table,
the rules with their examples, and how agents cheat. SKILL.md keeps no copy.
Every first call prints rules.md by its headings: everything before the rules, rules
1 to `RULES_IN_FULL` in full, the rest as one-line headings, and the cheat list. `prose.py` refuses to run when a section is missing or out of order, or the rules are
misnumbered.

**Why.** Agents skip documents but read a command's output at the moment they
act on it. A second copy drifts, and a summary is read in place of the rule.

**Rejected: rules behind a pointer** (a `reference.md`). A rule behind a
pointer is read after the mistake.

**Known gaps.** A fence closes at the next line starting with the same three
characters, a `####` heading inside a rule is refused, a blank `# ` title
passes, and a title placed after the opening principle (the bold lines before
*Scope*) passes. rules.md changes only through
reviewed pull requests, so stricter parsing would guard almost nothing.

---

## Each listed item is judged as its own reader

`prose check`'s `--goals` are the commit message's, for the reviewer. Every
changed doc and spec gets goals of its own, which the agent names per file
with `--goals-for <pattern> '<goals>'` or a `--goals-file` of
`pattern: goal; goal` lines. Without them the first call refuses, naming each
file and its kind's default from rules.md's reader table. A deleted doc needs
none; a code comment without goals gets its kind's default, labelled as one.
The pass token records the per-file goals. The signing call refuses goals
that differ from them, and a doc staged since the first call that they don't
cover.

**Why.** A commit to Igor's architecture doc passed with a valid trailer while
telling the doc's reader that an argument they never saw "does not apply".
The one goals string was the reviewer's, and a reviewer does want to know an
old argument no longer applies; the doc's reader does not. Only the
agent writing the change knows who a particular doc's reader is, and printing
each file's goals above it keeps that reader in front of the agent.

**Which goals win: the most specific match.** An exact path beats any pattern;
between patterns, more literal characters win. Equally specific matches with
different goals are refused, since choosing by order would hide a
contradiction. Patterns follow gitignore because agents know it; negation is
refused. A pattern matching no listed file is a warning, usually a typo.

**Rejected.**
- **One fixed reader per kind.** It cannot say an API reference and a runbook
  are read for different reasons.
- **One `check` per document.** A commit has one trailer and one message.
- **Goals per hunk or section.** A file is read by one reader.
- **Listing each changed passage's section heading.** Three bug-hunter rounds
  each found another Markdown construct it misread, and a wrong hint misleads
  silently. Reconsider only with a real Markdown parser, if agents ignore the
  instruction to reread each passage in its section.

**Where this stops applying.** If agents paste the reviewer's goals into
`--goals-for`, the next step is a separate first call per doc.

---

## `start` and `sign` take their goals from a file too

`start` and `sign` take `--goals-file <file>` in place of `--goals`: one or
more goals per line, separated by `;`, blank and `#` lines skipped. Both given
is refused, since joining them would choose an order nobody gave. The token is
bound to the goals, not to where they came from.

**Why.** Goals can hold text from the issue being worked on, which may be
private, and on Linux any
user can read another process's arguments in `/proc/<pid>/cmdline`. A file
readable only by its owner keeps them private, and needs no quoting.

**Rejected: goals on stdin.** `sign`'s signing call reads the post there.

---

## `check` takes the message's goals from a file too

`check` takes `--message-goals-file <file>`, written like `start`'s, in place
of `--goals`, for the same privacy reason. A second option is needed because
`check`'s `--goals-file` holds per-file `pattern: goal` lines, and a reserved
pattern naming the message could clash with a real file.

**Rejected: goals in the message file.** They would become part of the message.

---

## A revision request is drafted fresh, section by section

When someone asks for existing text to be improved with prose, the agent writes a draft of every section before rereading it, carries over every fact,
measurement, decision and warning the draft lacks, and keeps the original only
where the draft, written without it, says essentially the same thing. A tie
goes to the draft. A section an open branch also changes is held, with the
branch named. The agent's report to whoever asked counts sections redrafted, merged, kept and held, and
shows each kept section's draft beside the original.

**Why.** Asked to improve the comments in a 2,163-line file, an agent grepped
for patterns, skimmed comments without their code, changed 5 and called the
file good; the ones it kept included blocks that fail rules 3 and 7. A first
fix, "keep the original where it serves the reader better", still let poor
blocks through:
- **Editing anchors on the existing framing.** A sentence that sounds reasoned
  survives "is this wrong?", a much easier test than "would a fresh draft be
  better?".
- **A draft held in the head can't be checked,** so the procedure writes it out.
- **The original won ties,** read with the code's context already in mind.
  Churn (diff size, merge conflicts) also passed as a judgement about the
  reader. A held section now gives churn from an open branch its own name.
- **`prose check` lists only what the change touches,** so the report is the
  only record that the rest was read.

**Rejected.**
- **Always replacing the original.** Where the draft converges it only grows
  the diff, and a draft is sometimes worse.
- **A blind comparison by a second agent.** Removes the bias, but doubles the
  cost of every revision.
- **Keeping the original where the agent can name a rule the draft breaks.**
  Still a judgement the original wins easily.
- **A `--revise <path>` listing every section of a file** (issue #16). A
  listing proves printing, not reading. Build it if agents follow the
  procedure and still report files done with sections unread.

---

## Compaction keeps docs read before work compact

Decided by Adam, 2026-10-24. `prose check`'s first call prints `compaction
due for <file>: <why>` for a changed current-state doc that is over its size
budget or holds history markers. The agent then compacts it, in a commit of
its own in the same pull request: `prose compact <file>` prints a brief for a
fresh compactor ([compact.md](compact.md)), `--verify` checks the result
mechanically, and `--review` prints a brief for a fresh reviewer
([compact-review.md](compact-review.md)).

**Why.** Over two long sessions, about 69% of subagent spend was agents
rereading large documents; igor's `docs/architecture.md` was read 249 times.
Prose's pass rewrites only the lines a change touches, so rule 8 (*What is,
not how it got here*) never reaches the rest, and history piles up there.
This DECISIONS.md grew from 51 KB to 107 KB in three weeks. Adam's rules:
docs read before work stay compact, and current-state docs don't accumulate
history.

**It lives in prose** because it is rule 8 applied to a whole file, and
prose's commit check already lists every changed doc. Spec-check calls the
same commands for OpenSpec proposals and designs.

**Just do it; ask on loss.** The compaction is reviewed as a diff of its own,
so asking first only adds a wait. Dropping a conclusion is a decision, not an
edit: the compactor leaves one it believes dead in place and names it, and a
person decides. The reviewer's verdicts decide what is restored; the person
is asked only where restoring is itself a judgement call.

**The compactor drafts each section fresh.** On five real docs, a brief that
edited in place cut 1 to 12%. Drafting fresh cut 6 to 23%, with 1 live
conclusion lost after review. A naive "compact this" prompt cut 4 to 54% but
lost 41, with no reviewer to catch them.

**A fresh reviewer judges every removal** (Adam, 2026-10-24), as bug-hunter's
refuter judges findings, because a compactor checking its own work misses
losses: the compactor of pull request #31, which compacted this file,
missed eight, and a fresh reviewer caught them. `--review` writes every
change to a file, old and new text side by side, headed by the code
spans, flags, constants, paths and headings that are gone. That list is a
script's work and costs no tokens. The reviewer runs on the same model, never
a cheaper one. For each removal it answers superseded, folded in or lost; for
each rewritten claim, holds or false, checked against the code; it skips
unchanged text. It also checks that every decision the new text keeps still
carries its reason, since a decision without its reason invites the next
editor to undo it. The compactor restores and corrects. A second review runs only
if the first found something, and never a third.

**Measured** with skill-creator's benchmark harness on five docs, each seeded
with three conclusions hidden in history or repetition: this file before and
after #31, bug-hunter's DECISIONS.md, worktrees' DECISIONS.md and igor's
`docs/architecture.md`. Every seeded conclusion survived in every run. A
judge agent counted the live conclusions each result no longer states, and
the table gives that count; the reviewer counts more, since it also counts
lost reasons and claims made false.

| Brief | Size cut | Lost after review (judge's count) |
|---|---|---|
| Drafting fresh (shipped) | 6 to 23% | 1, after one review |
| Cutting boldly | 17 to 36% | 12, after two |
| Cutting boldly, reviewer checks reasons | 6 to 42% | 6, after two |

**Rejected: cutting boldly and relying on the reviewer** (Adam, 2026-10-24).
The brief once aimed for the 61% a hand compaction of this file reached. Even
with the reviewer told to check that every kept decision keeps its reason,
6 conclusions were lost after two reviews, mostly reasons dropped from
igor's architecture doc. Adam's bar was at most 1 to 3, which the gentler
brief meets with 1. A bold compaction also cost 365k to 780k tokens and 6 to
19 minutes. The reviewer keeps the reasons check.

**The reviewer, measured on #31's compaction,** caught 7 of the 11 points the
human review restored or corrected. It missed one rejected alternative, one
reason and two wrong statements, and found 23 more; 14 of those were real.

**The triggers are a script.** They read the index, git history and blob
sizes, in milliseconds per doc.
- **Size: 40,000 bytes** (about 10,000 tokens), or a 50% growth since the
  last compaction. Docs under it cut 6 to 13%, saving under 1,000 tokens per
  read, so their reviewed compactions, at 265k to 350k tokens, take hundreds
  of reads to repay. igor's architecture doc, 125 KB, cut 15 KB: about 3,800
  tokens on each of its 249 reads. The last compaction is the newest commit
  behind HEAD, merged branches included, that shrank the file by 10% or
  more, read from blob sizes, so it needs no marker.
- **Known gap: a squash merge.** It leaves one commit with the pull
  request's net change. If that shrank the file by less than a tenth, the
  compaction inside it is not found, and the doc is flagged again on its
  next change.
- **History markers,** at any size: a dated revision note or span, a
  "History:" or "Update:" label, "previously" (not "a previously issued"),
  "originally", "formerly", "was changed to". Over 26 docs here and in igor they fire on 8 lines of the
  pre-#31 file, on igor's architecture doc, bug-hunter's DECISIONS.md and an
  igor design, and on none of the nine SKILL.md files, rules.md, the post-#31 file
  or seven other DECISIONS.md files. They miss history phrased as "an
  earlier version", which the reviewer then catches.
- **The marker scan skips fenced code and quoted text** (Adam, 2026-10-24),
  by the simple rule: a line starting with three backticks or tildes opens
  or closes a block, and text in inline code, double quotes or guillemets
  is skipped. Prose's own docs quote Before and After specimens, which
  would otherwise fire the trigger constantly. A false trigger costs a full
  reviewed compaction, 300k to 500k tokens; a miss only waits for the next
  marker or the size trigger, which counts every byte, and a block the
  simple rule misjudges costs at most one extra "compaction due" line. Like
  `--verify`, the trigger errs the cheap way: for a trigger that means
  staying quiet, where for `--verify` it means blocking. `--verify` itself
  detects no fences.
- **Defaults:** `DECISIONS.md`, `SKILL.md`, `AGENTS.md`, `CLAUDE.md`,
  `architecture*.md`, and OpenSpec specs, proposals and designs outside the
  archive.
- **A declaration works on any file** (Adam, 2026-10-24). `prose check`
  reads the `prose-compact` declaration, the `-prose-compact` exemption and
  the `prose-compact-budget` and `prose-compact-growth` settings for
  every staged path, and a declared file of any type joins both triggers:
  the size check counts bytes and the marker scan reads text, so neither
  needs Markdown. A file git treats as binary, by `-diff` (which `binary`
  sets) or a NUL byte, is skipped. Declarations reach the triggers only;
  prose's writing rules still apply only to docs.
- **Settings live in `.gitattributes`:** committed, matched by path, read by
  one `git check-attr` call. The one line `* prose-compact-budget=60000`
  sets the budget for every file.

**`--verify` blocks on any reference to what was removed** (Adam,
2026-10-24). A heading or anchor the compaction removed counts as still
referenced when its heading text appears anywhere in another searched
file, in any context, or its `#slug` appears anywhere in a searched file or
in the file itself. Then `--verify` fails and the compactor keeps the
heading. Only removed headings and anchors are looked for, so a reference
broken before the compaction never counts. It also fails on a history
marker left, or a file that grew.

**Heading text is compared normalised** (Adam, 2026-10-24), on both sides:
case folded (`casefold`, so "STRASSE" matches "Straße"); backticks, `*`
and `_` dropped; and every run of whitespace made one space. So is each
line break, a bare CR among them, together with any comment or quote
markers (`#`, `//`, `*`, `>`) that start the next line, so a citation
wrapped inside a comment reads as one line. It is plain string clean-up, no parsing. The
anchor is searched as written. Comparing exact text missed 11 of 15 real
references in the benchmark below: citations drop a heading's backticks,
lowercase its first word, and wrap.

Every choice errs toward blocking (Adam, 2026-10-24); the logic that tried
to be precise is gone.
- **Over-blocking is accepted.** Each case below only keeps a heading:
  - an incidental mention of the heading's text, or of its `#anchor`;
  - a heading-shaped line (`#` to `######` and a space) inside a code block,
    which counts as a heading, since `--verify` detects no fences;
  - a heading renamed only in case or formatting, or removed while a kept
    heading gives the same anchor: the removed heading's anchor is searched
    anyway;
  - another doc with the same heading text.
- **Heading text under 16 characters, once normalised, is not searched;**
  its anchor always is. "Why", "Open" or "Rejected" appear in ordinary prose
  everywhere, so such a heading could never be removed.
- **Paths are taken exactly as `git ls-files` lists them.** Inside a
  repository, a file argument that is not a tracked path, mistyped case
  included, is refused as "not a tracked file". CRLF line ends are read as
  LF.
- **A git error is an error.** Anything `git grep` writes to stderr fails
  `--verify` (exit 2), whatever its exit code: it exits 0 when anything
  matched, and the staged copy of the file always matches, so an unreadable
  file would otherwise pass in silence.
- **Outside a repository means `git rev-parse` failed,** judged by its exit
  code alone. Its messages differ by git version and by cause, such as a
  filesystem boundary, so they are not read.
- **git grep reads the tracked files,** with a pattern every line matches,
  so the work tree and the index, binary files and files outside a sparse
  checkout are all read, and submodules are not; the matching is done in
  Python on the normalised text. Symlinks, which git grep skips, are not counted
  as searched. `advice.sparseIndexExpanded` is turned off, since its hint
  on stderr would otherwise fail every run in a sparse-index clone. Reading
  every binary has a cost: a repository
  with 100 MB of tracked binaries took 7 seconds and 1.1 GB. igor, 317
  files, takes under a second.
- **Known gap:** a heading underlined with `===` or `---` is not seen. No doc
  in this repository or igor uses one. An ATX heading indented up to three
  spaces, or with a tab after its hashes, is seen.
- **Known gap: a heading moved into a code block counts as kept.** With no
  fence detection, the line still looks like a heading, so its anchor is not
  searched, though GitHub no longer gives it. A compactor rarely does this,
  and the reviewer sees the change. Masking code on the new side only would
  close it; that is for Adam.
- **Known gap: an HTML anchor** such as `<a id="x">` is not a heading, so
  removing it is not checked.
- **Known gap: an assume-unchanged referrer.** git grep reads such a file's
  index copy in its work-tree pass, so an unstaged reference in it is not
  seen. The doc itself marked assume-unchanged or skip-worktree is refused,
  since its changes could not be seen.

**The caller names the files that might refer to the doc** (Adam,
2026-10-24), each one explicitly: after `--`, or listed by `--paths-from
<file|->`, one path per line or NUL-separated with `-0`, so names with
spaces or newlines survive `rg -l0` and `find -print0`. A file is read
whatever its type or size. A directory is refused, with how to list its
files by search. Walking folders needed filters for type, size, hidden
directories, symlinked folders and a file cap, each with its own bugs, one
of which left a large file unread when its folder was named first. A search
lists exactly the files meant. Inside a repository the given files add to the tracked ones. Outside one,
exactly the given files are read, and with none only the file's own links
are checked. The report always says what was searched, so a run that
checked too little shows it. Every file is read even when nothing was
removed, so the report stays true and an unreadable file is still an error.

**A compaction is signed only after it is verified and reviewed** (Adam,
2026-10-24). Inside a repository the agent stages the compaction first, and
`--verify` and `--review` read the staged blob, refusing a file with
unstaged changes, so what is checked is what is committed.
- **Two records,** in prose's pass directory under `.git/prose/passes/`:
  `compacted/` for a passing `--verify`, and `reviewed/` for a completed
  review. Each is named by the staged blob's id exactly as `git ls-files -s
  -z` lists it, and holds `before`, the blob id `prose compact <file>`
  snapshotted when the compaction started.
  A failed `--verify` deletes its record.
- **Every compaction is gated** (Adam, 2026-10-24), whatever kind of file.
  Once `prose compact <file>` has snapshotted a file in this work tree,
  `prose check` refuses to sign while that file is staged with a blob other
  than the base's, the base being HEAD's blob (HEAD's parent's with
  `--amend`), and lacks either record for its staged id with `before` equal
  to the base's id, as `git ls-tree` lists it. Each refusal names the
  missing step: "<file> was compacted but not verified; run `prose compact
  --verify <file>`", or "<file> was compacted but its review was not
  completed; ...". Its first call lists the same lines. No new trailer, hook
  or `Prose:` format.
- **Only a compaction started with `prose compact` is gated** (Adam,
  2026-10-25). A safety net that also gated any current-state file shrunk
  by a tenth was dropped: it refused merges, cherry-picks and reverts that
  bring in a compaction made elsewhere, and legitimate deletions, with no
  way to satisfy it, since `prose compact <file>` refuses unless the staged
  file equals HEAD's. A
  compaction by hand takes an agent deliberately skipping the tool.
- **`prose compact <file>` starts from the committed file.** It refuses a file whose
  staged blob differs from HEAD's, so the snapshot is always of the base.
  Running it again on an already-compacted copy is refused, and a snapshot
  from a compaction already committed no longer matches the base, so it
  gates nothing.
- **A snapshot belongs to its work tree.** Linked work trees share the git
  directory, so each snapshot names its root, and only this work tree's
  snapshots gate its commits.
- **Ids are read from listings, never from names.** The gate reads `git
  ls-files -s -z` and `git ls-tree -r -z`, so a path such as `0:x.md`, or
  one holding a newline or ending in a CR, cannot name another file.
- **A completed review** is one `--reviewed <reply> --dispositions <file>`
  accepts: the reviewer's reply gives each change of the last `--review` a
  verdict and a `Totals:` line that matches them, and each change with a
  `lost` or `false` finding is answered `fixed`, which needs a staged blob
  other than the one reviewed, or `kept: <reason>`. With nothing fixed, the
  staged blob must be the one reviewed, so a review taken before the
  compaction, or of an earlier draft, does not count. That a second review
  ran when the first found something stays SKILL.md's rule; the record
  cannot show it.
- **A symlink is skipped by its mode,** 120000: it holds no prose, and
  hashing its target would never match the link's blob.
- **Known gap, accepted** (Adam, 2026-10-24): a file renamed and changed in
  the same commit is not gated, since its new path has no base.
- **Snapshots and records live 7 days.** A later step refuses a snapshot
  older than that, as SKILL.md says, and writing a record deletes records
  older than that. Records sit in subdirectories of prose's pass directory:
  prose deletes the files there older than two hours, the life of a pass
  token, but leaves subdirectories alone.
- **Partial clones work offline.** Trees are listed without sizes, and a
  size is read by blob id only where a check needs it, so a blobless or
  sparse clone is neither refused nor made to fetch on every check.
- **Python 3.9 or later** (Adam, 2026-10-24). Paths after `--` are split off
  before argparse, which before 3.12 drops them once an option follows the
  file.
- **Outside git** `--verify` reads the working file and there is no gate;
  the brief names `--verify` as the required last step.

**Measured `--verify`** on the same benchmark's compactions, each in a clone
of its real repository at the doc's commit. Judge agents
labelled each of the 47 removed heading-shaped lines over the three briefs
as genuinely referenced or not: 15 are, all in this file before or after
#31; the other three docs lost no referenced heading.

| `--verify` | Caught | Missed | False blocks |
|---|---|---|---|
| Normalised text (shipped) | 15 of 15 | 0 | 6 |
| Exact text | 4 of 15 | 11 | 3 |
| f37015c, precise matching | 10 of 15 | 5 | 6 |

- **The false blocks** each keep one heading:
  - three lines of a code block that rules.md quotes;
  - `#rejected`, a prefix of a live link to `#rejected-a-github-action`;
  - "A claim is stated once, with its reason", which rules.md states as a rule;
  - "Every commit gets the pass", used in passing in a test.
- **Five of f37015c's six false blocks** came from one compaction whose
  fence it misread: it reported 38 headings gone where all 48 were kept, and
  five of those 38 are cited elsewhere.

**Rejected: matching links and citations precisely.** A Markdown parser
first, then grep with rules for paths, percent-encoding, comment prefixes,
emphasis, wrapped lines, shared headings, fences, path case and anchor
collisions. Bug-hunter found 14 bugs in the parser over three passes and
over 25 more in the matching rules over three runs, each fix exposing the
next case, and was still finding them at its cap. The
review of #31's compaction checked links the same way, by grep.

**Rejected.**
- **Firing at every commit over budget.** A doc that stays long after a
  compaction would be flagged forever. It gets its own budget instead, which
  `--verify` suggests.
- **A marker in the compaction commit.** An agent has to remember it, and a
  squash merge can drop it.
- **"No longer", "used to", "an earlier version" as markers.** Here they fire
  mostly on present state ("if the tree no longer matches") or on rejected
  alternatives stated in passing.
- **A config file of its own.** One more file, with its own pattern matching.
- **A cheaper model for the reviewer.** It is the check on a strong model's
  judgement.

---

## The rules are on screen before a signature

A trailer or footer takes two calls. The first, `check` or `sign` without
`--pass`, needs the reader's goals, prints them, the rules and a pass token,
signs nothing and exits 4. The signing call, with `--pass <token>`, signs.

**Why.** The rules help most while a draft exists and is not final. Goals on
the command make naming the reader part of the command, so it cannot be
skipped silently; without goals there is nothing to cut against.

**What it proves:** a first call printed the rules before the signature. Not
that the agent read them, or that the pass was good. Forging a token file or a
session mark is out of scope, as forging a footer is.

### The pass token

- **One token signs one text,** once: a commit and a PR description have different readers, and a reusable token
  would let later texts skip naming theirs. A commit's docs are signed with
  its token, each under its own per-file goals. It is bound to its goals and its command (`check`
  signs a commit, `sign` a post). A refused signing call keeps it.
- **Bound to the goals, not the text,** since the pass revises the text.
- **Expires after 2 hours;** each first call deletes older tokens.
- **Exit 4** for a first call, distinct from 2 (refused) and 0, so
  `sign … > signed.md && gh …` stops there.
- **Lives in `prose/passes/` under the repository's git directory,** never committed. Igor's workers each run in a throwaway clone with a shared HOME,
  so per-clone tokens mean no contention and no worker redeeming another's.
  Outside a repository, `${XDG_STATE_HOME:-$HOME/.local/state}/prose/passes/`.
  Written under a temporary name and renamed, so no call reads half of one.

### `prose start`

The gate (next section) blocks the first file write, so the call that opens
it must work
before any draft exists. `start` takes only goals, prints them and the rules,
marks the session, and issues no token: one would sign a text whose own
reader was never named.

**Rejected.**
- **Printing the rules on the signing call.** They would arrive after the
  footer, when nothing is left to rewrite.
- **Injecting the rules from a hook** (`additionalContext`). Shown, not acted
  on; what fixed skipping in bug-hunter was making the agent run a script.
- **A flag that prints only the trailer.** It is what an agent reaches for to
  skip the rules.

---

## The gate blocks a session's first file write

In Claude Code, `require-first-call.sh` blocks a session's first Write, Edit,
MultiEdit or NotebookEdit to any file, and its first `gh` or GitHub MCP post,
until `prose start` or a first call has run in the session. It checks the
session mark first, so in a marked session the gate does nothing else. It does not look
for comments or tell docs from code.

**Why not detect prose.** A gate that looked for comments in edits did not
converge: two bug-hunter runs hit their iteration cap, each round finding 4 or
5 real bugs (unparseable fragments, regex literals, directives, docstrings,
notebook cells). Nearly every session writes prose anyway, a commit message at
least, and the token already guarantees the rules before any signature. The
cost is one `prose start` in a session that writes no prose.

**The session mark** is an empty file named by the session id in
`${XDG_STATE_HOME:-$HOME/.local/state}/prose/sessions/`, deleted after 30
days, taken from `--session` or `CLAUDE_CODE_SESSION_ID`. It lives in the
state home because a session spans repositories.

**It fails open.** A missing `python3`, a crash or an unreadable state
directory lets the call through: a broken gate would block every write.

**What it relies on in Claude Code:** PreToolUse exit 2 blocks and feeds stderr
to the agent; the payload's `session_id` (a subagent carries its parent's),
`tool_name` and `tool_input`; `CLAUDE_CODE_SESSION_ID` equals that
`session_id`; matchers are unanchored regexes, so this one is anchored.

**Known gaps.** Files written through Bash (`sed -i`, `>`) skip the gate.
Cursor has no gate.

---

## A cold read before signing

Before a changed comment, doc passage or post is signed, an agent that never
saw the conversation reads it and reports every place it stopped, reread or
guessed. [cold-read.md](cold-read.md) is the brief's only copy.

**Why.** The author checks the text with the conversation in mind, so every gap
is already filled for them. Igor's `gitEnv` comment had seven failures, and the rules
already named four of them. A fresh subagent given only the brief found four
of the seven, and three more gaps that no review had named.

**The signing call enforces it,** because it holds the final text. Without
`--cold-read`, it signs nothing, keeps the token, exits 5 (distinct from 4 and
2, so a script can tell "do this step" from an error), and prints the brief:
cold-read.md, the `cold-read <token>` line the report starts with, and each
text with its reader's goals, a comment or doc by file and lines, a post
quoted. With a report and the author's answer to each finding (the dispositions,
next section), it checks both, then signs.

**What it reads, and what it skips.**
- **Every comment block the change touches, whole,** since a reader meets it
  whole; that includes a comment on a changed line whose own text did not
  change. Every doc or spec passage the change adds to. Every post.
- **No length threshold.** The first version read only texts of three or more
  lines, and every bug found in it was in that counting (comment syntax, binary-diffed docs, BOMs, UTF-16), and a
  character count has the same hard cases.
- **Not the commit message:** its body needs no cold read. A commit changing no comment or doc signs without a report.
- **Nothing with no new prose to read:** a doc git diffs as binary, a deleted
  doc, an edit that only removes lines, a symlink or submodule at a doc path,
  a code file that did not parse or could not be read.
- **One cold read per token.** Fixes are not read cold again, which would
  repeat until a reader found nothing; `fixed` is checked by the item having
  changed instead.

**What it proves:** a report for that token existed before the signature, and
each finding was answered. Not that a fresh agent wrote it; an author writing
its own report is forgery, which the cheat list names.

**Rejected.**
- **Procedure only, in SKILL.md.** A cold read is skipped exactly when the
  author thinks the text is clear, which is when the author is wrong.
- **The script running the reader through a model API.** Needs a key, a
  network and a provider in a standard-library script.
- **A brief from the first call.** The text is a draft then, and `sign`'s first
  call has no text at all.
- **A separate `brief` command.** One more thing to remember.
- **Giving the reader the rules.** It would check against them instead of
  reading; the pass already does that.
- **Asking the reader for rewrites.** A rewrite carries its guesses into the
  text; a stop with what was guessed tells the author what to fix.
- **Binding the report to the text's hash.** Every fix would need a new read.

**Where this stops applying.** If cold readers report nothing on text human
reviewers still find hard, change the brief. If authors dismiss what readers
report, the next step is a second cold read of the fixed text.

---

## Every cold-read finding is answered before signing

The signing call takes `--dispositions <file>` beside the report. Its first
line is `dispositions <token>`, so answers for one cold read cannot pass with
another, and it answers every finding once: `<n>. fixed`, or
`<n>. kept (asked): <reason>`. A missing, duplicate or unknown number is
refused.

**Why.** Proving a report existed let an author pass it and change nothing,
with a signature identical to one whose author fixed every place.

**The report has a fixed form,** which cold-read.md asks for and the script
parses: numbered findings `Finding <n>, item <i>, <stopped|reread|guessed>:
«<words>» <what was missing>`, `Item <i>: read straight through.`, and one
understood line per item. A line in any other form is refused, so the author
asks the reader again rather than prose guessing what a free-form report
meant.

**`fixed` is checked by its item changing.** The brief's call records each
item's file, line spans and the staged text. At signing, the script diffs the
recorded text against the current one: a line of the item changed or removed,
or a line added inside it or directly beside it, counts. An edit elsewhere that
only moves its lines does not. The quote is for the person deciding, and is
not checked.

**Why not the quote.** An earlier version refused `fixed` while the quoted
words remained. That check was its most intricate code and held one of the two
bugs bug-hunter found in it; it refused honest misquotes, and proved only that
those exact words were edited.

**A file the brief did not name is refused** when it now has a changed comment
or doc passage: no reader saw it, and the trailer would say one had.

**A person decides every kept finding.** A finding kept without `(asked)` is
refused, with the quote, the reader's note, the reason and the file paths. An
agent with a person and an interactive picker (in Claude Code, the
`AskUserQuestion` tool) asks one question per finding, "Keep as is"
or "Fix it". An agent that cannot ask leaves the change staged and hands that
refusal, the files and the token to whoever holds its result. `(asked)` proves
nothing the script can see; it is a claim made on purpose, and writing it
falsely is on the cheat list.

**The counts go in the `Prose:` value,** such as `; cold read: 5 findings, 3
fixed, 2 kept; understood: 4 items, 1 fixed, 0 kept`, accepted only in the
exact form the script prints. A commit with no cold read keeps the plain
value; posts keep their footer. The value, not a new trailer key, because the
commit script, the shared hook and bug-hunter already carry it as one opaque
line.

**Rejected.**
- **Withholding the token until a read comes back clean.** Readers rarely
  report nothing, and the author relays the report, so "clean" is unverifiable.
- **Free-form reports.** The text being read contains quotation marks too, and
  a guess at a report's meaning passes by mistake.
- **Signing with `kept` and fixing later, or showing kept findings after
  signing when no person can be asked.** Either way the wording lands before
  anyone sees it.

**Known gaps.** `fixed` proves the item changed, not that the edit touched the
place the reader stopped; editing another part of the item is on the cheat
list. A `kept` reason is checked only for being there.

---

## The cold reader says what it understood

For every item the reader writes `Item <n>, understood: <one line>`: who or
what does each thing, whether it always happens or only in some case, and
whether the code does it or someone else could make it happen. The author
answers each one: `matches`, `fixed` (checked like a fixed finding) or
`kept (asked): <reason>`. The counts gain `; understood: <items>, <fixed>,
<kept>`; a value without that part still verifies.

**Why.** A reader sure of a wrong meaning stumbles nowhere, so its report says
"read straight through": the rule 4 comment passed its third cold read that
way. The author, who knows what was meant, can see the difference. The three
questions are what a hypothetical written as fact gets wrong; a summary
without them tends to restate the item's words.

**Rejected: a line only for items read straight through.** An item with
findings can be misread confidently elsewhere.

**Known gap.** `matches` is the author's claim; answering it falsely is on the
cheat list.

---

## Without subagents, the cold read goes back to the caller

An agent that cannot start a subagent hands back the brief, its token, and the
paths of the message file and worktree, and does not sign or commit. It reads
the brief itself only when nothing will read its result.

**Why.** An author reading its own brief is the same author whose gaps the read
exists to find; in one workflow every author lacked a subagent tool, so every
"cold read" was the author's. A workflow script can start the fresh reader.
The token lives in the repository's git directory, so a different agent can
fix the findings and sign.

**Rejected: reading the brief yourself whenever no subagent is available.** It
produces a report that looks like a cold read and is not one.

---

## Commits carry a trailer that signs the snapshot

Every commit carries `Prose: ✓ <tree>:<message>`: the first 12 hex of the
staged tree (`git write-tree` when the signing call runs) and of the sha256 of
the normalised message. Agents commit through the shared commit script with
`--verified-value scripts/verify-staged.sh Prose <value>`, which refuses the
commit if the tree or message no longer match.

**Why.** The signature proves a script ran over the final text, and an edit
after it breaks it. Twelve hex per half stops a trailer written from memory;
no hash can prove when it was computed.

**Every commit gets the pass; prose issues no skip value.** Every commit has a
message a reviewer reads, so no commit honestly qualifies for a skip.

**One commit carries every installed skill's trailer.** Composing them is the
shared library's job (`../../lib/commit-trailer/`), through trailer families.
While bug-hunter runs, its commit step runs prose's two calls and carries the
`Prose:` value.

**An amend goes to git directly,** with `git commit --amend -F <file> --trailer
"<the Prose: line>"`, because the commit script cannot amend. Nothing checks the trailer before the
amend lands; the commit hook reports it afterwards if it no longer matches. Fix, if amends need checking before they land: an amend
mode in the commit script.

**Messages are UTF-8.** `prose check` refuses a message that is not valid UTF-8
or holds a Unicode noncharacter (git would store it re-encoded), and a
non-UTF-8 `i18n.commitEncoding` (reading it back converts the `✓`).
`verify-commit` reports a commit stored under any other encoding label as a
mismatch.

**The listing is not hashed.** `prose check` lists the message, each changed
doc or spec, and each touched code comment so the agent knows what to pass
over; history language in touched comments is printed as non-blocking flags.

**`verify-commit`** exits 0 valid, 1 invalid, 3 unable to check, matching the
library's callback contract. Its reason starts `missing` (git sees no `Prose`
key at all), `unrecognised` (any other form, including a blank value),
`mismatch` (the message half) or `tree` (only the tree half), so the report
says which half broke.

**Rejected.**
- **A rebase-proof signature over the prose lines a commit adds.** It grew
  rename, cancellation and parse-failure rules, each another way for check and
  verify to disagree. The hook exempts rebases and cherry-picks by reflog
  action instead.
- **Two lines** (`Prose: checked` plus a signature), or **counts of blocks
  rewritten** in the trailer: nobody needs them.
- **A git `commit-msg` hook.** Per-clone setup, and the reflog hook covers it.

**Known gap.** The commit script runs no verifier for a value starting
`skipped`, so a `Prose: skipped…` value written by hand or by another tool
lands, and only the hook reports it (see *Open*).

---

## `prose check` ends with the shared result block

The signing call prints only the shared `result-block.sh` block, holding the
trailer, so no one types it. The format lives in the shared script; prose does
not copy it. Either call stops before printing anything when `result-block.sh` is missing.

---

## `prose check` runs the pre-commit hook first

In a repository with a pre-commit hook, both calls run it, through the shared
`run-pre-commit.sh`, before they list or hash anything.

**Why.** A formatter in the hook rewrites staged files after the check would
have signed them, breaking the trailer. Running it on the first call too means
the agent passes over the text that lands, and a failing hook stops the agent
before the pass. The library records a passing run for the staged state, so
in the usual flow the hook runs once in total.

A failing hook makes `prose check` exit 2: the first call issues no token, and
the signing call keeps its token for after the fix. With `prose check --amend`,
`git commit --amend` runs the hook a second time itself; a formatter that
already ran changes nothing.

---

## The signed message is found by searching from its end

`prose check` hashes the whole message it is given. `verify-commit` removes 0, 1,
2 or more trailer-shaped lines from the end of the stored message's last
trailer block, and accepts the commit when any of those results hashes to the
message half. The search
stops at an indented line, any line that is not trailer-shaped, or the start
of the paragraph.

**Why.** git adds trailers only at the end, and `prose check` refuses the
`trailer.*` config that could move them, so the signed text is always the
stored message minus some lines from the end. A list of trailer keys missed
edits to keyed lines elsewhere and had to grow with every skill.

**How the message is normalised.** LF endings, trailing blanks off each line,
blank-line runs collapsed, ends trimmed. When git reads the last paragraph as
a trailer block, its lines are put in git's `token: value` form first, and an
empty-valued key is folded into the indented line after it, as git does. A line
starting with `#` or `core.commentChar` is refused, since git's cleanup may
delete it. A `prepare-commit-msg` hook that edits the message breaks the
signature, and the report says so.

**Accepted cost.** A trailer-shaped line appended after signing does not break
the hash.

**Rejected: git's own commands for parsing** (`git stripspace`, `git interpret-trailers`). A prototype committed about 2,500 test and fuzzed
messages for real. The git version round-tripped every default-config one, but
prose's own parser already matched git on all 2,464 of them that it accepts. The git version would save about 90 lines while adding git calls,
depending on the internal order of `git commit`, and still needing most
refusals. Revisit if people hit the refusals (configured trailer keys, `#`
lines, `core.commentString`) in practice.

**The fold follows git's default rule:** an empty-valued
key is folded only when git would read the whole paragraph as a trailer block.
A configured `trailer.<x>.key` makes git count more lines as trailers, but
`prose check` refuses to sign under any `trailer.*` config except
`separators=:`. So a mismatch arises only when a commit is verified under
trailer config that differs from where it was checked, and then it fails
loudly. Fix, if needed: read `trailer.*.key` config and count those keys as
git does.

**Rejected: folding every paragraph.** It would need no config, but folding
joins an indented line onto the empty-valued key above it, dropping its
indentation, so an edit to only that indentation would no longer break the
hash.

---

## Posted text carries a signed footer

A pull request description or comment ends with `prose ✓ <6 hex>`, the hash of
the text above it (LF endings, trailing blanks and blank lines removed), which
`sign` prints. A hook recomputes it before the post goes out and blocks a
mismatch. `sign` replaces an existing footer, so re-signing works.

**What it proves:** a script produced the footer for that exact text. Not when,
or that the rewrite was good. The hash is unkeyed, so a reimplementation could
forge one; a secret key would sit on the disk the agent reads. The design stops
skipping, and forgery is forbidden by SKILL.md's *Never* list and caught at review.

**Rejected: a plain `prose ✓`.** It can be typed from memory.

---

## Checks are layered by where the text goes

| Destination | Check |
|---|---|
| GitHub via MCP | a hook before the tool runs, which blocks |
| GitHub via `gh` | the same hook, on an allow-list of command forms |
| Commits | the reflog hook shared with bug-hunter, after the command |

Only an agent-side hook can stop a post before it is public. Linear and Discord
are to be added the same way. The MCP check matches the server, not a list of
tool names, because a tool a name list missed would pass silently. It requires
a footer when the input has a string under a `body` or `comment` key at any
depth, so each review comment needs its own footer (inline comments are the
agent text reviewers read most). A payload that is not JSON passes: the hook fails
open, like the commit hook. For a stricter setup than a hook that fails open,
permission rules can deny the raw GitHub tools outright.

---

## Rejected: a GitHub Action

prose has no CI check; it runs only where the agent works, through the hooks
the skill installs.

**Why.** Installing the skill installs the hooks, so every agent using prose is
already checked locally, and CI would catch only agents that don't use it. The
remedy for those is asking them to use it. Igor builds its trailers in code and
verifies them itself. A CI check would also need a policy for which commits are
a person's and for rebased commits. It would need back the code that verified
rebased and re-encoded messages, deleted with the Action.

**Where this stops applying.** If agents that never install the skill commit to
repositories adopting prose. `verify-commit` and `verify-post` are what such a
job would run, and the rewrite handling would come back from `e8da005`.

---

## The posting hook reads an allow-list

For a Bash command, the hook reads a post's body only when `gh` is the whole
command and the body comes one of two ways:
- `--body` or `-b` (`--comment` or `-c` for close and reopen) with a literal
  value, in single quotes or in double quotes without `$`, backtick or
  backslash;
- `--body-file` or `-F` naming an existing file.

Any other command that runs a `gh` post is blocked, and the message names
those forms.

**Why.** Two bug-hunter runs found about 25 places where a general parser read a
command differently from bash, most letting an unsigned post through. With a
short allow-list nothing is left to diverge.

**Rejected.**
- **A general parser,** however careful.
- **A heredoc body form.** macOS bash 3.2 parses a heredoc inside `$( )`
  differently, and it needed five refusal rules for that shell alone.
  `--body-file` covers the same flow.

**Titles are not checked.** A footer cannot go on a one-line title, so
`--title` is an ordinary value flag.

**Where this stops applying.** A deliberately disguised `gh` (`g''h`, `$GH`) passes; the hook stops accidents, not an agent set on getting around it.

---

## A command that runs no gh post is not a post

A command that mentions a `gh` post verb but is not the whole-command form passes when the hook can show the shell runs no `gh` post in it: every simple
command either names no `gh` as a word, or is a `gh` command that sends no
text (a label edit, `gh pr ready`, a close without a comment, `gh pr view`).

**Why.** Blocking every mention forced workarounds for commands that posted
nothing, such as a Python script whose string named `gh issue edit`, or
`cd … && gh issue edit 12 --add-label …`.

**How it keeps the allow-list's protection:** it reads no bodies, only shows
that no post runs, and blocks anything it cannot read exactly: backticks,
`<(…)`, `$'…'`, `${…}` beyond a name, `$(…)` in double quotes, unterminated
quotes, heredocs in parentheses or holding `$(`, multi-digit descriptors,
comments holding quotes or operators. The rules for each simple command:
- **The command word** is the first, after `if`, `then`, `elif`, `else`, `do`,
  `while`, `until`, `!`, `{` or `time`. `fi`, `done` or `}` alone is no
  command.
- **`gh` is named** when not followed by a letter, digit, `_` or `-`.
- **Text naming `gh` is data** only in a command from `DATA_COMMANDS` (`echo`,
  `cat`, `grep`, `git`, `python3` and a few more), which run neither their
  arguments nor their stdin. Any other command naming `gh` blocks, since it
  might run it (`sh -c`, `eval`, `trap`, `env -S`, `xargs`). `printf`, `test` and `[` are left out of `DATA_COMMANDS`: bash evaluates an array subscript given to `printf -v`
  or `test -v`, command substitution included.
- **A `gh` command** must be first and plain; its words are read after quote
  removal. `NO_TEXT_VERBS` lists the subcommands that send no text; `merge` is
  not on it.
- **A pipe or input redirection** matters only for the command that reads it,
  which must be a data command or a `NO_TEXT_VERBS` subcommand. A post verb reading input blocks even with no body flag: allowing it would rely on gh
  never reading a body from stdin except through `-F -` (`--body-file -`),
  which a later gh could change. When input can reach a group, loop or subshell, every
  command in it must be a data command.

**Rejected.**
- **Python's `shlex`.** It knows no heredocs, `$(…)` or bash comments.
- **Reading bodies in longer commands.** An earlier `cd` or `printf > body.md`
  changes which file `--body-file` names.
- **A list of commands that run text as code.** Such a list was missing `trap`
  and `env -S`, and is never complete; a closed list of data commands fails
  toward blocking.

**Where it stops applying.** A script handed to another interpreter
(`python3 - <<'EOF'`, `node -e`) can run `gh` itself, and text the shell
evaluates twice (`(( ))`, `let`, zsh `${(e)…}`, git aliases, `rebase -x`) is a
disguise, out of scope. Revisit if `gh` gains a way to read a body from stdin
without `-F -`.

---

## Cursor's posting hook is wired as a best guess

The posting hook is wired for Cursor on `beforeShellExecution` and
`beforeMCPExecution`, and the README says it is unverified.

**Why.** Cursor's payloads and its `permission` answer are documented and the
script reads them; waiting would leave Cursor users with no check. Unverified:
what a `beforeMCPExecution` matcher matches (so the script filters on
`mcp_server_name` itself) and a run in a real Cursor. Cursor blocks when a
permission hook prints no valid JSON, so every allowing path prints
`{"permission":"allow"}`.

---

## Docstrings are found by a child interpreter

Decided by Adam, 2026-10-25: a Python file too deep to parse is listed as one
that does not parse, never a crash. Python 3.9's parser crashes in C on a
deep enough expression, such as 200,000 terms added in a row, and a crash in
C cannot be caught. So `ast` runs in a child interpreter, which takes the
crash; a child that fails, by error or by signal, means the file does not
parse. A depth cap set before parsing was rejected: it could only guess the
parser's limits, which differ by Python version and by kind of expression.
The child costs one interpreter start per changed Python file.

## Which files are docs

Docs are `.md`, `.mdx`, `.markdown`, `.rst`, `.adoc`, `.asciidoc`, and files
named `README`, `CHANGELOG` or `CONTRIBUTING` with any extension. Specs are
anything under an `openspec/` directory.

**Docs are exempt only where vendored.** A doc under `node_modules/` or
`vendor/` is not prose; one under `build/`, `out/`, `dist/` or `generated/` is,
because people keep authored docs there. Code comments still skip the
scanner's whole list of build and vendored directories.

**Comments** are found by lexers for Python and the C family, and own-line `#`
comments in shell, YAML, TOML, Ruby, Perl, R, PowerShell, `Dockerfile` and
`Makefile`. A `#` after code is not read, since it may be in a string. In
JavaScript, a `/` opens a regex literal only after an operator or keyword and
only if it closes on the line; elsewhere its `//` is a false item in the
listing, which changes no trailer.

**Rejected: `.txt` as a doc type.** It takes in `requirements.txt` and
`LICENSE.txt`.

---

## Scripts are found from the skill's base directory

SKILL.md defines `S` as `scripts/` in the skill's base directory, the one
Claude Code names on its "Base directory for this skill:" line. When `prose.py` prints the command for the next call, it uses the path it
was run by, without resolving symlinks.

**Why.** Igor loads workers' skills from a pinned directory where the home
installs are missing or hold a different copy, and grants `prose.py` by that
path, so any other path is denied, including the clone the link resolves to.

**Rejected.** Home-directory paths, which cover only `manage-skills` installs;
`${CLAUDE_SKILL_DIR}`, which another agent reading SKILL.md sees unreplaced;
the resolved path, which the by-path grant denies.

---

## Known gaps, recorded rather than fixed

Each is left on purpose; its fix says what would close it.

- **`core.commentString` is not read,** only `core.commentChar`. Fix: read it.
- **`gh api` and `gh pr merge --body` are not checked.** Fix: add them, with
  `gh api`'s `-f body=` and `--input` as body sources.
- **zsh `extendedglob` or `magicequalsubst` change what gh receives** from an
  unquoted `#`, `^` or `=`. Neither is set on the machines checked. Fix: refuse
  those characters unquoted.
- **Two `prose check` runs at once in one checkout fail on git's index lock.**
  Each worktree and each Igor clone has its own index. Fix: compute the tree
  from a copy of the index (`GIT_INDEX_FILE`), tested to give the same hash.
- **Only an MCP server named exactly `github` is checked** in Claude Code. Fix:
  match case-insensitively and by substring, as the Cursor path does.
- **Config given only to `git commit`** (`git -c trailer.…`) is not seen by the
  check, giving an honest mismatch. It fails closed.
- **`commit.cleanup=verbatim` with a leading blank line,** and
  **`git interpret-trailers` without `--no-divider` on a message holding a
  `---` line,** both fail verify on an honest commit. They fail closed.

---

## Open

- **Skip notes,** undecided: the commit script runs no verifier for a value
  starting `skipped`, so a `Prose: skipped…` commit lands unchecked. Change
  the shared library to verify it, or keep the gap recorded here.
- More rules.
