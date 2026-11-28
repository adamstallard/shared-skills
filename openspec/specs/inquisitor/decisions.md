# inquisitor: constraints, rejected alternatives and rationale

## Constraints

- **Constraint: An agent in the person's session can have the `log` command write, as the person's, files the person never asked for: a decision, by passing their login as `answered_by` with no `answer_link`; and, by passing the service option, which is meant only for the answer service and whose caller the command does not check, a handled file closing a question, a miss file named by a reply's id (which lets the asking agent act on an automatic `Inquisitor: ` reply as one a person backed), or a log file recording any GitHub comment, or a Linear or Discord message, as the person's answer.**
  Because: that agent already holds the person's push access, so it could as well push any of these files itself, or commit a decision document that filter 1 counts, and closing these paths would protect nothing.
  Evidence: `gh api` makes each request with the login `gh auth login` stored, whichever program runs it, https://cli.github.com/manual/gh_auth_login, and `gh auth setup-git` makes gh git's credential helper with that same login, https://cli.github.com/manual/gh_auth_setup-git
  Holds while: an agent in the person's session runs with the person's push access.
  Paths: .agents/skills/inquisitor/scripts/inquisitor.py

- **Constraint: Each rule that depends on igor states what holds once the igor change it needs lands, with no clause for igor before that change.**
  Because: igor has published no release, so no igor before that change is supported for such a clause to serve.
  Evidence: igor's releases page listed none on 2026-11-09, https://github.com/adamstallard/igor/releases
  Holds while: igor has published no release.
  Paths: openspec/specs/inquisitor/spec.md, openspec/specs/answer-service/spec.md

## Rationale

- **Rationale: A question is pushed to the questions branch of what it concerns.**
  Committed with the work, a question's file would be invisible to other work until that work merged, and lost if the work were abandoned; a general question would ride in an unrelated pull request; and an answer service could not write the answer, since it cannot commit to another agent's work branch. A branch of its own, pushed with no pull request, has none of these costs, and needs no review, since a question's authority comes from who answered it.
  The script commits through GitHub's API and never moves HEAD, because prose's and bug-hunter's hooks report each commit that lands on HEAD without their trailers, and these machine records carry none.
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
  The scenario *Where an asked_in may be written*, under this requirement, fixes one form for a Discord or Linear message's URL, the Linear one with no title slug, because each surface gives a message's URL in more than one form, or none. Discord returns no URL for a message, only ids, so the asking agent and the answer service each build it; a message that starts a thread has two addresses, its parent channel's and one inside the thread, which holds a placeholder message pointing back to the original; and `discordapp.com` answers 301 to the same path on `discord.com`. Linear returns a comment's URL with the issue's title slug, and renaming the issue changed that slug in every comment's URL, so a URL recorded before a rename would match nothing after it. For GitHub it fixes the form that REST and GraphQL both gave each comment and review read, and that `gh issue comment` printed too.
  Evidence: the 2026-11-19 measurement, recorded in task 0.23, [tasks.md](../../changes/inquisitor/tasks.md)
  Evidence: the 2026-11-26 GitHub measurements, recorded in task 0.23, [tasks.md](../../changes/inquisitor/tasks.md)
  Evidence: Discord's message object carries `id` and `channel_id` and no URL, https://discord.com/developers/docs/resources/message#message-object

- **Rationale: A file is as new as the commit that added it, and supersedes only if it would count.**
  A commit's dates are whatever its committer sets, so they cannot order answers. The branch's commit order changes only when the branch is rewritten, which a writer can do wherever no admin has set the rule that setup suggests, a cost the answer-service decision record's *Rationale: Setup suggests a rule guarding each questions branch* accepts. A file that would not count supersedes nothing, so pushing an `input` file, or one answered by someone without write access, cannot hide an answer that counts.
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
  Evidence: task 0.11's measurements, which found an issue comment's author in GraphQL's `IssueComment` as `author { login }` on 2026-11-04, and on 2026-11-26 the text and author of each of 95 reviews and 35 review comments in a public repository, through GraphQL, and their authors through REST, [tasks.md](../../changes/inquisitor/tasks.md)

- **Rationale: The log command takes answered_by from the linked comment.**
  The command adds `[bot]` to a bot author's login so that the login never passes as a person's: a login holding `[bot]` fails the login syntax check of *A candidate or login that cannot be checked is skipped*, which shows the answer as input, while the bare slug GraphQL gives would pass as a person's login.
  Evidence: a measurement on 2026-11-23 of an App's issue comment, which GraphQL gave as `author { __typename: "Bot", login: "<slug>" }` and REST as `user.login` `<slug>[bot]`, recorded under task 0.11 in [tasks.md](../../changes/inquisitor/tasks.md)

- **Rationale: A lore decision record counts.**
  igor PR #202, open, specifies that igor's scribe puts a decision record in the repository the decision concerns, or in the team's lore repository when it spans repositories, so filter 1 reads both.
  Evidence: igor PR #202's decision 5, https://github.com/adamstallard/igor/pull/202

- **Rationale: A session with no person in it asks in a post, a handback or nowhere.**
  An Igor worker asks only through its Igor, in its handback comment or a file its Igor pushes, because igor gives it no credential that can post: its environment holds only its seat's token, the model-provider credential its work is charged to.
  The script tells a session with a person in it by `CLAUDE_CODE_SESSION_ATTENDED`, which Claude Code sets to `1` in an interactive session, its subagents and forks included, and to `0` under `claude -p`, while `CLAUDECODE` and `CLAUDE_CODE_CHILD_SESSION` are set in both. The variable shows that an interactive session is open, not that someone is watching it.
  Evidence: igor's requirement *The worker is given an explicit environment holding no credential but its seat's*, https://github.com/adamstallard/igor/blob/7d969cd/openspec/specs/task-execution/spec.md#L333
  Evidence: on 2026-11-27, in Claude Code 2.1.332, `CLAUDE_CODE_SESSION_ATTENDED` was `1` in an interactive session left detached in tmux, in its subagent and in its fork, and `0` under `claude -p`, recorded in task 0.9, [tasks.md](../../changes/inquisitor/tasks.md)

- **Rationale: A weakness is not described in public text before its advisory is published.**
  The rule lasts only until the advisory is published, because a rule with no end would leave a fix's commit message unable to say why the fix was made even after disclosure, which prose's rules require of every commit message's body.
  Evidence: prose's rule 14, "Commit subject says what changed; the body says why", https://github.com/adamstallard/shared-skills/blob/02c0a7782bc0392f5c1f5d8e3af0188cf84a9f0d/.agents/skills/prose/rules.md#L228

- **Rationale: A lore entry that stops a question gets a citation file.**
  igor's review never proposes as unused an entry an agent cited as the answer to a question, and reads those citations only from the lore repository's questions branch (igor PR #216's decisions 5 and 8), so without a citation file a use the inquisitor finds never keeps the entry from being proposed as unused. A citation file holds only an entry id the lore repository already shows and a date, in a commit whose author and message name no person; pushing it shows, besides, only who pushed it and when. So no visibility bar applies: a question more private than the lore repository is still cited, and its use counted. A question with a category gets none: its subject, a vulnerability, a secret or a personal matter, is sensitive enough that pairing the pusher with the entry could give it away. One question met in several sessions, such as by several people's agents, gets a citation from each; that overcount can only keep an entry that might otherwise be proposed as unused.
  Evidence: igor PR #216's proposal, decisions 5 and 8, https://github.com/adamstallard/igor/blob/59e7561/openspec/changes/lore-search/proposal.md
  Evidence: a citation file's fields and commit, as the inquisitor spec's *A citation file has one format* sets them, [spec.md](../../changes/inquisitor/specs/inquisitor/spec.md)
  Evidence: what pushing shows: GitHub's events API shows each push's pusher and time to anyone who can see the repository, https://docs.github.com/en/rest/activity/events

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
  The reply itself counts for nothing, because anyone can comment on a public repository, so without the file anyone could post a fake automatic reply such as `Inquisitor: filter 4` and have an agent decide for itself a question a maintainer should decide; only a writer, an account with write access, can push to a questions branch. A miss file backs a reply only when a person stands behind it: its `said_by` names the person who judged the question, or it is hash-only. Only the `log` command's service option writes a hash-only file, whose one intended caller is the answer service the person runs; an agent that passes it anyway already holds the person's push access, as the Constraint on the `log` command says. The Igor is a writer, but it pushes the files of its worker's and its own inquisitor runs, runs that may be steered by item text, which anyone can write; the inquisitor spec has it push neither a hash-only file nor one naming a `said_by` (*A file an Igor pushes names where it was asked from*), so none of its files backs a reply.
  Evidence: GitHub's repository roles give the push permission only from the Write role up, while the Read role can comment on issues and pull requests, https://docs.github.com/en/organizations/managing-user-access-to-your-organizations-repositories/managing-repository-roles/repository-roles-for-an-organization

- **Rationale: A hook blocks a picker question that was not vetted.**
  The hook can hold the picker to vetted questions only because Claude Code runs it before the picker opens, an exit 2 stops the call with the hook's message reaching the model, and the call's input holds each question's text, to match against the verdict a second call recorded for it.
  Evidence: Claude Code's hooks reference documents that exit code 2 from a `PreToolUse` hook blocks the call and feeds stderr to Claude, https://code.claude.com/docs/en/hooks
  Evidence: on 2026-11-26, in Claude Code 2.1.332, a `PreToolUse` hook on `AskUserQuestion` that exited 2 ran before any picker opened, blocked the call, and the model quoted its stderr; its input held `questions[].question` and `questions[].options[].label`, recorded in tasks 0.1 to 0.3, [tasks.md](../../changes/inquisitor/tasks.md)

- **Rationale: The credential patterns are a closed list of token shapes.**
  This entry explains the Discord bot token's shape, which no prefix marks, so the pattern rests on the lengths of its three parts.
  Evidence: on 2026-11-26 the pattern matched the token discord-bot holds as a whole, three URL-safe base64 parts of 26, 6 and 38 characters, recorded in task 0.33, [tasks.md](../../changes/inquisitor/tasks.md)

- **Rationale: A question in a post tags one person who can decide, if there is one.**
  This entry explains how two candidates are found. The approver is found from the decision's file through blame, each blamed commit's pull request and that pull request's approving review; a pull request merged with no approving review, as where approval is given by comment or the owner authors every pull request, gives no approver, and the candidate is skipped.
  The last commit's author is found by login: git records a commit's author as a name and an email, so GitHub gives a login only for a commit it links to an account, and a commit it links to none gives no login and its candidate is skipped.
  Evidence: on 2026-11-27, one GraphQL blame query per file led every blamed commit to its merged pull request: 18 of 22 pull requests behind a kubernetes/enhancements KEP had an `APPROVED` review naming the approver, and the other 4, approved through Prow `/approve` comments, had none, as had all 21 behind a shared-skills file whose owner authors every pull request, recorded in task 0.8, [tasks.md](../../changes/inquisitor/tasks.md)
  Evidence: on 2026-11-26, GitHub's commits listing for a file gave `author` `null` for 2 of the 30 newest commits to cli/cli's `README.md`, and a login for the rest, recorded in task 0.5, [tasks.md](../../changes/inquisitor/tasks.md)

- **Rationale: Every miss file is named by one hash.**
  This entry explains naming a GitHub reply's miss file by its `node_id`: the id must be the same in REST and GraphQL, present on every comment kind the answer service replies to, and unchanged by an edit, or an asking agent and the answer service would compute different names for one reply.
  Evidence: on 2026-11-26, all 102 issue, pull request and review comments read on cli/cli had a REST `node_id` equal to GraphQL's `id`, and the 3 edited after posting kept it, recorded in task 0.31, [tasks.md](../../changes/inquisitor/tasks.md)

- **Rationale: A permission that cannot be read is no write access.**
  GitHub shows a collaborator's permission only to a caller with push access, so wherever the agent lacks it no answer counts by write access. For an App's `<slug>[bot]` login GitHub answers `none`, even for an App that pushes to the repository, so a pull request or issue an App opened never has an author with write access.
  Evidence: on 2026-11-27, with gh 2.103.2, `GET repos/<owner>/<repo>/collaborators/<login>/permission` answered `403` "Must have push access to view collaborator permission." on cli/cli, where the caller could only read, for every login tried, and `404` for a login that does not exist; as an admin, it answered `200` `none` with `user.type` `Bot` for an App that had authored a pull request and pushed its commit, recorded in task 0.4, [tasks.md](../../changes/inquisitor/tasks.md)

- **Rationale: A post goes out as a GitHub App only through github-app's commands.**
  Only github-app's commands that send a request with the App's installation token, such as `gh` and `run`, post as the App; `wire` and `env` set `GITHUB_APP_ACT_AS` and `GIT_AUTHOR_NAME` but no token, so a plain `gh` post in a wired project goes out as the person, and counting it as the App's would tag the person on their own post. The identity such a command acts as shows only on its command line, which the script never reads, so the agent passes it; its `<identity>.bot.json` in github-app's state folder holds its `<slug>[bot]` login.
  Evidence: `agent_env`, the one source of `env`, `run` and `wire`'s variables, sets `GITHUB_APP_ACT_AS` and `GIT_AUTHOR_NAME` and no token, and only `run`, which github-app's own `gh` command calls, adds `GH_TOKEN`, read at 48370e0, [github_app.py](../../../.agents/skills/github-app/scripts/github_app.py); for each of the two identities task 0.7 tried, the `bot.json` name was the slug `GET /app` returned, followed by `[bot]`, and a plain `gh` post goes out as `gh api user`'s login, recorded in task 0.7, [tasks.md](../../changes/inquisitor/tasks.md)
