# inquisitor: constraints, rejected alternatives and rationale

## Constraints

- **Constraint: A `questions` branch is guarded against rewriting and deletion only where an admin of its repository sets the rule setup suggests.**
  Because: setting a branch rule takes admin access, which a person subscribing to the repository may lack, and the rule must allow the direct pushes every record needs, so the cost is accepted that a writer can delete or rewrite a branch without the rule, dropping a newer answer so that an older one counts again, and can push a handled file to any branch, closing a question so that the person never sees it.
  Evidence: a ruleset can "Restrict deletions" and "Block force pushes", https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets#restrict-deletions; of GitHub's repository roles, only Admin can "Manage branch protection rules and repository rulesets", https://docs.github.com/en/organizations/managing-user-access-to-your-organizations-repositories/managing-repository-roles/repository-roles-for-an-organization#permissions-for-each-role; and `git push --force` replaces a branch even when the push loses commits, https://git-scm.com/docs/git-push
  Holds while: setup suggests the rule and does not set it, and the rule allows direct pushes.
  Paths: .agents/skills/inquisitor/

- **Constraint: GitHub's events API shows each citation push's pusher and time to anyone who can see the lore repository.**
  Because: the inquisitor pushes no citation to a lore repository more visible than the question's repository or, for a question about an organization or other group, the repository it was asked from, and a citation file pushed with a person's credentials holds only the entry's id and a date, so the lore repository's readers learn only who cited which entry and when.
  Evidence: GitHub's events API lists each push event's actor and time, https://docs.github.com/en/rest/activity/events
  Holds while: a citation is pushed with a person's own credentials, and never to a lore repository more visible than that.
  Paths: .agents/skills/inquisitor/scripts/inquisitor.py

- **Constraint: An agent in the person's session can have the `log` command write, as the person's, files the person never asked for: a decision, by passing their login as `answered_by` with no `answer_link`, or, through the session option meant only for the answer session, which the command does not check, a handled file closing a question, a hash-only miss file (an empty file whose presence alone lets an agent act on an automatic `Inquisitor: ` reply), or a log file recording a Linear or Discord message as the person's answer.**
  Because: that agent already holds the person's push access, so it could as well push any of these files itself, or commit a decision document that filter 1 counts, and closing these paths would protect nothing.
  Evidence: git pushes with the credentials its configured helper holds for the host, whichever program runs `git push`, https://git-scm.com/docs/gitcredentials, and `gh auth setup-git` makes gh that helper with the person's own login, https://cli.github.com/manual/gh_auth_setup-git
  Holds while: an agent in the person's session runs with the person's push access.
  Paths: .agents/skills/inquisitor/scripts/inquisitor.py

- **Constraint: Each rule that depends on igor states what holds once the igor change it needs lands, with no clause for igor before that change.**
  Because: igor has published no release, so no igor before that change is supported for such a clause to serve.
  Evidence: igor's releases page listed none on 2026-11-09, https://github.com/adamstallard/igor/releases
  Holds while: igor has published no release.
  Paths: openspec/specs/inquisitor/spec.md, openspec/specs/answer-session/spec.md

## Rationale

- **Rationale: A question is pushed to the questions branch of what it concerns.**
  Committed with the work, a question's file would be invisible to other work until that work merged, and lost if the work were abandoned; a general question would ride in an unrelated pull request; and an answer session could not write the answer, since it cannot commit to another agent's work branch. A branch of its own, pushed with no pull request, has none of these costs, and needs no review, since a question's authority comes from who answered it.
  The script commits with git's plumbing and never moves HEAD, because prose's and bug-hunter's hooks report each commit that lands on HEAD without their trailers, and these machine records carry none.
  Evidence: work committed on one branch is not in another branch's files until it is merged into it, https://git-scm.com/book/en/v2/Git-Branching-Basic-Branching-and-Merging
  Evidence: prose's and bug-hunter's hooks run their trailer checks after every Bash command, [prose's hook.json](../../../.agents/skills/prose/hook.json) and [bug-hunter's hook.json](../../../.agents/skills/bug-hunter/hook.json), and prose's check asks git whether HEAD moved, [check-commit-trailer.sh](../../../.agents/lib/commit-trailer/check-commit-trailer.sh)

- **Rationale: The Igor reads questions branches with the script.**
  A worker holds no GitHub credential, and counting a decision needs GitHub's answer on write access. The Igor already runs `gh`, `git` and `claude` as child processes, so the script is one more program run the same way, and igor needs no second implementation of the rules.
  Evidence: a worker's only credential is its seat's model-provider token, under igor's requirement *The worker is given an explicit environment holding no credential but its seat's*, https://github.com/adamstallard/igor/blob/7d969cd/openspec/specs/task-execution/spec.md#L333
  Evidence: igor runs `gh`, https://github.com/adamstallard/igor/blob/8478aec/src/gh.ts#L74, `claude`, https://github.com/adamstallard/igor/blob/8478aec/src/execute.ts#L961-L965, and `git`, https://github.com/adamstallard/igor/blob/8478aec/src/github.ts#L13

- **Rationale: A questions-branch decision counts only unchanged and by write access.**
  Write access is the authority to decide for a repository, and that authority covers the file as it was pushed, not a later edit: an edit can change the answer while `answered_by` still names the person who gave the first one. Requiring a signed commit would not show who answered either: git signs with the configured key whatever the commit holds, so a signed file says only whose key signed it.
  Evidence: `git commit -S` signs the commit with the committer's key, whatever its content, https://git-scm.com/docs/git-commit#Documentation/git-commit.txt--Sltkey-idgt

- **Rationale: A work-branch decision answers only its own work.**
  This entry explains one of the requirement's conditions: the branch must be in the repository itself, not a fork. Pushing a branch to the repository itself needs write access, and a fork's branch does not, so without that condition an outside contributor could commit a decision that stops the agent's questions.
  Evidence: GitHub's repository roles give the push permission only from the Write role up, https://docs.github.com/en/organizations/managing-user-access-to-your-organizations-repositories/managing-repository-roles/repository-roles-for-an-organization

- **Rationale: An answer recorded on a work branch counts for other work once it lands.**
  This entry explains the requirement's merged-pull-request condition. A log file pins its decision document to a commit on the work branch, and a squash or rebase merge puts new commits on the default branch in place of the branch's own, so that commit never becomes an ancestor of the default branch even once the work has landed.
  Evidence: GitHub's docs on pull request merges say a squash merge creates one new commit and a rebase merge rewrites each commit, https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/incorporating-changes-from-a-pull-request/about-pull-request-merges

- **Rationale: Filter 1 hides every lore entry outside the question's scope.**
  igor's lore-firing spec treats scope as visibility and status as review state: an out-of-scope entry is one the asker may not see, while only an `active` entry, one a person reviewed, reaches a worker unasked. So scope hides an entry from the search, and status only labels it, since a search's results are asked for and reach no worker unasked.
  igor and the inquisitor must read a lore entry's scope alike, and igor matches a `project:` scope by a repository's short name. A project whose repositories have other names would need a mapping file in the lore repository, read by both, which nothing provides. A collective's question concerns no repository, so no short name picks a `project:` entry for it, and it sees only `global` entries.
  Evidence: igor PR #216's lore-firing spec at 59e7561, https://github.com/adamstallard/igor/blob/59e75617ad5c650986717b4603fb549ef62d5c05/openspec/changes/lore-search/specs/lore-firing/spec.md#L3-L29
  Evidence: `scopeMatches` in igor's `src/firing.ts`, https://github.com/adamstallard/igor/blob/7d969cd/src/firing.ts#L40

- **Rationale: A run's lore search keeps to the Igor's lore repository and scope.**
  igor hides a `project:X` entry from a run whose item's repository is more visible than the repository `project:X` names, since a worker could otherwise repost what it read about a private repository into a more public item. So the inquisitor's scenario *Inside an Igor, a project entry matches any repository the role works*, under *Only an answer with authority stops a question*, sets the item's repository no more visible than that one: with a more visible item, the entry would be hidden.
  Evidence: igor PR #216's lore-firing spec at 59e7561, https://github.com/adamstallard/igor/blob/59e75617ad5c650986717b4603fb549ef62d5c05/openspec/changes/lore-search/specs/lore-firing/spec.md#L3-L29

- **Rationale: A log file and a miss file have one format.**
  Of this requirement, the scenario *Where an asked_in may be written* fixes one form for a Discord or Linear message's URL because the forms the surfaces give differ. Discord returns no URL for a message, only ids, so the asking agent and the answer session each build it; a message that starts a thread has two addresses, its parent channel's and one inside the thread, where a placeholder message points back to it; and `discordapp.com` answers 301 to the same path on `discord.com`. Linear returns a comment's URL with the issue's title slug, and renaming the issue changed that slug in every comment's URL, so a URL recorded before a rename would match nothing after it. This was measured on 2026-11-19 on a test Discord thread and a test Linear issue, and task 0.23 in the change's tasks.md holds the result.
  Evidence: the 2026-11-19 measurement, recorded in task 0.23, [tasks.md](../../changes/inquisitor/tasks.md)
  Evidence: Discord's message object carries `id` and `channel_id` and no URL, https://discord.com/developers/docs/resources/message#message-object

- **Rationale: A file is as new as the commit that added it, and supersedes only if it would count.**
  A commit's dates are whatever its committer sets, so they cannot order answers; the branch's commit order changes only when the branch is rewritten, a cost the Constraint on guarding a `questions` branch accepts.
  Evidence: the committer date is whatever the committer's environment sets, https://git-scm.com/docs/git-commit#_commit_information

- **Rationale: The script tells an Igor's run by IGOR_RUN.**
  The script matches the variable's exact name and value, since a prefix match would take a seat's token variable, `IGOR_RUN_TOKEN`, for a run marker.
  It prints that it runs as in an Igor's run every time it finds `IGOR_RUN` set to a run's value. A repository can set `IGOR_RUN` in a person's session, through the `env` key of committed Claude Code settings or a direnv `.envrc`. The script would then search lore only through `igor lore-search`, which a person's session lacks, and push to no questions branch, since in a run only the Igor pushes. Without the message, the person could not tell why.
  Evidence: igor PR #171 adds `IGOR_RUN_TOKEN`, https://github.com/adamstallard/igor/pull/171
  Evidence: Claude Code's project settings file, `.claude/settings.json`, is checked into source control and sets environment variables for each session through its `env` key, https://docs.anthropic.com/en/docs/claude-code/settings
  Evidence: direnv loads a directory's `.envrc` into the shell's environment on entering it, https://direnv.net/

- **Rationale: In an Igor's run, filter 1 searches through igor.**
  A worker's Bash permission is only its role's `commands`, the list of commands the role lets its worker run, and its HOME holds no `inquisitor.json` or `gh` login unless a developer set one up, which igor's deployment guide warns against for `gh`. igor PR #175's spec would also run the worker as a user of its own and make the lore checkout mode 0750, closed to that user, though this is unchecked, since #175 is not built. So a worker, lacking that configuration and login, cannot run the script's own lore search even if its role lists the script, and the filter 1 search it runs, by the skill's instructions, goes through `igor lore-search`, a command its role's `commands` must list. igor passes the worker no lore repository, only the item's worktree and the lore rendered into its system prompt, and injects the active entries in scope only when all of them fit a 4,000-token budget, and none when they do not, so injected lore alone is not enough for filter 1. igor's lore-firing spec forbids offering a worker a search tool, reasoning only that a worker needs none, which filter 1's search disproves; igor PR #216 removes that rule, so a worker may be offered `igor lore-search`.
  Evidence: igor's rule and its reasoning, https://github.com/adamstallard/igor/blob/59e75617ad5c650986717b4603fb549ef62d5c05/openspec/specs/lore-firing/spec.md#L5-L14, and #216's removal of it, https://github.com/adamstallard/igor/blob/59e75617ad5c650986717b4603fb549ef62d5c05/openspec/changes/lore-search/specs/lore-firing/spec.md#L1105-L1115
  Evidence: task 0.12, measured 2026-10-20: the worker's `allowedTools` are its role's `commands`, https://github.com/adamstallard/igor/blob/8478aec/src/execute.ts#L1607
  Evidence: its system prompt, `workerSystemPrompt`, https://github.com/adamstallard/igor/blob/8478aec/src/execute.ts#L161
  Evidence: the deployment guide on the service user's `gh` login, https://github.com/adamstallard/igor/blob/8478aec/docs/deployment.md#L112-L115
  Evidence: #175's design, the row for "the Igor's home, lore checkout, `/etc/igor`", https://github.com/adamstallard/igor/blob/908c149/openspec/changes/worker-user/design.md; the worker runs as `claude -p`, https://github.com/adamstallard/igor/blob/8478aec/src/execute.ts#L960-L970; the worker starts in the item's worktree with lore only in its system prompt, https://github.com/adamstallard/igor/blob/8478aec/src/execute.ts#L1595-L1609; and lore is injected whole or not at all under a 4,000-token budget, https://github.com/adamstallard/igor/blob/8478aec/src/firing.ts#L104-L130

- **Rationale: The log command records a linked GitHub comment's own text.**
  The agent passing an answer has read the thread around the comment, and untrusted text there can steer what it passes, so taking its copy would let a crafted thread record, under a person's name, words they never wrote. Fetching the comment through GitHub records what the comment says and who wrote it, whatever the agent passed; GitHub's `Comment` interface, which issue comments, reviews and review comments implement, documents the text as `body` and the writer as `author`.
  Evidence: OWASP names indirect prompt injection, content from external sources that "alters the behavior of the model in unintended or unexpected ways", https://genai.owasp.org/llmrisk/llm01-prompt-injection/
  Evidence: GitHub's GraphQL reference documents `body` and `author` on the `Comment` interface, https://docs.github.com/en/graphql/reference/interfaces#comment

- **Rationale: A lore decision record counts.**
  igor PR #202, open, specifies that igor's scribe puts a decision record in the repository the decision concerns, or in the team's lore repository when it spans repositories, so filter 1 reads both.
  Evidence: igor PR #202's decision 5, https://github.com/adamstallard/igor/pull/202

- **Rationale: A session with no person in it asks in a post, a handback or nowhere.**
  An Igor worker asks only through its Igor, in its handback comment or a file its Igor pushes, because igor gives it no credential that can post: its environment holds only its seat's token, the model-provider credential its work is charged to.
  Evidence: igor's requirement *The worker is given an explicit environment holding no credential but its seat's*, https://github.com/adamstallard/igor/blob/7d969cd/openspec/specs/task-execution/spec.md#L333

- **Rationale: A weakness is not described in public text before its advisory is published.**
  The rule lasts only until the advisory is published, because a rule with no end would leave a fix's commit message unable to say why the fix was made even after disclosure, which prose's rules require of every commit message's body.
  Evidence: prose's rule 14, "Commit subject says what changed; the body says why", https://github.com/adamstallard/shared-skills/blob/02c0a7782bc0392f5c1f5d8e3af0188cf84a9f0d/.agents/skills/prose/rules.md#L228

- **Rationale: A lore entry that stops a question gets a citation file.**
  igor's review never proposes as unused an entry an agent cited as the answer to a question, and reads those citations only from the lore repository's questions branch (igor PR #216's decisions 5 and 8), so without a citation file a use the inquisitor finds never keeps the entry from being proposed as unused. The citation files count uses inexactly. They miss a use whose question is more private than the lore repository, since a citation pushed there would show that the question exists. And one question gets a citation from each person's machine whose filter 1 stops it. That overcount can only keep an entry that might otherwise be proposed as unused.
  Evidence: igor PR #216's proposal, decisions 5 and 8, https://github.com/adamstallard/igor/blob/59e7561/openspec/changes/lore-search/proposal.md
  Evidence: that a citation shows its question exists: GitHub's events API shows each push's pusher and time to anyone who can see the repository, https://docs.github.com/en/rest/activity/events

- **Rationale: Questions in posts pass the same filters.**
  Exempting from the filters a post that carries igor's handback marker would let any agent that adds the marker skip vetting, and would help no real handback: the Igor posts each handback, which igor's specs call a handoff, through its own code, which no tool hook sees, and the worker holds no credential that could post one.
  Evidence: igor's graceful-handoff spec has the Igor post each handoff, https://github.com/adamstallard/igor/blob/7d969cd/openspec/specs/graceful-handoff/spec.md
  Evidence: igor's task-execution spec keeps the surface credential out of the worker's environment, https://github.com/adamstallard/igor/blob/7d969cd/openspec/specs/task-execution/spec.md

- **Rationale: A proposed lore entry's path, fields and id follow igor's rules.**
  Of this requirement, only its rule for "id taken" needs a reason beyond following igor. During a run the Igor, not its worker, proposes the run's lore entries. When an entry's id is already held by something outside the run's scope, igor reports only "id taken", without saying what holds it. If an entry holds it, another id would do; if a rejected candidate, a file under the lore repository's `rejected/`, holds it, the entry may not be proposed at all. The Igor cannot tell which, so it does not propose that entry under any id.
  Evidence: igor PR #216's decision 6, https://github.com/adamstallard/igor/blob/59e7561/openspec/changes/lore-search/proposal.md#L166-L180

- **Rationale: The two calls' files and records stay private.**
  A question's text can name what its asker wants kept private, so neither the files that carry it nor its verdict records may be readable by another user of the host. A file written with the usual umask of 022 gets mode 0644, which every user can read, so the script refuses a file or directory others can read rather than trust the default. A directory made by `mktemp -d` is the owner's alone, unlike the system's temporary directory, which every user shares.
  Evidence: umask(2): with the usual umask of 022, "0666 & ~022 = 0644; i.e., rw-r--r--", https://man7.org/linux/man-pages/man2/umask.2.html
  Evidence: mktemp(1) creates a directory with "u+rwx, minus umask restrictions", https://man7.org/linux/man-pages/man1/mktemp.1.html

- **Rationale: The log command takes its input in a private file.**
  A question's text and its answer passed as arguments would be readable by every user of the host, since each process's command line is.
  Evidence: proc(5): with the default `hidepid=0`, "Everybody may access all /proc/pid directories", https://man7.org/linux/man-pages/man5/proc.5.html
  Evidence: proc_pid_cmdline(5): `/proc/pid/cmdline` "holds the complete command line for the process", https://man7.org/linux/man-pages/man5/proc_pid_cmdline.5.html

- **Rationale: An Inquisitor reply is acted on only with its miss file.**
  The reply itself counts for nothing, because anyone can comment on a public repository, so without the file anyone could post a fake automatic reply such as `Inquisitor: filter 4` and have an agent decide for itself a question a maintainer should decide; only a writer, an account with write access, can push to a questions branch. A miss file that is not hash-only must also name a `said_by`. The Igor is a writer, but it pushes the files of its worker's and its own inquisitor runs, which item text anyone can write may steer; this spec has it push none of those holding `said_by` (*A file an Igor pushes names where it was asked from*), so none of them backs a reply.
  Evidence: GitHub's repository roles give the push permission only from the Write role up, while the Read role can comment on issues and pull requests, https://docs.github.com/en/organizations/managing-user-access-to-your-organizations-repositories/managing-repository-roles/repository-roles-for-an-organization
