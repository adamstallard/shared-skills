# answer-service: constraints, rejected alternatives and rationale

## Constraints

- **Constraint: Two guards stop only accidents: the inquisitor's post hook, and linear-app's refusal to hand a relay identity's token to a command that can print it. The same refusal, asked of github-app, would too. An agent set on forging a relayed answer can read a relay's credentials from the keychain and post with `curl`.**
  Because: each guard stops an agent that posts through the skills as the skills' instructions say, and an agent that works around them still has the person's own tools and keychain.
  Evidence: a `PreToolUse` hook sees a tool call's command line, never what a program it starts sends, https://docs.anthropic.com/en/docs/claude-code/hooks
  Holds while: a relay identity's credentials sit where the person's own agents can read them.
  Paths: .agents/skills/inquisitor/scripts/check-post.sh, .agents/skills/github-app/, .agents/skills/linear-app/

- **Constraint: While github-app hands a relay identity's token to a command that can print it, any agent on the person's machine can print that token and post `User says: ` with a plain HTTP call no post hook sees.**
  Because: the inquisitor asks github-app (adamstallard/shared-skills#96) to hand the token to no such command, and ships without that change; it would close github-app's own commands, though not the keychain path the constraint above accepts.
  Evidence: github-app's `token` command prints a raw token for programs, [github-app's SKILL.md](../../../.agents/skills/github-app/SKILL.md); its `gh` command runs gh with the App's token in `GH_TOKEN`, [github_app.py](../../../.agents/skills/github-app/scripts/github_app.py); with `GH_TOKEN` set, gh 2.103.2 printed that token through `gh auth token` and through a shell alias running `echo "$GH_TOKEN"` (measured 2026-11-20), https://cli.github.com/manual/gh_auth_token
  Holds while: github-app hands a relay identity's token to a command that can print it.
  Paths: .agents/skills/github-app/

- **Constraint: GitHub's events API shows the pusher and push time of each hash-only miss file, one with no keys named by a hash, to anyone who can see its questions branch, even where that branch is more visible than the miss's thread.**
  Because: the cost is accepted: anyone who matches a reply's id they already know against the file's name, a hash of the surface (GitHub, Linear or Discord) and that id, finds a reply only its thread's readers can see, so others learn only that the person judged some question then.
  Evidence: GitHub's events API lists each push event's actor and time, https://docs.github.com/en/rest/activity/events; GitHub answers 404 for a private repository's resource to someone without access, https://docs.github.com/en/rest/using-the-rest-api/troubleshooting-the-rest-api#404-not-found-for-an-existing-resource; Discord gives a message only to someone who can view its channel and read its history, https://discord.com/developers/docs/resources/message#get-channel-message; and Linear's API reads only with a member's credentials, https://linear.app/developers/graphql#authentication
  Holds while: the answer service pushes a hash-only miss file with the person's own credentials.
  Paths: .agents/skills/inquisitor/

- **Constraint: The session's Read, Grep and Glob have no path limit, so a crafted thread could steer the model into a draft that quotes a file on disk, such as a credential.**
  Because: the cost is accepted: the person reviews every draft before confirming it, and that review is the guard, beside the relay post's scan for token shapes.
  Evidence: Claude Code's Read, Grep and Glob reach any path unless a permission rule denies it, https://code.claude.com/docs/en/settings#permission-settings
  Holds while: the session's Read, Grep and Glob have no path limit, and nothing the model drafts is posted before the person confirms it.
  Paths: .agents/skills/inquisitor/

- **Constraint: Each rule that depends on igor states what holds once the igor change it needs lands, with no clause for igor before that change.**
  Because: igor has published no release, so no igor before that change is supported for such a clause to serve.
  Evidence: igor's releases page listed none on 2026-11-09, https://github.com/adamstallard/igor/releases
  Holds while: igor has published no release.
  Paths: openspec/specs/inquisitor/spec.md, openspec/specs/answer-service/spec.md

## Rejected

- **Rejected: A TLA+ model of the answer service's owed pushes and automatic posts.**
  Facing: [spec-check's SKILL.md](../../../.agents/skills/spec-check/SKILL.md) says "Write one when a requirement is about concurrency, ordering, a crash between two writes, or a protocol between processes", and the answer service has such requirements: a push it owes after a post survives a crash and is retried.
  Lost because: every outcome a model would find follows from the spec's own rules and is accepted. Each push is recorded as owed before its post, but the answer push needs the post's URL and the miss push the reply's id, so a crash before the service saves them drops that push: at worst the answer's relay post, which keeps the answer in its thread, gets no answer file, or the asker, finding no miss file behind the reply, takes it as input, as *A miss or citation file's push is owed and retried as a handled file's is* describes. A crash after a post but before the handled file, which closes the question, or the citation file owed for it is pushed leaves that push owed, to be made after the restart, so at worst the person meets the question again until then, or, when the push had landed before the crash, a second citation file counts one lore use too many. When two machines both post an automatic reply to one question, the later machine deletes its own post while its miss or citation pushes still go out, counting one miss, or one `Recorded answer: ` reply's lore citation, too many, and when its fetch or delete fails, or a crash comes before them, both posts stay. Two machines' pushes to one questions branch cannot overwrite each other, since git refuses a push that would drop the other's commit, https://git-scm.com/docs/git-push
  Instead: these gaps are accepted, and scenarios state the crash and two-machine cases the answer service handles.
  Paths: .agents/skills/inquisitor/

## Rationale

- **Rationale: An automatic post is deleted when another relay post came first.**
  Only an earlier post by the person's own relay identities, the bots that post for them, makes the service delete its automatic post, so two people's services answering one message both post. Counting any bot's prefixed post would let anyone who registers a bot, as any GitHub or Discord user can, suppress an automatic answer with a fake one.
  Evidence: anyone can register a GitHub App, https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/registering-a-github-app, or a Discord bot, https://discord.com/developers/docs/quick-start/getting-started

- **Rationale: The answer service reads with the person's credentials, except on Discord.**
  Reading with the person's own logins keeps a relay's token to the right to post, and the service reads nothing as a bot that the person can read as themselves. Discord is the exception because reading as the person there would mean automating their user account, which Discord forbids, so the relay's bot both reads and posts. The person's own Linear key, which the service reads Linear with, stays out of command arguments because every user of the host can read each process's command line.
  Evidence: Discord's Community Guidelines, which its Terms of Service incorporate, say "Do not use self-bots or user-bots. Each account must be associated with a human, not a bot.", https://discord.com/terms/guidelines
  Evidence: proc(5): with the default `hidepid=0`, "Everybody may access all /proc/pid directories", https://man7.org/linux/man-pages/man5/proc.5.html
  Evidence: proc_pid_cmdline(5): `/proc/pid/cmdline` "holds the complete command line for the process", https://man7.org/linux/man-pages/man5/proc_pid_cmdline.5.html

- **Rationale: The answer service polls only while it is open.**
  The skill runs nothing while the answer service is closed, and receiving pushed events would need something running then: GitHub and Linear deliver webhooks only to a URL they can reach at any time, and Discord pushes events only over a gateway connection kept open, so a push sent while the service is closed would be lost. Polling needs neither, and catches up on what came while the service was closed when it next opens.
  Evidence: GitHub delivers each webhook to a payload URL as an HTTP request, https://docs.github.com/en/webhooks/using-webhooks/creating-webhooks
  Evidence: Linear's webhooks need a publicly reachable HTTPS URL, https://linear.app/developers/webhooks
  Evidence: Discord's gateway is a persistent WebSocket connection, https://discord.com/developers/docs/events/gateway
  Evidence: on 2026-11-26, in Claude Code 2.1.332, a mod's 60-second `$.clock.every` timer kept firing on time in a session left idle with no terminal attached, recorded in task 0.19, [tasks.md](../../changes/inquisitor/tasks.md)
  Evidence: on 2026-11-26, the approved prototype's new-question alerts, raised only by its `$.clock.after` timers, chimed and showed while its session sat idle and the person was away, recorded in task 0.19, [tasks.md](../../changes/inquisitor/tasks.md), with the timer call at https://github.com/adamstallard/shared-skills/blob/a16c60d16c5a5af7a7a8b368413acbf1b43b3c38/answer-mod/hooks/register.tsx#L2165

- **Rationale: The service's model has no shell, no writing tool and no web fetch.**
  The threat is a crafted message in a subscribed channel steering the model into posting, or recording a decision, as the person. A hook that reads a tool call's command line cannot stop a model that has a shell: each of `eval`, an encoded string, a script it writes, `python3 -c` or `curl` with a token from the keychain runs what the hook never reads, which is why the post hooks guard only against accidents (this record's first Constraint, on the post hooks). A model with no shell and no tool that posts or writes can do none of it, so the worst an injection can do is propose a reply the person sees and confirms, or pick one of `record_verdict`'s fixed values. General web fetch is left out too, since a crafted message could have the model fetch an attacker's URL carrying private text from another thread. Claude Code must enforce the restriction itself, since a hook reading command lines would bring back the same gap: `--tools Read,Grep,Glob` removes every other built-in tool, and `--strict-mcp-config` every MCP server's. Neither removes another mod's tools, which the entry for *The answer mod strips other tools from the answer session* covers.
  Evidence: a `PreToolUse` hook sees a tool call's command line, never what a program it starts sends, https://docs.anthropic.com/en/docs/claude-code/hooks
  Evidence: on 2026-11-26, in Claude Code 2.1.332, a session started with `--tools Read,Grep,Glob` offered its model Glob, Grep and Read alone among the built-in tools, and kept every MCP server's tool unless `--strict-mcp-config` was added too, recorded in task 0.34, [tasks.md](../../changes/inquisitor/tasks.md)
  Evidence: OWASP lists disclosure of sensitive information and exfiltration among prompt injection's impacts, and as mitigations restricting the model's privileges to the minimum and running privileged functions in the application's own code, https://genai.owasp.org/llmrisk/llm01-prompt-injection/

- **Rationale: The model's judgements reach the service's code only through record_verdict.**
  With no shell, the model's only outputs are its conversation and the tools the mod gives it, so the service's code needs a tool to learn what the model judged. The code puts each message before the model as a prompt of its own and acts once that turn ends, which a mod can do unattended. A free-text verdict would let a crafted thread steer the model into writing something the code then acts on; fixed fields, checked by the code, limit the worst such a thread can do to picking among the actions the code already offers.
  Evidence: OWASP lists, among prompt injection's mitigations, "Define and validate expected output formats", using "deterministic code to validate adherence to these formats", https://genai.owasp.org/llmrisk/llm01-prompt-injection/
  Evidence: on 2026-11-26, in Claude Code 2.1.332, a mod's `$.prompt.submit` started a turn in an idle session with no terminal attached, the model answered it by calling the mod's tool, and the mod's `turn.complete` hook saw the turn end, recorded in task 0.37, [tasks.md](../../changes/inquisitor/tasks.md)

- **Rationale: Claude's draft goes to the prompt box, never to a post.**
  The model reads untrusted thread text, which can steer it to write what the person would not say, so its draft goes where the person reads it before anything is sent, never straight to a post. `propose_reply` also refuses a call carrying an `agentId`, so that only the conversation the person is talking to fills their prompt box. Claude Code is taken to set one on a subagent's call to a mod's tool, as it sets `agent_id` on a subagent's hook events, and task 0.39 checks it; a subagent's call without one still lands only in the prompt box.
  Evidence: OWASP names indirect prompt injection, content from external sources that "alters the behavior of the model in unintended or unexpected ways", https://genai.owasp.org/llmrisk/llm01-prompt-injection/
  Evidence: Claude Code's hooks reference says a subagent's tool events carry "the `agent_id` and `agent_type` common input fields that identify the subagent", https://code.claude.com/docs/en/hooks

- **Rationale: An agent's question comes from a bot account or a log file.**
  A message counts as a bot account's by a mark the surface, not the account, sets on its author. On Linear an app user's comment has `user.app` `true`, with a null `botActor`, so a reader checking `botActor` would count every agent as a person; on Discord a bot's message has `author.bot` `true`, and a person's user object has no `bot` key. Of 77 comments in a test team, the 5 an app identity posted had `user.app` `true` and the other 72 `false`, and every message a bot posted in a test thread had `author.bot` `true`. That a person's Linear account cannot take on `app` rests only on the schema's description, untested, and a Discord webhook's message is not measured. On GitHub an App's comment has `user.type` `Bot` and a login of its slug followed by `[bot]`, which no account can take on, since a username holds only alphanumeric characters and dashes.
  Evidence: Linear's GraphQL schema describes `User.app` as "Whether this account represents an installed application rather than a person", https://linear.app/developers/graphql
  Evidence: Discord documents `bot` on its user object, https://discord.com/developers/docs/resources/user#user-object
  Evidence: the 2026-11-19 measurements, recorded in tasks 0.16 and 0.17, [tasks.md](../../changes/inquisitor/tasks.md)
  Evidence: on 2026-11-26, the 174 comments carrying a `performed_via_github_app` among the 300 newest issue comments of three public repositories all had `user.type` `Bot` and a login ending `[bot]`, and none of the 126 without one did, recorded in task 0.21, [tasks.md](../../changes/inquisitor/tasks.md)
  Evidence: GitHub documents that "Usernames for user accounts on GitHub can only contain alphanumeric characters and dashes", https://docs.github.com/en/enterprise-cloud@latest/admin/managing-iam/iam-configuration-reference/username-considerations-for-external-authentication

- **Rationale: A mention names a user outside code, quotes and links.**
  This entry explains reading a Linear mention by user id. A Linear comment's `body` holds a mention only as `@<displayName>`, and a user can change their display name, so a mention read from `body` stops naming its user after a rename and can name whoever takes the name next. The mentioned user's id is only in `bodyData`.
  Evidence: the 2026-11-19 measurement recorded in task 0.16, [tasks.md](../../changes/inquisitor/tasks.md)
  Evidence: Linear's GraphQL schema lets `UserUpdateInput` set a user's `displayName`, https://github.com/linear/linear/blob/master/packages/sdk/src/schema.graphql

- **Rationale: The poll reads every GitHub question source.**
  The poll reads each subscribed repository's issues, pull requests and their comments, so it costs rate-limited requests for every subscribed repository, including every repository of a subscribed owner, such as an organization. Reading notifications alone could miss a question: unless the person watches the whole repository, GitHub notifies them only for a thread they take part in or are asked to review. Their relay is the bot account that posts for them, which an asker may tag in place of the person, and a mention of it in a thread the person never joined reaches them through no notification. The full read makes at least three requests per repository each minute, for its issues and pull requests, their comments and their review-thread comments, plus one per open pull request for its reviews, against 5,000 an hour that the person's `gh` login shares with their agents: at 180 requests an hour each, about 27 repositories use it all before counting pull requests. So each list is read with its last `ETag`, since a `304` does not count against the limit, and a refused poll waits for the reset time instead of retrying.
  Evidence: GitHub's notification reasons, https://docs.github.com/en/rest/activity/notifications#about-notification-reasons
  Evidence: the REST rate limit these reads count against, which GitHub documents as 5,000 requests an hour for a user, https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api
  Evidence: GitHub documents that a conditional request answered `304` while correctly authorised does not count against the primary rate limit, and that a request refused for it should not be retried before the `x-ratelimit-reset` time, https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api
  Evidence: on 2026-11-26, five conditional requests that GitHub answered `304` left the `gh` login's `x-ratelimit-used` unchanged, and the next unconditional request raised it by 1, recorded in task 0.15, [tasks.md](../../changes/inquisitor/tasks.md)

- **Rationale: The answer service's filter 1 reads only subscribed and lore repositories.**
  Decision documents and questions-branch files are files, so searching them needs a copy on the machine, and the service keeps a copy only of each subscribed repository and each configured lore repository. Filter 1 also reads issues, which need no copy since they are read live, but with the person's credentials. Any other repository a question names is chosen by the question's own text, so fetching its files or reading its issues would let a crafted question choose which repository, a private one included, the service reads with the person's credentials and puts before the model. So one closed set covers everything filter 1 reads for the service. A question about a repository outside the set still comes to the person, so the set costs a recorded answer from that repository, never the question.
  Evidence: `git fetch` downloads a repository's objects before any of its files can be read on the machine, https://git-scm.com/docs/git-fetch
  Evidence: GitHub returns a private repository's issues to any request authenticated as a person who can read that repository, https://docs.github.com/en/rest/issues/issues#get-an-issue
  Evidence: OWASP lists, among prompt injection's mitigations, restricting the model's privileges to the minimum it needs, https://genai.owasp.org/llmrisk/llm01-prompt-injection/

- **Rationale: A handback that mentions no one goes to the item's assignee.**
  An Igor claims an item assigned to a person only when that person hands it over, so the assignee gave the Igor the work and is the right reader for its question.
  Evidence: igor's work-claiming requirement *An item someone else holds is not claimed*, under which an Igor claims an item assigned to a person only once the item's holder field, Linear's delegate or GitHub's `igor:` label, names that Igor, https://github.com/adamstallard/igor/blob/7d969cd6ab7820e143c2802a9ead44b3a91332b0/openspec/specs/work-claiming/spec.md#L465

- **Rationale: A handback is an Igor's comment holding igor's marker.**
  An Igor claims Linear items as well as GitHub ones, so it hands back on Linear too. If an Igor's Linear comment were never a handback, it would be an ordinary bot message, so one that mentions no one reaches every subscriber with write access, not the assignee who handed the Igor the work.
  Evidence: igor's work-claiming requirement *An item someone else holds is not claimed*, under which an Igor claims a Linear item once Linear's delegate field names it, https://github.com/adamstallard/igor/blob/7d969cd6ab7820e143c2802a9ead44b3a91332b0/openspec/specs/work-claiming/spec.md#L465

- **Rationale: Setup suggests a rule guarding each questions branch.**
  Without a rule blocking force pushes and deletion, a writer can rewrite or delete a `questions` branch, dropping a newer answer so that an older one counts again. Two gaps are accepted. Where no admin has set the rule, that stays possible, since only an admin can set it. Even with it, a writer can push a handled file, which closes a logged question so the answer service stops showing it, to any questions branch of a repository they can write to, since the rule must allow the direct pushes every record needs.
  Evidence: a ruleset can "Restrict deletions" and "Block force pushes", https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets#restrict-deletions; of GitHub's repository roles, only Admin can "Manage branch protection rules and repository rulesets", https://docs.github.com/en/organizations/managing-user-access-to-your-organizations-repositories/managing-repository-roles/repository-roles-for-an-organization#permissions-for-each-role; and `git push --force` replaces a branch even when the push loses commits, https://git-scm.com/docs/git-push

- **Rationale: Setup checks each relay identity before its channels are used.**
  The Discord relay reads messages that do not mention the bot, which needs Discord's privileged Message Content intent, so setup checks that `messageContent` is `true`. discord-bot's setup has the person turn the intent on, and its `check` reports `messageContent` from the bot's application flags.
  Evidence: Discord documents Message Content as a privileged intent, https://discord.com/developers/docs/events/gateway#message-content-intent
  Evidence: discord-bot's setup turns it on, https://github.com/adamstallard/shared-skills/commit/369ae16d02898cd68ba98241a7ee685b6492002c; its `check` reads it from the application's flags, https://github.com/adamstallard/shared-skills/commit/f83b167e6b52f8ad7f607bed6133b2d0e19fea6c

- **Rationale: A question with a person-required line gets no filter 2 to 4 reply.**
  The service finds the line by its fixed wording once markup is reduced, which works only where a surface returns the words as posted. Task 0.23 found on 2026-11-19 that Linear returns a comment's text unchanged, and escapes `[` only in an issue description, so the line in a Linear comment comes back unchanged; task 0.28 checks the line itself on Linear and Discord.
  Evidence: the 2026-11-19 measurement, recorded in task 0.23, [tasks.md](../../changes/inquisitor/tasks.md)

- **Rationale: A relay post is posted by a host command, unvetted.**
  A relay post carries words the person already confirmed, or a fixed text of the answer service's own, so no hook may block or reword it; a command the answer mod runs on the host is not a tool call, so no `PreToolUse` hook, the post hooks included, sees it.
  Evidence: on 2026-11-26, in Claude Code 2.1.332, a command a mod ran through `$.process.run` reached no `PreToolUse` hook, while the same hook saw the model's own Bash call, recorded in task 0.18, [tasks.md](../../changes/inquisitor/tasks.md)

- **Rationale: One answer service runs on each machine.**
  This entry explains the lock's refresh. The lock, which keeps a second answer service on the machine from opening, is refreshed by the answer mod's own timer. The timer must keep running while the person is away, or another session would find a live session's lock stale and take it.
  Evidence: on 2026-11-26, in Claude Code 2.1.332, a mod's 30-second `$.clock.every` timer kept firing on time in a session left idle with no terminal attached, recorded in task 0.19, [tasks.md](../../changes/inquisitor/tasks.md)

- **Rationale: propose_reply refuses a draft the prompt box would run.**
  Only `/` makes the prompt box run a filled draft as a command, when the word after it names a command; every `/` draft is refused, since whether a word names a command changes with the person's installed skills and commands. A draft starting `!` reaches the model as text, and the answer session's model has no shell to run it with.
  Evidence: on 2026-11-26, in Claude Code 2.1.332, each of the 95 printable ASCII characters was filled into the prompt box as a draft's first character and submitted, and only `/` followed by a word ran as a command, recorded in task 0.37, [tasks.md](../../changes/inquisitor/tasks.md)

- **Rationale: An item that asks the person something is shown once.**
  This entry explains dating a re-requested review. Each request has its own timeline event, so a review requested again after the item's questions were answered is dated after them and shown again.
  Evidence: on 2026-11-26, cli/cli pull request #15141, whose reviewer was re-requested after reviewing, listed a second `review_requested` timeline event, dated after the review, recorded in task 0.11, [tasks.md](../../changes/inquisitor/tasks.md)

- **Rationale: The answer service opens only beside its own tools.**
  `--tools` and `--strict-mcp-config` restrict built-in and MCP tools only, so a plugin's tool (a mod is a plugin) stays in the session until the answer mod strips it, and a mod loaded before the answer mod can add its tool back after the strip. So the hook does not replace the check. A mod can register a tool at any time after the session starts, which is why a tool that joins later ends the session (*A tool joining an open answer service ends the session*). The hook strips built-in tools too, so a session given the answer marker without the launcher's restriction, such as by a repository's committed settings through their `env`, is left with only the allowed tools.
  Evidence: on 2026-11-26, in Claude Code 2.1.332, a test mod's registered tool, and the built-in easel plugin's, stayed in a session started with `--tools Read,Grep,Glob --strict-mcp-config`; a mod read the whole list through `$.tool.list()` and a `tool.list` hook; under the launcher's flags, a mod's tool registered 8 seconds after start joined the list and the hook saw it; and a session run without those flags listed Bash, recorded in task 0.34, [tasks.md](../../changes/inquisitor/tasks.md)
  Evidence: on 2026-11-26, a mod loaded before a test answer mod re-added its tool after the test mod's hook stripped it, and the model called that tool; in a session started with no `--tools`, the hook stripped Bash and Write, recorded in task 0.41, [tasks.md](../../changes/inquisitor/tasks.md)

- **Rationale: The answer mod strips other tools from the answer session.**
  The hook removes every other tool, including one registered after start, and needs no list of plugins, so a plugin installed later is covered, and it changes nothing of another plugin but its tools. Turning plugins off through `--settings` `enabledPlugins`, or removing their tools with `--disallowedTools`, takes each plugin by id, since neither has a rule for "every plugin but one", and `--disallowedTools` must be passed again on every resume.
  Evidence: on 2026-11-26, in Claude Code 2.1.332, a test answer mod's `tool.list` hook removed another mod's tools, one registered 6 seconds after start included, and the built-in easel plugin's, at start and on resume, recorded in task 0.41, [tasks.md](../../changes/inquisitor/tasks.md)
  Evidence: on 2026-11-26, `enabledPlugins` with a `"*"` key turned nothing off, recorded in task 0.30, and `--disallowedTools mcp__*` removed the answer mod's own tool too, recorded in task 0.41, [tasks.md](../../changes/inquisitor/tasks.md)

- **Rationale: A tool joining an open answer service ends the session.**
  A tool registered mid-turn reaches the model within that turn, so ending the session alone would let the running turn call it; aborting the turn first closes that gap, and a mod can do both.
  Evidence: on 2026-11-26, in Claude Code 2.1.332, a tool a mod registered while a turn waited on another tool was offered within that turn and called; a mod calling `$.turn.abort` and then `$.command.run` of `exit` as the tool joined ended the session 32 ms later, before the tool was called, recorded in task 0.30, [tasks.md](../../changes/inquisitor/tasks.md)

