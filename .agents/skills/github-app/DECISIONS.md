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
(the assignment request returns 403) or a requested reviewer. That doesn't
stop an App claiming GitHub issues: it claims with a label naming the agent
(igor uses `igor:<role>`) and a comment, and the assignee stays the person's,
as Linear's delegate is separate from its assignee. An agent needs a machine
user, which this skill doesn't manage, only where it must be the assignee
itself or a requested reviewer.

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

## Identity lives in the process environment, never in git config

**Decision.** The App's git identity is a set of environment variables and is
never written to a git config file. One function, `agent_env`, builds them and
is the only source for every command that uses them:

- `GIT_AUTHOR_NAME`, `GIT_AUTHOR_EMAIL`, `GIT_COMMITTER_NAME` and
  `GIT_COMMITTER_EMAIL` for the bot.
- `GIT_CONFIG_COUNT`/`KEY_n`/`VALUE_n` (git 2.31+): an empty
  `credential.https://github.com.helper`, which clears every helper from
  config files, then this script's `credential` command, and
  `commit.gpgsign` and `tag.gpgsign` set to `false`.
- `GITHUB_APP_ACT_AS`, the identity the script uses in that process (see
  "Environment credentials belong to one identity").

The commands that deliver them:

- `run -- <command>`: execs one command with these variables plus
  `GH_TOKEN`. Its numbering starts after any `GIT_CONFIG_*` the caller
  already has. `gh …` is shorthand for `run -- gh …`.
- `env`: prints the variables as `KEY="value"` lines with `\ " $ `` escaped.
  systemd's `EnvironmentFile=` and a POSIX shell's `set -a; . file` read
  these the same way. It refuses when `GIT_CONFIG_COUNT` is already set,
  unless `--offset N` numbers its entries after the target's `N`.
- `wire --project <folder>`: adds the variables, never `GH_TOKEN`, to the
  `env` object of that folder's `.claude/settings.local.json`, with a
  `GITHUB_APP_WIRED` marker recording what it added (see "wire's bookkeeping
  lives in the settings file"). Through a symlink, it edits the target and
  leaves the link alone. It works everything out first and then makes one
  atomic write, so a failed `wire` leaves the file as it was.
- `unwire --project <folder>`: removes exactly the keys the marker names
  whose values are unchanged, and the marker. Without a marker it refuses and
  changes nothing. `wire` refuses to overwrite any key the marker doesn't
  name, or whose value changed since, including any `GIT_CONFIG_*`.

**Why.** Environment variables reach only the process given them and its
children. `GIT_AUTHOR_*`/`GIT_COMMITTER_*` outrank `user.*`, `author.*`,
`committer.*` and anything those are included from. `GIT_CONFIG_*` outranks
every file. A config file reaches every process that reads it, including the
person's own git. The rejected design proved this: a finder pass on
repository wiring observed each of these in a scratch repository:

1. Wiring a linked worktree wrote the shared `.git/config`, so the person's
   main checkout committed as the bot and pushed through the App.
2. `unwire` with no `wire` deleted the repository's own `user.email`,
   `commit.gpgsign` and github.com helper.
3. `wire` then `unwire` lost a github.com helper the repository already had.
4. A multi-valued `user.email` made `wire` fail halfway. That left the App's
   helper with the person's email and signing; `unwire` then lost a value.
5. A global `author.email` outranked the `user.email` that `wire` set, so the
   App's commits carried the person as author.
6. A local `[include]` after an existing `[user]` section outranked the
   bot's email.
7. An inherited `GIT_DIR` made `wire --repo X` write another repository's
   config while reporting X.
8. `env` lines were unquoted: `set -a; . file` ran the script and left the
   helper value empty.
9. `env` lines replaced any `GIT_CONFIG_*` the role's file already had.

Findings 1 to 7 cannot happen when nothing writes git config. Quoting
and `--offset` fix 8 and 9.

**Claude Code's `env`, checked against its documentation (2026-10-03), not
yet observed in a live session.** Settings `env` applies "to every session
and its subprocesses" and overwrites a variable exported in the shell. "In a
worktree, it uses the file at the main checkout's root." Values in project
and local settings apply after the folder is trusted, and again when the file
changes. They are ignored for a variable that the launch environment of the
Claude Desktop app or a self-hosted runner already sets. No `GIT_*` variable
is on the documented list of variables that project settings may not set.

**Rejected: wiring a repository's local git config**, which an earlier
version did: a helper, `user.name`/`user.email` and signing off in
`.git/config`, with the repository's own values saved for `unwire`. Every
finding above came from it, and saving and restoring config the person also
edits had no correct form.

**Where it stops applying.**
- A tool that ignores `GIT_CONFIG_*` or `GIT_AUTHOR_*`, such as a library
  that reimplements git (libgit2, JGit, go-git, isomorphic-git) and reads
  only config files, acts as the person or not at all.
- A process launched without the environment acts as the person: a terminal
  outside the wired project, a program that clears its children's
  environment, or a daemon started before `wire`.
- An SSH `origin` pushes with the person's SSH key, whatever the
  environment says.
- Wiring a project makes every Claude Code session there act as the App,
  including one the person starts for their own work.

## wire's bookkeeping lives in the settings file

**Decision.** `wire` records what it wrote in the file it wrote it to: one
more key in the same `env` object, `GITHUB_APP_WIRED`. Its value is compact
JSON:

```json
{"createdEnv":false,"createdFile":true,"identity":"acme","sha256":{"GIT_AUTHOR_NAME":"<16 hex>", ...}}
```

`sha256` maps each key `wire` added to the first 16 hex digits of its
value's SHA-256. `unwire` removes a key only while its value still matches,
and warns about the rest. `createdFile` and `createdEnv` say whether the first
`wire` created the file or its `env`, so `unwire` removes only those. A
rewire, to the same or another identity, keeps them and replaces the marker.
There is no other state.

**Why JSON, and why digests.** An `env` value must be a string, and JSON is
the one encoding the standard library both writes and reads back exactly.
Digests rather than values, because the values already sit next to the
marker. Repeating them would double what `wire` adds to every session's
environment, the helper command included. A digest is enough to tell whether
a value changed.

**Why.** Five rounds of review found the separate record and the file
drifting apart:
- a failed write left one updated and not the other, which needed a write
  order and a rollback;
- through a symlink, the record named the link and `unwire` missed the
  target;
- a repointed link left the record naming one file and `wire` editing
  another;
- a recorded file that could no longer be read left both commands refusing;
- moving the project folder lost the record, which was keyed by the folder's
  path, and stranded the keys.

With the record inside the file, none of these can happen. Moving a folder,
repointing a link, or reaching the file by another spelling changes nothing,
because the file carries its own state. Rollback reduces to computing
everything first and making one atomic write.

**Rejected: a separate record under `$XDG_STATE_HOME/github-app/wired/`,
keyed by the project's path**, which the version before this one used. Every
finding above came from it.

**Where it stops applying.**
- Keys whose marker the person deleted by hand are theirs: `unwire` refuses
  and `wire` won't overwrite them.
- Two projects whose settings are one file, through a link, share one wiring.
  Unwiring either unwires both.
- `forget` can't list the projects still wired. Search for the marker:
  `grep -l GITHUB_APP_WIRED <folders>/.claude/settings.local.json`.
- Claude Code exports the marker into every session in the project. It holds
  no secret.
- `wire` and `unwire` take a lock per settings file, so two of them never
  write over each other. The lock file sits in this script's state folder,
  under `locks/`, named by the device and inode of the settings file's
  folder and the file's name case-folded (so every spelling of one file
  shares one lock), and stays there empty: deleting it would let a waiting
  process lock a file another has already replaced. Nothing is left in the
  project. Deleting and recreating `.claude/` while a `wire` runs gives the
  folder a new inode, so a second run can lock separately; that is no worse
  than editing the file by hand mid-run.

## Environment credentials belong to one identity

**Decision.** As in `linear-app`: `GITHUB_APP_*` apply only to the identity
named by `GITHUB_APP_IDENTITY` (or `default`), and an App ID needs exactly one
key source.

**Why.** A server's environment file holds one role's credentials. Lending
them to another `--identity` would act as the wrong App.

**Which identity to act as is a separate variable, `GITHUB_APP_ACT_AS`.**
`run`, `wire` and `env` set it; `--identity` beats it, and it beats
`GITHUB_APP_IDENTITY`. Only `GITHUB_APP_IDENTITY` says whose `GITHUB_APP_*`
are in the environment, and `GITHUB_APP_OWNER` and
`GITHUB_APP_INSTALLATION_ID` count only for that identity too.

**Why.** `GITHUB_APP_IDENTITY` used to do both jobs, and `run`, `wire` and `env`
set it. A finder observed the result. A shell held `GITHUB_APP_*` for
`default` (App 999), and `run --identity acme -- git push` set
`GITHUB_APP_IDENTITY=acme` in the child. The child's credential helper then
took App 999's credentials as acme's. The commits named acme's bot, but the
push authenticated as App 999. A wired project did the same to every session
started from such a shell. A server role's file still works: it sets
`GITHUB_APP_IDENTITY` and its credentials together, and its `env` lines set
`GITHUB_APP_ACT_AS` to the same role.

**Rejected: stripping `GITHUB_APP_*` from the children of `run`.** Claude
Code applies the settings `env` that `wire` writes over the person's own
shell, so `wire` has no child to strip. A server role's file needs its
credentials and its identity in the same environment.

## Output

**Decision.** `token`, `credential`, `env`, `run` and `gh` print bare output, for
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

### Claude Code's settings `env` is unobserved (2026-10-03)

`wire --project` relies on Claude Code's documentation above. Its tests prove
only what is written to `settings.local.json`. The first live use should
confirm `echo $GIT_AUTHOR_NAME` in a session in the project and in one of its
`.claude/worktrees/`. If it doesn't hold, use `run --` there instead.

### Untested against a live App (2026-10-03)

Every request is tested against a fake GitHub. The first live run should
confirm minting, the installation lookup, `check`'s permissions and
repository list, the bot's noreply email, and a push and a draft pull request
through `run --`.
