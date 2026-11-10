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
  Evidence: OpenSpec's own reading of the same markdown changed in both 1.16 releases, which a hand-written reader would have had to track. In 1.16.0, a line beginning with inline code written in triple backticks (```` ```npm test``` ````) stopped being read as the opening of a code fence, which had hidden every requirement after it, https://github.com/Fission-AI/OpenSpec/releases/tag/v1.16.0 (Fission-AI/OpenSpec#2131)
  Evidence: in 1.16.1, section headings with a closing `#` run, such as `## ADDED Requirements ##`, began to be read the same as unclosed ones (Fission-AI/OpenSpec#2205), and a requirement under an unrecognized `## … Requirements` section, once silently dropped, began to be refused (Fission-AI/OpenSpec#2207), https://github.com/Fission-AI/OpenSpec/blob/main/CHANGELOG.md#1161

- **Rationale: The model step orders changes whose code calls each other's code.**
  This explains the requirement's limit on what the script takes from the model step: only edges between items, each with a reason. The model step reads changes' files, which anyone who opens a pull request writes, so text in a pull request can steer the model. If the script took whatever the model step returned, that text could steer anything the script publishes. With the limit, a misled model can only add a wrong code-calls-code edge or leave out a real one, and write each edge's reason. A wrong edge misplaces a recommendation and merges nothing, since the sequencer never merges. The script does not limit a reason's text, so a misled model's reason could carry mentions or links into every body that shows the edge.
  Evidence: OWASP ranks prompt injection first among risks to LLM applications, including indirect injection, where instructions hidden in files a model reads alter what it outputs, https://genai.owasp.org/llmrisk/llm01-prompt-injection/

- **Rationale: The workflow runs no code from a pull request.**
  The template triggers on `pull_request_target`, whose runs hold a token that can write to the repository, and the repository's secrets. Code from a pull request's head, run in such a run, would get both, so anyone who opens a pull request, from a fork included, could write to the repository or read its secrets.
  Evidence: GitHub Security Lab shows that a `pull_request_target` workflow has write permission and secrets, and that checking out and building an untrusted pull request in one lets its author run code with them, https://securitylab.github.com/resources/github-actions-preventing-pwn-requests/
