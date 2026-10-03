# github-app

Gives an agent its own identity on GitHub: a **GitHub App**, so the agent's
commits, branches, pull requests and comments show as `<app-slug>[bot]`, not
as you. An App isn't an organization member, so it takes no paid seat. The
long-lived credential is the App's private key, and
`scripts/github_app.py` mints hour-long installation tokens from it whenever
one is needed, so nobody renews a token by hand.

No server is needed. Minting a token and calling GitHub are outbound
requests; the App's webhook stays off.

**What an App can't do:** be an issue's assignee or a requested reviewer. If
your agents claim work, claim it on your issue tracker (for example by
delegating a Linear issue to the agent), and let GitHub carry the branches
and pull requests.

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
| Repository permissions | **Contents: Read and write**, **Pull requests: Read and write**, **Metadata: Read-only** (always on). Add **Issues: Read and write** only if the agent comments on issues. |
| Where can it be installed | **Only on this account.** |

Then, on the App's page:

- Note the **App ID** near the top.
- Under **Private keys**, **Generate a private key**. GitHub downloads a
  `.pem` file. It is the App's password; treat it like an SSH key.
- **Install App**, on the account that owns the repositories, for **only
  the repositories** the agent works in.

### 2. Name the identity

Pick a short name for this agent on your machine: `acme`, `reviewer`.
Commands take `--identity <name>`, else `GITHUB_APP_IDENTITY`, else `default`.

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

**On your own machine, one repository at a time:**

```bash
cd ~/code/web
python3 ~/.agents/skills/github-app/scripts/github_app.py --identity acme wire
```

That sets this repository's **local** git config only: a credential helper
that hands git a fresh token for `https://github.com`, `user.name` and
`user.email` for the App's bot, and commit signing off, so your own signing key
never signs the App's commits. Your other repositories, and your own global
git and `gh` login, are untouched. `origin` must be an `https://` URL; `wire`
warns if it uses SSH. `unwire` undoes it and gives back any name, email or
signing setting the repository had of its own.

The agent runs `gh` through the script, so `gh` acts as the App for that one
command and nothing is exported:

```bash
python3 ~/.agents/skills/github-app/scripts/github_app.py --identity acme gh pr create --draft --fill
```

**On a server, one process per role:** print the git settings for the role's
environment file:

```bash
python3 ~/.agents/skills/github-app/scripts/github_app.py --identity reviewer env >> /etc/<service>/reviewer.env
```

The lines set the commit name and email and the credential helper through
`GIT_CONFIG_*` variables, which apply to that process only and outrank every
config file. They hold no key and no token.

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

**git still pushes as you, or asks for a password**: run `wire` in that
repository, and make sure `origin` is an `https://` URL.

**A key is lost or leaked:** delete it on the App's page under **Private
keys** and generate another. Tokens minted from it stop working within the
hour.

To remove an identity from a machine: `github_app.py --identity <name>
forget`, then `unwire` in each repository you wired.
