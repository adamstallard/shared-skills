## 1. linear-app

- [ ] 1.1 Read the relay identity from `inquisitor.json` (linear-app
      spec: *The answer service's Linear relay is a relay identity*)
- [ ] 1.2 Refuse `token`, `headers` and `wire` for a relay identity, and
      warn in `check` of an MCP server wired to one (linear-app spec: *No
      command prints a relay identity's token*; *A relay identity cannot
      be wired to the Linear MCP server*)
- [ ] 1.3 Read a relay identity's credentials only from the keychain,
      cache its token there, delete any token linear-app cached for it in
      linear-app's state folder, and delete the keychain's copy in `forget`
      (linear-app spec: *A relay identity's credentials and token stay in
      the keychain*)
- [ ] 1.4 Add `post`, `edit` and `delete` (linear-app spec: *post, edit
      and delete act as an identity without printing its token*; *A
      comment's text comes from a named file and reaches Linear only as a
      GraphQL variable*)
- [ ] 1.5 Say in linear-app's SKILL.md and README what a relay identity
      is, which commands it refuses, and that `post` and `edit` take
      their text from `--body-file`

## 2. Inquisitor

- [ ] 2.1 The shared post reader reads linear-app's `post` and `edit`
      (gh-post spec: *The reader reads linear-app's post and edit as gh
      issue comment*)
- [ ] 2.2 Post, edit and delete on Linear through linear-app's `post`,
      `edit` and `delete` in place of the service's own request
      (answer-service spec: *A relay post is posted by a host command,
      unvetted*)
- [ ] 2.3 Drop Linear from the inquisitor README's warning that a relay's
      token can be printed (answer-service spec: *The README warns that a
      relay's token can be printed*)

## 3. Tests

- [ ] 3.1 Tag each test with the scenario it checks (spec-trace)
