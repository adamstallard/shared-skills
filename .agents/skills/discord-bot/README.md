# discord-bot

Lets an agent post to, read and manage Discord channels and threads as a **bot
account**: a named identity of its own, not yours. There's no service to run.
Each call to `scripts/discord_bot.py` does its work and exits, so it works the
same on a laptop, on a server, or called from another program.

Use it when agents should report to a team channel, coordinate with each other,
or answer people on Discord. It doesn't handle direct messages or voice, and it
doesn't react to new messages by itself: an agent reads a channel when it
decides to.

---

## Setup

You need the minimum Python version in the
[root README](../../../README.md#requirements), and for keeping the token on disk,
whichever of the macOS Keychain
or Linux `secret-tool` your system has. Allow about 10 minutes per bot.

### 1. Create the bot in Discord

Do this in a browser, once per bot. The script can't do any of it.

1. [Discord Developer Portal](https://discord.com/developers/applications) →
   **New Application**. Name it after the agent, not after yourself
   (`acme-agent-adam`, `acme-reviewer`): every message appears under this name.
2. **Bot** tab → set the same username, then **Reset Token** and copy it.
   Discord shows it once; you'll store it in step 3. Resetting it later stops
   the old token immediately.
3. On the same tab, under Privileged Gateway Intents, turn on **Message
   Content Intent**. `read` needs it: without it, Discord removes the text,
   attachments and embeds from other people's messages, except those that
   mention the bot. A bot in 100 or more servers needs Discord's
   verification and approval before it can use this intent.

   Leave Server Members Intent and Presence Intent off; the skill uses
   neither. `@name` mentions don't need Server Members Intent: they were
   tested with it off.
4. If someone else will add the bot to their server, such as an admin of a
   server you don't manage, turn on **Public Bot** on the same tab. While it is
   off, only you can add the bot, and only to servers where you have Manage
   Server. You can turn it off again once the bot has joined.

### 2. Name the identity

Each bot gets a name on your machine, its **identity**. Pick something short:
`acme`, `reviewer`. Commands use `--identity <name>`, else the
`DISCORD_BOT_IDENTITY` environment variable, else the identity `default`.

With one bot, call it `default` and you never need the flag. With several, one
per team or project, set `DISCORD_BOT_IDENTITY` in each project's environment,
so an agent working there acts as that project's bot.

### 3. Store the token

On your own machine, keep it in the keychain:

```bash
python3 ~/.agents/skills/discord-bot/scripts/discord_bot.py --identity acme store-token
```

Run it in a terminal window. It asks for the token without echoing it and
checks it with Discord before storing it under service `discord-bot`, account
`acme`. When it has no terminal, as when Claude Code's `!` prefix or an agent's
shell runs it, it refuses and stores nothing. The output's `bot`
field names the bot the token belongs to. If that is a different bot, you
copied another bot's token: run `store-token` again with the right one.

If Discord rejects the token, nothing is stored. The usual cause is pasting
the Client Secret or the Public Key, from other tabs of the developer portal,
instead of the bot token.

To delete a stored token, run `forget-token` the same way. It says if nothing
was stored. If `DISCORD_BOT_TOKEN` or `DISCORD_BOT_TOKEN_FILE` supplies a token
for that identity, it warns you: the bot keeps using that token until you
unset the variable.

On a server or in a container, give each bot's process its token in its own
environment instead, for example a systemd `EnvironmentFile` or a Docker env
file readable only by the service:

```bash
DISCORD_BOT_IDENTITY=reviewer
DISCORD_BOT_TOKEN_FILE=/etc/discord-bot/reviewer.token
```

`DISCORD_BOT_TOKEN_FILE` names a file holding only the token, so the
environment file needn't hold it. Set `DISCORD_BOT_TOKEN` to the token itself
instead if you prefer; setting both is an error.

Either one belongs to the identity named by `DISCORD_BOT_IDENTITY`, or to
`default` when that is unset. For that identity it wins over the keychain. A
command run with any other `--identity` ignores it and uses that identity's
keychain entry, so a process can't act as one bot with another bot's token.

Where one agent role runs per process, name the identity after the role, the
same name its GitHub App identity uses.

### 4. Add the bot to a server

```bash
python3 ~/.agents/skills/discord-bot/scripts/discord_bot.py --identity acme invite-url
```

It prints `inviteUrl`, the link that adds the bot to a server. Open it
yourself if you have Manage Server there, or send it to an admin who does.
They pick the server and click **Authorize**. A bot can't join through an
ordinary invite link.

Use this link, not the one on the developer portal's Installation tab. The
portal's link uses the app's default install settings, which may hold only
`applications.commands`: the admin authorizes, but the bot never joins the
server. This one asks for exactly the five permissions the skill
uses:

| Permission               | Used for                                   |
| ------------------------ | ------------------------------------------ |
| View Channel             | seeing the channels at all                 |
| Send Messages            | `post`                                     |
| Read Message History     | `read`, and finding a message to edit      |
| Create Public Threads    | `thread`                                   |
| Send Messages in Threads | posting inside a thread                    |

The output's `warnings` name each developer-portal setting that would stop
the link working: Public Bot off (Bot tab, step 1.4), Requires OAuth2 Code
Grant on (Bot tab), or Guild Install off (Installation tab, Installation
Contexts). Fix them before sending the link.

If a channel is private, add the bot's role to it (channel → Edit Channel →
Permissions). Being in the server doesn't give access to private channels.

### 5. Describe the channels and people

Create `~/.config/discord-bot/<identity>.json`, or under `$XDG_CONFIG_HOME` if
you set it. The agent reads it through `check`, so this is where you tell it
where to post and who is who:

```json
{
  "server": "Acme",
  "defaultChannel": "agents",
  "channels": {
    "agents": "your own agents coordinating; also for tests",
    "team": "shared with the rest of the team; real updates only"
  },
  "people": {
    "@adam": "Adam, who runs this bot",
    "@acme-reviewer": "the review bot"
  }
}
```

Every field is optional:

| Field            | What it does                                                                 |
| ---------------- | ---------------------------------------------------------------------------- |
| `server`         | server name or id; needed only if the bot is in several servers sharing a channel name |
| `defaultChannel` | the channel used when a command has no `--channel`; `DISCORD_BOT_CHANNEL` overrides it |
| `channels`       | what each channel is for, in your words                                      |
| `people`         | who each handle belongs to, in your words; use exact Discord names, since mentions match only exact names |
| `keychain`       | `{"service": ..., "account": ...}` to read a token stored under another name |

### 6. Check it

```bash
python3 ~/.agents/skills/discord-bot/scripts/discord_bot.py --identity acme check
```

You should see:

- the bot's name and your server. If `servers` holds `{"ok": false, ...}`
  instead, its error says what to fix;
- the default channel, with every permission `true`;
- `"memberSearch": true`: a search for the bot's own name returned members, so
  `@name` mentions will work;
- `"messageContent": true`: the bot's application has Message Content Intent
  on, so `read` will show what other people write. `false` means it is off;
  turn it on as in setup step 1.3, above. `null` means `check` couldn't read
  the setting from Discord: fix what `messageContentError` names, such as a
  network error or Discord refusing the request, and run `check` again.
  `check` reports `messageContent` even when it can't find the default
  channel.

---

## Using it

Ask your agent in plain words:

> "Post in #agents that the deploy finished, with a link to the PR."
> "What did people say in #team since yesterday?"
> "Start a thread on that message for the review notes."

An answer to one message can go out as a Discord reply to it. That doesn't
ping the message's author unless the text mentions them.

Every command prints one JSON object. To call it from another program, run it
as a subprocess and read `ok`, then the fields you need. The exit status is 0
on success, 1 on an error reported in the JSON, and 2 for a malformed command
line.

---

## When something goes wrong

**"no bot token for identity …"**: nothing is stored for that identity. Run
`store-token`, or set `DISCORD_BOT_TOKEN` or `DISCORD_BOT_TOKEN_FILE`. Check the
identity name too: without `--identity` or `DISCORD_BOT_IDENTITY`, it's
`default`. If the error says the token in the environment belongs to another
identity, that token is another bot's; give this identity its own.

**"Discord rejected the token entered"** from `store-token`: what you pasted
isn't a bot token. Copy it from the developer portal's **Bot** tab, after
**Reset Token**; the Client Secret and Public Key are not it.

**Rotating a token.** On the developer portal's **Bot** tab, click **Reset
Token**. Run `store-token` and paste the new token; it replaces the stored one,
so `forget-token` isn't needed first. Then run `check`. Resetting stops the old
token at once, so every machine and server using it needs the new one: on a
server, put it in the bot's environment file or token file.
Discord also resets a bot's token when it finds the token in a public GitHub
repository.

**"the bot is not in any server"** or **"no text channel #… that the bot can
see"**: the bot hasn't been added to that server, or the channel is private and
the bot's role wasn't added to it (setup step 4). The first error gives the
`invite-url` command to run, its identity filled in.

**"the bot is not in a server named or numbered …"**: `server` in the config
matches none of the servers the error lists. Matching is exact and
case-sensitive, so first compare the value with those names and fix it. If the
server really is missing, run the `invite-url` command the error gives.

**"#… exists in more than one server"**: set `server` in the config.

**Mentions stay plain text.** If the warning says no member, or several
members, have that name, use the person's exact username, display name or
server nickname: partial names are never guessed. If it says Discord refused
member search, `check` shows `"memberSearch": false`; turning on **Server
Members Intent** on the developer portal's Bot tab is the setting that
controls it.

**`read` leaves out other people's messages**, or `check` shows
`"messageContent": false`: turn on **Message Content Intent** on the developer
portal's Bot tab (setup step 1.3).

**A permission is `false` in `check`**, or a post fails with status 403: grant
it on the bot's role (Server Settings → Roles), or on the channel for a private
one.

**"rate limited by Discord"**: the script already waited and retried. Wait a
minute before the next burst of posts.

**"message … is not in this channel or thread, or was deleted"**: `--reply-to`
takes a message from the channel or thread you're posting to.

**Limiting where the bot posts and whose messages it reads.** Use Discord's
roles and channel permissions, which the server's moderators and admins
manage. The skill keeps no list of allowed users or channels.
