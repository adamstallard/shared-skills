# gh-post: constraints, rejected alternatives and rationale

## Constraints

- **Constraint: An allowlisted git subcommand can run any program the repository's configuration names, and the reader does not read that configuration.**
  Because: blocking the allowlisted subcommands beside every gh post would block ordinary work, and what a repository's configuration makes git run is outside what a reader of the command line can see. That covers its hooks, such as `pre-commit`, `pre-push`, `post-checkout` and `reference-transaction`, which any ref update runs, and programs such as `core.fsmonitor` and an external diff driver, which `status` and `diff` can run. On a line that mentions a gh post verb, `git config` and `-c` make the line unreadable, but an agent can set that configuration in an earlier command, so any agent, not only a hostile repository, can open this gap; the hooks stop accidents, not a determined forger.
  Evidence: git runs a repository's hooks on these commands, https://git-scm.com/docs/githooks; `core.fsmonitor` names a command git runs to find changed files, https://git-scm.com/docs/git-config#Documentation/git-config.txt-corefsmonitor; and git calls an external diff driver's configured `command` when it shows a diff, https://git-scm.com/docs/gitattributes#_defining_an_external_diff_driver
  Holds while: the reader judges only the command line.
  Paths: .agents/lib/gh-shell/

## Rationale

- **Rationale: The shared post reader reads a post's body from an allow-list.**
  A general command parser reads some commands differently from bash, and each difference can let a post through unread; an allow-list leaves nothing to diverge. Both post hooks read through this one reader, so neither runs a parser of its own.
  Evidence: two bug-hunter runs found about 25 places where prose's general parser read a command differently from bash, most letting an unsigned post through, [prose's DECISIONS.md, *The posting hook reads an allow-list*](../../../.agents/skills/prose/DECISIONS.md)

- **Rationale: The reader reads only gh's own top-level commands.**
  The reader cannot see what an alias or extension runs: with `c` aliased to `pr comment`, `gh c 5 -b 'User says: yes'` names no gh post verb, so letting it through would let an agent forge a relayed answer past both post hooks. The block costs every prose user gh's default alias `gh co` and read-only extensions such as `gh dash`.
  Evidence: `gh alias set` maps a name to any gh command, https://cli.github.com/manual/gh_alias_set

- **Rationale: A gh api call writes by its method, fields, input or a mutation.**
  The test follows gh's own choice of method. A GraphQL query and a mutation are both sent with `POST`, so only the operation tells a read from a write there, and a query the reader cannot see, such as one read from standard input, might be a mutation.
  Evidence: "The default HTTP request method is GET normally and POST if any parameters were added", overridden by `--method`, and a GraphQL query is sent through the `query` parameter, https://cli.github.com/manual/gh_api
