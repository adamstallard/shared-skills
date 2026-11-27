## Open Questions

- **Can a pull request carry GitHub's "blocked by" relation?** (task 0.1)
  If not, the relation orders only issues.
- **Does an edges file fit in a `workflow_dispatch` input?** (task 0.2)
  If not, the Igor that ran the model step, an agent that dispatches the workflow with its results, sends its pairs in several dispatches. Each is a self-contained edges file with the hashes of the changes its pairs name, sent after the run started by the previous dispatch has finished. A dispatch that a newer run in the shared concurrency group cancels while it waits leaves its pairs unchecked until a later model step.
- **How can the script tell that a GitHub App is installed on the
  repository?** (task 0.3) None of the permission API, `author_association`
  or reading installations lets the workflow's token, or any other token
  scoped to the repository, tell whether an App is installed. The permission API
  answers `none` for an App's bot (`openspec/specs/inquisitor/decisions.md`).
  `author_association` was `CONTRIBUTOR` or `NONE` on cli/cli for
  `github-actions[bot]`, `dependabot[bot]` and `cli-triage[bot]`, as for
  any outside contributor. `GET repos/<owner>/<repo>/installation` needs
  the App's own JWT, and listing installations needs a user-to-server
  token or, in an organization, `admin:org`. Unless another method is
  found, no App's bot account counts as a writer anywhere, and the
  scenarios that count an installed App's bot, and the rules built on
  them, are removed.
- **Should an organization MEMBER count as a writer when permissions
  cannot be read?** This is a decision, with no task. The fallback in
  *A token that cannot read permissions counts writers by association*
  counts OWNER, MEMBER and COLLABORATOR, though MEMBER does not imply
  write access. The permission read needs push access, so with a workflow
  token holding `contents: read` the fallback runs on every workflow run,
  and every member of the organization counts as a writer. Either drop
  MEMBER, or give the workflow's token the access the permission read
  needs.
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
