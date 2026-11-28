---
name: linear-app
description: >-
  Give an agent its own Linear identity (an OAuth app user) and keep its token
  working with no renewals by hand. Use when Linear tools fail with an
  authentication or authorization error, when the user asks to set up, check,
  wire or switch an agent's Linear identity, when work should be claimed by
  delegating an issue to an agent, or when an agent's Linear writes show up
  under a human's name.
---

# Linear as an app user

An agent should act in Linear as its own **app user**, never as its human.
`scripts/linear_app.py` holds each identity's OAuth client secret and mints
short-lived tokens from it whenever one is needed, so tokens never have to be
renewed by hand.

```bash
L="<base directory>/scripts/linear_app.py"
```

`<base directory>` is this skill's base directory: the directory that holds
this SKILL.md, which Claude Code names on the "Base directory for this skill:"
line above it. Write the path out in full; a home-directory install path may be
missing or hold a different copy.

The issue work itself (searching, creating and updating issues, comments)
goes through Linear's own MCP server. This skill only gives that server an
identity.

## Which identity

`--identity <name>`, else `$LINEAR_APP_IDENTITY`, else `default`. A machine
with several agents sets `LINEAR_APP_IDENTITY` per project or per service. Use
the identity you are given; never switch to another to get around a refusal.

## When Linear tools fail

If every Linear tool fails with an authentication error, run:

```bash
python3 $L check
```

- **`ok: true`**: the identity works. If Linear had revoked the cached token,
  `check` has already replaced it. The MCP server in this session still holds
  the old one: tell the user to run `/mcp` and reconnect `linear`, or start a
  new session. Nothing else is needed.
- **"no client credentials"**: this identity isn't set up on this machine.
  Point the user at the README's setup section. A human has to do the first
  step, in a browser.
- **"Linear answered 401"** or **"invalid_client"**: the client secret was
  rotated in Linear. Ask the user to run `store-credentials` again. Never ask
  them to paste a secret to you.
- **A warning that an MCP server "runs … which no longer exists"**: Python was
  upgraded, or the clone the server was wired from moved. The warning ends with
  the command that wires it again; run it, then tell the user to reconnect with
  `/mcp` or start a new session.

`check` also shows the app user's name and workspace. If the name is a
person's, the wrong credentials are stored: stop and tell the user.

## Commenting without a token

```bash
python3 $L post --issue ENG-5 --body-file c.md        # --parent <comment id> replies in its thread
python3 $L edit --comment <comment id> --body-file c.md
python3 $L delete --comment <comment id>
```

Each prints JSON with `ok` and the comment's `id` (and `url` for `post` and
`edit`). The text comes only from the regular file `--body-file` names,
given once and spelled in full, so the inquisitor's post hook reads the
same file; standard input is refused. When Linear
refuses, the output holds `"ok": false`, its HTTP `status` and its `errors`
unchanged.

## Relay identities

The identity that `answer_service.linear.relay` names in
`~/.config/shared-skills/inquisitor.json` is a **relay identity**: the
inquisitor's answer service posts your user's answers through it, as
comments starting `User says: `. So is any identity holding the same client
ID. For a relay identity, `token`, `headers` and `wire` refuse, since an
agent holding its token could post such a comment: it posts only through
`post`, `edit` and `delete`. Its credentials and cached token live only in the keychain, never
in the environment or the state folder. If that file exists but cannot be read, or the
relay's client ID cannot, every identity is treated as a relay identity, and
the refusal says why.

## Claiming work: delegate, never assign

An app user can be an issue's **delegate**, never its **assignee**. Setting an
app user as assignee *reports success and changes nothing*.

- To take an issue, set `delegate` to this identity's app user. The human
  assignee stays accountable.
- After any claim, read the issue back and confirm the delegate is you.
- `check` shows `canBeDelegate`. If it is `false`, the identity was set up
  without the `app:assignable` scope; tell the user.

## Wiring the MCP server

```bash
python3 $L wire                       # every session on this machine
python3 $L wire --project <folder>    # only sessions started in that folder
```

The MCP config then holds a command that fetches a fresh token for each
session, never a token. The server takes effect in **new** sessions (or after
`/mcp`), never in the one that ran `wire`. Say so when you report it.

## Rules

- Never fall back to `claude mcp login linear`: it signs in as the human, and
  everything the agent writes is then credited to them.
- Never change an identity's `scopes` on your own. A new scope string revokes
  every token that application has issued, including ones other processes are
  using right now.
- Never put a token or a secret in a file, a commit or a message.
- `token` prints a raw token for programs. Don't run it to look at the token.
  To comment as the identity, use `post`, `edit` and `delete` instead.
