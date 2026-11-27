## Purpose

The github-app skill lets an agent act on GitHub as its own GitHub App,
minting installation tokens on demand, and keeps a relay identity's token
away from every program that could print it.

## ADDED Requirements

### Requirement: Every identity of the answer service's GitHub relay App is a relay identity

github-app SHALL treat as a relay identity (answer-service spec: *The
person runs the service, and a relay identity posts for them*) the
identity that `answer_service.github.relay` names in
`~/.config/shared-skills/inquisitor.json`, and every other identity with
the same App ID. While that file exists but holds no JSON object
github-app can read, github-app SHALL treat every identity as a relay
identity, naming the file whenever it refuses a command for that reason.

#### Scenario: The identity the configuration names is a relay identity

- **WHEN** `inquisitor.json` holds `"answer_service": {"github": {"relay":
  "maya-relay"}}`
- **THEN** github-app treats `maya-relay` as a relay identity

#### Scenario: The same App stored for another account is a relay identity too

- **WHEN** `inquisitor.json` names `maya-relay` as the GitHub relay, and
  the identity `maya-relay-acme` holds the same App ID with another
  `owner`
- **THEN** github-app treats `maya-relay-acme` as a relay identity as well
- **AND** github-app also treats as one an identity whose credentials
  come from the environment, with that App ID in `GITHUB_APP_ID`

#### Scenario: Without a GitHub relay no identity is one

- **WHEN** `inquisitor.json` is missing, or holds no
  `answer_service.github.relay`
- **THEN** github-app treats no identity as a relay identity

#### Scenario: An unreadable configuration refuses token commands for every identity

- **WHEN** `inquisitor.json` holds text that is not JSON, and an agent
  runs `github_app.py --identity worker gh pr view 5`
- **THEN** github-app refuses, naming `inquisitor.json`, and runs no gh

### Requirement: No github-app command hands a relay identity's token to a program

For a relay identity, github-app SHALL refuse `token`, `gh`, `run`,
`wire`, `env` and the credential helper's `get`, saying the identity is a
relay identity that acts only through `api`, and print no token. Its
other commands SHALL keep working.

#### Scenario: Each token-handing command refuses a relay identity

- **WHEN** an agent runs, for the relay identity `maya-relay`, `token`,
  `gh auth token`, `run -- git push`, `wire --project .`, `env`, or
  `credential get` with `protocol=https` and `host=github.com` on
  standard input
- **THEN** each exits non-zero, saying `maya-relay` is a relay identity
  that acts only through `api`, starts no program, writes no settings,
  and prints no token

#### Scenario: A project wired before its identity became a relay cannot push

- **WHEN** a project was wired to `worker`, and `inquisitor.json` then
  names `worker` as the GitHub relay, and an agent there runs `git push`
- **THEN** git's call to the credential helper gets no token, and the
  helper's message says `worker` is a relay identity
- **AND** `unwire --project` still removes that project's wiring

#### Scenario: A relay identity's check still runs

- **WHEN** the answer service's setup runs `check` for the relay identity `maya-relay`
- **THEN** it reports the App and installation as it does for any
  identity, with no token in its output

### Requirement: The api command makes a GitHub request with the installation token and prints only the response

`github_app.py api <endpoint>` SHALL make a request to
`https://api.github.com`, for any identity, with the identity's
installation token and never the App's own key, in its own process, so
the token reaches no other program. It SHALL follow no redirect, exiting
non-zero and naming the redirect's location instead. It SHALL print the
response body, and on an HTTP error print the `message` of GitHub's error
response and exit non-zero.

#### Scenario: A relay posts, edits and deletes a comment through api

- **WHEN** the answer service runs, as the relay identity, `api
  repos/o/r/issues/5/comments -F body=@-` with the post's text on standard
  input, then `api -X PATCH repos/o/r/issues/comments/9 -F body=@-`, then
  `api -X DELETE repos/o/r/issues/comments/9`
- **THEN** the comment is posted, edited and deleted as the App's bot,
  each response body is printed, and no other process is started

#### Scenario: api follows no redirect

- **WHEN** an agent runs `api repos/o/r/tarball/main`, and GitHub answers
  with a redirect to another host
- **THEN** `api` exits non-zero naming the redirect's location, and sends
  no request there, so the token reaches no other host

#### Scenario: api cannot mint a token

- **WHEN** an agent runs, as the relay identity, `api -X POST
  app/installations/7/access_tokens`
- **THEN** the request carries the installation token, GitHub refuses it,
  and `api` prints GitHub's message and exits non-zero

### Requirement: The api command accepts only gh api's method, field and input options

`api` SHALL accept, of `gh api`'s options, only its method, field and
input options, with gh's forms and meanings. It SHALL refuse a call
whose endpoint names a host, or that holds a placeholder gh would fill
(`{owner}`, `{repo}`, `{branch}`, `:owner`, `:repo`, `:branch`) in the
endpoint or in a `-F` value typed in the command, not read with `@`.
`api` fills no placeholder, so these refusals keep what it sends equal to
what the post hook reads.

#### Scenario: gh api's method, field and input options are accepted

- **WHEN** an agent runs `api` with `-X`/`--method`, `-f`/`--raw-field`,
  `-F`/`--field` or `--input`, in any form gh accepts
- **THEN** `api` sends the request gh api would send, with `@-` and
  `--input -` reading standard input
- **AND** for the raw field `-f body={owner}`, and for `-F body=@c.md` where `c.md`
  holds `{owner}`, it sends `{owner}` unfilled, as gh does

#### Scenario: An option or endpoint api does not accept is refused

- **WHEN** an agent runs `api -H 'Accept: text/plain' repos/o/r/issues/5`,
  `api --paginate repos/o/r/issues`, `api http://localhost:8000/x`, `api
  //evil.example/x`, `api
  repos/{owner}/{repo}/issues/5/comments -f body=x`, `api
  repos/:owner/:repo/issues/5/comments -f body=x`, or `api
  repos/o/r/issues/5/comments -F body={owner}`
- **THEN** each exits non-zero naming what it does not accept, and sends
  no request
