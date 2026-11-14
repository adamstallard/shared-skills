The sequencer is a skill that recommends the order in which a repository's
open work is specified, implemented, reviewed and merged. Shared-skills
issue #43 and adamstallard/igor#231 hold the discussion behind it.

Terms used throughout, as the spec defines them:

- **An item** is an open issue or pull request the order holds. **The
  order's issue** is the one issue whose body holds the whole order.
- **An edge** is a rule's finding that one item comes after another, with
  its reason. The rules that set edges are **modifies** (a change that
  modifies a requirement another change adds comes after it), **cites** (a
  change that names another change's requirement comes after it),
  **explicit links** (GitHub's "blocked by" relations, `Depends on #n`
  lines and a proposal's `Builds on:` lines) and the model step's rule,
  below.
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
pointed at what unblocks the most; nobody asked about a place a rule can
decide.

**Non-Goals:** merging; what Igor builds for its
Sequencer role (igor#231); the spec-checker's dry archive, which archives
every open change in the order into a scratch copy of the default branch
to prove the order applies, and which igor#231's decision 7 gives to Igor's
spec-checker.

## How the script runs

The script is `.agents/skills/sequencer/scripts/sequencer.py`. It has three
commands:

- `order [--json] [--reviewers <login>,...]` computes the order and
  prints it, with a hash of its inputs and, for each pair of open changes,
  the backticked names that appear in both changes' `tasks.md` files, to
  help the model step. `--reviewers` tries a reviewer list in place of the
  configured one. It edits nothing.
- `publish [--code-edges FILE | --model api] [--decide '#<n> first' --by <login>]`
  computes the order and edits the order's issue and the items' bodies. It
  takes the model step's checked pairs and edges from `FILE`, which carries
  the inputs hash `order` printed, or from one API call with `--model api`.
  With `--decide` it records a person's override of a cycle's order; `--by`
  names that person.
- `setup-ci [--model-step none|api-key|igor] [--lore <owner>/<repo>] [--force]`
  writes the workflow template, and with `--lore` names the team's lore
  repository in `.github/sequencer.json`.

In a session, the agent runs `order`, applies the model step to the
printed changes and names, writes its edges to a file, and runs `publish
--code-edges` with it. The CI workflow runs `publish` on each trigger,
as `publish --model api` where the repository chose to run the model step
on its own API key. Where it chose an Igor, `publish` labels the
order's issue `sequencer: check code`, and an Igor in the Sequencer role
runs the model step and dispatches the workflow with its edges file, so the
workflow publishes them.

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

### Cycles are ordered by rule, and a person may override

**A cycle's members go lowest number first, by rule, and no one is asked.**
The order is review advice that can be re-chosen at any time before a
merge, so choosing a cycle's order is cheap to reverse. Whichever member
archives first will cite a requirement that is not yet in the main specs.
Whoever archives the changes deals with that when archiving; it does not
change which to review first.

**A writer's `#<n> first` comment on the order's issue overrides the rule,**
and the order's issue keeps the list of overrides. Every run, CI's
included, counts such a comment when two things hold: it was posted after
the cycle was first listed, so an old comment about another cycle cannot
count, and an account with write access posted it or it is a relayed
answer.
Comments on an ordered item's own thread are never read. In a session, an
agent can record an override a person gives it with `publish --decide`.

A relayed answer is a `User says: ` comment that a person's relay App, the
GitHub App through which the person's answer session (the inquisitor's
view for answering questions) posts, posted for them. Which Apps
are a person's is read from their relay file, `relays/<login>.yaml` in the
team's lore repository, the repository of shared answers the inquisitor
uses, which `.github/sequencer.json` names. The script reads it through the
inquisitor's reader: from the caller's own clone of the lore repository
when it has one, through GitHub's API when it has none, as in CI, and, for
an Igor, at the last lore commit the Igor's own lore step accepted. A public lore repository needs no
setup; only a private one needs a read-only token, which `setup-ci` stores
as a secret. Without access to the lore repository, only direct comments
count, and the order's issue says so. Telling a relayed answer from a
forgery needs two facts. The inquisitor's task 0.21 measures whether
GitHub's API names the App that wrote a comment. Task 0.22 measures whether
the API finds a relay file's newest commit as git does. Relayed answers are
counted only if both hold.

- *Ruled out by a scenario:* asking a person about a cycle's order (*A
  cycle's members are ordered by rule*).

### The model step runs only where a model is available

**The model step runs in a session through the agent running the skill, and
in CI only where the repository opts in.** The deterministic part always
runs and needs no secret. The order says plainly which pairs of changes
the model step did not check, and never treats them as checked; a change
the OpenSpec CLI refuses counts as unchecked too. The names both changes'
`tasks.md` files hold point the model at the pairs worth reading. In CI,
the model step is one API call with no tools, and the script validates its
reply; the decision record's Rationale for *With an API key, the model step
is one API call with no tools* says why. Every string the script takes from
a pull request or the model is written as inline code, so a reason that
text in a pull request steered the model into writing can @-mention no
one.

- *Ruled out by a scenario:* requiring a model for every run (*The
  workflow's deterministic part needs no secret*).
- *Ruled out by a scenario:* presenting unchecked code dependencies as
  checked (*The order says plainly what it did not check*).

### One issue holds the order; each item holds its own block

**The whole order is in one issue's body, and each item's body holds a block
giving its place, between markers the script owns, never in a comment.**
The decision record's Rationale for *The whole
order lives in one issue's body* says why not a comment. A block is rewritten only when the order or its reasons change, so a
run that finds nothing new edits nothing. The script touches nothing outside its markers, so a person may keep their own
text in the same body. The prose skill ends each body it signs with a
`prose ✓` footer holding a hash of the text above it, and prose's hook
reads the footer as the body's last line. A new block goes just above that footer
so it stays last; the decision record's Rationale for *The script edits
only the text between its markers* says why the footer's stale hash is
harmless.

- *Ruled out by a scenario:* keeping the order in comments (*The whole
  order lives in one issue's body*).
- *Ruled out by a scenario:* stamping each block with the date of the last
  run (*A block is rewritten only when the order or its reasons change*).

### Explicit links and overlapping files, in every repository

**Explicit links and overlapping files order work in every repository,
whether or not it has OpenSpec changes,** since an OpenSpec repository
still has issues with no change yet and code pull requests that overlap.
A proposal's `Builds on:` line is an explicit link too, since this
repository declares a stacked change's dependency there, and a stacked
change that cites none of its dependency's requirements would otherwise
get no edge from it. A
repository without OpenSpec gets its order from them alone, and the order
says dependencies between requirements were not checked. Overlapping files
give merge waits: each later pull request waits for the earlier one that
shares its files, and rebases once, onto it, rather than after every
merge. A merge wait follows the order the other rules and the
tiebreak give, and never changes it.

### Only writers' edges count

**An edge counts only when every item whose text sets it was opened by an
account with write access; the order's issue lists the others as not
counted.** Otherwise anyone who can open a pull request or an issue could
steer the order. An outsider could add a requirement whose title copies a
sentence already in a writer's change, which makes the writer's change
cite it. If the outsider's change also cites one of the writer's
requirements, the two form a cycle, and lowest number first may then put
the outsider's change first. Issues saying `Depends on #<n>` raise #n
in every reviewer's queue. Listing the uncounted edges lets a writer see
one worth keeping and set it again in their own item.

### Reviewers

**The order's issue names each reviewer's next review, ranking first the
pull request that the most items come after,** because reviewing it
unblocks the most work. Reviewers are the
`reviewers` list in the repository's `.github/sequencer.json`; with none,
everyone each pull request has requested on GitHub, including anyone
GitHub dropped from its request list when they submitted a review; and
when it has requested no one, the CODEOWNERS file. Every caller takes reviewers through this chain,
and `publish` accepts no reviewer list of its own, so a session and the CI
workflow publish the same issue body for the same inputs. A draft is not offered
for review, since its author has not handed it over yet.

A spec pull request ranks ahead of the pull requests that come after it.
Ranking by how many items come after each pull request already gives
that order: every item after a later pull request is also after the
spec, and the spec has that pull request after it too, so the spec's
count is always higher. *A spec pull request is reviewed before the
implementations that build on it* states the order outright, so that a
later change to the ranking keeps it. A pull request leaves a reviewer's
queue once they review its current head, which each review's
`commit_id`, the commit it was made on, shows, and returns when a push
moves the head.

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
wrong guess is cheap to reverse.

- *Ruled out by a scenario:* asking a person about each unordered pair
  (*Items no rule orders keep the order they were opened in*).

### The order's issue is found by its label

**The order's issue is the one open issue labelled `sequencer`.** `publish`
creates it when none is open, and refuses, naming both, when there are
two. A person with write access, or `igor init` running under such a
person's login, can also make one by adding the label, and no
configuration names it. The script refuses a labelled issue whose author
lacks write access; the decision record's Rationale for *The whole order
lives in one issue's body* says why.

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
the model step runs again on the new order.

### Three ways Igor uses the skill

**An Igor uses the skill in three ways, and the skill expects of each only
what it expects of any caller:**

- An Igor's worker may run the model step in its own session, on the
  `order --json` output its Igor passes it, since a worker has no GitHub
  credential of its own to run `order` with.
- An Igor in the Sequencer role, a Sequencer Igor, runs `order`, which
  takes reviewers as *Reviewers* above says for any caller, and publishes
  only by dispatching the workflow (`workflow_dispatch`). Its writes then
  share the workflow's `concurrency` group, so two runs never race to edit
  one body, as igor#231's decision 6 requires. Igor's work triage, the step
  where an Igor chooses which items to take, reads positions from
  `order --json`.
- Where a repository hands the model step to an Igor, `publish`, run by
  the workflow, labels the order's issue `sequencer: check code`. A
  Sequencer Igor then runs the model step and dispatches the workflow with
  its edges file.

What Igor builds for these, such as claiming the labelled issue,
dispatching the workflow from its loop and gating gate two on the order,
is igor#231's.

### It recommends and never merges

**The sequencer recommends a merge order and never merges, approves or
closes anything;** the decision record's Rationale for *The sequencer
recommends a merge order and never merges* says why.

- *Ruled out by a scenario:* merging the first approved pull request (*The
  sequencer recommends a merge order and never merges*).

### The CI workflow

**`setup-ci` writes the workflow template and never overwrites a copy
already there; `--force` replaces it,** as spec-check's `setup-ci`
does. The template triggers on every event that can change the order:
issues opened, edited, closed or commented on; pull requests opened,
edited, marked ready, reviewed or closed, merged or not; pushes to an open
pull request's branch; a Sequencer Igor's dispatch; and a daily run. All share one `concurrency` group,
so no two workflow runs edit the same body at once.

The template uses `pull_request_target`, and reads each pull request's
change files through `git fetch` of its head and the OpenSpec CLI, never
running them. `openspec/specs/sequencer/decisions.md` gives the reasons
for both choices: *Rejected: Running the workflow on `pull_request`*, and
the Rationale for *The workflow runs no code from a pull request*. The
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

- **Whether relayed overrides stay.** A relay App posts only an answer to
  a question that the person's answer session showed them, in that
  question's thread. The sequencer asks no question, so nothing puts a
  cycle in front of an answer session, and relayed overrides may never
  arrive unless something shows the cycle to it, such as a mention of the
  person or an assignment.
- **A private lore repository named in a public repository.**
  `.github/sequencer.json`, committed to a public repository, would name a
  private lore repository, and the order's issue line `Relayed answers were
  not read: <reason>` may too. The inquisitor's *A log or miss file is as
  private as its more private repository* forbids moving what concerns one
  repository to a place more people can see.

Tasks 0.1 to 0.6 measure six facts before building, listed below. The
last bullet of that list holds facts the inquisitor's tasks 0.21 and 0.22
measure, which relayed answers wait on.

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
  it needs a checkout, the script writes each head's change files, read
  with `git show`, into a scratch directory laid out as an `openspec/`
  tree and runs the CLI there.
- **A run on a review of a fork's pull request can edit bodies** (task
  0.4). Reviews trigger through `pull_request_review`, which for a fork's
  pull request may get a read-only token. If so, that run publishes
  nothing, and the next run with a write token, at the latest the daily
  one, publishes the order.
- **An edges file fits in a `workflow_dispatch` input** (task 0.5). If
  one can exceed GitHub's limit, a Sequencer Igor sends its edges in
  several dispatches, each a whole edges file for the same inputs hash.
- **A workflow's own token can read another account's permission and a
  CODEOWNERS team's members** (task 0.6). If it cannot read permissions,
  `setup-ci` stores a read-only token that can, as for a private lore
  repository; if it cannot expand a team, the team counts as one
  reviewer, with one next review.
- **GitHub's API names the App that wrote a comment, and finds a relay
  file's newest commit as git does** (the inquisitor's tasks 0.21 and
  0.22). Relayed answers are not counted, and no lore token is set up,
  until both are measured. If either fact is false, the repository's
  owner decides what to build, as the task that measured it says.
