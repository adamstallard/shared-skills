## Open Questions

One question for the repository's owner comes first. Every question
after it asks about a fact nobody has measured: a task in tasks.md's section 0,
with what the spec does if the fact turns out false.

- **Should the sequencer tie a pull request to an issue by the line forms
  that pull request #113 accepts?** #113 has the prose skill remind an
  author whose pull request body has no link line, and treats a body as
  linked when a closing keyword or `Part of`, then an optional colon, then
  `#N`, `owner/repo#N` or an issue's URL, appears anywhere, mid-sentence
  included, in any case. The sequencer ties only on a line that starts
  with one of them and names `#N` or `owner/repo#N`, with no colon or URL. *Option A:* keep
  the sequencer's form, and have #113 accept only that form.
  *Option B:* the sequencer accepts #113's forms. *Option C:* leave the two
  differing. *Recommended:* A. Prose also names issues that a pull request
  only mentions, and #113's mid-sentence forms match such prose, which the
  sequencer's scenario *Naming an issue in prose ties no pull request to
  it* rules out. Example: #108's body says "Implements the
  docs part of #107". Under A, #113 reminds #108's author to add a link line,
  and the order lists #108 as `tied to no issue`; under B, the order ties
  #108 to #107 and gives #107 its place; under C, #113 stays quiet while
  the order lists #108 as `tied to no issue`.

- **Can a pull request carry GitHub's "blocked by" relation, and can the
  workflow's token read the relations, including one to another
  repository's issue?** (task 0.1) If a pull request cannot carry one, the
  relation orders only issues. If the token can read none, the order
  reads only `Depends on` and `Builds on:` lines. If it can read all but
  those to another repository's issues, the order's issue cannot list
  those as not counted.
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
