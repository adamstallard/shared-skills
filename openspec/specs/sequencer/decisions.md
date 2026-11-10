# sequencer: constraints, rejected alternatives and rationale

## Rejected

- **Rejected: Locking publishes so that only one runs at a time.**
  Facing: a session, an Igor and the CI workflow can each run `publish` against the same bodies at once.
  Lost because: a GitHub Actions `concurrency` group serialises only one workflow's runs, so it cannot hold back a session's or an Igor's publish, https://docs.github.com/en/actions/using-jobs/using-concurrency.
  Instead: the later write wins. The next run recomputes the rule-decided order; code edges written by the losing publish are lost until a model step runs again.
  Paths: .agents/skills/sequencer/scripts/sequencer.py

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

- **Rationale: The whole order lives in one issue's body.**
  A reader who opens an issue with `gh issue view`, the default, sees its title and body and none of its comments, and an agent's piped `gh issue view --comments` prints the comments without the body. An order kept in comments would be missing from the default read, and one kept in the body is missing only from the comments-only read.
  Evidence: gh's manual says `gh issue view` displays "the title, body, and other information about an issue", and that "When output is piped or redirected, only the comments are printed" with `--comments`, https://cli.github.com/manual/gh_issue_view
  Evidence: measured on 2026-11-10 UTC with gh 2.103.2, on an issue whose body is 2521 bytes and which has one comment. `gh issue view 168 --repo adamstallard/igor | wc -c` printed 2803 bytes: the title, metadata and body. `gh issue view 168 --repo adamstallard/igor --comments | wc -c` printed 164: the one comment with its author header, and no title or body, https://github.com/adamstallard/igor/issues/168

- **Rationale: A prose footer stays valid whatever the script writes between its markers.**
  The prose skill signs a posted body with a footer that is a hash of all the text above it, and its hook checks that hash before a hand-back. Without this requirement, a block the script adds or rewrites above a prose footer would change that text, and every ordered body that prose had signed would fail its check.
  Evidence: prose's `footer_hash` hashes the whole body above the footer, and `verify_post` reports "the footer does not match the text above it (edited after signing?)" when it differs, [prose.py](../../../.agents/skills/prose/scripts/prose.py)
