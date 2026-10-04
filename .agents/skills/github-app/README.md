# github-app

Gives an agent its own identity on GitHub: a **GitHub App**, so the agent's
commits, branches, pull requests and comments show as `<app-slug>[bot]`, not
as you. An App isn't an organization member, so it takes no paid seat. The
long-lived credential is the App's private key, and
`scripts/github_app.py` mints hour-long tokens from it whenever one is
needed, so nobody renews a token by hand.

No server is needed. Minting a token and calling GitHub are outbound
requests; the App's webhook stays off.

**What an App can't do:** be an issue's assignee or a requested reviewer. It
can still claim GitHub issues: with a label naming the agent and a comment,
leaving the assignee to a person.

---

## Apps, installations, and identities

Setup involves four things. Three are on GitHub:

- **App**: the agent's account on GitHub.
  - Its work shows as `<app-slug>[bot]`.
  - It has an **App ID** and a **private key** (a `.pem` file). Setup asks
    for both.
  - One App per agent role: a reviewer and a docs writer are two Apps.
- **Installation**: the App added to one account.
  - That account chooses which of its repositories the App can reach.
  - An App can be installed once per account.
- **Owner**: the account an installation is on.
  - An organization, such as `acme`, or a personal account, such as yours.

One is on your machine:

- **Identity**: a short name you give one App acting on one account.
  - For example `acme` or `reviewer`.
  - You pick it in setup and name it in every command.

**For example,** you create an App called `acme-agent` and install it on the
`acme` organization. On your machine, you store it as the identity `acme`.

**How many identities you need:**

- **One App on one account:** one identity.
- **Two roles on one account:** two Apps, so two identities.
- **One App on two accounts,** such as an organization and your personal
  account: two identities, made from the same App ID and key, each naming
  its own owner. The App has to be installable on **Any account** (step 1).

---

## Setup

You need **Python 3.8+**, **openssl** and **git 2.31+**, and someone who can
create Apps for the account that owns the repositories. Allow about 10
minutes per identity.

### 1. Create the App

On GitHub: **Settings → Developer settings → GitHub Apps → New GitHub App**,
under the organization that owns the repositories (or your own account).

| Field                 | Value |
| --------------------- | ----- |
| GitHub App name       | The agent's name, e.g. `acme-agent`. Commits show as `acme-agent[bot]`. |
| Homepage URL          | Anything; your repository's URL is fine. |
| Webhook               | **Untick Active.** Nothing needs to receive events. |
| Repository permissions | **Contents: Read and write**, **Pull requests: Read and write**, **Metadata: Read-only** (always on). Add **Issues: Read and write** if the agent claims or comments on issues (`check` shows `canClaimIssues`), and **Workflows: Read and write** if it changes files under `.github/workflows/`. |
| Where can this GitHub App be installed? | **Only on this account**, or **Any account** if the agent will work on other accounts too. |

Then, on the App's **General** page:

- The **App ID** is near the top. Step 3 asks for it, because the script
  identifies the App by it when it asks GitHub for tokens. Copy it from here
  then; it stays on this page and isn't secret.
- Under **Private keys**, at the bottom of the page, **Generate a private
  key**. GitHub downloads a `.pem` file. It is the App's password; treat it
  like an SSH key.

### 2. Install it

In the App's settings, open **Install App** in the left sidebar. It lists your
account and the organizations you can install the App on. For each one the
agent works on:

1. Click **Install**.
2. Choose **Only select repositories**, and pick the ones the agent works in.
3. Confirm with **Install**. For an organization you don't own, this sends a
   request that an owner approves.

Steps 1 and 2 happen on GitHub. The rest runs on your machine: type the
commands below, or have your agent run them ([Asking your
agent](#asking-your-agent)).

### 3. Store an identity

On your own machine, once per installation:

```bash
python3 ~/.agents/skills/github-app/scripts/github_app.py --identity acme \
  store-credentials --app-id 123456 --key-file ~/Downloads/acme-agent.2026-10-03.private-key.pem
```

It checks that the file is a key openssl can sign with, copies it to
`~/.config/github-app/acme.pem`, and records the App ID. Then delete the
downloaded copy.

If the App is installed on more than one account, add `--owner <account>`,
and store one identity per account from the same key:

```bash
G=~/.agents/skills/github-app/scripts/github_app.py
python3 $G --identity acme     store-credentials --app-id 123456 --key-file agent.pem --owner acme
python3 $G --identity personal store-credentials --app-id 123456 --key-file agent.pem --owner your-login
```

### 4. Check it

```bash
python3 ~/.agents/skills/github-app/scripts/github_app.py --identity acme check
```

It mints a token and shows the App, `commitsAs`
(`acme-agent[bot] <…@users.noreply.github.com>`), the installation and its
permissions, the repositories it can reach, and
`"canPushAndOpenPullRequests": true`. It writes nothing to GitHub. Run it for
each identity.

### 5. Connect a Claude Code project

```bash
python3 ~/.agents/skills/github-app/scripts/github_app.py --identity acme wire --project ~/code/web
```

Every Claude Code session in `~/code/web` now acts as the App, once you trust
the folder; your own terminal doesn't. Wire each project to the identity for
the account that owns its repository.

The project's `origin` must be an `https://` URL.

In those sessions `git` works as usual. `gh` goes through the script, which
gives it a fresh token:

```bash
python3 ~/.agents/skills/github-app/scripts/github_app.py --identity acme gh pr create --draft --fill
```

To stop, `unwire --project ~/code/web`.

---

## Asking your agent

An agent with this skill installed runs the same commands for you. After
steps 1 and 2 on GitHub, you can ask it, for example:

- *"Store a github-app identity called acme from
  ~/Downloads/acme-agent.2026-10-03.private-key.pem, App ID 123456."* Give it
  the key's path, never its contents.
- *"Add a github-app identity called personal for my account your-login,
  using the same App and key as acme."*
- *"Check the acme github-app identity."*
- *"Wire ~/code/web to the acme github-app identity,"* and later *"Unwire
  ~/code/web."*
- *"My push went out as me, not the App; find out why."* It runs `check`,
  says what it found, and names anything only you can fix on GitHub.
- *"Remove the acme github-app identity and unwire every project under
  ~/code that uses it."*

---

## Other agents and scripts

Outside a wired Claude Code project, run a command through `run`. That
command, and everything it starts, acts as the App, with `GH_TOKEN` set for
`gh`:

```bash
python3 ~/.agents/skills/github-app/scripts/github_app.py --identity acme run -- ./release.sh
```

`GH_TOKEN` lasts an hour, so `run` suits a command, not a long session. Your
own `GIT_CONFIG_*` entries keep working: `run` numbers the App's after them.

**Programs:** `github_app.py --identity acme token` prints a token to use as a
bearer token. It lasts an hour; ask again rather than storing it.

---

## On a server

Give each role its own App, its own identity and its own environment file,
for example a systemd `EnvironmentFile` readable only by that service.

1. **Its credentials,** in place of `store-credentials`:

   ```ini
   GITHUB_APP_IDENTITY=reviewer
   GITHUB_APP_ID=123456
   GITHUB_APP_PRIVATE_KEY_FILE=/etc/<service>/reviewer.pem
   ```

   They belong to the identity named by `GITHUB_APP_IDENTITY` (or `default`)
   and win over stored credentials for that identity only.
   `GITHUB_APP_PRIVATE_KEY` can hold the key's text instead of a path, and
   `GITHUB_APP_OWNER` or `GITHUB_APP_INSTALLATION_ID` picks the installation.

2. **The App's variables,** in place of `wire`:

   ```bash
   python3 ~/.agents/skills/github-app/scripts/github_app.py --identity reviewer env >> /etc/<service>/reviewer.env
   ```

   Every value is double-quoted and escaped, so the file works as a systemd
   `EnvironmentFile` and with `set -a; . reviewer.env` in a shell. If the file
   already sets `GIT_CONFIG_COUNT=N`, pass `--offset N`: the App's entries are
   then numbered after yours, and its `GIT_CONFIG_COUNT` line, coming later,
   counts both. `env` refuses to run without `--offset` when
   `GIT_CONFIG_COUNT` is already set in its own environment.

Processes of one role share its cached token, with a lock so they never mint
over each other.

---

## Where an App can be installed

The **Where can this GitHub App be installed?** setting from step 1:

- **Only on this account:** the App can be installed only on the account that
  created it.
- **Any account:** any user or organization can install it, and it reaches
  only the repositories each one grants. Your key stays yours. Others install
  it from **Install App** or from its page,
  `https://github.com/apps/<app-slug>`.

GitHub calls these private and public. To change it after creating the App:
its settings → **Advanced** → **Danger zone** → **Make public** or **Make
private**. It can be made private again only while it's installed on no
other account.

The alternative to one App set to **Any account** is one App per account, each
set to **Only on this account**, with its own bot name and key.

---

## How it works

For anyone scripting around the skill or debugging it.

### Each identity's files

| File | Holds |
| ---- | ----- |
| `~/.config/github-app/<identity>.json` | Its config: `appId`, `owner` and the [config fields](#config-fields) below. |
| `~/.config/github-app/<identity>.pem` | Its copy of the App's private key, mode 600. |
| `~/.local/state/github-app/<identity>.json` | Its cached token, shared by every process acting as it. |

`$XDG_CONFIG_HOME` and `$XDG_STATE_HOME` replace `~/.config` and
`~/.local/state` when set.

Every token is minted for one installation, so it reaches that account's
chosen repositories and nothing else. That's why each account needs its own
identity.

### Which identity a command uses

`--identity`, else `GITHUB_APP_ACT_AS` (which `run`, `wire` and `env` set),
else `GITHUB_APP_IDENTITY`, else `default`.

### The agent's environment

The agent acts as the App through environment variables given only to the
processes that act as it. Nothing is written to a git config file, so your own
git, in every repository, checkout and worktree, stays yours. `run`, `wire`
and `env` all give the agent the same variables:

- `GIT_AUTHOR_NAME`, `GIT_AUTHOR_EMAIL`, `GIT_COMMITTER_NAME` and
  `GIT_COMMITTER_EMAIL` for the App's bot. They outrank `user.*`, `author.*`,
  `committer.*` and anything included from another config file.
- `GIT_CONFIG_*` (git 2.31+), which outranks every config file: an empty
  credential helper for `https://github.com`, which clears yours (such as the
  macOS keychain), then a helper that hands git a fresh token for this
  identity, and commit and tag signing off, so your signing key never signs
  the App's commits.
- `GITHUB_APP_ACT_AS`, the identity the script itself uses there. It is not
  `GITHUB_APP_IDENTITY`, which says only whose `GITHUB_APP_*` credentials an
  environment holds.

They hold no key and no token: git asks the helper for a token each time it
needs one.

### What `wire` changes

`wire --project <folder>` adds the variables to the `env` object of
`<folder>/.claude/settings.local.json`, creating the file if needed. Claude
Code applies that `env` to the commands it runs, and a session in a worktree
under `.claude/worktrees/` uses the main checkout's file.

- It refuses to overwrite any key you set there yourself.
- It records what it added in the same `env`, as `GITHUB_APP_WIRED`, so
  `unwire` works even after you move the folder. `unwire` removes exactly the
  keys `wire` added and leaves a key you changed since. If you delete
  `GITHUB_APP_WIRED` by hand, the keys become yours to remove.
- Claude Code applies project and local `env` only after you trust the
  folder. It ignores a settings value for a variable that the Claude Desktop
  app's or a self-hosted runner's launch environment already sets.

---

## Config fields

`~/.config/github-app/<identity>.json`:

| Field            | What it does |
| ---------------- | ------------ |
| `appId`          | The App's ID. `store-credentials` writes it. |
| `owner`          | The account whose installation to use. Needed when the App is installed on more than one. `store-credentials --owner` writes it. |
| `installationId` | Use this installation directly, skipping the lookup by `owner`. |
| `keyFile`        | Read the key from this path instead of `<identity>.pem`, for example so several identities share one copy. `forget` leaves such a file alone. |
| `repos`          | `["owner/name", …]`: `check` warns if the App can't reach any of them. |

---

## When something goes wrong

**"no App credentials for identity …"**: nothing is stored for that identity.
Run `store-credentials`, or set the environment variables, and check the
identity name.

**"openssl could not sign"**: the key file isn't the `.pem` GitHub generated,
or it's damaged. Generate a new key on the App's page.

**"the App is not installed on …"**: install the App on that account, or fix
`owner`.

**"installed on several accounts"**: set `owner` for this identity, with
`store-credentials --owner`, and store another identity for each other
account.

**`canPushAndOpenPullRequests` is false**: give the App the permissions in
step 1, then accept the new permissions on the installation (GitHub asks the
account's owner).

**git still commits or pushes as you, or asks for a password**: the command
ran without the App's environment. Check `echo $GIT_AUTHOR_NAME`; use `run --`,
or `wire --project` in a trusted Claude Code project. Make sure
`origin` is an `https://` URL--an SSH URL would push as you.

**A push to one account's repository is refused**: the identity's token is
for another account's installation. Use the identity whose `owner` is that
account.

**A key is lost or leaked:** delete it on the App's page under **Private
keys** and generate another. Tokens minted from it stop working within the
hour.

To remove an identity from a machine: `github_app.py --identity <name>
forget`, then `unwire --project` in each project still wired to it. To find
wired projects, search for the marker, for example `grep -l GITHUB_APP_WIRED
~/code/*/.claude/settings.local.json`.
