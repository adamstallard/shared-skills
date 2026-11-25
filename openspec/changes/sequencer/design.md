## Open Questions

Two questions for the repository's owner come first. Each question after
them asks about a fact nobody has measured: it names the task in tasks.md's
section 0 that measures it, and says what the spec does if the fact turns
out false.

- **Should a review request, or its removal, trigger a run?** Either
  changes a pull request's reviewers, and so the next review the order's
  issue names for each reviewer, but neither is in the workflow's events,
  nor in the list of events issue #43 records as decided. *Option A:* add both (`review_requested` and
  `review_request_removed`). *Option B:* leave them out; the next other
  event, or the daily run, catches up. *Recommended:* A: two more events
  and no new rule.
  Example: `maya` requests `li`'s review on #97; under A, `li`'s next
  review becomes #97 within minutes; under B, the order's issue may still
  name another pull request as `li`'s next review until the next day.
- **What happens when the stored checked pairs outgrow the order's
  issue?** The order's issue stores each pair of changes the model step has
  checked, with both changes' hashes, so later runs keep its code edges.
  The pairs grow with the square of the open changes, at about 150 to
  200 characters each: 30 open changes make 435 pairs, past GitHub's
  limit of 65,536 characters on an issue body, and the spec says nothing
  about it. *Option A:* store each change's hash once, beside the list
  of pairs, which keeps the same rule (a pair stays checked while both
  hashes match) in about a third of the space; past the limit, the pairs
  that do not fit stay unchecked and are named, and count neither for
  the `sequencer: check code` label that calls an Igor nor for an API
  call. *Option B:* accept the limit; past it,
  the script publishes nothing and says the order's issue is full.
  *Recommended:* A: it postpones the limit to about 45 open changes (990
  pairs) and
  degrades to named unchecked pairs instead of no order.
  Example: a repository with 40 open writers' changes has 780 pairs;
  under A all of them fit, at about 65 characters each;
  under B no order is published until changes merge.

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
