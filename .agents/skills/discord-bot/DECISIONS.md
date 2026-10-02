# discord-bot — decisions

**Read this before changing `scripts/discord_bot.py`.** Each entry is a
decision, why it was made, and what was tried and rejected, because the
rejected options look like improvements from the line you'd be editing.

---

## One call per run; no service

**Decision.** Each command calls Discord's HTTP API, prints one JSON object and
exits. Nothing stays running.

**Why.** Every operation an agent needs (post, read, edit, delete, start a
thread) is a single request it makes when it decides to. Nothing has to arrive
from Discord unprompted, and that is the only thing a persistent connection
would buy. Without one there is nothing to install, keep alive, restart or
point at a moved folder, and the same script works on a laptop, on a server,
and as a subprocess of another program.

**Rejected: a local HTTP service holding a gateway connection.** This skill
replaces one: a Node service using discord.js, run by launchd, that agents
reached with `curl` on port 3000. Its connection listened for nothing, so it
only served as a channel cache. It needed Node and npm, its dependencies could
not live inside a skill folder (skill loaders scan those recursively), and its
launchd file held an absolute path, so moving the repository broke it at the
next restart. That happened.

**If a future need is event-driven,** such as replying when someone mentions
the bot, that needs a service. Build it separately; don't turn this script into
one.

## The token comes from the environment, then the keychain, never a file

**Decision.** `DISCORD_BOT_TOKEN` wins. Otherwise the token is read from the
macOS Keychain or Linux `secret-tool`, under service `discord-bot` and the
identity's name as account. The config file holds no secrets; its `keychain`
field can name a different entry, but never holds the token itself.

**Why.** A server runs each bot as its own process with its own environment
file, and that file is its identity; a laptop has a keychain and no such
file. Naming entries by identity lets one machine hold several bots.

**Rejected: one fixed keychain entry per machine.** That was the old service's
design, and it can't hold a second bot.

## Refuse a message over 2,000 characters

**Decision.** A message longer than Discord's limit, header included, is an
error, and nothing is posted.

**Why.** The old service cut messages at 2,000 characters and reported
success, so the end of a long report vanished without anyone knowing.

**Rejected: splitting into several posts.** Where to split is a judgment about
the text, which the caller is better placed to make.

## Mentions never ping a crowd

**Decision.** Every post sends `allowed_mentions` with `parse: []` and only the
user ids the script resolved itself. `@everyone` and `@here` are never
converted.

**Why.** Message text often comes from a model, and from what it read.
Without this, a quoted `@everyone` or a role mention would notify a whole
server.

## Mentions match exact names only

**Decision.** `@name` becomes a mention only when exactly one member's
username, display name or server nickname equals the name, ignoring case. If a
name ends in `.`, `_` or `-`, the name without them is tried next, and the
stripped characters stay after the mention (`Thanks @adam.`, `_@adam_`).
Anything else stays plain text, with one warning per name.

**Why.** Pinging the wrong person is the failure that matters; missing a ping
is visible in the warnings and fixed by retrying with the right name.

**Rejected: matching by prefix, shortest name first.** The old service did
this, and it was ported first. Over three review passes it pinged the wrong
member for `@acme-reviewer` (cut at the hyphen), `@José` (cut at the `é`) and
`_@adam_` (which matched `adam_smith` first). Each was patched, and the next
pass found another. Exact matching removes the whole class.

**Where it stops applying.** A nickname typed partially (`@ada` for `adam`)
no longer resolves. That is deliberate. So does a name followed directly by Chinese or Japanese
text with no space (`请@adam看看` reads as the name `adam看看`); it gets a warning
rather than a ping.

## Code spans and links are never rewritten

**Decision.** Before mentions are converted, code spans and `http(s)` links are
masked and restored afterwards. A code span follows CommonMark's rule: a run of
N backticks opens it and the next run of exactly N closes it. A run with no
closer is ordinary text, so mentions after a stray backtick still work. An
unclosed ```` ``` ```` fence is ordinary text too, matching how Discord displays it.

**Rejected: a single-backtick regex, then masking to the end of the text
after an unmatched backtick.** The first missed ``` ``@adam`` ```; the second
silently dropped every mention after a backtick in prose ("press the ` key").

## Member search needs no privileged intent

**Decision.** Setup leaves all privileged intents off. Names are looked up
with Discord's member-search endpoint, which worked with Server Members Intent
off: tested 2026-10-02 against a real server, where a post's `@name` became a
mention that notified the person. If Discord ever refuses the search, names
stay plain text with one warning and the post still goes out.

**Why.** A bot should hold only the access it uses. The intent would also let
it read the whole member list.

`check` reports `memberSearch: true` only when a search for the bot's own name
returns members. Discord can accept a search and return nobody, so a request
that merely succeeds proves nothing. Requiring the bot itself in the answer was
rejected: the search is capped at 100 and unordered, so in a server where 100
names start with the bot's, the bot can be missing while search works.

## Permissions are computed in `check`, not before every post

**Decision.** `check` works out the bot's permissions in the default channel
from its roles and the channel's overrides, following Discord's documented
order. Other commands just try, and report Discord's 403.

**Why.** Computing them costs two extra requests. They're worth it once per
session to name the missing permission up front, because Discord's own error
for a missing thread permission is a bare code that names none.

## `store-token` passes the token to `security` as an argument

**Decision.** On macOS the token is stored with
`security add-generic-password -w <token>`.

**Why.** `security` has no way to read the secret from standard input, so it
is visible to this user's other processes for the instant the command runs.
Linux `secret-tool` reads it from standard input. Anyone who can't accept that
moment can add the entry with Keychain Access instead; the script only reads it.

## Output is JSON with fixed exit codes

**Decision.** One JSON object on standard output, with `ok`; exit status 0
for success, 1 for an error in the JSON, 2 for a malformed command line.

**Why.** Agents and programs both call it. Neither should parse prose, and a
program needs the exit status to tell a Discord error from its own mistake.

The JSON is ASCII, with other characters escaped. A program reading it
through a pipe on Windows gets the ANSI code page, not UTF-8, and printing an
emoji there would crash after a post was already made.

---

## Open questions

### Exact-name mention matching hasn't had a bug-finding pass (2026-10-02)

Bug-hunter's third and last review pass replaced prefix matching with exact
names (see "Mentions match exact names only"). Its budget ended before a pass
could read that rewrite. Unreviewed: `convert_mentions` and its member lookup,
`MENTION_RE` and what may precede `@`, one warning per name, and ASCII-only
JSON output in `main()`. 75 tests cover them, five of them regressions from
that pass. Recommended: one bug-hunter run scoped to those parts; it is cheap
and likely to find little, since the rewrite removed the riskiest logic.
