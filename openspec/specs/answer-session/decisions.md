# answer-session: constraints, rejected alternatives and rationale

## Constraints

- **Constraint: The post hooks, on GitHub, Linear and Discord, and github-app's refusals for a relay identity guard against accidents, not against an agent set on forging a relayed answer, which can read a relay's credentials from the keychain and post with `curl`.**
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

- **Constraint: The answer session works on Claude Code's main screen too, but nothing is designed or built for that screen alone.**
  Because: `answer` opens it fullscreen, the layout it is designed for.
  Evidence: the approved prototype build v0.1-33 is a fullscreen layout, fc3c35f
  Holds while: the approved layout is the fullscreen one.
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

- **Rationale: The log command commits with the person's git identity.**
  An answer file with no `answer_link` counts only through its commit's signature, and in a session set up for a GitHub App the github-app skill's settings make every commit the bot's and unsigned, so the answer session runs the `log` command without them, or the person's answers would never count.
  Evidence: github-app's `agent_env` sets `commit.gpgsign=false` and the bot's `GIT_AUTHOR_*` and `GIT_COMMITTER_*`, https://github.com/adamstallard/shared-skills/blob/02c0a7782bc0392f5c1f5d8e3af0188cf84a9f0d/.agents/skills/github-app/scripts/github_app.py#L499-L523

- **Rationale: The answer session polls only while it is open.**
  The skill runs nothing while the answer session is closed, and receiving pushed events would need something running then: GitHub and Linear deliver webhooks only to a URL they can reach at any time, and Discord pushes events only over a gateway connection kept open, so a push sent while the session is closed would be lost. Polling needs neither, and catches up on what came while the session was closed when it next opens.
  Evidence: GitHub delivers each webhook to a payload URL as an HTTP request, https://docs.github.com/en/webhooks/using-webhooks/creating-webhooks
  Evidence: Linear's webhooks need a publicly reachable HTTPS URL, https://linear.app/developers/webhooks
  Evidence: Discord's gateway is a persistent WebSocket connection, https://discord.com/developers/docs/events/gateway

- **Rationale: Claude's draft goes to the prompt box, never to a post.**
  Only the conversation the person is in may fill their prompt box: a subagent that read an untrusted Linear or Discord message could otherwise plant text the person then sends without seeing where it came from. Claude Code marks a subagent's tool calls with the subagent's id, so `propose_reply` refuses any call carrying an `agentId`.
  Evidence: Claude Code's hooks reference says a subagent's tool events carry "the `agent_id` and `agent_type` common input fields that identify the subagent", https://code.claude.com/docs/en/hooks

- **Rationale: Setup checks each relay identity before its channels are used.**
  The Discord relay reads messages that do not mention the bot, which needs Discord's privileged Message Content intent, so setup checks that `messageContent` is `true`. discord-bot's setup has the person turn the intent on, and its `check` reports `messageContent` from the bot's application flags.
  Evidence: Discord documents Message Content as a privileged intent, https://discord.com/developers/docs/events/gateway#message-content-intent
  Evidence: discord-bot's setup turns it on, https://github.com/adamstallard/shared-skills/commit/369ae16d02898cd68ba98241a7ee685b6492002c; its `check` reads it from the application's flags, https://github.com/adamstallard/shared-skills/commit/f83b167e6b52f8ad7f607bed6133b2d0e19fea6c
