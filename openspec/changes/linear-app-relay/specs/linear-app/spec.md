## Purpose

linear-app gives an agent its own Linear identity, an OAuth app user, and
mints that identity's tokens on demand, so the agent's writes in Linear
show as the app user's, never a person's.

## ADDED Requirements

### Requirement: The answer service's Linear relay is a relay identity

linear-app SHALL treat the identity that `answer_service.linear.relay`
names in `~/.config/shared-skills/inquisitor.json` as a relay identity.
While that file exists but holds no JSON object linear-app can read, or
holds an `answer_service.linear.relay` that is present but not a string, linear-app SHALL
treat every identity as a relay identity under every rule of this spec,
naming the file whenever it refuses a command for that reason.

#### Scenario: The identity the configuration names is a relay identity

- **WHEN** `inquisitor.json` holds `"answer_service": {"linear": {"relay":
  "answers-bot"}}`
- **THEN** linear-app treats `answers-bot` as a relay identity

#### Scenario: Without a Linear relay no identity is one

- **WHEN** `inquisitor.json` is missing, or holds no
  `answer_service.linear.relay`
- **THEN** linear-app treats no identity as a relay identity

#### Scenario: An unreadable configuration refuses token commands for every identity

- **WHEN** `inquisitor.json` holds text that is not JSON, and an agent
  runs `linear_app.py --identity worker token`
- **THEN** linear-app refuses, naming `inquisitor.json`, and prints no
  token
- **AND** every other rule for a relay identity applies to `worker` too:
  it ignores credentials in the environment, and any token linear-app's
  state folder holds for it is deleted

### Requirement: Every identity holding the relay's client ID is a relay identity

linear-app SHALL also treat as a relay identity every identity whose
client ID is the relay identity's. It SHALL read an identity's client ID
from the keychain entries its config names, but `LINEAR_CLIENT_ID` first
for the identity the environment's credentials belong to
(`LINEAR_APP_IDENTITY`, else `default`). It SHALL read the relay's own
client ID from the keychain only, and while a Linear relay is configured
and it cannot, SHALL treat every identity as a relay identity, saying
why.

#### Scenario: Another identity with the relay's client ID is a relay identity

- **WHEN** `inquisitor.json` names `answers-bot` as the Linear relay, the
  config of identity `worker` points its `keychain` entries at
  `answers-bot`'s, and an agent runs `token` for `worker`
- **THEN** linear-app refuses, as for `answers-bot`, and prints no token
- **AND** it refuses `token` for `default`, the identity used when none
  is named, while `LINEAR_CLIENT_ID` holds `answers-bot`'s client ID
- **AND** it refuses `token` for every identity, saying why, while the
  keychain cannot give `answers-bot`'s client ID

### Requirement: No command prints a relay identity's token

For a relay identity, `token` and `headers` SHALL refuse, print nothing
on standard output, and say on standard error that a relay identity
posts only through `post`, `edit` and `delete`. They refuse because any
agent on the machine can run them and post `User says: ` with the token,
unseen by the post hook. For any other identity they SHALL print the
token as before.

#### Scenario: token and headers refuse a relay identity

- **WHEN** an agent runs `token`, or `headers`, for a relay identity
- **THEN** the command exits non-zero, prints nothing on standard output,
  and its error names `post`, `edit` and `delete`

#### Scenario: Other identities keep token and headers

- **WHEN** `token`, or `headers`, runs for an identity that is not a
  relay identity
- **THEN** it prints the identity's token, bare or in its Authorization
  header

### Requirement: A relay identity cannot be wired to the Linear MCP server

`wire` SHALL refuse a relay identity, since the MCP server's headers
helper runs `headers`, which refuses a relay identity. For a relay
identity, `check` SHALL warn of each Claude Code MCP server whose
`headersHelper` runs `headers` for that identity, naming the server.

#### Scenario: wire refuses a relay identity

- **WHEN** `wire` runs for a relay identity
- **THEN** it changes no MCP server, and says that a relay identity posts
  only through `post`, `edit` and `delete`

#### Scenario: check warns of a server wired to a relay identity

- **WHEN** an identity was wired to the MCP server named `linear`,
  `inquisitor.json` then names that identity as the Linear relay, and
  `check` runs for it
- **THEN** its warnings name the `linear` server as wired to a relay
  identity, whose `headers` refuses

### Requirement: A relay identity's credentials come only from the keychain

For a relay identity, linear-app SHALL read the client ID and secret only
from the system keychain, never from `LINEAR_CLIENT_ID` or
`LINEAR_CLIENT_SECRET`, which every agent's environment can hold. On a
host with no keychain tool, neither macOS `security` nor Linux
`secret-tool`, it SHALL refuse every command but `forget` for a relay
identity, naming both tools.

#### Scenario: A relay identity ignores credentials in the environment

- **WHEN** the variable that picks the identity, `LINEAR_APP_IDENTITY`,
  names a relay identity; `LINEAR_CLIENT_ID` and `LINEAR_CLIENT_SECRET`
  are set; and the keychain holds no
  credentials for it
- **THEN** its commands fail with "no client credentials", and mint no
  token from the environment's credentials

#### Scenario: A host with no keychain tool refuses a relay identity

- **WHEN** neither `security` nor `secret-tool` is on the host, and
  `post` runs for a relay identity
- **THEN** it exits non-zero naming both tools, mints no token, and
  writes none to a file
- **AND** `forget` still runs for it
- **AND** while a Linear relay is configured, every identity is refused
  the same way, since the relay's own client ID cannot be read either

### Requirement: A relay identity's token is cached only in the keychain

linear-app SHALL cache a relay identity's token in the keychain under
the service `linear-app` and the account `<identity>:token`, whatever
service the identity's config names for its credentials, reusing the
token until it is halfway through its life. It SHALL never cache that
token in linear-app's state folder, and SHALL delete any token that
folder holds for the identity. `forget` SHALL also delete that cached
token from the keychain.

#### Scenario: A relay identity's token is cached in the keychain

- **WHEN** `post` runs for a relay identity, and then `edit` runs before
  the token is halfway through its life
- **THEN** the keychain holds the token the first command minted, under
  the service `linear-app` and the account `<identity>:token`, the
  second command reuses it without minting, and no file in linear-app's
  state folder holds it

#### Scenario: A token cached before the identity became a relay identity is deleted

- **WHEN** linear-app's state folder holds a cached token for an identity
  that `inquisitor.json` then names as the Linear relay, and any command
  runs for it
- **THEN** that folder holds no token for the identity

#### Scenario: forget deletes a relay identity's cached token

- **WHEN** `forget` runs for a relay identity
- **THEN** the keychain holds no cached token for it

### Requirement: post, edit and delete act as an identity without printing its token

linear-app SHALL have three commands, for any identity: `post --issue
<issue id>` comments on an issue, or with `--parent <comment id>` replies
in that comment's thread; `edit --comment <comment id>` replaces a
comment's text; and `delete --comment <comment id>` deletes a comment.
Each SHALL print JSON holding `"ok": true` and the comment's `id`, and
for `post` and `edit` its `url`, and never the token. When Linear answers
401, each SHALL replace the token once and retry, as `check` does.

#### Scenario: A post prints the comment's id and URL

- **WHEN** the answer service runs `post --issue <id> --body-file <path>`
  for the relay identity, the file holding `User says: yes`
- **THEN** the identity comments `User says: yes` on that issue, and the
  command prints `"ok": true` with the comment's `id` and `url`, and no
  token

#### Scenario: A reply goes into its comment's thread

- **WHEN** `post` runs with `--parent <comment id>`
- **THEN** the new comment's parent is that comment

#### Scenario: edit and delete change the identity's own comment

- **WHEN** `edit --comment <id>` runs with new text, and later
  `delete --comment <id>` runs, for the comment the identity posted
- **THEN** the edit leaves that comment holding the new text, with no new
  comment, and prints its `id` and `url`
- **AND** the delete removes it and prints `"ok": true` with its `id`

#### Scenario: A revoked token is replaced once

- **WHEN** Linear answers 401 to a `post` whose cached token was revoked
- **THEN** the command mints a new token, posts once with it, and reports
  a second 401 as an error

### Requirement: post, edit and delete pass on Linear's refusal

When Linear refuses a `post`, `edit` or `delete`, the command SHALL exit
non-zero and print JSON holding `"ok": false`, Linear's HTTP status and
the errors Linear returned, unchanged, so its caller reads the cause as
Linear reports it.

#### Scenario: A refusal for lack of permission is passed on

- **WHEN** Linear refuses a `post` because the identity may not comment
  in that team
- **THEN** the command exits non-zero and prints `"ok": false`, the HTTP
  status and Linear's errors as Linear returned them, and no token

### Requirement: check reports the identity's user id, scopes and teams

`check` SHALL report, beside the identity's name, fields filled only
from Linear's responses, never from the config: `userId`, the app
user's id; `grantedScopes`, the scopes Linear granted the token; and
`visibleTeams`, the keys of the teams the app user can see. When it
cannot read the teams, it SHALL say so in place of `visibleTeams` and
still pass, so setup shows each subscribed Linear team's posting check
as not checked.

#### Scenario: check prints the user id, scopes and teams

- **WHEN** `check` runs for an identity whose token holds the `read` and
  `write` scopes and whose app user can see the team `ENG`
- **THEN** its result holds the app user's name, its `userId`,
  `grantedScopes` holding `read` and `write`, and `visibleTeams` holding
  `ENG`, and no token
- **AND** when Linear refuses the teams read, `check` still passes and
  says it could not read the teams, with no `visibleTeams`

#### Scenario: Teams listed in the config are not visible teams

- **WHEN** the identity's config lists the team `OPS` under `teams`, and
  the app user cannot see `OPS`
- **THEN** `visibleTeams` does not hold `OPS`

### Requirement: A comment's text comes from a named file and reaches Linear only as a GraphQL variable

`post` and `edit` SHALL read the text only from the regular file
`--body-file` names, never from standard input, such as through `-` or
`/dev/stdin`, which the inquisitor's post hook cannot see. They SHALL
refuse an abbreviated option such as `--body`, and `--body-file` given
more than once. They SHALL send the text to Linear only as a GraphQL variable,
so no text can change the request.

#### Scenario: Text on standard input or an abbreviated option is refused

- **WHEN** `post --issue <id>` runs with no `--body-file` and text on
  standard input, with `--body-file /dev/stdin`, with `--body c.md`, or
  with `--body-file a.md --body-file b.md`
- **THEN** it exits non-zero, saying to name the text's file with
  `--body-file`, and posts nothing

#### Scenario: Text cannot change the request

- **WHEN** the `--body-file` file holds `"}) { id } } mutation {`,
  `$(rm -rf ~)` and a backtick
- **THEN** the comment holds that text exactly as given
