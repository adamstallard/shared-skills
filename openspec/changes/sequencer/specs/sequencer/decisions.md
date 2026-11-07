# sequencer: constraints and rejected alternatives

## Constraints

- **Constraint: A model step misled by a pull request's text can add a wrong code edge to the order.**
  Because: the model step reads changes' files, which anyone who opens a pull request writes, and the script accepts any edge between items that has a reason.
  Evidence: the script refuses only an edge naming no item or giving no reason (sequencer spec: *The model step orders changes whose code calls each other's code*), adamstallard/shared-skills#43
  Holds while: the model step's output is limited to edges between items, each showing its reason to a person who can reverse it.
  Paths: .agents/skills/sequencer/scripts/sequencer.py, .agents/skills/sequencer/ci/sequencer.yml

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

- **Rejected: Building the order only as an Igor role.**
  Facing: agents work out the order by hand in each session.
  Lost because: most repositories that need an order run no Igor, https://github.com/adamstallard/shared-skills/issues/43.
  Instead: a skill whose script any caller runs, with Igor's Sequencer role as one caller.
  Paths: .agents/skills/sequencer/

- **Rejected: Naming it stacker.**
  Facing: a name for the role and skill that computes the order.
  Lost because: "stacker" suggests stacked pull requests, https://github.com/adamstallard/igor/issues/231.
  Instead: sequencer.
  Paths: .agents/skills/sequencer/

- **Rejected: Parsing OpenSpec's markdown directly.**
  Facing: reading each change's deltas and requirements.
  Lost because: a format change in an OpenSpec release would break the script silently, while spec-check and spec-trace read OpenSpec only through its CLI, https://github.com/adamstallard/shared-skills/issues/43.
  Instead: the OpenSpec CLI, version 1.15.0 or later.
  Paths: .agents/skills/sequencer/scripts/sequencer.py

- **Rejected: Writing the script in shell or TypeScript.**
  Facing: a language for glue over `gh`, `git` and the OpenSpec CLI, and data work on what they return.
  Lost because: this repository's scripts that hold logic, such as spec-check's and spec-trace's, are Python, and shell is kept for wiring commands together, .agents/skills/spec-check/scripts/spec_check.py.
  Instead: Python, checked by `pyright --strict`.
  Paths: .agents/skills/sequencer/scripts/
