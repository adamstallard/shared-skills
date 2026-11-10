# sequencer: constraints, rejected alternatives and rationale

## Constraints

- **Constraint: An answer to a judgement question, or an edit to a body's `Depends on` line, waits for the next run to change the order, up to a day.**
  Because: the workflow's triggers are the events igor#231 decision 6 lists, and a comment or a body edit is none of them.
  Evidence: issue and pull request openings, pushes, merges and a daily run are the decided triggers, https://github.com/adamstallard/igor/issues/231
  Holds while: the workflow runs on those triggers alone.
  Paths: .agents/skills/sequencer/ci/sequencer.yml

- **Constraint: A `publish` run in a session can race the workflow's run, and the later write wins until the next run.**
  Because: only the workflow's runs share a concurrency group, so nothing serialises a session's publish with them.
  Evidence: a GitHub Actions `concurrency` group serialises only that workflow's runs, https://docs.github.com/en/actions/using-jobs/using-concurrency
  Holds while: sessions and the workflow publish to the same bodies with no lock between them.
  Paths: .agents/skills/sequencer/scripts/sequencer.py

## Rejected

- **Rejected: Naming it stacker.**
  Facing: a name for the role and skill that computes the order.
  Lost because: "stacker" suggests stacked pull requests, https://github.com/adamstallard/igor/issues/231.
  Instead: sequencer.
  Paths: .agents/skills/sequencer/

- **Rejected: Running the workflow on `pull_request`.**
  Facing: a trigger for the workflow's runs on pull request events.
  Lost because: a `pull_request` run for a fork's pull request gets a read-only token, which cannot edit that pull request's body, https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/events-that-trigger-workflows#workflows-in-forked-repositories.
  Instead: `pull_request_target`, reading each pull request's change files as data and running none of its code.
  Paths: .agents/skills/sequencer/ci/sequencer.yml

- **Rejected: Writing the script in shell or TypeScript.**
  Facing: a language for glue over `gh`, `git` and the OpenSpec CLI, and data work on what they return.
  Lost because: this repository's scripts that hold logic, such as spec-check's and spec-trace's, are Python, and shell is kept for wiring commands together, [spec_check.py](../../../.agents/skills/spec-check/scripts/spec_check.py).
  Instead: Python, checked by `pyright --strict`.
  Paths: .agents/skills/sequencer/scripts/

## Rationale

- **Rationale: The same inputs give the same order whoever runs the script.**
  One script computes the order for every caller, rather than an Igor role alone, so a session, a CI workflow and an Igor all get the same order. Built only as an Igor role, the order would reach no repository that runs no Igor, and agents there would go on working it out by hand in each session.
  Evidence: none yet; #43 asserts that most repositories that need an order run no Igor, without support, https://github.com/adamstallard/shared-skills/issues/43

- **Rationale: The script reads OpenSpec changes only through the OpenSpec CLI.**
  If the script parsed OpenSpec's markdown itself, a release that changed the format would leave the script silently wrong. Read through the CLI, as spec-check and spec-trace read it, such a release makes all three fail their tests instead.
  Evidence: none yet; #43 records the decision without evidence, https://github.com/adamstallard/shared-skills/issues/43

- **Rationale: The model step orders changes whose code calls each other's code.**
  The model step reads changes' files, which anyone who opens a pull request writes, so a pull request's text can mislead it into adding a wrong code edge or leaving out a real one. Because the script takes only edges between items, each with a reason, a misled model can change nothing but code edges, and each edge it adds shows its reason to a person who can reverse it.
  Evidence: none yet; neither the spec nor #43 gives any, https://github.com/adamstallard/shared-skills/issues/43
