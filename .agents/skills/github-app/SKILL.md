---
name: github-app
description: >-
  Let an agent act on GitHub as its own GitHub App, so its commits, branches,
  pull requests and comments show as a bot, never as its human, with tokens
  minted on demand. Use when the user asks to set up, check, wire or switch an
  agent's GitHub identity, when an agent's pushes or pull requests show up
  under a person's name, when git push or gh fails with an authentication
  error in a repository wired to an App, or before an agent opens a pull
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

`--identity <name>`, else `$GITHUB_APP_IDENTITY`, else `default`. Use the
identity you are given; never switch to another to get around a refusal.

## Working in a repository

A repository wired to an App (`python3 $G wire` in it) pushes and commits as
the App with plain `git`. Check before you push:

```bash
git config --local user.name     # <app-slug>[bot] in a wired repository
```

Run `gh` through the script, so it acts as the App for that one command:

```bash
python3 $G gh pr create --draft --title "..." --body-file body.md
python3 $G gh pr view 12 --comments
```

Never export `GH_TOKEN` yourself, and never run plain `gh` in a wired
repository: plain `gh` acts as the person who logged it in.

## When something fails

Run `python3 $G check`.

- **`ok: true`**: the App works. `commitsAs` is who commits will show as, and
  `canPushAndOpenPullRequests` must be `true`. Warnings name any missing
  permission or unreachable repository; tell the user, who changes the App's
  settings or installation in a browser.
- **"no App credentials"**: this identity isn't set up on this machine. Point
  the user at the README's setup. A person has to do the first steps.
- **"is not installed on"** or **"several accounts"**: the App isn't
  installed where the config says, or the config needs an `owner`.
- **git push asks for a password**, or pushes as the person: the repository
  isn't wired, or its `origin` uses SSH. `wire` warns about the latter.

## What an App can't do

An App **can't be an issue's assignee** or a **requested reviewer**. Claim
work on the issue tracker the team uses for claims, such as Linear by
delegate, not on GitHub. A person reviews and merges every pull request an App
opens; never merge your own.

## Rules

- Never wire a repository the user didn't ask for, and never set git config
  with `--global`: that would make the person's own commits and pushes come
  from the App.
- Never print, copy or commit the private key or a token. `token` prints a raw
  token for programs; don't run it to look at one.
- Never ask the user to paste a key to you. `store-credentials` takes a path to
  the file GitHub generated.
