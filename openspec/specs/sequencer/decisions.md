# sequencer: constraints, rejected alternatives and rationale

## Rejected

- **Rejected: Serialising a session's publish with the workflow's runs through an Actions concurrency group.**
  Facing: a person's session and the CI workflow can each run `publish` against the same bodies at once.
  Lost because: a session's publish is no GitHub Actions run, and GitHub's docs describe a `concurrency` group as holding back only Actions jobs and workflow runs, https://docs.github.com/en/actions/using-jobs/using-concurrency.
  Instead: the later write wins. The next run recomputes the rule-decided order. What only the losing publish wrote is lost until it is published again: its code edges until a model step runs, and its ask mark or recorded choice until the session publishes it again. A Sequencer Igor publishes only by dispatching the workflow, so its writes share the workflow's group.
  Paths: .agents/skills/sequencer/scripts/sequencer.py

- **Rejected: Running the workflow on `pull_request`.**
  Facing: a trigger for the workflow's runs on pull request events.
  Lost because: a `pull_request` run for a fork's pull request gets a read-only token, which cannot edit that pull request's body, https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/events-that-trigger-workflows#workflows-in-forked-repositories.
  Instead: `pull_request_target`, reading each pull request's change files as data and running none of its code. `pull_request_target` has no activity type for a submitted review (same page, https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/events-that-trigger-workflows#pull_request_target), so review events come through `pull_request_review`, whose run for a fork's pull request may get a read-only token and publish nothing; the next run with a write token publishes the order.
  Paths: .agents/skills/sequencer/ci/sequencer.yml

## Rationale

- **Rationale: The script reads OpenSpec changes only through the OpenSpec CLI.**
  If the script parsed OpenSpec's markdown itself, a release that changed the format would leave the script silently wrong. Read through the CLI, as spec-check and spec-trace read it, such a release makes all three fail their tests instead.
  Evidence: OpenSpec's own reading of the same markdown changed in both 1.16 releases, which a hand-written reader would have had to track. In 1.16.0, a line beginning with inline code written in triple backticks (```` ```npm test``` ````) stopped being read as the opening of a code fence, which had hidden every requirement after it, https://github.com/Fission-AI/OpenSpec/releases/tag/v1.16.0 (Fission-AI/OpenSpec#2131)
  Evidence: in 1.16.1, section headings with a closing `#` run, such as `## ADDED Requirements ##`, began to be read the same as unclosed ones (Fission-AI/OpenSpec#2205), and a requirement under an unrecognized `## … Requirements` section, once silently dropped, began to be refused (Fission-AI/OpenSpec#2207), https://github.com/Fission-AI/OpenSpec/blob/main/CHANGELOG.md#1161

- **Rationale: The model step orders changes whose code calls each other's code.**
  This explains the requirement's limit on what the script takes from the model step: only edges between items, each with a reason. The model step reads changes' files, which anyone who opens a pull request writes, so text in a pull request can steer the model. If the script took whatever the model step returned, that text could steer anything the script publishes. With the limit, a misled model can only add a wrong code-calls-code edge or leave out a real one, and write each edge's reason. A wrong edge misplaces a recommendation and merges nothing, since the sequencer never merges. A reason is written as inline code (*Text from a pull request or the model is written inert*), so a misled model's reason renders no mention or link.
  Evidence: OWASP ranks prompt injection first among risks to LLM applications, including indirect injection, where instructions hidden in files a model reads alter what it outputs, https://genai.owasp.org/llmrisk/llm01-prompt-injection/

- **Rationale: With an API key, the model step is one API call with no tools.**
  The model step reads changes' files, which anyone who opens a pull request writes, so that text can steer the model. A model can act only through the tools a request offers it: with none offered, a steered model can only return text, and the script takes from that text no more than validated edges. Run as an agent with tools, the same model could be steered into running commands or making requests with the run's credentials.
  Evidence: Anthropic's tool-use documentation says Claude calls functions "that you define or that Anthropic provides", returning "a structured call that your application runs (client tools) or that Anthropic runs (server tools)", https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview
  Evidence: OWASP ranks prompt injection first among risks to LLM applications, including indirect injection through files a model reads, https://genai.owasp.org/llmrisk/llm01-prompt-injection/

- **Rationale: The workflow runs no code from a pull request.**
  The template triggers on `pull_request_target`, whose runs hold a token that can write to the repository, and the repository's secrets. Code from a pull request's head, run in such a run, would get both, so anyone who opens a pull request, from a fork included, could write to the repository or read its secrets.
  Evidence: GitHub Security Lab shows that a `pull_request_target` workflow has write permission and secrets, and that checking out and building an untrusted pull request in one lets its author run code with them, https://securitylab.github.com/resources/github-actions-preventing-pwn-requests/

- **Rationale: The whole order lives in one issue's body.**
  A reader who opens an issue with `gh issue view`, the default, sees its title and body and none of its comments, and an agent's piped `gh issue view --comments` prints the comments without the body. An order kept in comments would be missing from the default read, and one kept in the body is missing only from the comments-only read.
  The order's issue is used only when its author has write access, because the issue's author can edit its body whatever their access, and so could rewrite the decided cycles and stored code edges kept there.
  Evidence: gh's manual says `gh issue view` displays "the title, body, and other information about an issue", and that "When output is piped or redirected, only the comments are printed" with `--comments`, https://cli.github.com/manual/gh_issue_view
  Evidence: measured on 2026-11-10 UTC with gh 2.103.2, on an issue whose body is 2521 bytes and which has one comment. `gh issue view 168 --repo adamstallard/igor | wc -c` printed 2803 bytes: the title, metadata and body. `gh issue view 168 --repo adamstallard/igor --comments | wc -c` printed 164: the one comment with its author header, and no title or body, https://github.com/adamstallard/igor/issues/168
  Evidence: GitHub's REST documentation for updating an issue says "Issue owners and users with push access or Triage role can edit an issue", https://docs.github.com/en/rest/issues/issues#update-an-issue
  Evidence: GitHub's table of repository roles gives "Edit anyone's issue titles and bodies" to the Moderate, Write, Maintain and Admin roles, and not to Read or Triage, so of those without write access only the issue's author can edit its body, https://docs.github.com/en/organizations/managing-user-access-to-your-organizations-repositories/managing-repository-roles/repository-roles-for-an-organization

- **Rationale: The script edits only the text between its markers.**
  A new block goes above the prose skill's `prose ✓` footer and changes the text that footer hashes, so the footer stops matching. That is harmless. The only posted body prose's hook fetches is a pull request's, when an agent hands the pull request back for review, and it reads only whether the footer says the body's cold read was put off until then, never the hash. An issue body, such as the order's issue, it never fetches.
  Evidence: prose's hook fetches a body only for a pull request being handed back, and calls only `deferred_footer(body)` on it, [.agents/skills/prose/scripts/prose.py:1561](https://github.com/adamstallard/shared-skills/blob/528ae4ec/.agents/skills/prose/scripts/prose.py#L1561)
