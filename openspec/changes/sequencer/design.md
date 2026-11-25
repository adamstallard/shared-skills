## Open Questions

Each question asks about a fact nobody has measured. It names the task in
tasks.md's section 0 that measures it, and either says what happens if
the answer is no or names the requirement that says so.

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
  request from a fork?** (task 0.2) If not, *An item the script cannot edit
  is named, not skipped silently* applies.
- **Can a `pull_request_review` run for a fork's pull request edit
  the order's issue and the items' bodies?** (task 0.3) If not, *A run that cannot edit the order's
  issue edits nothing* applies.
- **Does an edges file fit in a `workflow_dispatch` input?** (task 0.4)
  If not, the caller sends its pairs in several dispatches, each a
  self-contained edges file holding some of the pairs, and sends each only after the run
  of the one before has finished, so that its own dispatches never cancel
  each other: GitHub cancels a pending run when a newer one joins the
  concurrency group. Each run adds to the record of checked pairs those pairs
  whose changes' hashes still match the file's; a dispatch that a run from
  another trigger cancels leaves
  its pairs unchecked until a later model step.
- **Can the workflow's token read another account's permission?** (task
  0.5) If not, the spec's term *A writer* gives the `author_association`
  fallback.
- **Can the workflow's token tell that a GitHub App is installed on the
  repository?** (task 0.6) If not, the spec's term *A writer* says that
  no App's bot account counts as a writer.
- **Can a pull request's timeline tell apart the two ways a review
  request ends: GitHub clearing it when the reviewer reviews, and a
  person removing it?** (task 0.7) If not, a pull request awaits every reviewer
  it ever requested, a removed one included, as *Reviewers come from the
  repository's config, else from GitHub's requests, else CODEOWNERS*
  says.
