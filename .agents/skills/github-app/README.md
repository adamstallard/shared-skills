# github-app

Gives an agent its own identity on GitHub: a **GitHub App**, so the agent's
commits, branches, pull requests and comments show as `<app-slug>[bot]`, not
as you. An App isn't an organization member, so it takes no paid seat. The
long-lived credential is the App's private key, and
`scripts/github_app.py` mints hour-long installation tokens from it whenever
one is needed, so nobody renews a token by hand.

No server is needed. Minting a token and calling GitHub are outbound
requests; the App's webhook stays off.

**What an App can't do:** be an issue's assignee or a requested reviewer. It
can still claim GitHub issues: with a label naming the agent and a comment,
leaving the assignee to a person. On Linear, an agent claims by delegation.

---

## Setup

You need **Python 3.8+**, **openssl** and **git 2.31+**, and someone who can
create Apps for the account that owns the repositories. Allow about 10
minutes per identity.

### 1. Create the App

On GitHub: **Settings → Developer settings → GitHub Apps → New GitHub App**,
under the organization that owns the repositories (or your own account). One
App per agent identity.

| Field                 | Value |
| --------------------- | ----- |
| GitHub App name       | The agent's name, e.g. `acme-agent`. Commits show as `acme-agent[bot]`. |
| Homepage URL          | Anything; your repository's URL is fine. |
| Webhook               | **Untick Active.** Nothing needs to receive events. |
| Repository permissions | **Contents: Read and write**, **Pull requests: Read and write**, **Metadata: Read-only** (always on). Add **Issues: Read and write** if the agent claims or comments on issues. |
| Where can it be installed | **Only on this account.** |

Then, on the App's page:

- Note the **App ID** near the top.
- Under **Private keys**, **Generate a private key**. GitHub downloads a
  `.pem` file. It is the App's password; treat it like an SSH key.
- **Install App**, on the account that owns the repositories, for **only
  the repositories** the agent works in.

### 2. Name the identity

Pick a short name for this agent on your machine: `acme`, `reviewer`.
Commands take `--identity <name>`, else `GITHUB_APP_ACT_AS` (which `run`,
`wire` and `env` set), else `GITHUB_APP_IDENTITY`, else `default`.

### 3. Store the key

On your own machine:

```bash
python3 ~/.agents/skills/github-app/scripts/github_app.py --identity acme \
  store-credentials --app-id 123456 --key-file ~/Downloads/acme-agent.2026-10-03.private-key.pem
```

It checks that the file is a key openssl can sign with, copies it to
`~/.config/github-app/acme.pem` (mode 600), and records the App ID. Then
delete the downloaded copy. Add `--owner <account>` if the App is installed on
more than one account.

On a server, set these in that service's environment instead, for example in
a systemd `EnvironmentFile` readable only by the service:

```ini
GITHUB_APP_IDENTITY=reviewer
GITHUB_APP_ID=123456
GITHUB_APP_PRIVATE_KEY_FILE=/etc/<service>/reviewer.pem
```

They belong to the identity named by `GITHUB_APP_IDENTITY` (or `default`) and
win over stored credentials for that identity only. `GITHUB_APP_PRIVATE_KEY`
can hold the key's text instead of a path.

### 4. Check it

```bash
python3 ~/.agents/skills/github-app/scripts/github_app.py --identity acme check
```

It mints the first token and shows the App, `commitsAs`
(`acme-agent[bot] <…@users.noreply.github.com>`), the installation's
permissions, the repositories it can reach, and
`"canPushAndOpenPullRequests": true`. It writes nothing to GitHub.

### 5. Connect the agent

The agent's identity lives only in the environment of the processes that act
as it. Nothing is ever written to a git config file, so your own git, in every
repository, checkout and worktree, stays yours. The environment holds:

- `GIT_AUTHOR_NAME`, `GIT_AUTHOR_EMAIL`, `GIT_COMMITTER_NAME` and
  `GIT_COMMITTER_EMAIL` for the App's bot. They outrank `user.*`, `author.*`,
  `committer.*` and anything included from another config file.
- `GIT_CONFIG_*` (git 2.31+), which outranks every config file: an empty
  credential helper for `https://github.com`, which clears yours (such as the
  macOS keychain), then a helper that hands git a fresh token, and commit and
  tag signing off, so your signing key never signs the App's commits.
- `GITHUB_APP_ACT_AS`, the identity the script itself uses there. It is not
  `GITHUB_APP_IDENTITY`, which says only whose `GITHUB_APP_*` credentials an
  environment holds.

It holds no key and no token. `origin` must be an `https://` URL: an SSH
remote pushes with your SSH key.

**A Claude Code project:**

```bash
python3 ~/.agents/skills/github-app/scripts/github_app.py --identity acme wire --project ~/code/web
```

This adds those variables to the `env` object of
`~/code/web/.claude/settings.local.json`, creating the file if needed. Claude
Code applies that `env` to the commands it runs, and a session in a worktree
under `.claude/worktrees/` uses the main checkout's file. So every session in
that project acts as the App, and your own terminal doesn't. `wire` refuses to
overwrite any key you set there yourself. It records what it added in the
same `env`, as `GITHUB_APP_WIRED`, so `unwire --project ~/code/web` works
even after you move the folder. It removes exactly the keys `wire` added and
leaves a key you changed since. If you delete `GITHUB_APP_WIRED` by hand, the
keys become yours to remove.
Claude Code applies project and local `env` only after you trust the folder.
It also ignores a settings value for a variable that the Claude Desktop app's
or a self-hosted runner's launch environment already sets.

The agent runs `gh` through the script, so `gh` gets a fresh token for that
one command and nothing is exported:

```bash
python3 ~/.agents/skills/github-app/scripts/github_app.py --identity acme gh pr create --draft --fill
```

**Any other agent or script:** run each command through `run`, which sets the
same variables, plus `GH_TOKEN`, for that one process:

```bash
python3 ~/.agents/skills/github-app/scripts/github_app.py --identity acme run -- git push -u origin my-branch
```

`GH_TOKEN` lasts an hour, so `run` suits a command, not a long session. The
caller's own `GIT_CONFIG_*` entries keep working: `run` numbers the App's
after them.

**On a server, one process per role:** print the lines for the role's
environment file:

```bash
python3 ~/.agents/skills/github-app/scripts/github_app.py --identity reviewer env >> /etc/<service>/reviewer.env
```

Every value is double-quoted and escaped, so the same file works as a systemd
`EnvironmentFile` and with `set -a; . reviewer.env` in a shell. If that file
already sets `GIT_CONFIG_COUNT=N`, pass `--offset N`: the App's entries are
then numbered after yours, and its `GIT_CONFIG_COUNT` line, coming later,
counts both. `env` refuses to run without `--offset` when `GIT_CONFIG_COUNT`
is already set in its own environment.

**Programs:** `github_app.py --identity acme token` prints a token to use as a
bearer token. It lasts an hour; ask again rather than storing it.

---

## Optional config

`~/.config/github-app/<identity>.json` (or under `$XDG_CONFIG_HOME`):

| Field            | What it does |
| ---------------- | ------------ |
| `appId`          | The App's ID. `store-credentials` writes it. |
| `owner`          | The account whose installation to use, when the App is installed on several. |
| `installationId` | Use this installation directly, skipping the lookup. |
| `keyFile`        | Read the key from this path instead of `~/.config/github-app/<identity>.pem`. `forget` leaves such a file alone. |
| `repos`          | `["owner/name", …]`: `check` warns if the App can't reach any of them. |

## Several roles on one server

Give each role its own App, as in step 1, and its own environment file with
its own `GITHUB_APP_IDENTITY`, `GITHUB_APP_ID` and key, plus the lines from
`env`. Processes of the same role share one cached token under
`~/.local/state/github-app/` (or `$XDG_STATE_HOME`), with a lock so they never
mint over each other.

---

## When something goes wrong

**"no App credentials for identity …"**: nothing is stored for that identity.
Run `store-credentials`, or set the environment variables, and check the
identity name.

**"openssl could not sign"**: the key file isn't the `.pem` GitHub generated,
or it's damaged. Generate a new key on the App's page.

**"the App is not installed on …"**: install the App on that account, or fix
`owner`.

**`canPushAndOpenPullRequests` is false**: give the App the permissions in
step 1, then accept the new permissions on the installation (GitHub asks the
account's owner).

**git still commits or pushes as you, or asks for a password**: the command
ran without the App's environment. Check `echo $GIT_AUTHOR_NAME`; use `run --`,
or `wire --project` in a trusted Claude Code project. Make sure
`origin` is an `https://` URL.

**A key is lost or leaked:** delete it on the App's page under **Private
keys** and generate another. Tokens minted from it stop working within the
hour.

To remove an identity from a machine: `github_app.py --identity <name>
forget`, then `unwire --project` in each project still wired to it. To find
wired projects, search for the marker, for example `grep -l GITHUB_APP_WIRED
~/code/*/.claude/settings.local.json`.
