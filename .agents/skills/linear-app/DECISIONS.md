# linear-app — decisions

**Read this before changing `scripts/linear_app.py`.** Each entry is a
decision, why it was made, and what was tried and rejected.

---

## The stored credential is the client secret, not a token

**Decision.** Each identity stores its OAuth client ID and secret. Tokens are
minted from them with the `client_credentials` grant whenever the cached one
has less than 5 days left.

**Why.** Linear's `client_credentials` tokens last 30 days and come with no
refresh token. Storing the token means someone renews it every month; storing
the secret means nobody does.

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

**Why.** A service may run many processes of one identity. Each minting its own
token is wasteful at best, and if a mint ever revokes earlier tokens, they
would revoke each other.

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

## `store-credentials` passes the secret to `security` as an argument

**Decision.** On macOS the secret is stored with
`security add-generic-password -w <secret>`.

**Why.** `security` can't read a secret from standard input, so the secret is
visible to this user's other processes for the instant the command runs. Linux
`secret-tool` reads it from standard input. Anyone who can't accept that can
add the entries in Keychain Access; the script only reads them.

## Output

**Decision.** `token` and `headers` print bare values, for `$(...)` and for
MCP clients, with errors on stderr and exit 1. Every other command prints one
JSON object with `ok`, and exits 0 or 1.

---

## Open questions

### `forget`'s final warning logic hasn't had a review pass (2026-10-02)

Bug-hunter's second run ended its budget on a rewrite of `cmd_forget`'s
warnings: after deleting, it checks every source the identity could still
use (a full or half environment pair, its own entries if the delete failed,
kept entries under another service) and names each. No pass has read that
rewrite. It changes only `forget`'s warnings, which nothing else depends on,
and 4 regression tests cover the cases found so far. Recommended: one
bug-hunter run scoped to `cmd_forget`, when it is next changed.
