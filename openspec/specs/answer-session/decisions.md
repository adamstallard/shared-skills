# answer-session: constraints, rejected alternatives and rationale

## Constraints

- **Constraint: The inquisitor's GitHub post hook and the refusals asked of github-app for a relay identity guard against accidents, not against an agent set on forging a relayed answer, which can read a relay's credentials from the keychain and post with `curl`.**
  Because: the hook stops an agent that uses the skills, as its instructions tell it, and one that works around them has its person's own tools and keychain.
  Evidence: a `PreToolUse` hook sees a tool call's command line, never what a program it starts sends, https://docs.anthropic.com/en/docs/claude-code/hooks
  Holds while: a relay identity's key sits where the person's own agents can read it.
  Paths: .agents/skills/inquisitor/scripts/check-post.sh, .agents/skills/github-app/

- **Constraint: Until github-app refuses `token`, `run`, `credential get` and `wire` for a relay identity, any agent on the person's machine can print a relay App's token and post `User says: ` with a plain HTTP call no post hook sees.**
  Because: the inquisitor asks github-app for those refusals and ships without them; they would close the skill's own commands, though not the keychain path the constraint above accepts.
  Evidence: github-app's `token` command prints a raw token for programs, [github-app's SKILL.md](../../../.agents/skills/github-app/SKILL.md)
  Holds while: github-app hands a relay identity's token to a command.
  Paths: .agents/skills/github-app/

- **Constraint: Nothing is designed or built for the answer session outside Claude Code's fullscreen layout.**
  Because: the only layout the answer session's prototype has been built and used in is the fullscreen one, so no other layout has a design to build from, and `/answer` typed in another layout shows the session there as it comes, untried.
  Evidence: the approved prototype build v0.1-33 is a fullscreen layout, tag [`answer-session-ui-approved-v0.1-33`](https://github.com/adamstallard/shared-skills/tree/answer-session-ui-approved-v0.1-33) (commit fc3c35f)
  Holds while: the approved layout is the fullscreen one.
  Paths: .agents/skills/inquisitor/

- **Constraint: GitHub's events API shows the pusher and push time of each hash-only miss file, one with no keys named by a hash, to anyone who can see its questions branch, even where that branch is more visible than the miss's thread.**
  Because: the cost is accepted: anyone who recovers the reply's id from the file's name, a hash of the surface (GitHub, Linear or Discord) and that id, finds a reply only its thread's readers can see, so others learn only that the person judged some question then.
  Evidence: GitHub's events API lists each push event's actor and time, https://docs.github.com/en/rest/activity/events; GitHub answers 404 for a private repository's resource to someone without access, https://docs.github.com/en/rest/using-the-rest-api/troubleshooting-the-rest-api#404-not-found-for-an-existing-resource; Discord gives a message only to someone who can view its channel and read its history, https://discord.com/developers/docs/resources/message#get-channel-message; and Linear's API reads only with a member's credentials, https://linear.app/developers/graphql#authentication
  Holds while: the answer session pushes a hash-only miss file with the person's own credentials.
  Paths: .agents/skills/inquisitor/

- **Constraint: The session's Read, Grep and Glob have no path limit, so a crafted thread could steer the model into a draft that quotes a file on disk, such as a credential.**
  Because: the cost is accepted: the person reviews every draft before confirming it, and that review is the guard, beside the relay post's scan for token shapes.
  Evidence: Claude Code's Read, Grep and Glob reach any path unless a permission rule denies it, https://code.claude.com/docs/en/settings#permission-settings
  Holds while: the session's Read, Grep and Glob have no path limit, and nothing the model drafts is posted before the person confirms it.
  Paths: .agents/skills/inquisitor/

- **Constraint: A `questions` branch is guarded against rewriting and deletion only where an admin of its repository sets the rule setup suggests.**
  Because: setting a branch rule takes admin access, which a person subscribing to the repository may lack, and the rule must allow the direct pushes every record needs, so the cost is accepted that a writer can delete or rewrite a branch without the rule, dropping a newer answer so that an older one counts again, and can push a handled file to any branch, closing a question so that the person never sees it.
  Evidence: a ruleset can "Restrict deletions" and "Block force pushes", https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets#restrict-deletions; of GitHub's repository roles, only Admin can "Manage branch protection rules and repository rulesets", https://docs.github.com/en/organizations/managing-user-access-to-your-organizations-repositories/managing-repository-roles/repository-roles-for-an-organization#permissions-for-each-role; and `git push --force` replaces a branch even when the push loses commits, https://git-scm.com/docs/git-push
  Holds while: setup suggests the rule and does not set it, and the rule allows direct pushes.
  Paths: .agents/skills/inquisitor/

- **Constraint: Each rule that depends on igor states what holds once the igor change it needs lands, with no clause for igor before that change.**
  Because: igor has published no release, so no igor before that change is supported for such a clause to serve.
  Evidence: igor's releases page listed none on 2026-11-09, https://github.com/adamstallard/igor/releases
  Holds while: igor has published no release.
  Paths: openspec/specs/inquisitor/spec.md, openspec/specs/answer-session/spec.md

## Rejected

- **Rejected: A TLA+ model of the answer session's owed pushes and lock.**
  Facing: [spec-check's SKILL.md](../../../.agents/skills/spec-check/SKILL.md) says "Write one when a requirement is about concurrency, ordering, a crash between two writes, or a protocol between processes", and the answer session has such requirements: a push it owes after a post survives a crash and is retried, and a crash while it writes its lock leaves the old lock or the new one whole.
  Lost because: little is left to interleave: a crash between a post and its push loses no file, since the push is recorded as owed first and retried, leaving at worst a repeated post or a question shown twice; the lock is replaced by a rename, which leaves the old file or the new one whole, https://pubs.opengroup.org/onlinepubs/9699919799/functions/rename.html; and two machines' pushes to one questions branch cannot overwrite each other, since git refuses a push that would drop the other's commit, https://git-scm.com/docs/git-push
  Instead: scenarios state each crash and two-machine case, and tests check them.
  Paths: .agents/skills/inquisitor/

## Rationale

- **Rationale: The answer session polls GitHub's notifications.**
  Polling notifications costs little while nothing changes: a conditional request that finds nothing new does not count against the rate limit, and GitHub's `X-Poll-Interval` header sets how long to wait. Task 0.15 checks that the endpoint behaves as documented; if it does not, this reason fails.
  Evidence: GitHub's notifications API documents conditional requests and `X-Poll-Interval`, https://docs.github.com/en/rest/activity/notifications

- **Rationale: The answer session reads with the person's credentials, except on Discord.**
  Reading with the person's own logins keeps a relay's token to the right to post, and reads nothing the person reads under a bot's name. Discord is the exception because reading as the person there would mean automating their user account, which Discord forbids, so the relay's bot both reads and posts.
  Evidence: Discord's Community Guidelines, which its Terms of Service incorporate, say "Do not use self-bots or user-bots. Each account must be associated with a human, not a bot.", https://discord.com/terms/guidelines

- **Rationale: An answer is relayed as the person's words.**
  A relay post is the person's own answer, so it carries no header naming an agent, session or project as its author. discord-bot already posts that way: its `post` adds a header only when `--agent`, `--session` or `--project` is given, so the relay passes none of them and needs no new option.
  Evidence: `header()` in discord-bot's script, https://github.com/adamstallard/shared-skills/blob/90a0237/.agents/skills/discord-bot/scripts/discord_bot.py

- **Rationale: The answer session polls only while it is open.**
  The skill runs nothing while the answer session is closed, and receiving pushed events would need something running then: GitHub and Linear deliver webhooks only to a URL they can reach at any time, and Discord pushes events only over a gateway connection kept open, so a push sent while the session is closed would be lost. Polling needs neither, and catches up on what came while the session was closed when it next opens.
  Each poll also fetches every questions branch it reads, a fetch each, since a push to a branch creates no notification.
  Evidence: GitHub delivers each webhook to a payload URL as an HTTP request, https://docs.github.com/en/webhooks/using-webhooks/creating-webhooks
  Evidence: Linear's webhooks need a publicly reachable HTTPS URL, https://linear.app/developers/webhooks
  Evidence: Discord's gateway is a persistent WebSocket connection, https://discord.com/developers/docs/events/gateway
  Evidence: none of GitHub's notification reasons is a push to a branch, https://docs.github.com/en/rest/activity/notifications#about-notification-reasons

- **Rationale: The session's model has no shell, no writing tool and no web fetch.**
  The threat is a crafted message in a subscribed channel steering the model into posting, or recording a decision, as the person. A hook that reads a tool call's command line cannot stop a model that has a shell: `eval`, an encoded string, a script it writes, `python3 -c` or `curl` with a token from the keychain each runs what the hook never reads, which is why the post hooks guard only against accidents (this record's first Constraint). A model with no shell and no tool that posts or writes can do none of it, so the worst an injection can do is propose a reply the person sees and confirms, or pick one of `record_verdict`'s fixed values. General web fetch is left out too, since a crafted message could have the model fetch an attacker's URL carrying private text from another thread. Claude Code must enforce the restriction itself, since a hook would bring back the same gap; task 0.34 measures how.
  Evidence: a `PreToolUse` hook sees a tool call's command line, never what a program it starts sends, https://docs.anthropic.com/en/docs/claude-code/hooks
  Evidence: OWASP lists disclosure of sensitive information and exfiltration among prompt injection's impacts, and as mitigations restricting the model's privileges to the minimum and running privileged functions in the application's own code, https://genai.owasp.org/llmrisk/llm01-prompt-injection/

- **Rationale: The model's judgements reach the session's code only through record_verdict.**
  With no shell, the model's only outputs are its conversation and the tools the mod gives it, so the session's code needs a tool to learn what the model judged. A free-text verdict would let a crafted thread steer the model into writing something the code then acts on; fixed fields, checked by the code, limit the worst such a thread can do to picking among the actions the code already offers.
  Evidence: OWASP lists, among prompt injection's mitigations, "Define and validate expected output formats", using "deterministic code to validate adherence to these formats", https://genai.owasp.org/llmrisk/llm01-prompt-injection/

- **Rationale: Claude's draft goes to the prompt box, never to a post.**
  The model reads untrusted thread text, which can steer it to write what the person would not say, so its draft goes where the person reads it before anything is sent, never straight to a post. `propose_reply` also refuses a call carrying an `agentId`, keeping out a subagent's draft wherever Claude Code marks the call as a subagent's; a subagent's call without one still lands only in the prompt box. The spec assumes Claude Code sets one on a subagent's call to a mod's tool, as it sets `agent_id` on a subagent's hook events; task 0.26 measures that.
  Evidence: OWASP names indirect prompt injection, content from external sources that "alters the behavior of the model in unintended or unexpected ways", https://genai.owasp.org/llmrisk/llm01-prompt-injection/
  Evidence: Claude Code's hooks reference says a subagent's tool events carry "the `agent_id` and `agent_type` common input fields that identify the subagent", https://code.claude.com/docs/en/hooks

- **Rationale: An agent's question comes from a bot account or a log file.**
  This covers the rule's bot-account half; its log-file half needs no measurement. A message counts as a bot account's by a mark the surface, not the account, sets on its author. On Linear an app user's comment has `user.app` `true`, with a null `botActor`, so a reader checking `botActor` would count every agent as a person; on Discord a bot's message has `author.bot` `true`, and a person's user object has no `bot` key. Both were read back from the API on 2026-11-19, and tasks 0.16 and 0.17 in the change's tasks.md hold the results: of 77 comments in a test team, the 5 an app identity posted had `user.app` `true` and the other 72 `false`, and every message a bot posted in a test thread had `author.bot` `true`. That a person's Linear account cannot take on `app` rests only on the schema's description, untested, and a Discord webhook's message and GitHub's mark (task 0.21) are not measured.
  Evidence: Linear's GraphQL schema describes `User.app` as "Whether this account represents an installed application rather than a person", https://linear.app/developers/graphql
  Evidence: Discord documents `bot` on its user object, https://discord.com/developers/docs/resources/user#user-object
  Evidence: the 2026-11-19 measurements, recorded in tasks 0.16 and 0.17, [tasks.md](../../changes/inquisitor/tasks.md)

- **Rationale: Until notifications are measured, the poll reads every GitHub question source.**
  The poll reads each subscribed repository's issues, pull requests and their comments, so it costs rate-limited requests for every subscribed repository, each repository of a subscribed owner included, a cost accepted until task 0.15 shows notifications alone suffice. Without them a question could be missed: GitHub notifies a person only for a thread they take part in, watch or are asked to review, so a mention of their relay, the bot account that posts for them and that an asker may tag in place of the person, in a thread they never joined reaches them through no notification.
  Evidence: GitHub's notification reasons, https://docs.github.com/en/rest/activity/notifications#about-notification-reasons
  Evidence: the REST rate limit these reads count against, https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api

- **Rationale: The answer session's filter 1 reads only subscribed and lore repositories.**
  Decision documents and questions-branch files are files, so searching them needs a copy on the machine, and the session keeps a copy fresh only of each subscribed repository and each configured lore repository. Issues need no copy, since they are read live, but those reads also use the person's credentials. Any other repository a question names is chosen by the question's own text, so fetching its files or reading its issues would let a crafted question choose which repository, a private one included, the session reads with the person's credentials and puts before the model. So one closed set covers everything filter 1 reads in the session. The session acts on a closed set of places elsewhere too (*A concerns line settles what an agent's question concerns*), because untrusted text may only pick among what the code already offers (*Rationale: The model's judgements reach the session's code only through record_verdict*). A question the limit leaves unstopped still comes to the person, so the limit costs a recorded answer from that repository, never the question.
  Evidence: `git fetch` downloads a repository's objects before any of its files can be read on the machine, https://git-scm.com/docs/git-fetch
  Evidence: GitHub returns a private repository's issues to any request authenticated as a person who can read that repository, https://docs.github.com/en/rest/issues/issues#get-an-issue
  Evidence: OWASP lists, among prompt injection's mitigations, restricting the model's privileges to the minimum it needs, https://genai.owasp.org/llmrisk/llm01-prompt-injection/

- **Rationale: A handback that mentions no one goes to the item's assignee.**
  An Igor claims an item assigned to a person only when that person hands it over, so the assignee gave the Igor the work and is the right reader for its question.
  A handback that mentions people reaches only the first person it mentions. igor issue #229, open, proposes the order an Igor mentions people in, which no igor spec states yet. Under it, an Igor that stops on a fault it detects itself, such as an error, mentions its operator, the person who runs it, first. Every other handback, a question included, mentions the item's assignee and then its creator.
  Evidence: igor's work-claiming requirement *An item someone else holds is not claimed*, under which an Igor claims an item assigned to a person only once the item's holder field, Linear's delegate or GitHub's `igor:` label, names that Igor, https://github.com/adamstallard/igor/blob/7d969cd6ab7820e143c2802a9ead44b3a91332b0/openspec/specs/work-claiming/spec.md#L465
  Evidence: igor issue #229, which proposes the order an Igor mentions people in, https://github.com/adamstallard/igor/issues/229

- **Rationale: A handback is an Igor's comment holding igor's marker.**
  An Igor claims Linear items as well as GitHub ones, so it hands back on Linear too. Without a Linear handback, its comment there is an ordinary bot message, which reaches only the first person it mentions, so one that mentions no one reaches no one and its question waits unseen.
  Evidence: igor's work-claiming requirement *An item someone else holds is not claimed*, under which an Igor claims a Linear item once Linear's delegate field names it, https://github.com/adamstallard/igor/blob/7d969cd6ab7820e143c2802a9ead44b3a91332b0/openspec/specs/work-claiming/spec.md#L465

- **Rationale: Setup checks each relay identity before its channels are used.**
  The Discord relay reads messages that do not mention the bot, which needs Discord's privileged Message Content intent, so setup checks that `messageContent` is `true`. discord-bot's setup has the person turn the intent on, and its `check` reports `messageContent` from the bot's application flags.
  Evidence: Discord documents Message Content as a privileged intent, https://discord.com/developers/docs/events/gateway#message-content-intent
  Evidence: discord-bot's setup turns it on, https://github.com/adamstallard/shared-skills/commit/369ae16d02898cd68ba98241a7ee685b6492002c; its `check` reads it from the application's flags, https://github.com/adamstallard/shared-skills/commit/f83b167e6b52f8ad7f607bed6133b2d0e19fea6c

- **Rationale: A question with a person-required line gets no filter 2 to 4 reply.**
  The session finds the line by its fixed wording once markup is reduced, which works only where a surface returns the words as posted. Task 0.23 found on 2026-11-19 that Linear returns a comment's text unchanged, and escapes `[` only in an issue description, so the line in a Linear comment comes back unchanged; task 0.28 checks the line itself on Linear and Discord.
  Evidence: the 2026-11-19 measurement, recorded in task 0.23, [tasks.md](../../changes/inquisitor/tasks.md)

- **Rationale: The person runs the session, and a relay identity posts for them.**
  A relay identity is the bot of a skill the person already uses, so posting for them needs no service running beside the session: on Discord, discord-bot's script makes its API calls on each run and exits.
  Evidence: [discord-bot's SKILL.md](../../../.agents/skills/discord-bot/SKILL.md)

- **Rationale: The Linear relay's token stays in memory.**
  A token passed in a command's arguments would be readable by every user of the host, since each process's command line is.
  Evidence: proc(5): with the default `hidepid=0`, "Everybody may access all /proc/pid directories", https://man7.org/linux/man-pages/man5/proc.5.html
  Evidence: proc_pid_cmdline(5): `/proc/pid/cmdline` "holds the complete command line for the process", https://man7.org/linux/man-pages/man5/proc_pid_cmdline.5.html
