## Open Questions

Each question asks about a fact nobody has measured. It names the task in
tasks.md's section 0 that measures it, and the behaviour to specify once
it is measured. The requirement for that behaviour is written only then.

- **Can a pull request carry GitHub's "blocked by" relation?** (task 0.1)
  If not, the relation orders only issues.
- **Does an edges file fit in a `workflow_dispatch` input?** (task 0.4)
  If not, the caller sends its pairs in several dispatches, each a
  self-contained edges file holding some of the pairs, and sends each only after the run of the one before has finished, as its status on GitHub shows. Each run adds to the record of checked pairs those pairs whose changes' hashes still match the hashes that dispatch's edges file carries. All the workflow's runs share one concurrency group, and GitHub cancels a waiting run when a newer one joins it, so a dispatch that a run from another trigger cancels leaves its pairs unchecked until a later model step.
- **How can the script tell that a GitHub App is installed on the
  repository?** (task 0.6) The task finds which of the permission API,
  `author_association` or the repository's list of installations tells
  it, and the spec's term *A writer* then names that method. If no method exists, no App's bot account counts
  as a writer anywhere, and the scenarios that count an installed App's
  bot are removed.
- **Can a pull request's timeline tell apart the two ways a review
  request ends: GitHub clearing it when the reviewer reviews, and a
  person removing it?** (task 0.7) If yes, a reviewer a person removed is no longer awaited: where #98 requested `li` and `maya`, and a person removed `li` before `li` reviewed, #98 awaits `maya` and not `li`. If not, a pull request awaits every reviewer it ever requested, a removed one included. Either way, the spec's reviewers rule already holds.
- **How does a refused read show that GitHub refused it?** (task 0.8)
  Each fallback for a read the token cannot make (counting writers by association, counting no App, ordering without "blocked by" relations) needs to tell a refusal from an empty answer, such as a permission read that returns
  404 both for a refused read and for an account with no access. If a refusal looks like an empty answer or like a 404 for a missing item, the script first makes a read of the same
  kind whose answer is known not to be empty, such as of its own
  account's permission before reading others', and treats an empty
  answer to it as a refusal of every read of that kind.
