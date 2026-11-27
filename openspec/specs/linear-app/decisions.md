# linear-app: constraints, rejected alternatives and rationale

## Rationale

- **Rationale: No command prints a relay identity's token.**
  The inquisitor's answer service treats any post by the person's relay identity that starts `User says: ` as the person's answer. The inquisitor's post hook, which blocks an agent's post with that prefix, reads an agent's command line, so it reads a linear-app `post`'s text but not what a program such as `curl` sends with a printed token.
  Evidence: linear-app's `token` command prints a raw token for programs, [linear-app's SKILL.md](../../../.agents/skills/linear-app/SKILL.md), and `headers` prints it inside an Authorization header, [linear_app.py](../../../.agents/skills/linear-app/scripts/linear_app.py); a `PreToolUse` hook sees a tool call's command line, never what a program it starts sends, https://docs.anthropic.com/en/docs/claude-code/hooks

- **Rationale: A relay identity cannot be wired to the Linear MCP server.**
  `wire` gives the MCP server a headers helper that runs `headers`, and any agent can run that same command line, so a relay identity wired to the server would need `headers` to print its token to whichever agent runs it.
  Evidence: `wire` stores `headersHelper` as a run of `linear_app.py --identity <identity> headers`, [linear_app.py](../../../.agents/skills/linear-app/scripts/linear_app.py)

- **Rationale: A relay identity's credentials and token stay in the keychain.**
  linear-app's state folder holds the token in a mode 0600 file, which keeps out other users but not the person's own agents, which run as the person and can `cat` it; client credentials in the environment are in every agent's environment. With both in the keychain, an agent gets the token only by reading the keychain, the path accepted for an agent set on forging.
  Evidence: `write_cache` writes the token as plain JSON in linear-app's state folder, and `client_credentials` reads `LINEAR_CLIENT_ID` and `LINEAR_CLIENT_SECRET` before the keychain, [linear_app.py](../../../.agents/skills/linear-app/scripts/linear_app.py); the accepted keychain path, [answer-service decisions](../answer-service/decisions.md)
