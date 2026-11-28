## 1. linear-app

- [x] 1.1 Read the relay identity from `inquisitor.json`, and match every
      identity holding its client ID (linear-app spec: *The answer
      service's Linear relay is a relay identity*; *Every identity holding
      the relay's client ID is a relay identity*)
- [x] 1.2 Refuse `token`, `headers` and `wire` for a relay identity, and
      warn in `check` of an MCP server wired to one (linear-app spec: *No
      command prints a relay identity's token*; *A relay identity cannot
      be wired to the Linear MCP server*)
- [x] 1.3 Read a relay identity's credentials only from the keychain,
      refusing on a host with no keychain tool; cache its token only in
      the keychain; delete any token cached for it in linear-app's state
      folder; and delete the keychain's copy in `forget` (linear-app spec:
      *A relay identity's credentials come only from the keychain*; *A
      relay identity's token is cached only in the keychain*)
- [x] 1.4 Add `post`, `edit` and `delete`, passing on Linear's refusals
      (linear-app spec: *post, edit and delete act as an identity without
      printing its token*; *post, edit and delete pass on Linear's
      refusal*; *A comment's text comes from a named file and reaches
      Linear only as a GraphQL variable*)
- [x] 1.5 Report the user id, scopes and visible teams in `check`
      (linear-app spec: *check reports the identity's user id, scopes and
      teams*)
- [x] 1.6 Say in linear-app's SKILL.md and README what a relay identity
      is, which commands it refuses, and that `post` and `edit` take
      their text from `--body-file`

## 2. Inquisitor

- [ ] 2.1 The shared post reader reads linear-app's `post` and `edit`
      (gh-post spec: *The reader reads linear-app's post and edit only
      from a body file*; *A simple command holding a linear-app post word
      counts as naming gh*)
- [ ] 2.2 The answer service posts, edits and deletes on Linear through
      linear-app's `post`, `edit` and `delete`, not its own request; this
      replaces the Linear part of the inquisitor change's task 6.4. It
      reads a refusal's cause from what linear-app passes on, and takes
      the Linear relay's user id from linear-app's `check`
      (answer-service spec as this change modifies it: *A relay post is
      posted by a host command, unvetted*; *The service reads the Linear
      relay's user id from linear-app's check*)
- [ ] 2.3 Setup's Linear posting check reads the scopes and teams from
      linear-app's `check` (answer-service spec as this change modifies
      it: *A posting check reads what each surface grants*)
- [ ] 2.4 Drop Linear from the inquisitor README's warning that a relay's
      token can be printed, which the inquisitor change's task 5.2 adds (answer-service spec as this change modifies
      it: *The README warns that a relay's token can be printed*)

## 3. prose

- [ ] 3.1 prose's posting hook,
      `.agents/skills/prose/scripts/check-post.sh`, passes a tool call
      whose command names `linear_app.py` on to the shared post reader, and a test
      shows it, so prose's check for a signed footer
      applies to every linear-app `post` and `edit` an agent runs as a
      tool call; say so in prose's SKILL.md, since prose has no spec

## 4. Tests

- [ ] 4.1 Tag each test with the scenario it checks (spec-trace)
