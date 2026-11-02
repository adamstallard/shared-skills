# linear-app — decisions

**Read this before changing `scripts/linear_app.py`.** Each entry is a
decision, why it was made, and what was tried and rejected.

---

## The stored credential is the client secret, not a token

**Decision.** Each identity stores its OAuth client ID and secret. Tokens are
minted from them with the `client_credentials` grant whenever the cached one
is past half its life.

**Why.** Linear's `client_credentials` tokens last 30 days and come with no
refresh token. Storing the token means someone renews it every month; storing
the secret means nobody does. Half the life Linear reports, rather than a fixed
number of days, works whatever lifetime Linear issues, and a session that keeps
the token it got at start always has at least half of it left. Renewing early
costs nothing, because a mint with the same scopes leaves earlier tokens
valid.

**Rejected: storing the token and renewing it by hand.** That was the
aura-workroom script this replaces. Its agent skill existed mainly to explain
the monthly expiry and walk the agent through renewing.

## Delegate scopes are minted by default

**Decision.** The default scopes are `read,write,app:assignable,app:mentionable`.

**Why.** Tested 2026-10-02 against the Aura workspace: an app user whose token
was minted with only `read,write` could be neither delegate nor assignee
("One or more app users lack the required capability"). Minted with
`app:assignable,app:mentionable` added, it could be delegated issues, with no
browser install. It still couldn't be an assignee, and that request reported
success while changing nothing.

**Where it stops applying.** These are the scopes Linear accepted for
`client_credentials` on that date. If Linear stops accepting them for that
grant, the fallback is a one-time browser install with `actor=app`.

## Scopes are never reordered or changed implicitly

**Decision.** The scope string is used exactly as configured, and the cache
records it. A different string mints a new token.

**Why.** Minting with a different scope string revokes every token the
application has issued, including ones other processes are using. Sorting
the scopes would have changed the string for anyone migrating from the old
script, and revoked their working token on the first run.

## One cached token per identity, shared under a lock

**Decision.** Tokens are cached in `$XDG_STATE_HOME/linear-app/<identity>.json`
(mode 600), and minting happens under an exclusive lock that re-reads the cache
before minting.

**Why.** A service may run many processes of one identity, and each minting its
own token would be wasteful. Minting again with the *same* scopes does not
revoke earlier tokens: observed 2026-10-02, when a token minted by this script
left the aura-workroom script's token working. Only a different scope string
revokes them, so the lock prevents waste, not breakage.

**Rejected: the keychain as the token cache.** A server has no keychain, and
two caches mean two code paths. The token is short-lived and derived; the
secret it comes from stays in the keychain or the environment.

## A cached token is tied to the exact credentials that minted it

**Decision.** The cache records one SHA-256 fingerprint of the client ID,
the client secret and the scope string, never the secret itself. Any change to
them mints a new token.

**Why.** Rotating a secret keeps the client ID and revokes the app's tokens.
A cache keyed only on the client ID went on serving the revoked token for up to
25 days after `store-credentials`, the step the docs prescribe for a 401. The
fingerprint lets the cache notice without ever storing the secret.

## `check` replaces a token Linear has revoked

**Decision.** When Linear answers 401 to a cached token, `check` mints a fresh
one and retries once. `token` and `headers` never call Linear, so they can't
notice; the docs send an agent to `check` when Linear tools fail.

**Why.** A token can be revoked while every local input stays the same, for
example when the same application mints with other scopes on another machine.
The cache can't detect that, and before this nothing short of `forget`, which
also deletes the credentials, forced a fresh mint.

## Environment credentials belong to one identity

**Decision.** `LINEAR_CLIENT_ID` and `LINEAR_CLIENT_SECRET` apply only to the
identity named by `LINEAR_APP_IDENTITY` (or `default` when it is unset), and
both or neither must be set.

**Why.** A service's environment file holds one role's credentials. Applying
them to whatever `--identity` was asked for acted as the wrong app user, and
with a different scope string would have revoked that app's tokens. Half the
pair set paired one app's ID with another app's secret from the keychain.

## `wire` adds the new server before removing the old one

**Decision.** `wire` first adds the new configuration under a temporary name,
and replaces the real server only once that succeeds.

**Why.** Removing first meant a failed add (an older Claude Code that doesn't
know `headersHelper`, say) left the user with no Linear server at all.

## The MCP config holds a command, not a token

**Decision.** `wire` registers Linear's MCP server with a `headersHelper`: a
command Claude Code runs at session start, which prints the header from a
fresh token.

**Why.** A token pasted into the config goes stale in 30 days and sits in
`~/.claude.json` in plain text. This was the second half of Philip's
aura-workroom PR #18 (AUR-330). Its first half, limiting the server to one
project folder, is `wire --project`.

## A broken helper is detected, not prevented

**Decision.** The helper names the installed skill's script
(`~/.claude/skills/linear-app/...`) when that leads to this file, and the
Python that ran `wire`. `check` reads Claude Code's config
(`$CLAUDE_CONFIG_DIR/.claude.json`, else `~/.claude.json`) and warns about any
server wired to the identity whose Python or script no longer exists, with the
command that wires it again.

**Why.** The script path is easy to make stable: manage-skills repairs the
installed links when the clone moves. The Python path isn't. An attempt to
record a name that survives upgrades (`python3` on PATH, a venv's base
interpreter) needed fixes in three review iterations in a row: venvs, relative
PATH entries, Homebrew's versioned Cellar folders. Re-running `wire` after an
upgrade is one command, so `check` saying when it is needed is enough.

## `store-credentials` gives `security` each value on standard input, twice, and reads it back

**Decision.** On macOS, `store-credentials` stores the client ID and the
client secret by running `security add-generic-password` with `-w` as its last
option and no value. It writes the value to `security`'s standard input twice,
one line each. It starts `security` in a new process session, which leaves it
no controlling terminal. Then it reads the entry back, and fails if that read
fails or returns anything but the value. No value appears on a command line,
in an error or in the output.

**Why.** Passing the secret as `-w <secret>` would make it visible to this
user's other processes while `security` runs. Tested 2026-10-20 on macOS with
a throwaway keychain entry, since deleted: given `-w` with no value,
`security` asks for the password twice, the second time to confirm it.

- **Twice:** given only one copy, `security` reports that the passwords don't
  match, stores an empty password and still exits 0.
- **No terminal:** `security` reads the answers from standard input only when
  it has no terminal. Run from a terminal, it prompts there and ignores
  standard input.
- **Read back:** the exit status can't be trusted, as the first point shows,
  so only reading the entry proves it holds the value.

**A read-back that fails or doesn't match leaves the entry as it is.** The
read-back searches every keychain in the user's search list, so a mismatch may
mean it found an entry with the same service and account in another keychain.
Deleting by service and account could remove that entry, which
`store-credentials` did not write. Deleting the entry it did write would gain little: the one-copy
case above leaves it empty, and the script reads an empty entry as missing
credentials and says to run `store-credentials`.

On Linux, `secret-tool` asks once and stores all of its standard input as
the secret, so the one-copy case can't arise there, and `store-credentials`
doesn't read the value back.

## On Linux, `forget` trusts a lookup, not `secret-tool clear`'s exit code

**Decision.** If `secret-tool clear` exits 0, the entry is gone. If it exits
any other way, the entry counts as gone when `secret-tool lookup` can't find it.

**Why.** `clear` exits 1 both when nothing matched and when it failed outright,
for example on a server with no secret service.

**Rejected: reading `clear`'s stderr.** Treating a silent exit 1 as "nothing
matched" and anything on stderr as a failure warned "could not delete" on every
`forget` on a server with no secret service, where nothing can be stored.

**Where it stops applying.** On Linux, `forget` can't detect a locked
collection. Tested 2026-10-02 with libsecret 0.21.7 in a Debian container: with
the login collection locked and no prompter, `clear` and `lookup` both exit 1
and print nothing, exactly as for a missing entry. `forget` reported a clean
forget, and after an unlock the secret was still stored. No reading of
`secret-tool`'s output can tell the two apart. macOS does report a locked
keychain, because `security` exits 36.

## Output

**Decision.** `token` and `headers` print bare values, for `$(...)` and for
MCP clients, with errors on stderr and exit 1. Every other command prints one
JSON object with `ok`, and exits 0 or 1.

---

## Open questions

### `forget` removes the cache without taking the lock (2026-10-02)

A process minting while `forget` runs can write a fresh cache after `forget`
reports. A later `token` still fails on the missing credentials, but a live
token is left on disk. Taking the lock in `forget` would fix it.

### The keychain helpers can't tell "absent" from "unreachable" (2026-10-02)

`read_keychain` returns None both when an entry doesn't exist and when the
keychain can't be reached (locked, a denied prompt, no secret service). So
`forget` can't confirm that entries kept under another service survive a
locked keychain, and on Linux it counts entries as gone when the lookup fails
(see "On Linux, `forget` trusts a lookup"). A read that returns present,
absent or unreachable would close both. It touches credential lookup, which
every command uses, so it is not done here.
