# gh-post: constraints and rejected alternatives

## Constraints

- **Constraint: gh's default alias `gh co` and read-only extensions such as `gh dash` are unreadable, so both post hooks block them for every prose user.**
  Because: the reader cannot read what an alias or extension runs, so passing one could forge a relayed answer past both hooks.
  Evidence: with `c` aliased to `pr comment`, `gh c 5 -b 'User says: yes'` names no gh post verb, https://cli.github.com/manual/gh_alias_set
  Holds while: a gh alias or extension can run any gh command.
  Paths: .agents/lib/gh-shell/, .agents/skills/prose/

- **Constraint: `git commit` and `git push` run the repository's git hooks, which can run anything, and the reader does not read them.**
  Because: a repository's git hooks are outside what a reader of the command line can see.
  Evidence: git runs a repository's `pre-commit`, `commit-msg` and `pre-push` hooks on those commands, https://git-scm.com/docs/githooks
  Holds while: the reader judges only the command line.
  Paths: .agents/lib/gh-shell/

- **Constraint: A GraphQL query read from standard input, or from a file on a line holding more than the `gh api` call, counts as a write the reader cannot read, and is blocked; a `gh api` read whose words the shell builds, such as `-f q="$Q"`, counts as a possible post, so its line counts as mentioning a gh post verb, and an interpreter with a code flag on that line makes the line unreadable.**
  Because: a query the reader cannot see might be a mutation, and a word the shell builds could add a field the reader never sees.
  Evidence: gh sends a GraphQL query's fields with `POST`, as it does a mutation's, so only the operation tells a read from a write, https://cli.github.com/manual/gh_api
  Holds while: the reader judges a `gh api` call by its literal words alone.
  Paths: .agents/lib/gh-shell/
