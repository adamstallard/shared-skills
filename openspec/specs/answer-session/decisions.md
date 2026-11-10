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

- **Rationale: An answer is relayed as the person's words.**
  A relay post carries the person's words with no agent header, and discord-bot already posts that way: its `post` adds a header only when `--agent`, `--session` or `--project` is given, so the relay passes none of them and needs no new option.
  Evidence: `header()` in discord-bot's script, https://github.com/adamstallard/shared-skills/blob/90a0237/.agents/skills/discord-bot/scripts/discord_bot.py
