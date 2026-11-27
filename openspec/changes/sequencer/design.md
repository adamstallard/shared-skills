## Open Questions

- **Can a pull request carry GitHub's "blocked by" relation?** (task 0.1)
  If not, the relation orders only issues.
- **Does an edges file fit in a `workflow_dispatch` input?** (task 0.2)
  If not, the Igor that ran the model step, an agent that dispatches the workflow with its results, sends its pairs in several dispatches. Each is a self-contained edges file with the hashes of the changes its pairs name, sent after the run started by the previous dispatch has finished. A dispatch that a newer run in the shared concurrency group cancels while it waits leaves its pairs unchecked until a later model step.
- **Can a pull request's timeline tell apart the two ways a review
  request ends: GitHub clearing it when the reviewer reviews, and a
  person removing it?** (task 0.4) If yes, a reviewer a person removed is no longer awaited: where #98 requested `li` and `maya`, and a person removed `li` before `li` reviewed, #98 awaits `maya` and not `li`. If not, a pull request awaits every reviewer it ever requested, a removed one included. Either way, the spec's reviewers rule already holds.
- **How does a refused "blocked by" read show that GitHub refused
  it?** (task 0.5) When the token cannot read "blocked by" relations,
  the script orders without them, so it needs to tell a refused read from
  an issue with no relations. If a refused read looks like an empty list
  or like the 404 for a missing item, the script first reads an issue it
  last saw hold a relation, and treats an empty answer or a 404 to that
  read as a refusal of every "blocked by" read; with no such issue, the
  order's issue says "blocked by" relations may not have been read. If GitHub
  leaves out silently a relation to another repository's issue the token
  cannot see, the order's issue says that relations to other repositories
  may be missing. Permission reads
  need no such test: a refused one is a `403`, and an account with no
  access gets `200` `none` (`openspec/specs/inquisitor/decisions.md`).
