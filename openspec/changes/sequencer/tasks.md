Section 0's measurements need no approval and can run first. The rest is
the implementation, built on this branch once the spec is approved. Every test tags the scenario it checks with `@scenario <capability>:
<Scenario name>`, where `<capability>` is `sequencer` or `inquisitor` (spec-trace).

## 0. Measure before building

Each task answers one of design.md's open questions. Write each result into the requirement or term it bears on, with its evidence in
`openspec/specs/sequencer/decisions.md` where a rule rests on it, and
remove the question from design.md.

- [ ] 0.1 Whether a pull request can carry GitHub's "blocked by"
      relation
- [ ] 0.2 The largest input a `workflow_dispatch` run accepts, against the
      size of an edges file for a large repository
- [ ] 0.3 How the workflow's token can tell that an issue's or pull
      request's author is the bot account of a GitHub App installed on the
      repository, by a method other than the permission API,
      `author_association` or reading the repository's installations,
      none of which tells it whether an App is installed (design.md)
- [ ] 0.4 Whether a pull request's timeline tells apart the two ways a
      review request ends: GitHub clearing it when the reviewer reviews,
      and a person removing it
- [ ] 0.5 How a refused read of "blocked by" relations shows that GitHub refused it:
      an error status, an empty answer, or a 404 like the one for a
      missing item; and whether a relation to an issue in another
      repository the token cannot see is refused or left out silently

## 1. Reading the repository

- [ ] 1.1 `.agents/skills/sequencer/scripts/sequencer.py`, checked by
      `pyright --strict`: read the open issues and pull requests through
      `gh`, with creation times, closing references, `Part of` lines,
      blocked-by relations, requested reviewers, the review-request events
      in each pull request's timeline, drafts and changed files
- [ ] 1.2 Find each open change on the default branch and on each open pull
      request's head, and the pull request it belongs to
- [ ] 1.3 Read each change's deltas through OpenSpec's CLI, 1.16.1 or later,
      and report a missing or older CLI as *The script reads OpenSpec
      changes only through the OpenSpec CLI* says
- [ ] 1.4 List a change the CLI refuses as not checked, with the CLI's
      reason
- [ ] 1.5 Select the issues the order holds, as *The order holds every
      open pull request and the issues linked to the work* says

## 2. The rules

- [ ] 2.1 Modifies and cites edges, with their reasons
- [ ] 2.2 `Depends on` lines, outside code fences, with `#<number>` and
      `<owner>/<repo>#<number>` references whose owner and repository
      names hold only the characters *A Depends on line names items by
      number, with or without their repository* allows, blocked-by
      relations, read as task 0.1 finds, and
      `Builds on:` lines in a change's `proposal.md`
- [ ] 2.3 Merge waits between pull requests that change a file in common,
      only where a writer opened the earlier one
- [ ] 2.4 The topological order: items no rule orders go earliest opened
      first; each cycle takes one place, its members ranked earliest
      opened first and its line marked `ordered by rule`, unless an
      override counts, which puts its member first
- [ ] 2.5 The backticked names, such as `claim_item()`, that both
      changes' `tasks.md` files hold, printed for the model step for each
      pair of changes
- [ ] 2.6 The record of checked pairs in the order's issue: its legend,
      `code edges:` and `unchecked:` lists, updated each run; taking the code
      edges of each pair in an edges file whose two changes' hashes match
      the legend's current ones, and dropping the rest; refusing
      a file that names a change without its repository; and the size
      check, which, once the body would pass GitHub's limit, writes in
      place of the order the note that the order's issue is full, keeping
      only the cycles' lines
- [ ] 2.7 The statements of what the order did not check, as *The order
      says plainly what it did not check* says
- [ ] 2.8 A test that two runs on the same inputs give byte-identical text
- [ ] 2.9 Count an edge only when a writer opened every item whose text
      sets it, counting each issue or pull request that an installed
      App's bot opened as opened by a writer, the App's installation
      read as task 0.3 finds, and list the rest as not counted
- [ ] 2.10 List links to outside items, as *A link to an outside item is
      listed as not counted* says
- [ ] 2.11 Tie issues to pull requests: place each issue with its pull
      requests, list each pull request tied to no issue, and name in a
      pull request's block each issue GitHub will not close

## 3. Publishing

- [ ] 3.1 Find or create the order's issue labelled `sequencer`, and stop on
      two open order issues, or on broken markers in it
- [ ] 3.2 Write the order's issue and each item's block between the
      markers, each opening with its heading, each block giving its place
      without the number of places, editing a body only when that text
      changes, rereading each body just before writing it, and removing
      the block of an item that leaves the order
- [ ] 3.3 Name each item whose body could not be edited or holds
      unmatched markers, leaving that body as it is
- [ ] 3.4 Each reviewer's next review, with reviewers from
      `.github/sequencer.json`, GitHub's requests or CODEOWNERS, and
      `order --reviewers` for a dry run
- [ ] 3.5 A test that no command calls a merge, approve, close or reopen
      API
- [ ] 3.6 `order --json`, which edits nothing, naming each item by
      repository and number, and printing a change's files only where a
      writer opened its pull request
- [ ] 3.7 Stop a pull request awaiting a reviewer once their review's
      `commit_id` is its head commit, and awaiting a team once a
      review with that `commit_id` comes from any writer other than the
      pull request's author
- [ ] 3.8 Write outside text inert, as *Text from a pull request or the
      model is written inert* says
- [ ] 3.9 Fall back where the token cannot read permissions, installations
      or "blocked by" relations, and say so; where the repository has the
      workflow, also apply in a session, or in an Igor's run of `order`,
      each fallback the order's issue names, as *Other callers follow the
      fallbacks the workflow wrote* says

## 4. Cycle overrides

- [ ] 4.1 Count writers' `#<n> first` comments on the order's issue as
      cycle overrides, and have the skill tell an agent in a session to
      record a person's choice by posting `#<n> first` there with the
      person's own `gh` login, or, in a project whose agents act as a
      GitHub App through the github-app skill, to ask the person to post
      it, since an App's comments override nothing

## 5. The CI workflow

- [ ] 5.1 `.agents/skills/sequencer/ci/sequencer.yml`: every trigger
      *The workflow recomputes the order on GitHub events and once a day*
      names, one concurrency group, `pull_request_target` reading pull
      requests as data, the sequencer script fetched from the shared-skills commit `setup-ci`
      writes into the template, and OpenSpec's CLI installed at a pinned
      version, 1.16.1 or later
- [ ] 5.2 The three model-step choices: none; `ANTHROPIC_API_KEY` through
      `publish --model api`, one API call with no tools whose reply the
      script parses and validates, called only in the runs
      *An API key's model step runs only on events that can change a pair* names; an Igor, through the label
      `sequencer: check code`
- [ ] 5.3 `setup-ci [--model-step none|api-key|igor] [--force]`, refusing an
      existing file without `--force`
- [ ] 5.4 Run the workflow in this repository

## 6. Docs

- [ ] 6.1 `.agents/skills/sequencer/SKILL.md`: when to run it, the session's
      model step, the commands, the identity a session's `publish` runs as
      (the App's, through the github-app skill, in a project wired to
      one), and the `Part of` line for a pull request that does only part
      of an issue's work
- [ ] 6.2 The README's skills table

## 7. The inquisitor's exception for sequencer blocks

This change carries a delta on the inquisitor spec, since the sequencer
makes the edits it covers; the code goes in the inquisitor's script.

- [ ] 7.1 Keep a numbered `Inquisitor: ` reply in force across an edit
      that only added sequencer blocks, changed them between their
      markers, or changed blank lines, comparing the body now with the
      body the reply saw: the `diff` of the newest `userContentEdits`
      entry whose `editedAt` is before the reply was posted, as the
      inquisitor spec's *A sequencer block's update keeps a numbered
      reply* says
