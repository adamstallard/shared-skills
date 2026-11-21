# gh-post: constraints, rejected alternatives and rationale

## Constraints

- **Constraint: An allowlisted git subcommand can run any program the repository's configuration names, and the reader does not read that configuration.**
  Because: blocking the reader's allowlisted git subcommands on every line with a gh post verb would block ordinary work, and what a repository's configuration makes git run, such as its hooks, `core.fsmonitor` and an external diff driver, is outside what a reader of the command line can see, and an agent can set that configuration in an earlier tool call, which the reader never sees.
  Evidence: git runs a repository's hooks on these commands, https://git-scm.com/docs/githooks; `core.fsmonitor` names a command git runs to find changed files, https://git-scm.com/docs/git-config#Documentation/git-config.txt-corefsmonitor; and git calls an external diff driver's configured `command` when it shows a diff, https://git-scm.com/docs/gitattributes#_defining_an_external_diff_driver
  Holds while: the reader judges only the command line.
  Paths: .agents/lib/gh-shell/

## Rationale

- **Rationale: Only allowlisted git is a data command beside a gh post verb.**
  A deny-list of the git forms that run code is never complete, and each form it misses lets a post through unread: git runs code from an alias starting with `!`, from `difftool -x` and from `filter-branch --tree-filter`, among others. An allowlist names only subcommands whose options were checked by hand and found to take no code, so a subcommand nobody checked is blocked.
  Evidence: an alias whose expansion starts with an exclamation point "will be treated as a shell command", https://git-scm.com/docs/git-config#Documentation/git-config.txt-alias; `git difftool -x <command>` runs that command, https://git-scm.com/docs/git-difftool; and `git filter-branch --tree-filter <command>` runs a command on each commit, https://git-scm.com/docs/git-filter-branch

- **Rationale: The reader reads only gh's own top-level commands.**
  The reader cannot see what an alias or extension runs: with `c` aliased to `pr comment`, `gh c 5 -b 'User says: yes'` names no gh post verb, so letting it through would let an agent forge a relayed answer past both post hooks. The block costs every prose user gh's default alias `gh co` and read-only extensions such as `gh dash`.
  Evidence: `gh alias set` maps a name to any gh command, https://cli.github.com/manual/gh_alias_set

- **Rationale: A gh api call writes by its method, fields, input or a mutation.**
  The test follows gh's own choice of method. A GraphQL query and a mutation are both sent with `POST`, so only the operation tells a read from a write there, and a query the reader cannot see, such as one read from standard input, might be a mutation.
  Evidence: "The default HTTP request method is GET normally and POST if any parameters were added", overridden by `--method`, and a GraphQL query is sent through the `query` parameter, https://cli.github.com/manual/gh_api

- **Rationale: A command that mentions no gh post verb sends no post.**
  A gh command left off the closed list sends its text past both post hooks unread, so the list holds every gh command that posts text a person reads. `gh discussion` posts are on it but never read, since gh's discussion commands are a preview whose flags can change without notice, so a reader built on them would rest on nothing stable. `gh release create` and `edit` post notes an agent writes, given by `--notes` or `--notes-file`, or taken by `--notes-from-tag` from a tag annotation the agent can write; with `--generate-notes`, GitHub writes them. Release notes are blocked, not read, because the post hooks judge only issue and pull request posts; the reader blocks a release `body` sent through `gh api` the same way, so neither route lets release notes through unchecked.
  Evidence: `gh discussion --help` in gh 2.103.2 opens "Working with discussions in the GitHub CLI is in preview and subject to change without notice", https://cli.github.com/manual/gh_discussion; `gh release create` takes notes from `--notes`, `--notes-file`, `--notes-from-tag` ("get the release notes from the annotated git tag") or `--generate-notes`, https://cli.github.com/manual/gh_release_create
