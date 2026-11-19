# inquisitor: constraints, rejected alternatives and rationale

## Constraints

- **Constraint: Anyone with write access to a repository can rewrite or delete its unprotected `questions` branch.**
  Because: the branch takes direct pushes, so setup asks for no protection of it, and the cost is accepted: a rewrite can delete records, or drop a newer answer so that an older one counts again, and a pushed handled file can close a question so that the person never sees it.
  Evidence: `git push --force` replaces a branch even when the push loses commits, https://git-scm.com/docs/git-push
  Holds while: setup asks for no protection of a `questions` branch.
  Paths: .agents/skills/inquisitor/

- **Constraint: Nothing in the skill verifies who wrote a questions-branch file, so anyone who can push to the branch can name any author.**
  Because: a reader checks only that the named person has write access to what the question concerns, and enforcement is left to each repository's admin, who can require signed commits on the branch or run their own checks on the files' `answered_by` and `said_by` keys.
  Evidence: GitHub's branch protection can "Require signed commits", https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches#require-signed-commits
  Holds while: the spec trusts who a question, answer or miss file says wrote it.
  Paths: .agents/skills/inquisitor/

- **Constraint: GitHub's events API shows each citation push's pusher and time to anyone who can see the lore repository.**
  Because: that repository is never more visible than the question's, so the pusher is shown only to people who may already see the question.
  Evidence: GitHub's events API lists each push event's actor and time, https://docs.github.com/en/rest/activity/events
  Holds while: a citation is pushed with a person's own credentials.
  Paths: .agents/skills/inquisitor/scripts/inquisitor.py

- **Constraint: A rule that depends on igor states its end state, with no clause for an igor state before the igor change it needs lands.**
  Because: igor has published no release, so there is no released igor state for an interim design to serve.
  Evidence: igor's releases page listed none on 2026-11-09, https://github.com/adamstallard/igor/releases
  Holds while: igor has published no release.
  Paths: openspec/specs/inquisitor/spec.md, openspec/specs/answer-session/spec.md

## Rationale

- **Rationale: A question is pushed to the questions branch of what it concerns.**
  Committed with the work, a question's file would be invisible to other work until that work merged, and lost if the work were abandoned; a general question would ride in an unrelated pull request; and an answer session could not write the answer, since it cannot commit to another agent's work branch. A branch of its own, pushed with no pull request, has none of these costs, and needs no review, since a question's authority comes from who answered it.
  Evidence: work committed on one branch is not in another branch's files until it is merged into it, https://git-scm.com/book/en/v2/Git-Branching-Basic-Branching-and-Merging

- **Rationale: The Igor reads questions branches with the script.**
  A worker holds no GitHub credential, and counting a decision needs GitHub's answer on write access. The Igor already runs `gh`, `git` and `claude` as child processes, so the script is one more program run the same way, and igor needs no second implementation of the rules.
  Evidence: igor spawns its helper programs as child processes, https://github.com/adamstallard/igor/blob/7d969cd6ab7820e143c2802a9ead44b3a91332b0/src/gh.ts

- **Rationale: A questions-branch decision counts only unchanged and by write access.**
    Write access is the authority to decide for a repository, and a file changed after its push no longer says what was pushed. A commit's signature would not show who answered: most answers are logged by an agent in the person's own session, and git signs with the configured key whatever the commit holds, so a signed file says only whose session pushed it. Where the admin requires signed commits, a file naming someone who did not answer is itself signed by whoever pushed it, which shows who forged it.
  Evidence: `git commit -S` signs the commit with the committer's key, whatever its content, https://git-scm.com/docs/git-commit#Documentation/git-commit.txt--Sltkey-idgt

- **Rationale: Filter 1 hides every lore entry outside the question's scope.**
  igor and the inquisitor must read a lore entry's scope alike, and igor matches a `project:` scope by a repository's short name. A project whose repositories have other names would need a mapping file in the lore repository, read by both, which nothing provides.
  Evidence: `scopeMatches` in igor's `src/firing.ts`, https://github.com/adamstallard/igor/blob/main/src/firing.ts

- **Rationale: A file is as new as the commit that added it, and supersedes only if it would count.**
  A commit's dates are whatever its committer sets, so they cannot order answers; the branch's commit order changes only when the branch is rewritten, which the Constraint on a rewritable `questions` branch covers.
  Evidence: the committer date is whatever the committer's environment sets, https://git-scm.com/docs/git-commit#_commit_information

- **Rationale: The script tells an Igor's run by IGOR_RUN.**
  The script matches the variable's exact name and value, since a prefix match would take a seat's token variable, `IGOR_RUN_TOKEN`, for a run marker.
  Evidence: igor PR #171 adds `IGOR_RUN_TOKEN`, https://github.com/adamstallard/igor/pull/171

- **Rationale: In an Igor's run, filter 1 searches through igor.**
  An Igor worker cannot run the skill's script, so the filter 1 search it runs, by the skill's instructions, goes through `igor lore-search`, a command its role's `commands` must list. A worker's Bash permission is only its role's `commands`, the list of commands the role lets its worker run; Read is refused outside its working tree, and its HOME holds no `inquisitor.json` or `gh` login unless a developer set one up; igor's deployment guide says not to log `gh` in as the service user. igor PR #175's spec makes the lore checkout mode 0750, which the worker cannot read, though this is unchecked, since #175 is not built; and the run is headless, `claude -p`, with no picker. igor passes the worker no lore repository, only the item's worktree and the lore rendered into its system prompt, and injects the active entries in scope only when all of them fit a 4,000-token budget, and none when they do not, so injected lore alone is not enough for filter 1.
  Evidence: task 0.12, measured 2026-10-20: the worker's `allowedTools` are its role's `commands`, https://github.com/adamstallard/igor/blob/8478aec/src/execute.ts#L1607
  Evidence: its system prompt, `workerSystemPrompt`, https://github.com/adamstallard/igor/blob/8478aec/src/execute.ts#L161
  Evidence: the deployment guide on the service user's `gh` login, https://github.com/adamstallard/igor/blob/8478aec/docs/deployment.md#L112-L115
  Evidence: #175's design, the row for "the Igor's home, lore checkout, `/etc/igor`", https://github.com/adamstallard/igor/blob/908c149/openspec/changes/worker-user/design.md; the worker runs as `claude -p`, https://github.com/adamstallard/igor/blob/8478aec/src/execute.ts#L960-L970; the worker starts in the item's worktree with lore only in its system prompt, https://github.com/adamstallard/igor/blob/8478aec/src/execute.ts#L1595-L1609; and lore is injected whole or not at all under a 4,000-token budget, https://github.com/adamstallard/igor/blob/8478aec/src/firing.ts#L104-L130

- **Rationale: A lore decision record counts.**
  igor PR #202, open, specifies that igor's scribe puts a decision record in the repository the decision concerns, or in the team's lore repository when it spans repositories, so filter 1 reads both.
  Evidence: igor PR #202's decision 5, https://github.com/adamstallard/igor/pull/202

- **Rationale: A session with no person in it asks in a post, a handback or nowhere.**
  An Igor worker asks only in its handback comment because igor gives it no credential that can post: its environment holds only its seat's token, a credential for its model provider.
  Evidence: igor's requirement *The worker is given an explicit environment holding no credential but its seat's*, https://github.com/adamstallard/igor/blob/main/openspec/specs/task-execution/spec.md

- **Rationale: A weakness is not described in public text before its advisory is published.**
  The rule lasts only while the fix is public and the advisory is not, because a blanket rule would leave a fix's commit message unable to say why the fix was made even after disclosure, which prose's rules require of every commit message's body.
  Evidence: prose's rule 14, "Commit subject says what changed; the body says why", https://github.com/adamstallard/shared-skills/blob/02c0a7782bc0392f5c1f5d8e3af0188cf84a9f0d/.agents/skills/prose/rules.md#L228
