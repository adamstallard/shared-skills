---
name: github-app
description: >-
  Let an agent act on GitHub as its own GitHub App, so its commits, branches,
  pull requests and comments show as a bot, never as its human, with tokens
  minted on demand. Use when the user asks to set up, check, wire or switch an
  agent's GitHub identity, when an agent's pushes or pull requests show up
  under a person's name, when git push or gh fails with an authentication
  error while acting as an App, or before an agent opens a pull
  request in such a repository.
---

# GitHub as an App

An agent with its own GitHub identity acts as a **GitHub App**: its work shows
as `<app-slug>[bot]` with a bot badge. `scripts/github_app.py` holds each
identity's App ID and private key and mints installation tokens from them,
which last an hour, whenever one is needed. Nobody renews anything.

```bash
G=~/.agents/skills/github-app/scripts/github_app.py   # or ~/.claude/skills/...
```

## Which identity

`--identity <name>`, else `$GITHUB_APP_ACT_AS`, else `$GITHUB_APP_IDENTITY`,
else `default`. Use the
identity you are given; never switch to another to get around a refusal.

## Acting as the App

The App's identity lives only in the environment of the processes that act as
it: `GIT_AUTHOR_*` and `GIT_COMMITTER_*` name the bot, and `GIT_CONFIG_*` adds
a credential helper that mints tokens and turns signing off. Nothing is
written to any git config file. Check before you commit or push:

```bash
echo "$GIT_AUTHOR_NAME"     # <app-slug>[bot] when this process acts as the App
```

**In a Claude Code project wired with `wire --project`**, every command you run
already has that environment, so use plain `git`. Run `gh` through the script,
because `gh` needs a token and a token lasts only an hour:

```bash
python3 $G gh pr create --draft --title "..." --body-file body.md
python3 $G gh pr view 12 --comments
```

**Anywhere else**, run each command through `run`, which sets the environment
and `GH_TOKEN` for that one process:

```bash
python3 $G run -- git commit -m "..."
python3 $G run -- git push -u origin my-branch
```

Never export `GH_TOKEN` yourself, and never run plain `gh`: it acts as the
person who logged it in.

## When something fails

Run `python3 $G check`.

- **`ok: true`**: the App works. `commitsAs` is who commits will show as, and
  `canPushAndOpenPullRequests` must be `true`. `canClaimIssues` must be
  `true` before you claim or comment on an issue. Warnings name any missing
  permission or unreachable repository; tell the user, who changes the App's
  settings or installation in a browser.
- **"no App credentials"**: this identity isn't set up on this machine. Point
  the user at the README's setup. A person has to do the first steps.
- **"is not installed on"** or **"several accounts"**: the App isn't
  installed where the config says, or the config needs an `owner`.
- **git push asks for a password**, or commits or pushes as the person: the
  command ran without the App's environment (`$GIT_AUTHOR_NAME` isn't the
  bot), or `origin` uses SSH, which pushes with the person's SSH key. Use
  `run --` and an `https://` remote.

## What an App can't do

An App **can't be an issue's assignee** or a **requested reviewer**. Never
try to assign yourself. To claim a GitHub issue, add the label that names you
and comment; the assignee is a person's. On Linear, claim by delegation.
Claim only on the tracker the team uses for claims. A person reviews and merges every pull request an App
opens; never merge your own.

## Rules

- Never wire a project the user didn't ask for, and never write the App's
  identity into git config, local or `--global`: config outlives the process
  and reaches the person's own commits and pushes.
- Never print, copy or commit the private key or a token. `token` prints a raw
  token for programs; don't run it to look at one.
- Never ask the user to paste a key to you. `store-credentials` takes a path to
  the file GitHub generated.
