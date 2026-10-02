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

You need **Python 3.8+**, and for keeping the token on disk, the macOS
Keychain or Linux `secret-tool`. Allow about 10 minutes per bot.

### 1. Create the bot in Discord

Do this in a browser, once per bot. The script can't do any of it.

1. [Discord Developer Portal](https://discord.com/developers/applications) →
   **New Application**. Name it after the agent, not after yourself
   (`acme-agent-adam`, `acme-reviewer`): every message appears under this name.
   Copy the **Application ID** from General Information.
2. **Bot** tab → set the same username, then **Reset Token** and copy it.
   Discord shows it once; you'll store it in step 3. Resetting it later stops
   the old token immediately.
3. Leave the privileged intents off for now. If `@name` mentions later come
   out as plain text, see [Mentions](#mentions-stay-plain-text).
4. Invite the bot to your server with this URL, using your Application ID:

   ```
   https://discord.com/api/oauth2/authorize?client_id=<APPLICATION_ID>&scope=bot&permissions=309237713920
   ```

   That number grants exactly the five permissions the skill uses:

   | Permission               | Used for                                   |
   | ------------------------ | ------------------------------------------ |
   | View Channel             | seeing the channels at all                 |
   | Send Messages            | `post`                                     |
   | Read Message History     | `read`, and finding a message to edit      |
   | Create Public Threads    | `thread`                                   |
   | Send Messages in Threads | posting inside a thread                    |

5. If a channel is private, add the bot's role to it (channel → Edit Channel →
   Permissions). Being in the server doesn't give access to private channels.

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

It asks for the token without echoing it, and stores it under service
`discord-bot`, account `acme`.

On a server or in a container, set `DISCORD_BOT_TOKEN` in that process's
environment instead, for example in a systemd `EnvironmentFile` or a Docker env
file readable only by the service. The environment variable wins over the
keychain.

### 4. Describe the channels and people

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

### 5. Check it

```bash
python3 ~/.agents/skills/discord-bot/scripts/discord_bot.py --identity acme check
```

You should see the bot's name, your server, the default channel with every
permission `true`, and `"memberSearch": true`.

---

## Using it

Ask your agent in plain words:

> "Post in #agents that the deploy finished, with a link to the PR."
> "What did people say in #team since yesterday?"
> "Start a thread on that message for the review notes."

Every command prints one JSON object. To call it from another program, run it
as a subprocess and read `ok`, then the fields you need. The exit status is 0
on success, 1 on an error reported in the JSON, and 2 for a malformed command
line.

---

## When something goes wrong

**"no bot token for identity …"**: nothing is stored for that identity. Run
`store-token`, or set `DISCORD_BOT_TOKEN`. Check the identity name too: without
`--identity` or `DISCORD_BOT_IDENTITY`, it's `default`.

**"no text channel #… that the bot can see"**: the bot isn't in that server,
or the channel is private and the bot's role wasn't added (setup step 1.5).

**"#… exists in more than one server"**: set `server` in the config.

<a id="mentions-stay-plain-text"></a>**Mentions stay plain text.** If the
warning says Discord refused member search, turn on **Server Members Intent**
on the developer portal's Bot tab; `check` shows `"memberSearch": false` until
you do. If it says no member, or several members, have that name, use the
person's exact username, display name or server nickname: partial names are
never guessed.

**A permission is `false` in `check`**, or a post fails with status 403: grant
it on the bot's role (Server Settings → Roles), or on the channel for a private
one.

**"rate limited by Discord"**: the script already waited and retried. Wait a
minute before the next burst of posts.
