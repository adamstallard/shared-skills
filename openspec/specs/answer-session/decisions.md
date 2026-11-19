# answer-session: constraints, rejected alternatives and rationale

## Constraints

- **Constraint: The post hooks, on GitHub, Linear and Discord, and the refusals asked of github-app for a relay identity guard against accidents, not against an agent set on forging a relayed answer, which can read a relay's credentials from the keychain and post with `curl`.**
  Because: the hooks stop an agent that uses the skills, as its instructions tell it, and one that works around them has its person's own tools and keychain.
  Evidence: a `PreToolUse` hook sees a tool call's command line, never what a program it starts sends, https://docs.anthropic.com/en/docs/claude-code/hooks
  Holds while: a relay identity's key sits where the person's own agents can read it.
  Paths: .agents/skills/inquisitor/scripts/check-post.sh, .agents/skills/github-app/, .agents/skills/linear-app/, .agents/skills/discord-bot/

- **Constraint: Until github-app refuses `token`, `run`, `credential get` and `wire` for a relay identity, any agent on the person's machine can print a relay App's token and post `User says: ` with a plain HTTP call no post hook sees, and the README says so.**
  Because: the inquisitor asks github-app for those refusals and ships without them.
  Evidence: github-app's `token` command prints a raw token for programs, [github-app's SKILL.md](../../../.agents/skills/github-app/SKILL.md)
  Holds while: github-app hands a relay identity's token to a command.
  Paths: .agents/skills/github-app/, .agents/skills/inquisitor/README.md

- **Constraint: The session's model runs with the person's tools, so it can reach the keychain entry holding the person's own Linear key, and the answer session adds no guard against that.**
  Because: it is the same exposure as the person's `gh` login in any session, and the same exposure reaches the relay's credentials, as the constraint on forging a relayed answer says.
  Evidence: a Claude Code session's tools reach whatever the person's own commands can, https://docs.anthropic.com/en/docs/claude-code/security
  Holds while: the session's model runs with the person's tools.
  Paths: .agents/skills/inquisitor/

- **Constraint: Nothing is designed or built for the answer session outside Claude Code's fullscreen layout.**
  Because: `answer` opens the answer session in that layout, the only one approved; `/answer` opens it on whichever screen the session is on, with nothing made for another.
  Evidence: the approved prototype build v0.1-33 is a fullscreen layout, fc3c35f
  Holds while: the approved layout is the fullscreen one.
  Paths: .agents/skills/inquisitor/

## Rejected

- **Rejected: A TLA+ model of the answer session's owed pushes and lock.**
  Facing: spec-check's SKILL.md says "Write one when a requirement is about concurrency, ordering, a crash between two writes, or a protocol between processes", and the answer session has such requirements: a push it owes after a post survives a crash and is retried, and a crash while it writes its lock leaves the old lock or the new one whole.
  Lost because: a push is recorded as owed before its post and retried, so a crash before it loses no file, and its worst outcome, like that of two of one person's machines handling one question, is a repeated post or a question shown twice or asked again, which costs the person a second look; and little is left to interleave, since one person uses the session, the lock makes one session per machine the only writer of that machine's state, and the only state shared between machines is the threads, which each write appends to and each read fetches again; the rule this is weighed against is in [spec-check's SKILL.md](../../../.agents/skills/spec-check/SKILL.md)
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
  Evidence: GitHub delivers each webhook to a payload URL as an HTTP request, https://docs.github.com/en/webhooks/using-webhooks/creating-webhooks
  Evidence: Linear's webhooks need a publicly reachable HTTPS URL, https://linear.app/developers/webhooks
  Evidence: Discord's gateway is a persistent WebSocket connection, https://discord.com/developers/docs/events/gateway

- **Rationale: Claude's draft goes to the prompt box, never to a post.**
  Only the conversation the person is in may fill their prompt box: a subagent that read an untrusted Linear or Discord message could otherwise plant text the person then sends without seeing where it came from. `propose_reply` refuses any call carrying an `agentId`. The spec assumes Claude Code sets one on a subagent's call to a mod's tool, as it sets `agent_id` on a subagent's hook events; task 0.26 measures that.
  Evidence: the approved prototype's `tool.call` handler for `propose_reply` refuses such a call, in `answer-session/hooks/register.tsx`, fc3c35f
  Evidence: Claude Code's hooks reference says a subagent's tool events carry "the `agent_id` and `agent_type` common input fields that identify the subagent", https://code.claude.com/docs/en/hooks

- **Rationale: An agent's question comes from a bot account or a log file.**
  This covers the bot-account half of the rule: a message counts as a bot account's by a mark the surface, not the account, sets on its author. On Linear an app user's comment has `user.app` `true`, with `botActor` and `externalUser` null, so a reader checking `botActor` would count every agent as a person; on Discord a bot's message has `author.bot` `true`, and a person's user object has no `bot` key. Both were read back from the API on 2026-11-19, and tasks 0.16 and 0.17 in the change's tasks.md hold the results: of 77 comments in a test team, the 5 an app identity posted had `user.app` `true` and the other 72 `false`, and every message a bot posted in a test thread had `author.bot` `true`. That a person's Linear account cannot take on `app` rests only on the schema's description, untested, and a Discord webhook's message and GitHub's mark (task 0.21) are not measured.
  Evidence: Linear's GraphQL schema describes `User.app` as "Whether this account represents an installed application rather than a person", https://linear.app/developers/graphql
  Evidence: Discord documents `bot` on its user object, https://discord.com/developers/docs/resources/user#user-object
  Evidence: the 2026-11-19 measurements, recorded in tasks 0.16 and 0.17, [tasks.md](../../changes/inquisitor/tasks.md)

- **Rationale: Whom a message reaches is set by its mentions.**
  The rule gives an Igor's question to the person who should answer it, because an Igor mentions that person first. Igor issue #229 sets the order, and igor's specs do not state it: an Igor mentions its operator, the person who runs it, first only when it stops for a reason it detects itself, then the assignee and the creator; every other handback, a question included, mentions the assignee and then the creator.
  Evidence: igor issue #229, https://github.com/adamstallard/igor/issues/229

- **Rationale: Setup checks each relay identity before its channels are used.**
  The Discord relay reads messages that do not mention the bot, which needs Discord's privileged Message Content intent, so setup checks that `messageContent` is `true`. discord-bot's setup has the person turn the intent on, and its `check` reports `messageContent` from the bot's application flags.
  Evidence: Discord documents Message Content as a privileged intent, https://discord.com/developers/docs/events/gateway#message-content-intent
  Evidence: discord-bot's setup turns it on, https://github.com/adamstallard/shared-skills/commit/369ae16d02898cd68ba98241a7ee685b6492002c; its `check` reads it from the application's flags, https://github.com/adamstallard/shared-skills/commit/f83b167e6b52f8ad7f607bed6133b2d0e19fea6c
