## Open Questions

Two questions for the repository's owner come first. Then come facts
nobody has measured: each is a task in tasks.md's section 0, and each says
what the spec does if the fact turns out false.

- **Should every installed App's pull request count as a writer's, or
  only the Apps `.github/sequencer.json` names?** Under the spec, any
  installed App counts. A dependency bot such as Renovate then counts too, and its pull
  request bodies quote upstream release notes. A quoted line such as
  `Fixes #43` would tie its pull request to this repository's #43, placing
  #43 with a dependency bump. Such bots usually rewrite `#43` in quoted
  notes into a link, which is no reference, so the case is rare.
  *Recommended:* keep any installed App, which needs no config. Under a
  named list, an Igor (an AI teammate of adamstallard/igor, which opens
  pull requests as its App's bot) places #43 with its `Part of #43` only
  after someone adds its App to the list.
- **Should an issue an installed App opened count as a writer's too?**
  Only pull requests do today. So a `Depends on #9` in an issue an Igor
  opened through its App sets no edge. And the spec uses an order's issue
  only when a writer or `github-actions[bot]` opened it, so one that
  `igor init`, Igor's setup command, opens through an App is refused, and
  nothing is published. An App
  installed with permission to edit issues can already edit any issue's
  body, so counting its issues gives it nothing new. *Recommended:* count
  issues too, so the Igor's `Depends on #9` orders its issue after #9, and
  `igor init` may open the order's issue.

- **Can the workflow's token read GitHub's "blocked by" relations,
  including one to another repository's issue?** (task 0.1) If it can
  read none, the order reads only `Depends on` and `Builds on:` lines. If
  it can read all but those to another repository's issues, those are
  missing from the order's issue.
- **Can a `pull_request_target` run's token edit the body of a pull
  request from a fork?** (task 0.2) If not, the fork's pull request is
  placed but gets no block, as *An item the script cannot edit is named,
  not skipped silently* says.
- **Does `openspec show --json` read a change written into a scratch
  `openspec/` tree?** (task 0.3) If not, the script treats every change
  as one the CLI refuses.
- **Can a `pull_request_review` run for a fork's pull request edit
  bodies?** (task 0.4) If not, that run publishes nothing, and the next
  run with a write token, at the latest the daily one, publishes the
  order.
- **Does an edges file fit in a `workflow_dispatch` input?** (task 0.5)
  If not, a Sequencer Igor sends its pairs in several dispatches, each a
  whole edges file, and each run stores the pairs whose hashes still
  match beside those already stored.
- **Can the workflow's token read another account's permission, and the
  members of a team CODEOWNERS names?** (task 0.6) If it cannot read
  permissions, writers are decided by `author_association`, as the spec's
  definition of a writer says. If it cannot expand a team, the team counts
  as one reviewer, for every caller, and gets one next review.
- **Does an issue transferred into the repository keep its creation
  time?** (task 0.7) If not, it sorts by the time of its transfer.
- **Can the workflow's token tell that a GitHub App is installed on the
  repository?** (task 0.8) If not, a pull request an App's bot opened
  counts as no writer's, for every caller.
