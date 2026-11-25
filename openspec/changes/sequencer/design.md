## Open Questions

One question for the repository's owner comes first. Every question after
it asks about a fact nobody has measured: it names the task in tasks.md's
section 0 that measures it, and says what the spec does if the fact turns
out false.

- **Should a push to the default branch trigger a run?** The workflow runs
  on a push to an open pull request's branch, but issue #43, which records the
  sequencer's decisions, says "pushes" in general. A commit straight to the default branch can add, revise or
  archive a change there, or edit `.github/sequencer.json`, which lists the reviewers. *Option A:*
  also run on a push to the default branch. *Option B:* keep pull request
  branches only, and narrow issue #43's wording to match. *Recommended:* A: one
  more event and no new rule, and the order then follows every commit
  that could change it.
  Example: a commit to the default branch archives `claims`, which #90's
  change modifies; under A, the run it starts drops #90's edge from
  `claims` at once; under B, #90 keeps waiting on `claims` until another
  event triggers a run, or the daily run does.

- **Can a pull request carry GitHub's "blocked by" relation, and can the
  workflow's token read the relations, including one to another
  repository's issue?** (task 0.1) If a pull request cannot carry one, the
  relation orders only issues. If the token can read none, the script,
  whoever runs it, reads only `Depends on` and `Builds on:` lines, so
  that every caller gives the same order, and the order's issue says
  `"Blocked by" relations were not read.` If it can read all but
  relations to another repository's issues, the order's issue
  says `"Blocked by" relations to other repositories were not read.`
- **Can a `pull_request_target` run's token edit the body of a pull
  request from a fork?** (task 0.2) If not, the fork's pull request is
  placed but gets no block, as *An item the script cannot edit is named,
  not skipped silently* says.
- **Can a `pull_request_review` run for a fork's pull request edit
  bodies?** (task 0.3) If not, that run publishes nothing, and the next
  run with a write token, at the latest the daily one, publishes the
  order.
- **Does an edges file fit in a `workflow_dispatch` input?** (task 0.4)
  If not, a Sequencer Igor sends its pairs in several dispatches, each a
  whole edges file, and each run stores the pairs whose hashes still
  match beside those already stored.
- **Can the workflow's token read another account's permission?** (task
  0.5) If not, writers are decided by `author_association`, as the spec's
  definition of a writer says.
- **Can the workflow's token tell that a GitHub App is installed on the
  repository?** (task 0.6) If not, an issue or pull request an App's bot
  opened counts as opened by an account without write access, whichever
  caller runs the script, and the script opens no order's issue as an
  App, since it uses an order's issue only when a writer opened it.
