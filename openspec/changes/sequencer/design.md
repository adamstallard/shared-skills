The sequencer is a skill that recommends the order in which a repository's
open work is specified, implemented, reviewed and merged. Shared-skills
issue #43 decides what it does. adamstallard/igor#231 decides how the order
is kept and published, and the skill follows those decisions.

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
- `publish [--code-edges FILE] [--decide '#<n> first' --by <login>]
  [--reviewers <login>,...]`
  computes the order and edits the order's issue and the items' bodies. It
  takes the model step's edges from `FILE`, which carries the inputs hash
  `order` printed, and records a person's choice in a cycle given with
  `--decide`. A caller with its own reviewer list passes it with
  `--reviewers`.
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

Each entry states the decision and its reasons. An alternative not taken
that a test can check is marked ***Ruled out by a scenario***, naming the
requirement whose scenario it would fail. The capability's decision record,
`openspec/specs/sequencer/decisions.md`, holds three kinds of entry: a
constraint no test can check, an alternative no requirement guards against,
and a requirement's reason that rests on evidence (a failure, a measurement
or an outside fact). A reason with no such evidence stays here, in
design.md.

### A skill, with Igor's role as one caller

**The rules and the script live in a shared-skills skill; Igor's Sequencer
role is one caller of it,** as Igor's inquisitor role calls the inquisitor
skill (igor#231, decision 9). Igor adds what only a running Igor can do:
builders claiming work in the order, and gate two waiting on the changes
before it.

### The script is Python

**The script is Python, checked by `pyright --strict`,** since it is glue
over `gh`, `git` and the OpenSpec CLI, and data work on what they return.

### The rules are read from the changes' files, with no model

**Modifies, cites, copy duties and cycles come from the open changes' files,
read through the OpenSpec CLI, and the same inputs give the same text.** A
deterministic order means any two callers agree, and a reviewer can check
a reason against the files it names.

- *Ruled out by a scenario:* a model choosing the rule-decided places
  (*The same inputs give the same order whoever runs the script*).

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

**The order's issue body keeps the list of decided cycles, and the
sequencer checks that list before asking,** as the inquisitor's filter 1,
already answered, checks for an earlier answer. So a decided cycle is not
asked again. A run with no model can judge no free-text answer, so each
question offers its members as options labelled `#<n> first`. A run counts
a comment on the order's issue as the answer when it was posted after the
cycle's question and starts with one of those labels. The comment must
come from a person with write access, or from their relay App, the bot
that posts a person's answers for them; for a relay App, only the text
after its `User says: ` line is read. In a session, the agent records the
answer the person gave through the picker, the host's question tool, with
`publish --decide`.

The decided cycles are kept in the order's issue rather than in a committed
file, as the inquisitor keeps a repository's answers, because the order's
issue has no branch to commit a file to.

- *Ruled out by a scenario:* choosing by number or age (*A cycle is asked
  about, never chosen*).

### The model step runs only where a model is available

**The model step runs in a session through the agent running the skill, and
in CI only where the repository opts in.** The deterministic part always
runs and needs no secret. The order says plainly which pairs of changes
the model step did not check, and never treats them as checked. The names
both changes' `tasks.md` files hold point the model at the pairs worth
reading. In CI, the model step runs with read-only access. Only the
script edits the order's issue and the items' bodies, and the workflow runs
it from the shared-skills commit it pins, so no pull request can change the
code that edits.

- *Ruled out by a scenario:* requiring a model for every run (*The
  workflow's deterministic part needs no secret*).
- *Ruled out by a scenario:* presenting unchecked code dependencies as
  checked (*The order says plainly what it did not check*).

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

### Explicit links and overlapping files, in every repository

**Explicit links and overlapping files order work in every repository,
whether or not it has OpenSpec changes,** since an OpenSpec repository
still has issues with no change yet and code pull requests that overlap. A
repository without OpenSpec gets its order from them alone, and the order
says dependencies between requirements were not checked (#43). Overlapping files give merge waits, so each later
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

### Which issues the order holds

**The order holds every open pull request, and only the issues that an
explicit link, or a closing reference such as a pull request's `Fixes #n`,
connects to another item.** Every
open issue in a large repository would otherwise get a block, most with no
rule placing them.

### Items no rule orders go lowest number first, unasked

**Among items no rule orders, the lowest number goes first, and nobody is
asked, for every caller, Igor's Sequencer included.** The order needs a
deterministic tiebreak, nearly every pair of items is unordered, and a
wrong guess is cheap to reverse. igor#231's decision 3 sends only a
cycle's order to a person, and says that items the rules leave unordered go
lowest number first, unasked.

- *Ruled out by a scenario:* asking a person about each unordered pair
  (*Items no rule orders keep the order they were opened in*).

### The order's issue is found by its label

**The order's issue is the one open issue labelled `sequencer`.** `publish`
creates it when none is open, and refuses, naming both, when there are
two. `igor init`, or a person, can then make one by adding the label, and
no configuration names it.

### Code edges outlast runs with no model

**The order's issue body stores each model-step edge with one hash for each
of the two changes it joins, of that change's files, and a later run keeps
the edge while both hashes match.** These per-change hashes keep the order
steady between a Sequencer Igor's runs where the repository hands it the
model step. A CI run with no model, after a merge, keeps the code edges
the Igor found for the changes the merge left unchanged.

**An edges file also carries the inputs hash, a hash of everything `order`
read to compute the order it was built from, and `publish` refuses the
file when the inputs it reads hash differently.** This stops a result
computed before a merge from overwriting the order computed after it. Any
change to the inputs, such as a newly opened issue, makes a file stale, and
the model step runs again on the new order. Both hashes adopt igor#231's
hash recommendation for every caller.

### Three ways Igor uses the skill

**An Igor uses the skill in three ways, and the skill expects of each only
what it expects of any caller:**

- An Igor's worker may run the skill in its own session, as any agent
  does. A worker's session has no person in it, so it asks a judgement
  question in its handback comment, the comment in which its Igor hands
  the item back to a person, as the inquisitor's *A session with no person
  in it asks in a post, a handback or nowhere* says.
- Igor's Sequencer role calls the script, passing the reviewers its
  configuration lists. Igor's work triage, the step where an Igor chooses
  which items to take, reads positions from `order --json`.
- Where a repository hands the model step to an Igor, `publish`, run by
  the workflow, labels the order's issue `sequencer: check code`. A
  Sequencer Igor then runs the model step and publishes its edges through
  the script.

What Igor builds for these, such as claiming the labelled issue, editing a
body from its loop and gating gate two on the order, is igor#231's.

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

### The CI workflow

**`setup-ci` writes the workflow template and never overwrites a copy
already there; `--force` replaces it** (#43), as spec-check's `setup-ci`
does. The template triggers on issues opened, pull requests opened, pushes
to an open pull request's branch, merges, and a daily run (igor#231,
decision 6), in one `concurrency` group so two runs never edit the same
body at once.

The template uses `pull_request_target` (the decision record's *Rejected:
Running the workflow on `pull_request`* says why). A `pull_request_target`
run holds a write token, which a pull request's code could misuse, so the
run reads each pull request's change files as data, through `git fetch` of its
head and the OpenSpec CLI, and never checks out or runs its code. The
repository's choice of model step is written into the template by
`setup-ci --model-step`, so changing it is a reviewed change to the
workflow file.

- *Ruled out by a scenario:* overwriting a customised workflow (*The setup
  command writes the CI workflow and never overwrites it*).
- *Ruled out by a scenario:* checking out a pull request's head with a write
  token (*The workflow runs no code from a pull request*).

## Risks / Trade-offs

- **A wrong edge from a verbatim title match.** A short title could appear
  in another change's prose by chance. The reason names the title, so a
  reviewer sees it at once.
- **A large repository's first publish edits many bodies.** Each item gets
  one edit, and later runs edit only blocks whose text changes.

## Open Questions

No design question is open. Three facts are measured before building.

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
