---
name: discord-bot
description: >-
  Post to, read, edit and delete messages in Discord channels and threads as a
  bot account, and start threads. Use when the user asks to post or reply on
  Discord, check what was said in a Discord channel, tell the team something
  on Discord, or follow up in a Discord thread; and when a Discord message you
  read needs an answer. Not for Discord direct messages or voice.
---

# Discord as a bot

`scripts/discord_bot.py` acts on Discord as one bot account. Each run makes its
API calls, prints one JSON object, and exits. `"ok": true` means it worked;
`"ok": false` carries an `error` to read and act on.

```bash
D=~/.agents/skills/discord-bot/scripts/discord_bot.py   # or ~/.claude/skills/...
```

## Start with `check`

Run it once per session, before posting:

```bash
python3 $D check
```

It reports the bot's name, its servers, its default channel and what the bot may
do there, whether `@name` mentions work, and two things from the bot's
configuration that you need:

- **`channels`**: what each channel is for. Post where it says, not where it is convenient.
- **`people`**: who is who, by Discord handle. Use these to tag people.

If it fails with "no bot token", the bot isn't set up on this machine. Point the
user at the skill's README; don't try to find a token yourself.

## Which bot

`--identity <name>`, else `$DISCORD_BOT_IDENTITY`, else `default`. A machine with
several bots, one per project or team, sets `DISCORD_BOT_IDENTITY` per project.
Use the identity you are given; never switch to another one to get around a
refusal.

## Posting

```bash
python3 $D post --channel agents --agent Scout --session pr-review --project "repo#47" \
  --message "Review done: two blocking comments on the migration."
```

- `--channel` takes a name or an id; leave it out for the default channel.
- `--message -` reads the text from standard input. Use it for anything with
  quotes or several lines.
- Discord's limit is 2,000 characters, header included. A longer message is
  refused, not cut: shorten it or post in parts.

The output gives the new `messageId` and a `url` to link to.

### The header

`--agent`, `--session` and `--project` put one line above the message:

```
👤 Scout  🎯 pr-review  📦 repo#47
```

Use all three when several agents share one bot, so a reader can tell them
apart. Pick them at the start of a session and keep them for every post.

- `--agent`: a name for whoever is posting, one a teammate can address: `Scout`.
  Two agents in one session need different names.
- `--session`: a short, stable name for this working session: `pr-review-thu`.
- `--project`: what the work is about. An issue or package (`repo#47`,
  `scorer`) beats a whole repository.

### Mentions

`@name` becomes a real mention that notifies the person, and `#channel` becomes
a channel link. A name must match a member's username, display name or server
nickname exactly, ignoring case; partial names are never guessed. Text inside
code or a URL is left alone, and `@everyone` and `@here` never ping anyone.

A name that matches nobody, or more than one member, stays plain text and is
listed once under `warnings`. Check the `people` list from `check` and retry
with the exact handle.

## Reading

```bash
python3 $D read --channel agents --limit 20
python3 $D read --channel agents --limit 100 --before <oldest messageId seen>
```

Newest first, up to 100 per call; `--before` pages further back. A message that
has a thread carries its `threadId`.

## Threads

Keep a side conversation, such as a review or a debugging back-and-forth,
attached to the message that started it instead of flooding the channel.

```bash
python3 $D thread --channel agents --message-id <id> --name "PR 47 review"
python3 $D post   --thread <threadId> --agent Scout --session pr-review --project "repo#47" --message "Fixed."
python3 $D read   --thread <threadId>
```

Address a thread by its `threadId`, never by name. A message can carry only one
thread; starting a second fails with status 409.

## Editing and deleting

```bash
python3 $D edit   --channel agents --message-id <id> --message "Corrected text"
python3 $D delete --channel agents --message-id <id>
```

Add `--thread <threadId>` for a message inside a thread. `edit` keeps the
message's header and replaces the rest; to fix a wrong header, delete and post
again.

## How to behave on Discord

- **Answer on Discord.** If a message you read needs a reply, reply in that
  channel or thread. People there can't see your chat with the user.
- **Edit rather than repost** to fix a mistake, add a detail, or update a
  status. Post new for a new topic or a reply to someone else.
- **Link to things**: pull requests, issues, files, other messages (each post's
  `url`).
- **Ask for a missing permission rather than working around it.** When the
  output says the bot lacks a permission, tell the user; only a server admin
  can grant it.
