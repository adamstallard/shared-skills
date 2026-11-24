## Open Questions

Two questions for the repository's owner come first. Every question
after those two is a fact nobody has measured: a task in tasks.md's
section 0, with what the spec does if the fact turns out false.

- **When does a team stop awaiting review?** A team counts as one
  reviewer, and a pull request stops awaiting a reviewer when that
  reviewer reviews its current head; but a team never reviews, its
  members do, so under the spec a team awaits until the pull request
  closes. *Option A:* any writer's review of the current head,
  other than the author's, takes it off the team's queue. *Option B:* only a
  review by a member of the team does, which needs the workflow's token
  to read team membership, not yet measured. *Option C:* keep the spec.
  *Recommended:* A, which needs no new fact; its cost is that a writer
  outside the team ends the team's wait. Example: CODEOWNERS gives
  `@octo/docs` #96's files, and `maya`, a writer, reviews #96's head.
  Under A, #96 is no longer `@octo/docs`' next review; under B, the same
  if `maya` is in the team and the token can read that; under C, #96
  stays `@octo/docs`' next review until it closes.
- **Should the spec forbid callers to ask a person about a place the
  tiebreak or a cycle's rule decides?** The tiebreak puts the earliest
  opened first where no edge orders two items. The requirement *Items no
  rule orders keep the order they were opened in* ends with a sentence
  saying no caller asks a person about such a place. No test of the script
  can check it, since it binds callers, and adamstallard/igor#231 already
  forbids it for the Igor. *Option A:* keep it. *Option B:* cut it.
  *Recommended:* B. The published order is the same under both. Example:
  #82 and #85 form a cycle ordered by rule. Under A, an agent publishing
  in a session places #82 first and asks nothing; under B, it may first
  ask the person running it whether to record `#85 first` as an
  override.

- **Can the workflow's token read GitHub's "blocked by" relations,
  including one to another repository's issue?** (task 0.1) If it can
  read none, the order reads only `Depends on` and `Builds on:` lines. If
  it can read all but those to another repository's issues, those are
  missing from the order's issue.
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
- **Does an issue transferred into the repository keep its creation
  time?** (task 0.6) If not, it sorts by the time of its transfer.
- **Can the workflow's token tell that a GitHub App is installed on the
  repository?** (task 0.7) If not, an issue or pull request an App's bot
  opened counts as opened by an account without write access, whichever
  caller runs the script.
