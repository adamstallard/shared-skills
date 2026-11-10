# inquisitor: constraints, rejected alternatives and rationale

## Constraints

- **Constraint: Until its work merges, a repository's log file is invisible to parallel work, so an agent on another branch may ask the same question again.**
  Because: a change's questions belong in its history and merge with it.
  Evidence: work committed on one branch is not in another branch's files until it is merged into it, https://git-scm.com/book/en/v2/Git-Branching-Basic-Branching-and-Merging
  Holds while: one repository's questions are committed with the work under `.inquisitor/questions/`.
  Paths: .agents/skills/inquisitor/scripts/inquisitor.py

- **Constraint: GitHub's events API shows each citation push's pusher and time to anyone who can see the lore repository.**
  Because: that repository is never more visible than the question's, so the pusher is shown only to people who may already see the question.
  Evidence: GitHub's events API lists each push event's actor and time, https://docs.github.com/en/rest/activity/events
  Holds while: a citation is pushed with a person's own credentials.
  Paths: .agents/skills/inquisitor/scripts/inquisitor.py

- **Constraint: Someone who can push to a person's open pull request, such as a maintainer GitHub's "allow edits by maintainers" lets push to it, can change the person's relay file under it, and the change counts once merged.**
  Because: the relay notice mentions the person for that push, so they can close the pull request.
  Evidence: GitHub lets maintainers push to a fork's pull request branch when its author allows edits, https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/working-with-forks/allowing-changes-to-a-pull-request-branch-created-from-a-fork
  Holds while: a reader ties a relay file to its person by who last changed it on the default branch.
  Paths: .agents/skills/inquisitor/

- **Constraint: Anyone who can rewrite the lore repository's default branch can restore an older relay file of the person's own, listing an App the person removed, so removing a compromised App from the file does not stop it speaking for the person.**
  Because: uninstalling the App or revoking its key does stop it, and the README says to do that.
  Evidence: `git push --force` replaces a branch even when the push loses commits, so a rewrite can drop the commit that removed the App, https://git-scm.com/docs/git-push
  Holds while: a relay file counts by who last changed it on the default branch.
  Paths: .agents/skills/inquisitor/

- **Constraint: A rule that depends on igor states its end state, with no clause for an igor state before the igor change it needs lands.**
  Because: igor has published no release, so there is no released igor state for an interim design to serve.
  Evidence: igor's releases page listed none on 2026-11-09, https://github.com/adamstallard/igor/releases
  Holds while: igor has published no release.
  Paths: openspec/specs/inquisitor/spec.md, openspec/specs/answer-session/spec.md

## Rejected

- **Rejected: Counting a relay file's pull request only when all its commits are the person's.**
  Facing: someone else pushing to a person's open pull request to change their relay file.
  Lost because: neither a commit nor its pull request in GitHub's API names who pushed it, and the events API, which does, keeps only recent events, https://docs.github.com/en/rest/activity/events.
  Instead: a reader counts the file only when its last default-branch change came from its login, and the relay notice mentions the person when someone else pushes to their pull request.
  Paths: .agents/skills/inquisitor/

## Rationale

- **Rationale: Filter 1 hides every lore entry outside the question's scope.**
  igor and the inquisitor must read a lore entry's scope alike, and igor matches a `project:` scope by a repository's short name. A project whose repositories have other names would need a mapping file in the lore repository, read by both, which nothing provides.
  Evidence: `scopeMatches` in igor's `src/firing.ts`, https://github.com/adamstallard/igor/blob/main/src/firing.ts

- **Rationale: A file is as new as its proof, and supersedes only if it would count.**
  The signer sets a commit's committer date, so a signature dated by it alone would let a proven writer, or a skewed clock, date a commit far in the future and outrank every later answer for good. Bounding it by this machine's first fetch costs this: two machines that first fetched a file at different times can order it differently against a file pushed between those fetches.
  Evidence: the committer date is whatever the committer's environment sets, https://git-scm.com/docs/git-commit#_commit_information

- **Rationale: A reader counts no signature GitHub may have made.**
  GitHub signs the commits it makes itself, such as one from its web editor. If GitHub verified such a commit for an account that did not make it, anyone with push access could make a commit that proves another person's answer or relay file.
  Evidence: "GitHub will automatically use GPG to sign commits you make using the web interface", https://docs.github.com/en/authentication/managing-commit-signature-verification/about-commit-signature-verification
  Evidence: task 0.11 read a merge commit on shared-skills' main as `VALID`, signed by `web-flow` with `wasSignedByGitHub` set, on 2026-11-04, https://github.com/web-flow.gpg

- **Rationale: The script tells an Igor's run by IGOR_RUN.**
  The script matches the variable's exact name and value, since a prefix match would take a seat's token variable, `IGOR_RUN_TOKEN`, for a run marker.
  Evidence: igor PR #171 adds `IGOR_RUN_TOKEN`, https://github.com/adamstallard/igor/pull/171

- **Rationale: In an Igor's run, filter 1 searches through igor.**
  An Igor worker cannot run the skill's script, so the filter 1 search it runs, by the skill's instructions, goes through `igor lore-search`, a command its role's `commands` must list. A worker's Bash permission is only its role's `commands`, the list of commands the role lets its worker run; Read is refused outside its working tree, and its HOME holds no `inquisitor.json` or `gh` login unless a developer set one up; igor's deployment guide says not to log `gh` in as the service user. Under igor PRs #174 and #175, by their specs, unchecked since neither is built, skills load only from `/opt/igor/skills`, the lore checkout is mode 0750, which the worker cannot read, the worker loads no hooks, and the run is headless, with no picker. igor passes the worker no lore repository, and injects only the active entries that fit its token budget, so injected lore alone is not enough for filter 1.
  Evidence: task 0.12, measured 2026-10-20: the worker's `allowedTools` are its role's `commands`, https://github.com/adamstallard/igor/blob/8478aec/src/execute.ts#L1607
  Evidence: its system prompt, `workerSystemPrompt`, https://github.com/adamstallard/igor/blob/8478aec/src/execute.ts#L161
  Evidence: the deployment guide on the service user's `gh` login, https://github.com/adamstallard/igor/blob/8478aec/docs/deployment.md#L112-L115
  Evidence: #175's design, the row for "the Igor's home, lore checkout, `/etc/igor`", https://github.com/adamstallard/igor/blob/908c149/openspec/changes/worker-user/design.md

- **Rationale: A lore decision record counts.**
  igor PR #202, open, specifies that igor's scribe puts a decision record in the repository the decision concerns, or in the team's lore repository when it spans repositories, so filter 1 reads both.
  Evidence: igor PR #202's decision 5, https://github.com/adamstallard/igor/pull/202

- **Rationale: A session with no person in it asks in a post, a handback or nowhere.**
  An Igor worker asks only in its handback comment because igor gives it no credential that can post: its environment holds only its seat's token, a credential for its model provider.
  Evidence: igor's requirement *The worker is given an explicit environment holding no credential but its seat's*, https://github.com/adamstallard/igor/blob/main/openspec/specs/task-execution/spec.md

- **Rationale: A relay App is one its person's counted relay file lists.**
  A person may own other Apps, such as their own Igor's, whose code posts text no hook sees, so only the Apps their counted relay file lists may speak for them. A reader never counts an App whose slug starts `igor-` as a relay App, even where a relay file lists it, so a person's own Igor cannot speak for them. That every Igor's App carries the prefix rests on igor PR #216, still open, which specifies that an Igor whose App's slug lacks it refuses to start.
  Evidence: igor PR #216's decision 62, https://github.com/adamstallard/igor/pull/216
