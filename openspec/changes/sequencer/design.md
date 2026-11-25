## Open Questions

Each question asks about a fact nobody has measured, except the last,
which asks the repository's owner. A measurement question names the task
in tasks.md's section 0 that measures it, and says what the spec does if
the fact turns out false.

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
  whole edges file. It sends each only after the run of the one before
  has finished, because GitHub cancels a pending run when a newer one
  joins the concurrency group. Each run adds the pairs whose hashes
  still match to those already stored.
- **Can the workflow's token read another account's permission?** (task
  0.5) If not, writers are decided by `author_association`, as the spec's
  definition of a writer says.
- **Can the workflow's token tell that a GitHub App is installed on the
  repository?** (task 0.6) If not, an issue or pull request an App's bot
  opened counts as opened by an account without write access, even in a
  session whose token could tell, so that every caller gives the same
  order. The script then opens an order's issue only as a writer or as
  `github-actions[bot]`, which the spec accepts by name, since it uses
  that issue only when one of those opened it.
- **Can a pull request's timeline tell apart the two ways a review
  request ends: GitHub clearing it when the reviewer reviews, and a
  person removing it?** (task 0.7) If not, a pull request awaits every
  reviewer it ever requested, a removed one included: dropping both
  kinds would stop awaiting a reviewer who reviewed, even after a later
  push.
- **How does an edges file name a change when one pull request holds two?**
  An edges file names each item by repository and number, and its edges
  run item to item (#90 after #82), but the order's issue's record of checked
  pairs keys its rows by change, through its `legend:`, and nothing stops a pull request from holding two changes. So
  `publish` cannot tell which of #90's changes a pair or an edge means.
  *Option A:* an edges file names each change by repository and name, as
  the legend does, in its pairs and edges. *Option B:* the script treats a
  pull request holding two or more changes as one change, hashing all
  their files together. *Recommended:* A: each pair and edge in the file then
  maps through the legend to one row of the record, and the script still writes `after #82` for readers.
  Example: #82 holds `add-claims-table`, and #90 holds
  `claim-audit-log` and `claim-retries`; under A the file
  says `octo/app claim-retries` comes after `octo/app add-claims-table`;
  under B a revision of `claim-audit-log` also unchecks every pair of
  `claim-retries`.
