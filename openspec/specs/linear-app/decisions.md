# linear-app: constraints, rejected alternatives and rationale

## Rationale

- **Rationale: No command prints a relay identity's token.**
  The inquisitor's answer service treats any post by the person's relay identity that starts `User says: ` as the person's answer. The inquisitor's post hook, which blocks an agent's post with that prefix, reads an agent's command line, so it reads a linear-app `post`'s text but not what a program such as `curl` sends with a printed token.
  Evidence: linear-app's `token` command prints a raw token for programs, [linear-app's SKILL.md](../../../.agents/skills/linear-app/SKILL.md), and `headers` prints it inside an Authorization header, [linear_app.py](../../../.agents/skills/linear-app/scripts/linear_app.py); a `PreToolUse` hook sees a tool call's command line, never what a program it starts sends, https://docs.anthropic.com/en/docs/claude-code/hooks

- **Rationale: A relay identity cannot be wired to the Linear MCP server.**
  `wire` gives the MCP server a headers helper that runs `headers`, and any agent can run that same command line, so a relay identity wired to the server would need `headers` to print its token to whichever agent runs it.
  Evidence: `wire` stores `headersHelper` as a run of `linear_app.py --identity <identity> headers`, [linear_app.py](../../../.agents/skills/linear-app/scripts/linear_app.py)

- **Rationale: Every identity holding the relay's client ID is a relay identity.**
  linear-app mints a token from the client ID, secret and scopes alone, with nothing of the identity's name in the request, and Linear ties tokens to the OAuth application, not to the identity, as revocation shows: changing one identity's scopes revokes every token the application issued. So any identity holding the relay's client ID and secret mints tokens that act as the relay's app user, and linear-app lets an identity's config name any keychain entries, or take credentials from the environment.
  Evidence: a new scope string revokes every token that application has issued, [linear-app's SKILL.md](../../../.agents/skills/linear-app/SKILL.md); `mint` sends only `client_id`, `client_secret` and `scope` with the client-credentials grant, `keychain_entries` reads the service and accounts from the identity's `keychain` config, and `client_credentials` reads `LINEAR_CLIENT_ID` and `LINEAR_CLIENT_SECRET`, [linear_app.py](../../../.agents/skills/linear-app/scripts/linear_app.py)

- **Rationale: A relay identity's credentials come only from the keychain.**
  Client credentials in the environment can be in any agent's environment, so any agent could mint the relay's token with them without setting out to. Kept in the keychain, they reach only an agent that sets out to read the keychain, a risk the answer-service record accepts as one no guard stops.
  Evidence: `client_credentials` reads `LINEAR_CLIENT_ID` and `LINEAR_CLIENT_SECRET` before the keychain, [linear_app.py](../../../.agents/skills/linear-app/scripts/linear_app.py); the accepted keychain path, [answer-service decisions](../answer-service/decisions.md)

- **Rationale: A relay identity's token is cached only in the keychain.**
  linear-app's state folder holds the token in a mode 0600 file, which keeps out other users but not the person's own agents, which run as the person and can `cat` it by accident. In the keychain the token reaches only an agent that sets out to read the keychain, the risk the answer-service record accepts.
  Evidence: `write_cache` writes the token as plain JSON in linear-app's state folder, [linear_app.py](../../../.agents/skills/linear-app/scripts/linear_app.py)
