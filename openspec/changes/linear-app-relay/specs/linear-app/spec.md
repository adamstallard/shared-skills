## Purpose

linear-app gives an agent its own Linear identity, an OAuth app user, and
mints that identity's tokens on demand, so the agent's writes in Linear
show as the app user's, never a person's.

## ADDED Requirements

### Requirement: An identity's config marks it as a relay

linear-app SHALL treat an identity as a **marked relay**, an identity
that posts for a person through the inquisitor's answer service, when
its config file, `<identity>.json` in linear-app's config folder
(`~/.config/linear-app/`), holds `"relay": true`. `check` SHALL report
`relay` as `true` or `false`.

#### Scenario: check reports a marked relay

- **WHEN** the config of identity `answers-bot` holds `"relay": true`
  and `check` runs for it
- **THEN** its result holds `"relay": true`, and no token

### Requirement: No command prints a marked relay's token

For a marked relay, `token` and `headers` SHALL refuse, print nothing on
standard output, and say on standard error that a marked relay posts only
through `post`, `edit` and `delete`, and that an agent must leave the mark
as it is. They refuse because any agent on the machine can run `token`
and `headers`. For any other identity they SHALL print the token as
before.

#### Scenario: token and headers refuse a marked relay

- **WHEN** an agent runs `token`, or `headers`, for a marked relay
- **THEN** the command exits non-zero, prints nothing on standard output,
  and its error names `post`, `edit` and `delete` and tells the agent to
  leave the mark as it is

#### Scenario: Other identities keep token and headers

- **WHEN** `token`, or `headers`, runs for an identity whose config holds
  no `relay`
- **THEN** it prints the identity's token, bare or in its Authorization
  header

### Requirement: A marked relay cannot be wired to the Linear MCP server

`wire` SHALL refuse a marked relay, since the MCP server would get the
token from `headers`. For a marked relay, `check` SHALL warn of each
Claude Code MCP server whose `headersHelper` runs `headers` for that
identity, naming the server.

#### Scenario: wire refuses a marked relay

- **WHEN** `wire` runs for a marked relay
- **THEN** it changes no MCP server, and says that a marked relay posts
  only through `post`, `edit` and `delete`

#### Scenario: check warns of a server wired to a marked relay

- **WHEN** an identity was wired to the MCP server named `linear` and its
  config then gains `"relay": true`, and `check` runs for it
- **THEN** its warnings name the `linear` server as wired to a marked
  relay, whose `headers` refuses

### Requirement: A marked relay's credentials and token stay in the keychain

For a marked relay, linear-app SHALL read the client ID and secret only
from the system keychain, never from `LINEAR_CLIENT_ID` or
`LINEAR_CLIENT_SECRET`, which every agent's environment can hold. It
SHALL cache the token there too, beside them, reusing it until it is
halfway through its life, never in linear-app's state
folder (`~/.local/state/linear-app/`), and SHALL delete any token that
folder holds for the identity. `forget` SHALL delete the cached token
from the keychain too.

#### Scenario: A marked relay ignores credentials in the environment

- **WHEN** `LINEAR_APP_IDENTITY` names a marked relay, `LINEAR_CLIENT_ID`
  and `LINEAR_CLIENT_SECRET` are set, and the keychain holds no
  credentials for it
- **THEN** its commands fail with "no client credentials", and mint no
  token from the environment's credentials

#### Scenario: A marked relay's token is cached in the keychain

- **WHEN** `post` runs for a marked relay, and then `edit` runs before
  the token is halfway through its life
- **THEN** the keychain holds the token the first command minted, the
  second command reuses it without minting, and no file in linear-app's
  state folder holds it

#### Scenario: A token cached before the identity was marked is deleted

- **WHEN** linear-app's state folder holds a cached token for an identity
  whose config then gains `"relay": true`, and any command runs for it
- **THEN** that folder holds no token for the identity

#### Scenario: forget deletes a marked relay's cached token

- **WHEN** `forget` runs for a marked relay
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

- **WHEN** `post --issue <id>` runs for a marked relay with
  `User says: yes` on standard input
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

### Requirement: A comment's text reaches Linear only as a GraphQL variable

`post` and `edit` SHALL read the text from standard input and send it to
Linear only as a GraphQL variable, so no text can change the request.

#### Scenario: Text cannot change the request

- **WHEN** the text on standard input holds `"}) { id } } mutation {`,
  `$(rm -rf ~)` and a backtick
- **THEN** the comment holds that text exactly as given
