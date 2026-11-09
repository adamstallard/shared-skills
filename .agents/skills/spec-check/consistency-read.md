You are checking one OpenSpec change against everything it has to agree
with. You did not write it, which is why you were asked: its author cannot
read it cold. Report what you find; edit nothing.

The change: <change directory, e.g. openspec/changes/keep-action-log>
Read it from: <"the working tree", or a git ref such as origin/spec/my-change>

When it is a ref, read each file with `git show <ref>:<path>`.
Its base branch: <base, e.g. origin/main>

The change's files:
<one path per line: every file under the change's directory, e.g.
openspec/changes/keep-action-log/proposal.md>

The decision records it must agree with:
<one path per line, as `spec_check.py records <change>` prints them, or "none">

Read each of these files whole, every line. With the Read tool, page
through a long file with offset and limit until you reach its end; from a
ref, read `git show` in pieces with `sed -n` the same way. Do not skim, grep
or sample them: a problem may sit anywhere in a long delta spec. Read each
decision record listed above whole too, from the same place.

Read, in this order:

1. Every file of the change, listed above, whole: proposal.md, design.md if
   present, tasks.md, and each specs/<capability>/spec.md. Then each
   decision record listed above. A change holds no record of its own: the
   branch edits a record directly, so for a record the list says the
   branch edits, also read its diff, `git diff <base>...<ref> -- <record>`
   (`git diff <base> -- <record>` for the working tree). What that diff adds,
   changes or deletes is part of the change.
2. Every spec under openspec/specs/ on the base branch:
   `git show <base>:openspec/specs/<capability>/spec.md`. Read all of them,
   not only those the change names.
3. Each dependency the proposal declares, if it is a stacked change: a line
   `Builds on: <change> (<owner>/<repo>#<number>)`. Run
   `git fetch origin pull/<number>/head`, which works for an open or merged
   pull request, from a fork too, and read every file of the dependency's
   change with `git show FETCH_HEAD:openspec/changes/<change>/<file>`. If the
   fetch fails, or the change is not there, report that as a finding and
   read on without it. Apply the dependencies to the base branch's specs in
   the order listed, each delta's RENAMED, REMOVED, MODIFIED and ADDED
   requirements in that order. From here on, "the base" means the base
   branch plus those dependencies: a requirement a dependency removes or
   renames is gone, and one it rewrites reads as the dependency wrote it.
   Compare the change against that base, and check that what it modifies or
   removes still matches what the dependency now says. Do not report a
   dependency as a conflicting change for what it defines; the change builds
   on it.
4. Every other open change under openspec/changes/ (not archive/).
5. Every open pull request that touches openspec/: list them with
   `gh pr list --state open --json number,title,files`. Then, for each pull
   request that changes a spec this change also touches, or that adds or
   edits an OpenSpec change naming the same capability, read `gh pr view <n> --json title,body,comments` and
   `gh pr diff <n>`. Never use `gh pr view --comments` or
   `gh issue view --comments`: when output is not a terminal they print only
   the comments and drop the title and body. Read an issue the change cites
   with `gh issue view <n> --json title,body,comments`.
6. The repository's architecture or design docs, if it has them (for example
   docs/architecture.md, ARCHITECTURE.md, docs/design/).

Then go through the checklist below. For a finding that sets the change
against something else (items 1, 2, 3, 7, 9, 11, 12, 14, 16), quote both sides:
the change's words with file:line, and the words it conflicts with, with
file:line, PR number or issue number. Such a finding with one quote is a
guess. A finding about the change alone (items 4, 5, 6, 8, 10, 13, 15, 17)
quotes the change and says what is missing.

1. Contradiction inside the change: two of its rules that cannot both hold
   (a rule that the log keeps no file contents, beside a rule that keeps shell
   output, which includes `cat` of a file).
2. Contradiction with a spec, another open change, or an open PR touching the
   same spec (a PR's scenario publishes "exactly that description" while this
   change appends lines after it).
3. A rule stated in two places, here and in another change or spec. One rule
   belongs in one place; the other refers to it.
4. A SHALL or MUST no scenario tests, or a scenario that does not follow from
   its requirement's text.
5. A term used before it is defined, or defined nowhere.
6. Rationale inside requirement text that is not needed to apply the rule.
   A requirement holds its SHALL statement plus at most one *because*
   sentence, a plain reason for orientation that may stay even when a
   Rationale entry gives the evidence. Further reasoning with evidence
   moves to a Rationale entry in the capability's decision record, however
   short; the rest belongs in design.md.
7. A code citation (file:line) that does not point at what it claims on the
   base branch. Open each one: `git show <base>:<path>`.
8. An unhandled hazard: credentials reachable by repository code; secrets
   under arbitrary variable names; shell or markdown injection through an
   untrusted string (shell syntax in a command line, a backtick in a path
   inside a code span); private content written to a public place.
9. An interaction with another workflow that silently voids the change (a
   check that flags every pull request of one kind and skips every push of
   another, so a label built on it carries no information).
10. A fact the change depends on that nobody has measured (whether a stream
    reports exit codes), stated as if known. It belongs in tasks.md as a task
    to measure it and in design.md's Open Questions, and anything built on it
    must degrade honestly when it turns out false.
11. Evidence shown as checked when its source does not exist yet. A value
    from something unbuilt must read "not checked", never pass by default.
12. Two decisions that contradict or repeat each other, in design.md's
    Decisions or wherever the change states its decisions (one decision lets
    a release delete files, another says a release never deletes).
13. A decision not needed to build the change: one that only records who
    asked what or when, or settles something no requirement, task or other
    decision rests on.
14. A rule, design or task that brings back an approach a decision record
    rejects, or breaks a constraint one records while its *Holds while*
    condition still holds (a change that adds a lookup tool the worker
    calls, beside a record entry "Rejected: A retrieval tool the worker
    calls"). Quote the record entry as the other side. A change that means
    to reverse the entry edits or deletes it in the record, on its branch.
15. A rejected alternative or constraint named in design.md that no
    decision record holds. design.md is
    archived with the change and never read again, so one that must
    outlive the change belongs in the record.
16. A Constraint or Rejected entry, in a record listed above, whose rule a requirement or scenario already
    states (an entry "Constraint: Records are kept for thirty days" beside
    a requirement that keeps them thirty days, with a scenario testing it).
    Quote the requirement or scenario as the other side. Say to cut the
    entry. If it gives a reason with evidence, that reason goes in a
    Rationale entry naming the requirement, however short. A reason
    without evidence becomes the requirement's plain *because* sentence
    when it has none yet, or goes to design.md.
17. Reasoning in design.md, or an entry in a record listed above, that
    does any of these:
    - names a person as its reason;
    - records who decided or amended a decision, or when ("(<name>,
      <date>)", "reversed by <name> on <date>", "<name> narrowed the
      scope", "decided on <date>");
    - states a preference;
    - claims a fact without Evidence;
    - gives a Rationale entry its requirement's own test as its only
      Evidence, which shows the rule is enforced but not why it is needed;
    - gives a Rejected entry for an alternative that a requirement guards
      against (one its scenario would fail), which belongs in that
      requirement's Rationale;
    - only restates its requirement ("Constraint: Keep it simple", or a
      Rationale entry that says only that its requirement is needed).

    Say to fix it in this round:
    ask the person who decided for the evidence and write it, move a
    rejection a requirement guards against into that requirement's
    Rationale, reopen the decision, or strike the entry.

Write each finding as:

  Finding <n> [<checklist number>] <change file>:<line>
    Change: «exact words»
    Conflicts with: «exact words» (<file>:<line> | PR #<n> | issue #<n>),
                    or "none" for a finding about the change alone
    Why they cannot both hold, or what is missing: <one or two sentences>
    Who decides: author | a person (a question for design.md's Open Questions) |
                 another change or PR (report it; do not edit it)

End with one line per checklist item you found nothing for:

  [<checklist number>] nothing found

## A record read on its own

A decision record the branch edits, for a capability no open change
touches, is read on its own. The brief then names it in place of the
change:

The record: <path, e.g. openspec/specs/action-log/decisions.md>
Read it from: <"the working tree", or a git ref>
Its base branch: <base, e.g. origin/main>

Read the record whole, its diff against the base (`git diff
<base>...<ref> -- <record>`, or `git diff <base> -- <record>` from the
working tree), and its capability's spec on the base branch, `git show
<base>:openspec/specs/<capability>/spec.md`, whole. Skip the reading list
and items 1 to 13 above, and go through items 14 to 17 with the spec in
place of the change:

- [14] a requirement of the spec that brings back an approach an entry
  rejects, or breaks a constraint an entry records while its *Holds
  while* condition still holds;
- [15] an entry the diff deletes whose rejection or constraint must still
  hold, and that no requirement or other entry holds instead;
- [16] an entry whose rule a requirement or scenario of the spec already
  states;
- [17] an entry the diff adds or changes that does any of item 17's
  things.

Write findings in the form above, with the record's path and line in
place of the change file, and end with a line for each of items 14 to 17
you found nothing for.
