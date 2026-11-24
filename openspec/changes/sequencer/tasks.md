The tasks below are the implementation, built on this branch once Adam
approves the spec. Every test tags the scenario it checks with `@scenario sequencer:
<Scenario name>` (spec-trace).

## 0. Measure before building

Record each result in design.md's *Facts measured before building*,
including a result that contradicts what design.md assumed.

- [ ] 0.1 GitHub's "blocked by" relations of an issue or pull request can
      be read through its API with a workflow run's `GITHUB_TOKEN`
- [ ] 0.2 A `pull_request_target` run's `GITHUB_TOKEN`, with
      `pull-requests: write`, can edit the body of a pull request from a fork
- [ ] 0.3 `openspec show --json` reads a change's deltas, with each
      requirement's operation and title, from a pull request head's files
      written into a scratch `openspec/` tree, as spec-check's `show()` does

- [ ] 0.4 A `pull_request_review` run for a fork's pull request gets a
      `GITHUB_TOKEN` that can edit issue and pull request bodies
- [ ] 0.5 The largest input a `workflow_dispatch` run accepts, against the
      size of an edges file for a large repository
- [ ] 0.6 Whether a workflow run's `GITHUB_TOKEN` can read another
      account's permission on the repository, and the members of a team
      CODEOWNERS names
- [ ] 0.7 Whether an issue transferred into a repository keeps the
      creation time it had

## 1. Reading the repository

- [ ] 1.1 `.agents/skills/sequencer/scripts/sequencer.py`, checked by
      `pyright --strict`: read the open issues and pull requests through
      `gh`, with creation times, closing references, `Part of` lines,
      blocked-by relations, requested reviewers, drafts and changed files
- [ ] 1.2 Find each open change on the default branch and on each open pull
      request's head, and the pull request it belongs to
- [ ] 1.3 Read each change's deltas through OpenSpec's CLI, 1.16.1 or later,
      and report a missing or older CLI as *The script reads OpenSpec
      changes only through the OpenSpec CLI* says
- [ ] 1.4 List a change the CLI refuses as not checked, with the CLI's
      reason, and its pairs as unchecked
- [ ] 1.5 Select the issues the order holds, as *The order holds every
      open pull request and the issues linked to the work* says

## 2. The rules

- [ ] 2.1 Modifies and cites edges, with their reasons
- [ ] 2.2 Copy duties
- [ ] 2.3 `Depends on` lines, outside code fences, with `#<number>` and
      `<owner>/<repo>#<number>` references whose names hold only the
      characters the spec allows, blocked-by relations, and
      `Builds on:` lines in a change's `proposal.md`
- [ ] 2.4 Merge waits between pull requests that change a file in common
- [ ] 2.5 The topological order with the earliest-opened tiebreak, cycles
      grouped, ordered earliest opened first and marked `ordered by rule`,
      and cycle overrides placed as overridden
- [ ] 2.6 The names both changes' `tasks.md` files hold, for the model step
- [ ] 2.7 Model-step checked pairs and edges: validate, record with the two changes' hashes,
      keep or drop them on later runs, and refuse edges computed against
      other inputs
- [ ] 2.8 The statements of what the order did not check
- [ ] 2.9 A test that two runs on the same inputs give byte-identical text
- [ ] 2.10 Count an edge only when a writer opened every item whose text
      sets it, and list the rest as not counted
- [ ] 2.11 List each explicit link that names an outside item as not
      counted, setting no edge and writing the outside item as plain
      `owner/repo#N` text: on the line of the item that has the link, or
      in the list of edges not counted when the order does not hold that
      item
- [ ] 2.12 Tie each issue to the open pull requests that close it or name
      it in a `Part of` or closing-keyword line. Counting only pull
      requests writers opened and issues in this repository, place the issue with the earliest of
      them, put each item that comes after the issue after every one of
      them, put every one of them after each item the issue comes after,
      and drop edges between the issue and them.
      Write `tied to no issue` on the line of each open pull request with
      no tie of any kind

## 3. Publishing

- [ ] 3.1 Find or create the order's issue labelled `sequencer`, and stop on
      two
- [ ] 3.2 Write the order's issue and each item's block between the
      markers, each opening with its heading, editing a body only when
      that text changes, and removing the block of an item that leaves the order
- [ ] 3.3 Name each item whose body could not be edited
- [ ] 3.4 Each reviewer's next review, with reviewers from
      `.github/sequencer.json`, GitHub's requests or CODEOWNERS, and
      `order --reviewers` for a dry run
- [ ] 3.5 A test that no command calls a merge, approve, close or reopen
      API
- [ ] 3.6 `order --json`, which edits nothing, naming each item by
      repository and number, as the edges file and the stored checked
      pairs and code edges do
- [ ] 3.7 Rank a spec pull request ahead of the pull requests that come
      after it, and stop a pull request awaiting a reviewer once their
      review's `commit_id` is its head commit
- [ ] 3.8 Write every string taken from an issue, a pull request, a
      change's files or the model step as inert inline code, and refuse
      one holding the end marker

## 4. Cycle overrides

- [ ] 4.1 Count writers' `#<n> first` comments on the order's issue as
      cycle overrides, and record a session's override with
      `publish --decide`

## 5. The CI workflow

- [ ] 5.1 `.agents/skills/sequencer/ci/sequencer.yml`: every trigger
      *The workflow recomputes the order on each event that can change it*
      names, one concurrency group, `pull_request_target` reading pull
      requests as data, the sequencer script fetched from the shared-skills commit `setup-ci`
      writes into the template
- [ ] 5.2 The three model-step choices: none; `ANTHROPIC_API_KEY` through
      `publish --model api`, one API call with no tools whose reply the
      script parses and validates; an Igor, through the label
      `sequencer: check code`
- [ ] 5.3 `setup-ci [--model-step none|api-key|igor] [--force]`, refusing an
      existing file without `--force`
- [ ] 5.4 Run the workflow in this repository

## 6. Docs

- [ ] 6.1 `.agents/skills/sequencer/SKILL.md`: when to run it, the session's
      model step, the commands, and the `Part of` line for a pull request
      that does only part of an issue's work
- [ ] 6.2 The README's skills table

## 7. Archive

- [ ] 7.1 At archive, move out of design.md, into
      `openspec/specs/sequencer/decisions.md`, anything still there that
      the record holds: a constraint no test can check, an alternative no
      requirement guards against, or a requirement's reason with evidence
      (spec-check's SKILL.md, *Current-state passes*). That record is the
      capability's only decision file, so write no
      `.agents/skills/sequencer/DECISIONS.md`
