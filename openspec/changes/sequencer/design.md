## Open Questions

Each question asks about a fact nobody has measured, except the last two,
which ask the repository's owner. A measurement question names the task
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
- **Which data that later runs read back from the order's issue should
  name a repository?** Issue #100 records the decision that this change's stored
  data name an item by repository and number, and its displayed text by
  `#<number>`, so a later order spanning several repositories can reuse
  them. Later runs read back three things from the order's issue: the record's
  legend, which names a change by name alone; each cycle's mark
  (`ordered by rule since <time>`); and the list of overrides the script
  copies from `#<n> first` comments. The last two sit on lines that name
  items by `#<number>`. *Option A:* all three name the
  repository. *Option B:* only the legend does, as `a1
  adamstallard/shared-skills add-claims-table <hash>`; the cycle marks and overrides
  count as displayed text, which #100 lets keep `#<number>`. *Option C:* none; a later
  change letting one order span several repositories rewrites them. *Recommended:* B: only the
  script reads the legend, at about 30 more characters per change in a
  pair, while people read the cycle lines.
  Example: with 50 changes in pairs, B adds about 1,500 characters to a body
  that may hold 65,536, and leaves `#82 and #90: ordered by rule since
  2026-11-24 10:00 UTC` as it reads now.
- **What do readers see once the order's issue is full?** Past GitHub's
  limit the script publishes nothing, so every block keeps giving a place
  that is no longer true, a new item gets no block, and the order's issue
  shows a stale order; "says the order's issue is full" reaches only the
  run's log. *Option A:* replace the order between the order's issue's
  markers with a short fixed note saying it is full and how many open
  changes there are, leaving the blocks. *Option B:* as A, and also
  replace each item's block with a one-line note linking the order's
  issue. *Option C:* write nothing, as now. *Recommended:* A: one small
  edit that fits, where readers look for the order, and each block's link
  already leads there.
  Example: with 320 open changes, under A the order's issue reads `The
  order's issue is full: 320 open changes need more than GitHub's 65,536
  characters. No order is published until some merge or close.`
