# spec-check — decisions

`spec-check` does the part of spec review that needs every other spec in
mind, so the person reviewing judges only whether the rules are right. It
serves the spec stage of review: a change's specification is reviewed and
approved before any code for it is written, and that review is where a
reviewer's time goes. It has two parts: a script, `scripts/spec_check.py`,
and a consistency read done by a fresh subagent. The script's `check`
subcommand runs the mechanical checks, `sign` runs them on the staged tree
and prints the commit trailer, and `setup` adds a rule to OpenSpec's config.
This file is why it works the way it does.

Each entry: the decision, why, and what was rejected.

---

## Why the skill exists, and what it is checked against

**Decision.** The checklist in [consistency-read.md](consistency-read.md) is
built from one run. Four OpenSpec changes were drafted, and a fresh agent
cross-checked each against the rest of the corpus. The cross-checks made 44
amendments, in eleven kinds: contradictions inside a change and with other
specs, changes or open pull requests; a rule stated twice; a SHALL with no
scenario; an undefined term; rationale in requirement text; stale citations;
unhandled hazards; a workflow interaction that voided a change; an unmeasured
fact stated as known; and evidence shown as checked when its source did not
exist. The script takes the kinds a program can detect, and the subagent's
consistency read takes the rest.

**Why.** Those are the mistakes a careful author made. A checklist from
first principles would rank them by guesswork.

---

## A skill plus a script, not a script alone

**Decision.** The script checks what is mechanical. The skill directs the
consistency read, the fixing and the commit.

**Why.** Most of the 44 amendments were judgment: whether two rules can both
hold, whether a hazard is handled, whether a fact was measured. Of the eleven
kinds, only a SHALL with no scenario, a rule stated twice and stale
citations can be decided by a program. The script also checks one thing
outside them: that the proposal opens with its decisions. A script alone would pass the
specs that needed the most work.

**Rejected.**
- **Repeating what `openspec validate --strict` checks.** The script runs it
  and shows its result instead. The one overlap is a requirement with no
  scenario: validate reports it with no line number, and the script needs it
  to say where.
- **A heuristic for "every SHALL sentence has a scenario".** Counting
  normative sentences against scenarios flags nearly every real requirement:
  one scenario often tests several sentences. That judgment is the
  subagent's (checklist item 4).

---

## A citation fails only where it cannot be wrong

**Decision (Adam, 2026-10-13).** A citation is an error only when it has a `/`
and the cited line is in neither the base branch nor the change's own copy of
the file: the file is missing from both, or both are shorter than the line.
Every other citation finding is a check, which never fails the run: a bare
name such as `config.py:50`, whether it matches no file or several, and a
line that only the change adds. Text in a code fence, including a fence inside a
list item or a blockquote, is never read as a citation. Fences follow
CommonMark, with a fence's indent counted from the content column of the list
item it sits in. A cited path is read the way the file system would read it:
through symlinks. A path into a submodule cannot be read from the parent
repository, so a citation there is at most a check.

**Why.** `sign` refuses while any error remains, so a false error stops a
correct spec from being committed. Six passes of bug-hunter, the skill that
hunts for bugs before a commit, each found the next case where guessing at
citations misread ordinary spec text. The cases were of four kinds:
- an IP address, a service address (`redis.cache:6379`) or an image name
  read as a file;
- a quoted stack trace read as a citation;
- a citation of code the change's implementation adds, wrongly called
  broken (the implementation is committed on the spec's branch once the
  spec is approved, so the base never has it);
- a bare name that matched a different file than the one meant.

Each narrower guess fixed one input and broke another. A path with a `/` that
neither tree has, at that line, is the one citation the script can be sure is
broken.

**The decisions section is read with the same caution: only an
unmistakable label ends it.** Each list item is a decision until the "still
open" label, and a label guessed wrongly would leave decisions unchecked or
call open questions decisions. The label counts only
as a whole label: a heading, a bold or italic label, a line ending in a
colon, or a line saying nothing else. An indented line continues the
decision above it, whatever it says.

**Rejected:**
- An allowlist of file extensions deciding which bare names are files. Each
  version of the list had a gap the next pass found. A list of host
  suffixes survives only to skip addresses such as `example.com:443`, which
  are never files.
- Treating every citation as a check. That would drop the error for a
  citation copied from another branch, whose line no longer exists here.

---

## The consistency read is a fresh subagent

**Decision.** A subagent that did not write the change does the read, from a
fixed brief. The author does it only where no subagent can be started, and
the trailer says so (`read by its author, no subagent`).

**Why.** An agent cannot judge its own spec cold: it reads what it meant, not
what it wrote. In the run above, the 44 amendments came from fresh readers
cross-checking changes their authors had submitted as finished.

**The brief is fixed** and the author adds no summary. A summary is the
author's reading of the change, which is the reading under test.

**`--json title,body,comments`, never `--comments`.** `gh issue view N
--comments` and `gh pr view N --comments` print only the comments, with no
title or body, when output is not a terminal, which is how an agent runs
them. A reader using them sees the discussion and misses the decision.

---

## Findings go into the spec, not into comments

**Decision.** A finding is fixed by amending the spec. A question only a
person can decide goes into the proposal's decisions section as an open
question. A conflict with another change or pull request is reported, not
edited.

**Why.** The spec is what `openspec validate` checks, what an implementer
builds from, and what a reviewer approves. `gh pr view` shows the body
without the comments, so a decision left in a comment is invisible to the
default read, and the change looks reviewable when it is not.

**Rejected:** editing another change to resolve a conflict. That change has
its own author and reviewer, and an edit from outside lands in a review
nobody is doing.

---

## Proposals open with their decisions

**Decision.** A proposal opens with the decisions the reviewer is asked to
make, each with the alternative it rejects; then what is still open; then
everything else. The script fails a proposal whose first section is not a
decisions section, and a decision whose text never says what it rejects.
`setup` puts the rule in `openspec/config.yaml`, which OpenSpec prints to
the agent drafting the proposal (verified with OpenSpec 1.6.0: config rules
appear inside `<rules>` in `openspec instructions proposal`).

**Why.** At the spec stage, the reviewer's job is the decisions. A decision without
its rejected alternative cannot be judged: the reviewer cannot tell a choice
from a default.

**Rejected:** a decisions section anywhere in the proposal. OpenSpec's own
template opens with "Why", and a reviewer reads in order.

**`setup` edits text, not YAML.** The standard library has no YAML parser,
and a parse-and-dump would drop every comment. The edit appends a marker
comment and one list item, and refuses flow style rather than guess at it.
The marker is what makes a second run a no-op even after someone rewords the
rule.

---

## TLA+ is guidance, not automation

**Decision.** The skill says when a requirement gets a TLA+ model and how it
maps to requirements and CI. It does not write models.

**Why.** Only requirements about concurrency, ordering, crashes between
writes or protocols between processes get a model. A model is worth only as
much as its correspondence to the spec, and choosing what to abstract is the
design work itself. A generated model would check whatever the generator
understood.

---

## The trailer is bound to the tree

**Decision.** `sign` runs the mechanical checks on the staged tree and prints
`Spec-check: ✓ <tree> <summary>`. The commit script runs `verify-staged.sh`
before committing, and the hook runs `verify-commit` after, both comparing
the value's tree with the tree that lands. A value starting `skipped` binds
nothing.

**Why.** A trailer typed from memory can look right. One bound to the tree
proves the checks ran on what landed, and an edit staged after signing breaks
it. This is the commit-trailer library's design
([its DECISIONS.md](../../lib/commit-trailer/DECISIONS.md#the-trailer-is-minted-from-the-tree-not-recalled-by-the-agent)).

**The value carries the binding** (`--verified-value`), rather than a separate
`Spec-check-Tree:` line (`--minted`). bug-hunter's commit script forwards
`--verified-value` families unchanged, so Bug-hunter, Prose and Spec-check
land on one commit through one call, with no change to bug-hunter.

**The signing refuses on errors.** A `✓` over a change with errors would read
as passed. Work in progress commits with a skip note.

**Rejected:** binding the message too, as prose does. The checks read the
spec, not the commit message.

---

## Only commits that change `openspec/` are judged

**Decision.** The hook sets the library's `COMMIT_TRAILER_PATHSPEC` to
`:(top)openspec/`. A commit that changes nothing there is never judged, with
or without a trailer.

**Why.** A code-only commit has nothing to check, and a report on it would
teach readers to ignore the report.

**Rejected:**
- **Filtering inside this skill's report.** The library has already decided
  to report by then, and an empty report falls back to the library's
  generic one.
- **A callback the library calls per commit.** A pathspec is data, so it
  needs none of the subshell and marker machinery a sourced callback does.

**Limit:** only `openspec/` at the repository root counts, which is where
OpenSpec puts it.

---

## The hook is enabled by default

**Decision.** `hook.json` says `"default": "enabled"`.

**Why.** Several organizations install from this repository, each with its
own repositories, so the default must suit a repository that uses OpenSpec and
one that does not:
- Installing spec-check is itself the opt-in. Nobody gets the hook without
  asking for the skill.
- The hook judges only commits that change `openspec/`, so in a repository
  without OpenSpec it never speaks.
- It reports and never blocks.
- Off by default, an installed spec-check would leave the spec stage
  unchecked, and nothing would say so.

**Rejected:** off by default. It suits a hook that reports on every commit,
which this one does not.
