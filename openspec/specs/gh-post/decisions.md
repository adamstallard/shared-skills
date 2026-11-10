# gh-post: constraints, rejected alternatives and rationale

## Constraints

- **Constraint: An allowlisted git subcommand can run any program the repository's configuration names, and the reader does not read that configuration.**
  Because: blocking the reader's allowlisted git subcommands on every line with a gh post verb would block ordinary work, and what a repository's configuration makes git run, such as its hooks, `core.fsmonitor` and an external diff driver, is outside what a reader of the command line can see, and an agent can set that configuration in an earlier tool call, which the reader never sees.
  Evidence: git runs a repository's hooks on these commands, https://git-scm.com/docs/githooks; `core.fsmonitor` names a command git runs to find changed files, https://git-scm.com/docs/git-config#Documentation/git-config.txt-corefsmonitor; and git calls an external diff driver's configured `command` when it shows a diff, https://git-scm.com/docs/gitattributes#_defining_an_external_diff_driver
  Holds while: the reader judges only the command line.
  Paths: .agents/lib/gh-shell/

## Rationale

- **Rationale: The reader reads only gh's own top-level commands.**
  The reader cannot see what an alias or extension runs: with `c` aliased to `pr comment`, `gh c 5 -b 'User says: yes'` names no gh post verb, so letting it through would let an agent forge a relayed answer past both post hooks. The block costs every prose user gh's default alias `gh co` and read-only extensions such as `gh dash`.
  Evidence: `gh alias set` maps a name to any gh command, https://cli.github.com/manual/gh_alias_set

- **Rationale: A gh api call writes by its method, fields, input or a mutation.**
  The test follows gh's own choice of method. A GraphQL query and a mutation are both sent with `POST`, so only the operation tells a read from a write there, and a query the reader cannot see, such as one read from standard input, might be a mutation.
  Evidence: "The default HTTP request method is GET normally and POST if any parameters were added", overridden by `--method`, and a GraphQL query is sent through the `query` parameter, https://cli.github.com/manual/gh_api
