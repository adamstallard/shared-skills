# sequencer: constraints, rejected alternatives and rationale

## Constraints

- **Constraint: A `publish` run in a session can race the workflow's run, and the later write wins until the next run.**
  Because: only the workflow's runs share a concurrency group, so nothing serialises a session's publish with them.
  Evidence: a GitHub Actions `concurrency` group serialises only that workflow's runs, https://docs.github.com/en/actions/using-jobs/using-concurrency
  Holds while: sessions and the workflow publish to the same bodies with no lock between them.
  Paths: .agents/skills/sequencer/scripts/sequencer.py

## Rejected

- **Rejected: Running the workflow on `pull_request`.**
  Facing: a trigger for the workflow's runs on pull request events.
  Lost because: a `pull_request` run for a fork's pull request gets a read-only token, which cannot edit that pull request's body, https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/events-that-trigger-workflows#workflows-in-forked-repositories.
  Instead: `pull_request_target`, reading each pull request's change files as data and running none of its code.
  Paths: .agents/skills/sequencer/ci/sequencer.yml

## Rationale

- **Rationale: The script reads OpenSpec changes only through the OpenSpec CLI.**
  If the script parsed OpenSpec's markdown itself, a release that changed the format would leave the script silently wrong. Read through the CLI, as spec-check and spec-trace read it, such a release makes all three fail their tests instead.
  Evidence: none yet; #43 records the decision without evidence, https://github.com/adamstallard/shared-skills/issues/43

- **Rationale: The model step orders changes whose code calls each other's code.**
  The model step reads changes' files, which anyone who opens a pull request writes, so text in a pull request can steer the model. If the script took whatever the model step returned, that text could steer anything the script publishes. Taking only edges between items, each with a reason, limits a misled model to adding a wrong edge for the code rule or leaving out a real one, with its reason shown. A wrong edge misplaces a recommendation and merges nothing, since the sequencer never merges.
  Evidence: OWASP ranks prompt injection first among risks to LLM applications, including indirect injection, where instructions hidden in files a model reads alter what it outputs, https://genai.owasp.org/llmrisk/llm01-prompt-injection/
