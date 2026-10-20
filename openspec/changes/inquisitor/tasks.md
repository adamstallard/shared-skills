Gate two: these follow on this branch once Adam approves the spec.

## 0. Measure before building

Record each result in design.md, *What the hook relies on, not yet
measured*, or under *Configuration* for 0.4, including a result that
contradicts what design.md assumed.

- [ ] 0.1 A `PreToolUse` hook with matcher `AskUserQuestion` fires before the
      picker opens
- [ ] 0.2 Its exit 2 blocks the picker, and its stderr reaches the model
- [ ] 0.3 The hook's `tool_input` carries `questions[].question` and
      `questions[].options[].label`, and how many questions one picker call
      takes
- [ ] 0.4 `gh api repos/<owner>/<repo>/collaborators/<login>/permission` works
      for a caller without push access, or fails in a way the script can tell
      from "no access"
- [ ] 0.5 The GitHub login of the last person to commit to a file can be
      found from the repository's commits on GitHub, such as the
      `author.login` that `gh api repos/<owner>/<repo>/commits?path=<file>`
      returns, or the script must skip that candidate
- [ ] 0.6 How an Igor posts its handback comment, and whether the post hook
      can tell that comment from other posts
- [ ] 0.7 How the script can learn which login a post goes out as, when the
      agent posts through the github-app skill's script
- [ ] 0.8 Whether the script can find the approver of the pull request that
      added a decision, from a `DECISIONS.md` section through blame, the
      commit and its pull request's reviews
- [ ] 0.9 How the script tells a session with a person in it from a
      headless run, such as an Igor worker or `claude -p`, and which Igor
      role a worker runs
- [ ] 0.10 Whether the agent can open, and write in, a repository's private
      security advisory, and what access that needs
- [ ] 0.11 GitHub's API gives a comment's or review's author, and whether a
      commit's signature is verified and for which account, as decision 78
      needs
- [ ] 0.12 Whether an Igor's worker can run this skill, with a lore clone and
      `inquisitor.json` in reach, as igor PR #216's task 3.1 measures
- [ ] 0.13 Whether GitHub lets a security advisory's private-fork pull
      request be merged before the advisory is published, as decision 108
      needs

## 1. Shared post reader

- [ ] 1.1 Move prose's `gh` and GitHub MCP body reader into `.agents/lib/gh-post/`,
      called from a thin script in each skill, with no change in behaviour
- [ ] 1.2 prose's tests pass unchanged; add the library's own tests beside it,
      each tagged `@scenario gh-post: <Scenario name>` for the `gh-post`
      spec's scenario it checks
- [ ] 1.3 The library also reads `python3 <github-app script> gh pr|issue …`
      posts, and `gh api` comments whose body is given by `-f body=`,
      `--raw-field body=`, `-F body=` or `--field body=` (with or without
      `@<file>`), or by `--input`, and blocks as unreadable any `gh api`
      call that writes (its method `POST`, `PATCH` or `PUT`, given or implied by
      fields, or a GraphQL mutation), whose
      body it can't read; add tests for these to prose's and the
      library's tests. prose's `DECISIONS.md` section on the allow-list then
      points at the library's list instead of restating it

## 2. The script

- [ ] 2.1 `.agents/skills/inquisitor/scripts/inquisitor.py vet` (first call):
      `--questions` and `--post`, printing the filters and filter 1's search
      results, issuing a token
- [ ] 2.2 `vet --pass <token> --verdicts <file>` (second call): the four
      verdicts and their fields, the three categories recorded by hash only,
      the refusals, and the records the hooks read, each deleted once it is
      more than 2 hours old except a `deferred` record without a category
- [ ] 2.3 Filter 1's search over decision documents, issues through `gh`, the
      repository's question log, and configured lore clones' entries and
      `questions` branch, fetched and read with `git show`; the authority
      rules, with scope as igor's `scopeMatches` gives it inside an Igor
      and by the short name outside one, and a decision record counted
      only when `accepted`, a change's own decisions within that change, and
      a questions-branch `decision` file only with its writer proven by a
      linked comment or a verified signature (decision 78), while an
      `agent` file there is always input; each source not searched; when
      each clone's remote-tracking default branch was last updated by a
      fetch
- [ ] 2.4 `log` and `miss`, writing one file per question or miss with a safe
      name, quoted frontmatter, an `authority` of `decision`, `input` or
      `agent`, and `answered_by: agent` for an agent's choice: in the
      repository's `.inquisitor/` for a
      question about it (by a pull request when it is not the repository
      holding the current work), or pushed to the team's lore repository's
      `questions` branch for a question about the organization or project,
      fetching and pushing again when rejected; the secret scan and the
      visibility refusal; `misses`, listing the misses by filter for a review
- [ ] 2.4b `cite`, pushing a citation file (entry id and date only) to the
      lore repository's `questions` branch when filter 1 stops a question
      with a lore entry, with author and committer `inquisitor <noreply>`
      and a day-only date, and none to a more visible lore repository; or,
      during an Igor's run, printing it for the Igor to push; commits to that branch use the fixed message
      `inquisitor: log <file>`
- [ ] 2.5 The question finder for posts, as one function the post hook also
      calls
- [ ] 2.6 `tag`, choosing whom a post's question tags. It takes the first
      candidate with write access. When there is none, it turns to the login
      configured for the person running the session, if it equals the
      account `gh` is logged in as. The picker cases below apply only in a
      session with a person in it; a session with no person in it tags the
      login only when it has write access and the post goes out as someone
      else, and otherwise tags no one:
      - no login configured: ask through the picker instead;
      - the login has no write access: tag no one;
      - the login has write access and the post goes out as that login, or
        the script can't tell which login it goes out as: ask through the
        picker instead;
      - the login has write access and the post goes out as anyone else:
        tag it
- [ ] 2.7 `lore`, opening a lore pull request, or a promotion from the
      `questions` branch, or refusing it by visibility

## 3. Hooks

- [ ] 3.1 `scripts/check-ask.sh`: `PreToolUse` on `AskUserQuestion` (Claude Code
      only), checking verdicts, blocking with exit 2, and failing open,
      including when it can't read its records
- [ ] 3.2 `scripts/check-post.sh`: `PreToolUse` on Bash and the GitHub MCP tools,
      through `.agents/lib/gh-post/`, blocking a post that holds a question
      with a category, blocking a post with a question when it can't read
      its records, and letting an Igor's handback comment through as
      far as task 0.6 finds the hook can tell that comment apart from other
      posts
- [ ] 3.3 `hook.json` with both hooks, `"default": "enabled"`

## 4. Tests

- [ ] 4.1 `scripts/test_inquisitor.py`, standard library only, each test tagged
      `@scenario inquisitor: <Scenario name>` for the scenario it checks
- [ ] 4.2 Every scenario has a tagged test: `spec_trace.py report
      --include-changes` lists no scenario of this change as `none`, its mark
      for a scenario with no tagged test. A scenario about what the agent
      does is tagged on a test that checks SKILL.md states the rule

## 5. Docs and registration

- [ ] 5.1 `SKILL.md`: the filters, the two calls, writing a question at the
      privacy of what it concerns, posting no more publicly than that, the
      questions other skills require a person to decide, preparing, batching and tagging, the order
      with prose, logging answers and misses, the three categories recorded
      by hash only, what a headless session does (no picker, an Igor's
      handback comment, stopping on a categorized question), describing no
      weakness in public text before its advisory is published, reviewing
      misses, and lessons by scope
- [ ] 5.2 `README.md`: what the skill is for, `inquisitor.json` and
      `.inquisitor/reviewers`, what to say to the agent, and troubleshooting a
      blocked picker or post
- [ ] 5.3 A row in the README's skills table, and `inquisitor` in its list of
      skills that turn on a hook
- [ ] 5.4 `manage-skills` installs it and wires its hooks: check with
      `skills.py install inquisitor` and `skills.py doctor`

## 6. Archive

- [ ] 6.0 Archive only after igor PR #216 has merged, since filter 1's
      search in an Igor worker depends on it; keep `docs/decisions/` as a
      decision-document location until igor PR #202 settles where the
      scribe's records live
- [ ] 6.1 Say in prose's and bug-hunter's `DECISIONS.md` that the
      inquisitor's commits to a lore `questions` branch are machine records,
      exempt from their trailers
- [ ] 6.2 Fold this change's lasting reasoning, from proposal.md and
      design.md, into a new `.agents/skills/inquisitor/DECISIONS.md`, and
      fold the reasoning for moving the post reader into prose's
      `DECISIONS.md`, as `AGENTS.md` says
