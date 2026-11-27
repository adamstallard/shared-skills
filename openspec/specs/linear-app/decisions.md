# linear-app: constraints, rejected alternatives and rationale

## Rationale

- **Rationale: No command prints a marked relay's token.**
  The inquisitor's answer service treats any post by the person's relay identity that starts `User says: ` as the person's answer. The inquisitor's post hook, which blocks an agent's post with that prefix, reads only GitHub posts, so on Linear nothing but keeping the token from agents stops an agent from forging one with a plain HTTP call.
  Evidence: linear-app's `token` command prints a raw token for programs, [linear-app's SKILL.md](../../../.agents/skills/linear-app/SKILL.md), and `headers` prints it inside an Authorization header, [linear_app.py](../../../.agents/skills/linear-app/scripts/linear_app.py); the post hook reads only `gh`, github-app and GitHub MCP posts, [gh-post spec](../../changes/inquisitor/specs/gh-post/spec.md)

- **Rationale: A marked relay cannot be wired to the Linear MCP server.**
  `wire` gives the MCP server a headers helper that runs `headers`, and any agent can run that same command line, so a marked relay wired to the server would need `headers` to print its token to whichever agent runs it.
  Evidence: `wire` stores `headersHelper` as a run of `linear_app.py --identity <identity> headers`, [linear_app.py](../../../.agents/skills/linear-app/scripts/linear_app.py)

- **Rationale: A marked relay's credentials and token stay in the keychain.**
  linear-app's state folder holds the token in a mode 0600 file, which keeps out other users but not the person's own agents, which run as the person and can `cat` it; client credentials in the environment are in every agent's environment. With both in the keychain, an agent gets the token only by reading the keychain, the path accepted for an agent set on forging.
  Evidence: `write_cache` writes the token as plain JSON in linear-app's state folder, and `client_credentials` reads `LINEAR_CLIENT_ID` and `LINEAR_CLIENT_SECRET` before the keychain, [linear_app.py](../../../.agents/skills/linear-app/scripts/linear_app.py); the accepted keychain path, [answer-service decisions](../answer-service/decisions.md)
