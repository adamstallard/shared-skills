# gh-post: constraints, rejected alternatives and rationale

## Rationale

- **Rationale: A gh api call writes by its method, fields, input or a mutation.**
  The test follows gh's own choice of method. A GraphQL query and a mutation are both sent with `POST`, so only the operation tells a read from a write there, and a query the reader cannot see, such as one read from standard input, might be a mutation.
  Evidence: "The default HTTP request method is GET normally and POST if any parameters were added", overridden by `--method`, and a GraphQL query is sent through the `query` parameter, https://cli.github.com/manual/gh_api

- **Rationale: A command that mentions no gh post verb sends no post.**
  The post hooks, prose's and the inquisitor's, catch accidents in the common ways an agent posts on a GitHub issue or pull request, or with linear-app on a Linear issue; they cannot stop an agent set on posting unseen by either hook: such an agent can run gh from a script file, through a gh alias, or from a program git runs because of repository configuration set in an earlier tool call, none of which a command line shows. So the closed list of gh post verbs holds only the `gh pr` and `gh issue` verbs that post, `gh api` calls that can write, and linear-app's `post` and `edit`. A line that mentions none of them passes both hooks unread, and only the skills' instructions cover what it posts: `gh pr merge --body`, `gh release` notes, `gh discussion` posts, project draft issues, agent-task descriptions, gists, label descriptions, gh aliases and extensions, and code given to a data command, such as `python3 -c` or `git -c`. Such a form is blocked only when its words happen to mention a gh post verb, as `gh pr merge 5 --body 'edit docs'` does.
  Evidence: a `PreToolUse` hook sees a tool call's command line, never what a program it starts sends, https://docs.anthropic.com/en/docs/claude-code/hooks; `gh alias set` maps a name to any gh command, https://cli.github.com/manual/gh_alias_set; git runs a repository's hooks, https://git-scm.com/docs/githooks, and the command `core.fsmonitor` names, https://git-scm.com/docs/git-config#Documentation/git-config.txt-corefsmonitor
