## Open Questions

Two questions for the repository's owner come first. Every question after
them asks about a fact nobody has measured: each names its task in
tasks.md's section 0 and says what the spec does if the fact turns out
false.

- **Should a session record a cycle override through `publish --decide
  '#85 first' --by maya`, or by posting the comment `#85 first` on the
  order's issue as the person?** `--decide` refuses unless `maya` has
  write access. Where task 0.5 finds the workflow's token cannot read
  another account's permission, writers are decided by the
  `author_association` of an item or comment, and `--decide` has no item
  or comment to read it from. *Option A:* drop `--decide`; in a session,
  the agent posts `#85 first` through `gh` logged in as the person, so
  every override is a comment, checked as *A cycle override is read from
  the order's issue* says. *Option B:* keep `--decide`, and where writers
  are decided by `author_association`, check the person's own permission
  with the session's token, which acts as the person. A read-only
  organization member, whose `author_association` is MEMBER, would then
  count as a writer in a comment but not in `--decide`.
  *Recommended:* A: the spec loses the requirement *A session records a
  cycle override only as that person* with its two scenarios, and the
  overrides' login-and-time form. Example: under A, #85's reason reads
  `` before #82, though it cites #82's `<title>`: chosen at <link to
  maya's comment> ``; under B, `` …: chosen by maya at 2026-11-24 10:00
  UTC ``.

- **Should the script stop refusing a string that holds
  `<!-- sequencer:end -->`?** Markers count only as whole lines, and every
  string from an issue, a pull request, a change or the model step is
  written as inline code with its line breaks as spaces, so it can never
  form a marker line. *Option A:* cut the refusal and its two scenarios.
  *Option B:* keep it. *Recommended:* A: the refusal guards a case the inline-code writing already rules out. Example: a model
  edge whose reason holds the marker. Under A, the order publishes it,
  with the reason shown as inline code; under B, `publish` refuses that
  whole edges set, and the order names its pairs as unchecked. Likewise a
  requirement title holding the marker sets its edge under A, and under B
  sets none, and the order's issue names the change as holding the end
  marker.

- **Can a pull request carry GitHub's "blocked by" relation, and can the
  workflow's token read the relations, including one to another
  repository's issue?** (task 0.1) If a pull request cannot carry one, the
  relation orders only issues. If the token can read none, the order
  reads only `Depends on` and `Builds on:` lines, and its issue says
  `"Blocked by" relations were not read.` If it can read all but
  relations to another repository's issues, the order misses those
  relations without saying so, rather than listing them as not counted.
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
