# Sequencer

Builds on: inquisitor (adamstallard/shared-skills#25)

## Why

When several changes are open at once, someone has to work out which to
specify, build, review and merge first, and agents work it out again by
hand in each session. In adamstallard/igor#204, one archive order for 23
changes, the order in which their OpenSpec changes are archived into the
main specs, took about a week of edits by agents and Adam, and nothing checks
that such a list still matches the changes it orders. Most repositories
that need the order run no Igor, so the rules and the script belong in a
skill that any caller runs: an agent in a session, a CI workflow, or an
Igor's Sequencer role (adamstallard/igor#231).

## What Changes

- A new skill, `sequencer`, whose script computes the order from the
  repository's open pull requests, issues and OpenSpec changes, with no
  model, and gives a reason for each place a rule decides. A change that
  modifies or names another change's requirement comes after it, and an
  item comes after what GitHub's "blocked by" relations or its `Depends on`
  lines say it waits on. Where two changes modify one requirement, the
  order says which must copy the other's new scenarios before archiving.
  Pull requests that change the same files get a merge order. Items that
  wait on each other in a loop are a cycle, which a person resolves.
- One rule, that a change whose code calls another change's code is built
  after it, needs a model. That model step runs where a model is
  available, and the order says plainly when it did not run.
- The order is published in one issue's body, with a block in each ordered
  item's body, never in a comment. The order's issue also names each
  reviewer's next review. The sequencer recommends a merge order and never
  merges.
- A question of judgement, such as which change in a cycle goes first, goes
  to a person through the inquisitor skill, and the order leaves that place
  unchosen until a person answers.
- `setup-ci` writes a GitHub Actions workflow that keeps the order current.
  The repository chooses how its model step runs: not at all, with the
  repository's API key, or by an Igor.

design.md's *Decisions* gives the reason for each rule, and its *Open
Questions* lists three facts to measure before building.
`specs/sequencer/decisions.md` holds the constraints and rejected
alternatives no test can check.

An Igor uses the skill in three ways, each through the same commands as
any other caller: its worker, the agent an Igor starts to do one item, runs
it in its own session; its Sequencer role calls the script; and a
repository's workflow can hand the model step to a Sequencer Igor.

**Out of scope:** what Igor builds for its Sequencer role, igor#231: builders
claiming work in the order, an approved spec's implementation waiting on
the changes before it, and
what a Sequencer Igor needs to run the model step.

## Capabilities

### New Capabilities

- `sequencer`: computing, publishing and keeping current the order of a
  repository's open work, the reviewers' next reviews, and the questions of
  judgement the order raises.

### Modified Capabilities

None.

## Impact

- New: `.agents/skills/sequencer/` with its script, its tests and the CI
  workflow template.
- The README's skills table.
- In each repository that runs it, the sequencer edits the body of the issue
  labelled `sequencer` and the bodies of the items it orders, between its
  own markers, and `setup-ci` writes `.github/workflows/sequencer.yml`.
