# answer-session: constraints, rejected alternatives and rationale

## Constraints

- **Constraint: The inquisitor's GitHub post hook and the refusals asked of github-app for a relay identity guard against accidents, not against an agent set on forging a relayed answer, which can read a relay's credentials from the keychain and post with `curl`.**
  Because: the hook stops an agent that uses the skills, as its instructions tell it, and one that works around them has its person's own tools and keychain.
  Evidence: a `PreToolUse` hook sees a tool call's command line, never what a program it starts sends, https://docs.anthropic.com/en/docs/claude-code/hooks
  Holds while: a relay identity's key sits where the person's own agents can read it.
  Paths: .agents/skills/inquisitor/scripts/check-post.sh, .agents/skills/github-app/

- **Constraint: Until github-app refuses `token`, `run`, `credential get` and `wire` for a relay identity, any agent on the person's machine can print a relay App's token and post `User says: ` with a plain HTTP call no post hook sees, and the README says so.**
  Because: the inquisitor asks github-app for those refusals and ships without them.
  Evidence: github-app's `token` command prints a raw token for programs, [github-app's SKILL.md](../../../.agents/skills/github-app/SKILL.md)
  Holds while: github-app hands a relay identity's token to a command.
  Paths: .agents/skills/github-app/, .agents/skills/inquisitor/README.md

- **Constraint: Nothing is designed or built for the answer session outside Claude Code's fullscreen layout.**
  Because: the only layout the answer session's prototype has been built and used in is the fullscreen one, so no other layout has a design to build from, and `/answer` typed in another layout shows the session there as it comes, untried.
  Evidence: the prototype build v0.1-33, the only build used, is a fullscreen layout, fc3c35f
  Holds while: the approved layout is the fullscreen one.
  Paths: .agents/skills/inquisitor/

- **Constraint: GitHub's events API shows each hash-only miss file's pusher and push time to anyone who can see its questions branch, even where that branch is more visible than the miss's thread.**
  Because: the cost is accepted: the file's name, a hash of the surface and the reply's id, does not identify the thread, so the pusher and time show only that the person judged some question then.
  Evidence: GitHub's events API lists each push event's actor and time, https://docs.github.com/en/rest/activity/events
  Holds while: the answer session pushes a hash-only miss file with the person's own credentials.
  Paths: .agents/skills/inquisitor/

## Rejected

- **Rejected: A TLA+ model of the answer session's owed pushes and lock.**
  Facing: [spec-check's SKILL.md](../../../.agents/skills/spec-check/SKILL.md) says "Write one when a requirement is about concurrency, ordering, a crash between two writes, or a protocol between processes", and the answer session has such requirements: a push it owes after a post survives a crash and is retried, and a crash while it writes its lock leaves the old lock or the new one whole.
  Lost because: little is left to interleave: a crash between a post and its push loses no file, since the push is recorded as owed first and retried, leaving at worst a repeated post or a question shown twice; the lock is replaced by a rename, which leaves the old file or the new one whole, https://pubs.opengroup.org/onlinepubs/9699919799/functions/rename.html; and two machines' pushes to one questions branch cannot overwrite each other, since git refuses a push that would drop the other's commit, https://git-scm.com/docs/git-push
  Instead: scenarios state each crash and two-machine case, and tests check them.
  Paths: .agents/skills/inquisitor/

## Rationale


- **Rationale: The answer session polls GitHub's notifications and comments.**
  Notifications are what the answer session polls first, and polling them costs little while nothing changes: a conditional request that finds nothing new does not count against the rate limit, and GitHub's `X-Poll-Interval` header sets how long to wait. Task 0.15 checks that the endpoint behaves as documented.
  Evidence: GitHub's notifications API documents conditional requests and `X-Poll-Interval`, https://docs.github.com/en/rest/activity/notifications

- **Rationale: The answer session reads with the person's credentials, except on Discord.**
  Reading with the person's own logins keeps a relay's token to the right to post, and reads nothing the person reads under a bot's name. Discord is the exception because reading as the person there would mean automating their user account, which Discord forbids, so the relay's bot both reads and posts.
  Evidence: Discord's Community Guidelines, which its Terms of Service incorporate, say "Do not use self-bots or user-bots. Each account must be associated with a human, not a bot.", https://discord.com/terms/guidelines

- **Rationale: An answer is relayed as the person's words.**
  A relay post carries the person's words with no agent header, and discord-bot already posts that way: its `post` adds a header only when `--agent`, `--session` or `--project` is given, so the relay passes none of them and needs no new option.
  Evidence: `header()` in discord-bot's script, https://github.com/adamstallard/shared-skills/blob/90a0237/.agents/skills/discord-bot/scripts/discord_bot.py

- **Rationale: The answer session polls only while it is open.**
  The skill runs nothing while the answer session is closed, and receiving pushed events would need something running then: GitHub and Linear deliver webhooks only to a URL they can reach at any time, and Discord pushes events only over a gateway connection kept open, so a push sent while the session is closed would be lost. Polling needs neither, and catches up on what came while the session was closed when it next opens.
  Each poll also fetches every questions branch it reads, a fetch each, since a push to a branch creates no notification.
  Evidence: GitHub delivers each webhook to a payload URL as an HTTP request, https://docs.github.com/en/webhooks/using-webhooks/creating-webhooks
  Evidence: Linear's webhooks need a publicly reachable HTTPS URL, https://linear.app/developers/webhooks
  Evidence: Discord's gateway is a persistent WebSocket connection, https://discord.com/developers/docs/events/gateway
  Evidence: none of GitHub's notification reasons is a push to a branch, https://docs.github.com/en/rest/activity/notifications#about-notification-reasons

- **Rationale: The session's model has no shell, no writing tool and no web fetch.**
  The threat is a crafted message in a subscribed channel steering the model into posting, or recording a decision, as the person. A hook that reads a tool call's command line cannot stop a model that has a shell: `eval`, an encoded string, a script it writes, `python3 -c` or `curl` with a token from the keychain each runs what the hook never reads, which is why the post hooks guard only against accidents (*Constraint: The inquisitor's GitHub post hook …*). A model with no shell and no tool that posts or writes can do none of it, so the worst an injection can do is propose a reply the person sees and confirms. General web fetch is left out too, since a crafted message could have the model fetch an attacker's URL carrying private text from another thread. Claude Code must enforce the restriction itself, since a hook would bring back the same gap; task 0.34 measures how.
  Evidence: a `PreToolUse` hook sees a tool call's command line, never what a program it starts sends, https://docs.anthropic.com/en/docs/claude-code/hooks
  Evidence: OWASP lists disclosure of sensitive information and exfiltration among prompt injection's impacts, and as mitigations restricting the model's privileges to the minimum and running privileged functions in the application's own code, https://genai.owasp.org/llmrisk/llm01-prompt-injection/

- **Rationale: Claude's draft goes to the prompt box, never to a post.**
  The model reads untrusted thread text, which can steer it to write what the person would not say, so its draft goes where the person reads it before anything is sent, never straight to a post. `propose_reply` also refuses a call carrying an `agentId`, keeping out a subagent's draft wherever Claude Code marks the call as a subagent's; a subagent's call without one still lands only in the prompt box. The spec assumes Claude Code sets one on a subagent's call to a mod's tool, as it sets `agent_id` on a subagent's hook events; task 0.26 measures that.
  Evidence: OWASP names indirect prompt injection, content from external sources that "alters the behavior of the model in unintended or unexpected ways", https://genai.owasp.org/llmrisk/llm01-prompt-injection/
  Evidence: Claude Code's hooks reference says a subagent's tool events carry "the `agent_id` and `agent_type` common input fields that identify the subagent", https://code.claude.com/docs/en/hooks

- **Rationale: An agent's question comes from a bot account or a log file.**
  This covers the bot-account half of the rule: a message counts as a bot account's by a mark the surface, not the account, sets on its author. On Linear an app user's comment has `user.app` `true`, with `botActor` and `externalUser` null, so a reader checking `botActor` would count every agent as a person; on Discord a bot's message has `author.bot` `true`, and a person's user object has no `bot` key. Both were read back from the API on 2026-11-19, and tasks 0.16 and 0.17 in the change's tasks.md hold the results: of 77 comments in a test team, the 5 an app identity posted had `user.app` `true` and the other 72 `false`, and every message a bot posted in a test thread had `author.bot` `true`. That a person's Linear account cannot take on `app` rests only on the schema's description, untested, and a Discord webhook's message and GitHub's mark (task 0.21) are not measured.
  Evidence: Linear's GraphQL schema describes `User.app` as "Whether this account represents an installed application rather than a person", https://linear.app/developers/graphql
  Evidence: Discord documents `bot` on its user object, https://discord.com/developers/docs/resources/user#user-object
  Evidence: the 2026-11-19 measurements, recorded in tasks 0.16 and 0.17, [tasks.md](../../changes/inquisitor/tasks.md)

- **Rationale: Until notifications are measured, the poll reads every GitHub question source.**
  These reads cost rate-limited requests for every subscribed repository and every repository of an owner a subscription names, since a subscription may name an owner, a cost accepted until task 0.15 shows notifications alone suffice. Without them a question could be missed: GitHub notifies a person only for a thread they take part in, watch or are asked to review, so a mention of their relay in a thread they never joined reaches them through no notification.
  Evidence: GitHub's notification reasons, https://docs.github.com/en/rest/activity/notifications#about-notification-reasons
  Evidence: the REST rate limit these reads count against, https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api

- **Rationale: Whom a message reaches is set by its mentions.**
  The rule gives an Igor's question to the person who should answer it, because an Igor is to mention that person first. Igor issue #229, open, decides the order, which no igor spec states and igor does not yet build: an Igor mentions its operator, the person who runs it, first only when it stops for a reason it detects itself, then the assignee and the creator; every other handback, a question included, mentions the assignee and then the creator.
  Evidence: igor issue #229, https://github.com/adamstallard/igor/issues/229

- **Rationale: Setup checks each relay identity before its channels are used.**
  The Discord relay reads messages that do not mention the bot, which needs Discord's privileged Message Content intent, so setup checks that `messageContent` is `true`. discord-bot's setup has the person turn the intent on, and its `check` reports `messageContent` from the bot's application flags.
  Evidence: Discord documents Message Content as a privileged intent, https://discord.com/developers/docs/events/gateway#message-content-intent
  Evidence: discord-bot's setup turns it on, https://github.com/adamstallard/shared-skills/commit/369ae16d02898cd68ba98241a7ee685b6492002c; its `check` reads it from the application's flags, https://github.com/adamstallard/shared-skills/commit/f83b167e6b52f8ad7f607bed6133b2d0e19fea6c

- **Rationale: A question with a person-required line gets no filter 2 to 4 reply.**
  The session finds the line by its fixed wording once markup is reduced, which works only where a surface returns the words as posted. Task 0.23 found on 2026-11-19 that Linear returns a comment's text as sent, parentheses included, and escapes `[` only in an issue description, so the line in a Linear comment comes back unchanged; task 0.28 checks the line itself on Linear and Discord.
  Evidence: the 2026-11-19 measurement, recorded in task 0.23, [tasks.md](../../changes/inquisitor/tasks.md)
