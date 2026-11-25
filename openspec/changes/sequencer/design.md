## Open Questions

Two questions for the repository's owner come first. Every question after
them asks about a fact nobody has measured: each names its task in
tasks.md's section 0 and says what the spec does if the fact turns out
false.

- **How should the order treat `Closes #10, #123`?** The sequencer ties a
  pull request to every issue such a line names, but GitHub closes only
  #10, since its documentation asks for a keyword before each issue. So
  #123 would stay open after the merge, unflagged. *Option
  A:* after a closing keyword, tie only the first issue, the one
  GitHub closes. *Option B:* keep tying every issue. *Option C:* tie every
  issue, and have the pull request's line name each one GitHub will not
  close. *Recommended:* C: only C shows the reader that #123 will stay
  open. Example: under A, #123 is not tied to the pull request, so it
  takes no position from it, and nothing mentions it; under B, #123 shares the pull request's place and
  stays open after the merge; under C, it shares the place and the line
  says `` GitHub will not close #123: write `Closes` before it ``.

- **Should a reopened issue or pull request, and a pull request
  converted to draft, trigger a run?** Neither event is in the trigger
  list, so the order stays wrong until another event or the daily run.
  *Option A:* add `reopened`, for issues and pull requests, and
  `converted_to_draft`. *Option B:* keep the list. *Recommended:* A: two
  event names, and no new rule. Example: under B, a reopened #82 is
  missing from the order, and a pull request just made a draft is still
  some reviewer's next review, until the daily run; under A, the run the
  event starts fixes both.

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
  repository?** (task 0.7) If not, an issue or pull request an App's bot
  opened counts as opened by an account without write access, whichever
  caller runs the script, and the script opens no order's issue as an
  App, since it would then refuse that issue.
