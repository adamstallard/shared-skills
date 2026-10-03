# linear-app

Gives an agent its own identity in Linear: an **app user**, so everything it
writes is credited to the agent, not to you. App users aren't paid seats. The
long-lived credential is the OAuth application's client secret, and
`scripts/linear_app.py` mints short-lived tokens from it whenever one is
needed, so nobody ever renews a token by hand.

It works on a laptop and on a headless server, and one machine can run several
identities: one per agent role, each with its own app user.

Issue work itself goes through [Linear's MCP server](https://linear.app/docs/mcp);
this skill gives that server an identity. Programs can also take a token from
`linear_app.py token` and call Linear's API directly.

---

## Setup

You need **Python 3.8+**, and a workspace admin for step 1. Allow about 10
minutes per identity.

### 1. Create the OAuth application in Linear

In Linear: **Settings → API → + New OAuth application**
(`https://linear.app/<workspace>/settings/api`). One application per identity:
an application *is* one app user.

| Field              | Value |
| ------------------ | ----- |
| Application name   | The agent's name, e.g. `acme-agent-adam`. It appears on every issue the agent touches. |
| Developer name     | The person who runs and answers for this agent. |
| Client credentials | **Enable.** This is how tokens are minted, with no browser. |
| Redirect URIs      | Required by the form, unused here. Enter `http://localhost:8765/callback`. |
| Webhooks           | Leave **off**. |

Open the application afterwards to copy its **client ID** and **client
secret**.

### 2. Name the identity

Pick a short name for this agent on your machine: `acme`, `reviewer`.
Commands use `--identity <name>`, else `LINEAR_APP_IDENTITY`, else `default`.

### 3. Store the credentials

On your own machine, keep them in the keychain (macOS Keychain or Linux
`secret-tool`):

```bash
python3 ~/.agents/skills/linear-app/scripts/linear_app.py --identity acme store-credentials
```

On a server, set `LINEAR_CLIENT_ID` and `LINEAR_CLIENT_SECRET` in that
service's environment instead, for example in a systemd `EnvironmentFile`
readable only by the service. They belong to the identity named by
`LINEAR_APP_IDENTITY` (or `default` when it is unset) and win over the keychain
for that identity only; set both or neither.

### 4. Check it

```bash
python3 ~/.agents/skills/linear-app/scripts/linear_app.py --identity acme check
```

It mints the first token and shows the app user's name, the workspace,
`"canBeDelegate": true`, and how many days the token has left. **The `user`
must be the agent's name, not yours.**

### 5. Connect the agent

**Claude Code:**

```bash
python3 ~/.agents/skills/linear-app/scripts/linear_app.py --identity acme wire
python3 ~/.agents/skills/linear-app/scripts/linear_app.py --identity acme wire --project ~/code/acme
```

The first form serves every session; the second only sessions started in that
folder. Either way the config stores a command that fetches a token, never the
token itself. Start a new session (or run `/mcp`) afterwards.

**Other MCP clients:** point them at `https://mcp.linear.app/mcp` with an
`Authorization` header from `linear_app.py --identity acme headers`, which
prints it as JSON.

**Programs** (igor, scripts): run `linear_app.py --identity acme token` and
use what it prints as a bearer token.

---

## Optional config

`~/.config/linear-app/<identity>.json` (or under `$XDG_CONFIG_HOME`). Every
field is optional:

| Field       | What it does |
| ----------- | ------------ |
| `scopes`    | The scopes tokens are minted with. Default `read,write,app:assignable,app:mentionable`; the last two let the agent be delegated issues and @mentioned. **Changing this revokes every token the application has issued.** |
| `workspace` | The workspace's URL key, e.g. `acme`. `check` fails if the credentials belong to another workspace. |
| `keychain`  | `{"service": ..., "clientIdAccount": ..., "clientSecretAccount": ...}` to read credentials stored under other names. |
| `teams`, `people`, `notes` | Anything the agent should know: which teams it works in, who is who. `check` prints them. |

## Several agents on one server

Give each its own Linear application, as in step 1, and its own environment:

```ini
# /etc/<service>/<role>.env
LINEAR_APP_IDENTITY=reviewer
LINEAR_CLIENT_ID=...
LINEAR_CLIENT_SECRET=...
```

Processes of the same identity share one cached token, under
`~/.local/state/linear-app/` (or `$XDG_STATE_HOME`), with a lock so they never
mint over each other.

Claim work by **delegate**, never assignee. An app user can't be an assignee,
and Linear accepts the request and silently ignores it, so always read the
issue back after claiming it.

## Moving over from the aura-workroom script

Point the config at the Keychain entries that script already made, so nothing
is retyped:

```json
{
  "scopes": "read,write,app:assignable,app:mentionable",
  "keychain": {"service": "aura-linear-agent",
               "clientIdAccount": "linear-client-id",
               "clientSecretAccount": "linear-client-secret"}
}
```

Keep `scopes` identical to what the old token was minted with, or the first
mint revokes it. Then run `check` and `wire`.

---

## When something goes wrong

**"no client credentials for identity …"**: nothing is stored for that
identity. Run `store-credentials` or set the environment variables, and check
the identity name.

**Linear tools fail with 401:** run `check`. If Linear revoked the cached
token (for example, the same application minted with other scopes elsewhere),
`check` mints a replacement and answers `ok: true`. If `check` itself fails
with 401 or `invalid_client`, the client secret was rotated in Linear, or
client credentials were disabled on the application: run `store-credentials`
with the current secret.

**Linear tools fail in a session after `wire` or a scope change**: MCP servers
connect at session start. Run `/mcp` and reconnect, or start a new session.

**`canBeDelegate` is false**: the identity's `scopes` lack `app:assignable`.
Adding it revokes the application's current tokens, so do it when nothing else
is using them.

**A machine is lost:** rotate the application's client secret in Linear. That
revokes every token minted from it.

To remove an identity from a machine: `linear_app.py --identity <name> forget`.
It deletes the cached token and any credentials stored under the `linear-app`
keychain service. Entries the config points at under another service, such
as the aura-workroom script's, are left alone, and `forget` lists them.
