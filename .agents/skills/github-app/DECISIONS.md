# github-app — decisions

**Read this before changing `scripts/github_app.py`.** Each entry is a
decision, why it was made, and what was tried and rejected.

---

## An App, not a machine user

**Decision.** An agent's GitHub identity is a GitHub App, acting through
installation tokens.

**Why.** An App is no organization member, so it takes no paid seat; its key
mints tokens, so no personal access token expires on anyone; and its work is
marked `[bot]`, so nobody mistakes it for a person. It needs no server.

**Where it stops applying.** An App's bot user can't be an issue assignee
(the assignment request returns 403) or a requested reviewer. Where GitHub is
the surface an agent claims work on by assignment, it needs a machine user,
which this skill doesn't manage. This skill is for agents that claim on an
issue tracker and use GitHub for code.

## The key stays a file, never the keychain

**Decision.** The private key is a file: a copy in
`~/.config/github-app/<identity>.pem` (mode 600) on a laptop, or a path or the
key's text in the environment on a server.

**Why.** GitHub hands you a file, and `openssl` signs from a file. The file
gets the protection an SSH key gets.

**Rejected: the keychain, as `linear-app` does for its client secret.** macOS
`security` takes the value only as an argument, so the whole private key
would be visible to this user's other processes while it is stored, and it
hands a multi-line value back hex-encoded. A key is also not something a
person types, which is what the keychain prompt suits.

**Where it stops applying.** On a machine where a key at rest in a file is not
acceptable, put it in the environment from a secrets manager instead.

## RS256 by `openssl`, not by Python

**Decision.** The token GitHub asks for, a JWT signed with RS256, is signed by
running `openssl dgst -sha256 -sign`. Everything else is standard library.

**Why.** Python's standard library has no RSA, and the skill installs no
packages. `openssl` is on every macOS and almost every Linux. The key goes to
it as a file in a private temporary folder, removed straight after, never as
an argument.

**Rejected: a pure-Python RSA signer.** Hand-written cryptography is the wrong
place to save a dependency.

The JWT is dated a minute in the past and lasts 9 minutes: GitHub refuses one
issued "in the future" by a fast clock, and allows at most 10 minutes.

## Renew at half a token's life

**Decision.** Same as `linear-app`: the cache records `renewAt`, half the life
GitHub reports. An installation token lasts an hour, so it is replaced after
30 minutes.

**Why.** A process that keeps the token it was handed, such as a long `git
push`, still has at least half an hour. Minting again costs one request and
revokes nothing.

## Wiring is per repository on a laptop, per process on a server

**Decision.** On a laptop, `wire` writes a repository's **local** git config:
a credential helper for `https://github.com`, preceded by an empty value, and
`user.name` and `user.email` for the bot. `gh` runs through the script's `gh`
command, which sets `GH_TOKEN` for that one process. On a server, `env`
prints `GIT_CONFIG_*` and `GIT_AUTHOR_*`/`GIT_COMMITTER_*` lines for the
role's environment file.

**Why.** The person's own git and `gh` must keep acting as the person. A
global helper, a global `user.name` or an exported `GH_TOKEN` would make their
own commits and pushes come from the App. The empty helper value clears
helpers from lower-priority config, such as the macOS keychain helper, for
github.com in that repository only; a test proves the person's global helper
never answers there. `GIT_CONFIG_*` (git 2.31+) outranks every config file and
applies to one process, which is exactly one role on a shared server.

`wire` also sets `commit.gpgsign` and `tag.gpgsign` to `false` in that
repository, and `env` does the same for a server process: a person who signs
every commit would otherwise sign the App's commits with their own key,
claiming them cryptographically as theirs. The first `wire` keeps the
repository's own values for these settings and for `user.name` and
`user.email`, such as a work email, under `github-app.saved-*`, and `unwire`
puts them back.

**Rejected: setting `GH_TOKEN` in a project's environment or settings.** A
token lasts an hour, and `gh` has no hook to fetch one, so a stored token goes
stale mid-session.

**Rejected: a global helper keyed by repository path.** Git matches helpers by
URL, not by folder, so it can't tell the person's checkout of a repository
from the agent's.

**Where it stops applying.** SSH remotes use SSH keys, which this skill does
not manage; `wire` warns when `origin` isn't `https://`.

## Environment credentials belong to one identity

**Decision.** As in `linear-app`: `GITHUB_APP_*` apply only to the identity
named by `GITHUB_APP_IDENTITY` (or `default`), and an App ID needs exactly one
key source.

**Why.** A server's environment file holds one role's credentials. Lending
them to another `--identity` would act as the wrong App.

## Output

**Decision.** `token`, `credential`, `env` and `gh` print bare output, for
`$(...)`, git, environment files and `gh` itself, with errors on stderr and
exit 1. Every other command prints one ASCII JSON object with `ok`, and exits
0 or 1.

---

## Open questions

### GitHub's MCP server with an installation token (2026-10-03)

Not wired. GitHub's MCP server documents personal access tokens and OAuth. An
installation token may work for most tools, but whether it does, and which
tools assume a user (such as "who am I"), is unverified. If it works, `wire`
could register the server with a `headersHelper`, as `linear-app` does.

### The last bug-hunter iteration's fixes are unreviewed (2026-10-03)

Bug-hunter's third and last iteration added two fixes no finder pass has read:
`env` turning off commit and tag signing, and `wire` saving the repository's
own `user.name`, `user.email` and signing settings for `unwire` to restore,
with a `github-app.wired` marker so a second `wire` doesn't save the bot's
values as the person's. Both have regression tests. Recommended: one
bug-hunter run scoped to `cmd_wire`, `cmd_unwire` and `cmd_env`.

### Untested against a live App (2026-10-03)

Every request is tested against a fake GitHub. The first live run should
confirm minting, the installation lookup, `check`'s permissions and
repository list, the bot's noreply email, and a push and a draft pull request
from a wired repository.
