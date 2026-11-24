## Open Questions

Two questions for the repository's owner come first. Every question
after those two is a fact nobody has measured: a task in tasks.md's
section 0, with what the spec does if the fact turns out false.

- **Should a change archived on an open pull request's head still count
  as open?** Under the spec, an open change is a directory under
  `openspec/changes/` other than `archive/`. Where an implementation pull
  request archives its change on its own branch before it merges, the
  change stops being open while nothing has merged: other changes lose
  the edges its requirements set, and the order's issue stops saying
  which change owes a copy of its new scenarios (*Two changes that modify
  one requirement owe a copy, which sets no order*). *Option A:* keep the
  spec, accepting until the merge the missing edges and the copies no one
  is told they owe. *Option B:* count a
  change under `openspec/changes/archive/` on an open pull request's head,
  and not on the default branch, as open. *Recommended:* B, if
  implementation pull requests here archive their change before they
  merge, which would make the gap part of normal operation; no change here
  has been archived yet. Otherwise A. Example: #82 archives its change on
  its branch, and #90's change modifies #82's requirement. Under A, #90
  loses its place after #82 and nothing says #90 owes #82's scenarios;
  under B, #90 stays after #82 and the order's issue still says #90 owes
  the copy.
- **Should a block give the number of places in the order?** Each block
  says, for example, `fifth of twelve places`. Under the spec, an item
  joining or leaving the order changes the total, so every block is
  rewritten. *Option A:* keep the total. *Option B:* give only the place,
  as `fifth in the order`, so a block is rewritten only when its own
  place, or what it waits on, changes. An item joining still moves every
  item after it, so B saves the edits to blocks before it.
  *Recommended:* B, for fewer edits and notifications. Example: #120 joins
  at the end of a twelve-item order. Under A, all twelve blocks are
  rewritten to `of thirteen places`; under B, only #120 gets a block.

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
  0.6) If not, writers are decided by `author_association`, as the spec's
  definition of a writer says.
- **Does an issue transferred into the repository keep its creation
  time?** (task 0.6) If not, it sorts by the time of its transfer.
- **Can the workflow's token tell that a GitHub App is installed on the
  repository?** (task 0.7) If not, an issue or pull request an App's bot
  opened counts as opened by an account without write access, whichever
  caller runs the script.
