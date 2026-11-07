The sequencer is a skill that recommends the order in which a repository's
open work is specified, implemented, reviewed and merged. Shared-skills
issue #43 decides what it does. adamstallard/igor#231 decides how the order
is kept and published, and the skill follows those decisions. Adam
(adamstallard) owns this repository and decides this change.

Terms used throughout, as the spec defines them:

- **An item** is an open issue or pull request the order holds. **The
  order's issue** is the one issue whose body holds the whole order.
- **An edge** is a rule's finding that one item comes after another, with
  its reason. The rules that set edges are **modifies** (a change that
  modifies a requirement another change adds comes after it), **cites** (a
  change that names another change's requirement comes after it),
  **explicit links** (GitHub's "blocked by" relations and `Depends on #n`
  lines) and the model step's rule, below.
- **A copy duty** sets no edge. Where two changes modify one requirement,
  whichever archives second must add the other's new scenarios to its own
  copy of the requirement, since archiving replaces the requirement with
  the archiving change's whole copy.
- **A cycle** is a set of items whose edges lead from each back to itself.
- **A merge wait** is not an edge either: where two pull requests change a
  file in common, the later in the order waits for the earlier to merge.
- **The model step** applies the one rule that needs a model: a change
  whose code will call another change's code is built after it.
- **A caller** is whatever runs the script: an agent in a session, the CI
  workflow, or an Igor, one of the AI teammates of adamstallard/igor.
- **Gate one** is approving a change's spec, in a pull request holding
  only the spec; **gate two** is its implementation, built on the same
  branch after that approval.

## Context

Agents work out "what next, what to review, what merges first" by hand in
each session. adamstallard/igor#204 shows the cost: one archive order for 23
changes, the order in which their OpenSpec changes are archived into the
main specs, took about a week of edits. Under the two-gate workflow that
one order is also, with few exceptions, the order to build, review and
merge in.

## Goals / Non-Goals

**Goals:** one deterministic order, whoever computes it; a reason for each
place a rule decides; an order kept in issue and pull request bodies, which
`gh issue view` and `gh pr view` print without comments; review effort
pointed at what unblocks the most; questions of judgement left to a person.

**Non-Goals:** merging; choosing a cycle's order; what Igor builds for its
Sequencer role (igor#231); the spec-checker's dry archive, which archives
every open change in the order into a scratch copy of the default branch
to prove the order applies, and which igor#231's decision 7 gives to Igor's
spec-checker.

## How the script runs

The script is `.agents/skills/sequencer/scripts/sequencer.py`. It has three
commands:

- `order [--json]` computes the order and prints it, with a hash of its
  inputs and, for each pair of open changes, the names written in
  backticks in both changes' `tasks.md` files, to help the model step. It
  edits nothing.
- `publish [--code-edges FILE] [--decide '#<n> first' --by <login>]`
  computes the order and edits the order's issue and the items' bodies. It
  takes the model step's edges from `FILE`, which carries the inputs hash
  `order` printed, and records a person's choice in a cycle given with
  `--decide`.
- `setup-ci [--model-step none|api-key|igor] [--force]` writes the workflow
  template.

In a session, the agent runs `order`, applies the model step to the
printed changes and names, writes its edges to a file, and runs `publish
--code-edges` with it. The CI workflow runs `publish` on each trigger.
Where the repository chose its API key, a second job then runs the model
step and publishes its edges. Where it chose an Igor, `publish` labels the
order's issue, and a Sequencer Igor runs the model step and publishes its
edges through the same script.

## Decisions

Each entry states the decision and its reasons, and labels each
alternative not taken or cost taken on:

- ***Ruled out by a scenario:*** an alternative a test can check. The spec
  holds the rule as a requirement with a scenario the alternative would
  fail; the entry names that requirement.
- ***Recorded:*** an entry in `specs/sequencer/decisions.md`, in the form
  shared-skills issue #56 sets: a rejected alternative under its
  *Rejected*, a cost or untestable constraint under its *Constraints*.

### A skill, with Igor's role as one caller

**The rules and the script live in a shared-skills skill; Igor's Sequencer
role is one caller of it,** as Igor's inquisitor role calls the inquisitor
skill (igor#231, decision 9). The order is needed wherever several changes
are open at once: in a person's own session, as CI in a repository with no
Igor, and in this repository, whose open OpenSpec changes, such as this one
and the inquisitor change, cite each other's requirements. Igor adds what
needs its loop: builders claiming work in the order, and gate two waiting
on the changes before it.

- *Recorded:* Rejected, *Building the order only as an Igor role*.
- *Recorded:* Rejected, *Naming it stacker*.

### The script is Python

**The script is Python, checked by `pyright --strict`,** since it is glue
over `gh`, `git` and the OpenSpec CLI, and data work on what they return.

- *Recorded:* Rejected, *Writing the script in shell or TypeScript*.

### The rules are read from the changes' files, with no model

**Modifies, cites, copy duties and cycles come from the open changes' files,
read through the OpenSpec CLI, and the same inputs give the same text.** A
deterministic order means any two callers agree, and a reviewer can check
a reason against the files it names. spec-check and spec-trace read
OpenSpec through the same CLI, so an OpenSpec release that changes its
format makes all three fail their tests, rather than leaving one of them
silently wrong.

- *Ruled out by a scenario:* a model choosing the rule-decided places
  (*The same inputs give the same order whoever runs the script*).
- *Recorded:* Rejected, *Parsing OpenSpec's markdown directly*.

A citation is a requirement's full title appearing verbatim in another
change's files. Titles in this repository's specs are whole sentences, so
a verbatim match rarely fires by chance, and spec authors already cite a
requirement by its title in italics. A copy duty sets no edge, because
either of the two changes may archive first, as long as the second carries
the first one's new scenarios. The script names the change that owes the
copy: the later of the two in the order.

### Cycles go to a person

**A cycle is reported as a question and its place left unchosen,** because
whichever member archives first cites a requirement not yet in force, and
only a person may accept that gap (igor#231, decision 3). Once a person
chooses, the chosen member's reason links the answer.

- *Ruled out by a scenario:* choosing by number or age (*A cycle is asked
  about, never chosen*).

### The model step runs only where a model is available

**The model step runs in a session through the agent running the skill, and
in CI only where the repository opts in.** The deterministic part always
runs and needs no secret. The order says plainly which pairs of changes
the model step did not check, and never treats them as checked. The names
both changes' `tasks.md` files hold point the model at the pairs worth
reading.

The script accepts from the model step only edges between items, each with
a reason. A model misled by a pull request's text can then at most add a
wrong recommendation, which a person reverses after reading its reason. In
CI, the model step runs with read-only access, and only the script, at the
commit the workflow pins, writes.

- *Ruled out by a scenario:* requiring a model for every run (*The
  workflow's deterministic part needs no secret*).
- *Ruled out by a scenario:* presenting unchecked code dependencies as
  checked (*The order says plainly what it did not check*).
- *Recorded:* Constraint, *A model step misled by a pull request's text can
  add a wrong code edge to the order*.

### One issue holds the order; each item holds its own block

**The whole order is in one issue's body, and each item's body holds a block
giving its place, between markers the script owns, never in a comment**
(igor#231, decision 1). `gh issue view` and `gh pr view` print the body
without comments, so an order kept in comments is invisible to the default
read. A block is rewritten only when the order or its reasons change
(igor#231, decision 2), so a watcher is notified only of a real move. The
script touches nothing outside its markers, so a person may keep their own
text in the same body.

- *Ruled out by a scenario:* keeping the order in comments (*The whole
  order lives in one issue's body*).
- *Ruled out by a scenario:* stamping each block with the date of the last
  run (*A block is rewritten only when the order or its reasons change*).

### Without OpenSpec, explicit links and overlapping files

**A repository without OpenSpec gets an order from explicit links and
overlapping files, and the order says dependencies between requirements
were not checked** (#43). Overlapping files give merge waits, so each later
pull request rebases once, onto the one merged before it, rather than after
every merge. A merge wait follows the order the other rules and the
tiebreak give, and never changes it.

### Reviewers

**The order's issue names each reviewer's next review, ranking first the
pull request that the most items come after,** because review time usually
limits how fast a team ships (igor#231, decision 4). Reviewers are the list
the caller passes, such as an Igor's `reviewers`; with none, each pull
request's requested reviewers; and when it requests no one, the CODEOWNERS
file (#43). A draft is not offered for review, since its author has not
handed it over yet.

### It recommends and never merges

**The sequencer recommends a merge order and never merges, approves or
closes anything** (igor#231, decision 5). A person approves and merges every
pull request.

- *Ruled out by a scenario:* merging the first approved pull request (*The
  sequencer recommends a merge order and never merges*).

### Judgement questions go through the inquisitor

**A question of judgement goes through the inquisitor skill as a question
the sequencer requires a person to decide** (#43). The inquisitor has four
filters, which stop a question before a person sees it: 1, already
answered; 2, deferrable; 3, not a real question; 4, cheap to reverse. A
question another skill requires a person to decide skips filters 2 to 4
(the inquisitor's *A question another skill requires skips filters 2 to
4*), since those let an agent defer or decide the question itself. In a
session the question is asked through the picker. In CI it is posted once
on the order's issue, where the person's answer session, the inquisitor's
view for answering the questions asked of them, shows it (the answer
session's *A question asked of the person comes from one of four
sources*). Until it is answered, the order shows the question and leaves
that place unchosen.

- *Recorded:* Constraint, *An answer to a judgement question, or an edit to
  a body's `Depends on` line, waits for the next run to change the order,
  up to a day*.

### The CI workflow

**`setup-ci` writes the workflow template and never overwrites a copy
already there; `--force` replaces it** (#43), as spec-check's `setup-ci`
does. The template triggers on issues opened, pull requests opened, pushes
to an open pull request's branch, merges, and a daily run (igor#231,
decision 6), in one `concurrency` group so two runs never edit the same
body at once.

The template uses `pull_request_target`, because a `pull_request` run for a
fork's pull request gets a read-only token, which cannot edit that pull
request's body. A `pull_request_target` run holds a write token, so it
reads each pull request's change files as data, through `git fetch` of its
head and the OpenSpec CLI, and never checks out or runs its code. The
repository's choice of model step is written into the template by
`setup-ci --model-step`, so changing it is a reviewed change to the
workflow file.

- *Ruled out by a scenario:* overwriting a customised workflow (*The setup
  command writes the CI workflow and never overwrites it*).
- *Ruled out by a scenario:* checking out a pull request's head with a write
  token (*The workflow runs no code from a pull request*).
- *Recorded:* Constraint, *A `publish` run in a session can race the
  workflow's run, and the later write wins until the next run*.

## Risks / Trade-offs

- **A wrong edge from a verbatim title match.** A short title could appear
  in another change's prose by chance. The reason names the title, so a
  reviewer sees it at once.
- **A large repository's first publish edits many bodies.** Each item gets
  one edit, and later runs edit only blocks whose text changes.

## Open Questions

Each of these is a design question #43 does not answer. The spec follows
the recommendation, and each entry names the requirements to change if
Adam decides otherwise.

- **Where a person's answer to a judgement question is recorded, and how a
  run with no model checks it before asking again.** The inquisitor's
  filter 1 prints search hits for a model to judge, and a CI run with no
  credential has no model. The inquisitor records a repository's answers
  in files committed with the work, and no branch exists for the order's
  issue to commit an answer file to. *Recommended:* the order's issue body
  keeps a list of decided cycles, each naming the member chosen first and
  linking the answer. The question offers each member as an option
  labelled `#<n> first`. A run counts as the answer a later comment on the
  order's issue whose text starts with one of those labels, from a person
  with write access or from their relay App, the bot that posts a person's
  answers from their answer session, after its `User says: ` line. In a
  session, the agent records the picker's answer with `publish --decide`.
  The sequencer checks that list before asking, as filter 1 checks for an
  earlier answer, so a decided cycle is not asked again. Built on it: *A
  cycle a person has decided is ordered as decided*, *A person's choice in
  a cycle is read from the order's issue*.
- **Which issues the order holds.** Every open issue in a large repository
  would get a block, most with no rule placing them. *Recommended:* every
  open pull request, and each issue that an explicit link or a closing
  reference connects to another item. Built on it: *The order holds every
  open pull request and the issues linked to the work*.
- **Whether explicit links and overlapping files also apply where OpenSpec
  changes exist.** #43 decides them for a repository without OpenSpec.
  *Recommended:* yes, in every repository, since an OpenSpec repository
  still has issues with no change yet and code pull requests that overlap.
  Built on it: *Explicit links order the items they connect*, *Pull
  requests that change the same files merge one after another*.
- **How items the rules leave unordered are placed.** The order needs a
  deterministic tiebreak, and igor#231's decision 3 names "a choice between
  two changes the rules leave unordered" as a move needing judgement.
  *Recommended:* the lowest number goes first, with no question, for every
  caller, Igor's Sequencer included, since nearly every pair is unordered
  and a wrong guess is cheap to reverse; only cycles are asked. This reads
  decision 3 as asking only about cycles, which Adam would need to confirm.
  Built on it: *Items no rule orders keep the order they were opened in*.
- **How the script finds the order's issue.** igor#231 leaves open whether
  `igor init` creates it or the config names it. *Recommended:* the one open
  issue labelled `sequencer`, which `publish` creates when none is open, so
  `igor init` can create it by the same label. Built on it: *The whole order
  lives in one issue's body*.
- **Whether model-step edges outlast a run that cannot run the model step,
  and how a stale result is refused.** Otherwise a CI run with no
  credential would erase, at the next merge, what a session's model step
  found. For Igor mode, igor#231 recommends that the order carry a hash of
  its inputs; Adam has not ruled on it. *Recommended:* for every caller,
  the edges file carries the inputs hash `order` printed, and `publish`
  refuses it when the inputs it reads hash differently. The order records,
  with each code edge, one hash for each of the two changes' files, and
  keeps the edge while both match. Built on it: *A code edge is kept while
  both changes it joins are unchanged*.

### Facts measured before building

Each bullet says what the spec does if the fact is false.

- **GitHub's "blocked by" relations can be read through its API with the
  workflow's token** (task 0.1). If not, the order reads only `Depends on`
  lines and says that blocked-by relations were not read.
- **A `pull_request_target` run's token can edit the body of a pull request
  from a fork** (task 0.2). If not, a fork's pull request is placed but gets
  no block, which *An item the script cannot edit is named, not skipped
  silently* covers.
- **`openspec show --json` gives each delta's operation and title for a
  change read outside a checkout** (task 0.3), as spec-check relies on. If
  it needs a checkout, the script reads each head into a scratch worktree
  of the default branch's clone, still running none of its code.
