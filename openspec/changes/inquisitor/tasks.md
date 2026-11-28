## Before gate one is approved

- [x] G.1 The repository's owner approves the prototype build covering thread replies and
      the recorded answer shown beside the question, and task 6.1 names
      the approved build's tag. Done: build v0.2-9, which covers both,
      tagged `answer-mod-approved-v0.2-9`

Gate two: the tasks below follow on this branch once the repository's owner approves the
spec.

## 0. Measure before building

design.md's Open Questions say what the software does if each task's
fact does not hold. Record each result on its task's line below, and as
Evidence in the decision record of each capability it bears on; task
0.29's result goes in igor issue #247's body instead, since it is a fact
about igor's host. In the same commit, write the requirements the result
supports, and drop the task's Open Question unless the result leaves a
choice to the repository's owner. Numbers 0.14, 0.22, 0.24, 0.26, 0.27,
0.32, 0.36 and 0.42 have no task, so that the other tasks keep their numbers.

- [x] 0.1 A `PreToolUse` hook with matcher `AskUserQuestion` fires before the
      picker opens. Done 2026-11-26, Claude Code 2.1.332, in a throwaway
      project whose settings held the hook: the model's `AskUserQuestion`
      call ran the hook, which logged the call's input before any picker
      opened
- [x] 0.2 Its exit 2 blocks the picker, and its stderr reaches the model.
      Done 2026-11-26, same run: the hook exited 2, the call returned
      `PreToolUse:AskUserQuestion hook error: [<hook path>]: <stderr>`,
      and the model quoted the stderr's marker back
- [x] 0.3 The hook's `tool_input` carries `questions[].question` and
      `questions[].options[].label`, and how many questions one picker call
      takes. Done 2026-11-26, same run: `tool_input` held
      `questions[]`, each with `question`, `header`, `multiSelect` and
      `options[]` of `label` and `description`; a call takes 1 to 4
      questions, and a call with 5 failed input validation (`too_big`,
      maximum 4) before the hook ran
- [x] 0.4 `gh api repos/<owner>/<repo>/collaborators/<login>/permission` works
      for a caller without push access and when `<login>` is an App's
      `<slug>[bot]`, or fails in a way the script can tell from "no access".
      Done 2026-11-27 with gh 2.103.2, read-only calls: neither case gives a usable answer.
      On cli/cli, where the caller could only read, every login gave
      `403` "Must have push access to view collaborator permission.",
      and GraphQL's `repository.collaborators` `FORBIDDEN`, while a login
      that does not exist gave `404`. As an admin, an App's
      `<slug>[bot]`, raw or percent-encoded, gave `200` `none` with
      `user.type` `Bot`, even for `igor-generalist[bot]`, which authored
      a pull request on a private repository and pushed its commit; users
      read as `admin`, `read` or `none`. Not measured: a caller with
      write but not admin access, and an App's installation token as the
      caller; *A permission that cannot be read is no write access* covers
      both
- [x] 0.5 The GitHub login of the last person to commit to a file can be
      found from the repository's commits on GitHub, such as the
      `author.login` that `gh api repos/<owner>/<repo>/commits?path=<file>`
      returns, or the script must skip that candidate. Done 2026-11-26
      with gh 2.103.2: `commits?path=README.md` gave each commit's
      `author.login` and `author.type` on shared-skills, and on cli/cli
      gave `author` `null` for 2 of the file's 30 newest commits, which
      name no GitHub account, so the script skips them
- [ ] 0.6 Record, once igor PR #216 gives it, the form of the fixed
      marker on igor's handback comments on GitHub and on Linear, a marker that no text the
      Igor quotes from its item can produce, by which the answer service
      tells a handback from the Igor's other comments. On GitHub and on
      Linear, *A handback is an Igor's comment holding igor's marker*
      waits on it
- [x] 0.7 How the script can learn which login a post goes out as, when the
      agent posts through the github-app skill's script. Done 2026-11-27,
      reading github-app's script at 48370e0 with read-only calls: the
      script acts as `--identity`, else `GITHUB_APP_ACT_AS`, else
      `GITHUB_APP_IDENTITY`, else `default`, as that identity's
      `<slug>[bot]`; `~/.local/state/github-app/<identity>.bot.json`,
      which `check`, `run`, `env` and `wire` write, holds that login as
      `name`, matching the slug `GET /app` returned for both identities
      tried; a wired project, or `run`, also sets `GIT_AUTHOR_NAME` to it.
      A plain `gh` post goes out as `gh api user`'s login. Not measured:
      `gh api user` under an installation token, which GitHub documents
      as unavailable. An identity passed only as `--identity` shows only
      on the posting command line
- [x] 0.8 Whether the script can find the approver of the pull request that
      added a decision, from a spec or decision record file through blame, the
      commit and its pull request's reviews. Done 2026-11-27, one GraphQL
      query per file (blame, each range's commit, its associated pull
      requests and their `APPROVED` reviews' authors): on
      kubernetes/enhancements' `keps/sig-cli/1441-kubectl-debug/README.md`,
      all 22 blamed commits led to merged pull requests, 18 with an
      approver and 4 approved only through Prow `/approve` comments; on
      shared-skills' `.agents/skills/spec-check/SKILL.md`, squash-merged,
      all 43 commits led to 21 pull requests, none with an approving
      review, since the owner authors them all. REST
      `commits/<sha>/pulls` gave the same pull request as GraphQL. The
      script skips the candidate where no approving review exists
- [ ] 0.9 How the script tells a session with a person in it from a
      headless run, such as an Igor worker or `claude -p`, and whether a
      headless session that is not an Igor worker can post. The script
      reads from `IGOR_RUN` whether it runs in an Igor's run and whether
      that run is a worker's or the Igor's own; once igor builds it, check
      that igor sets `IGOR_RUN` as igor PR #216 specifies. Local part done
      2026-11-27, Claude Code 2.1.332: `CLAUDE_CODE_SESSION_ATTENDED` was
      `1` in an interactive session detached in tmux, in its subagent's
      and its fork's Bash too, and `0` under `claude -p`, where a mod's
      `session.start` gave `isInteractive` `false` under `claude -p` and `true` in the interactive session;
      `CLAUDECODE` and `CLAUDE_CODE_CHILD_SESSION` were `1` in both. The
      variable shows that an interactive session is open, not that anyone
      watches it. Not measured: whether a headless session that is not an
      Igor worker can post, and `IGOR_RUN`
- [ ] 0.10 Whether the agent can open, and write in, a repository's private
      security advisory, and what access that needs
- [x] 0.11 GitHub's API gives a comment's or review's text and author
      (inquisitor spec: *The log command takes answered_by from the linked
      comment*). Measured 2026-11-04 for an issue comment's author only: GraphQL's
      `IssueComment` has `author { login }`. Measured 2026-11-23 for an
      App's issue comment: GraphQL gives `author { __typename: "Bot",
      login: "<slug>" }`, without `[bot]`, and REST's `user.login` gives
      `<slug>[bot]`, a form task 0.21 found no account can take on. The task also checks that
      re-requesting a review adds a new `review_requested` timeline
      event, by which *An item that asks the person something is shown
      once* dates a request. Measured 2026-11-26 with read-only calls on
      public repository cli/cli's 40 newest merged pull requests: GraphQL
      gave `body` and `author { __typename login }` on all 95 reviews and
      all 35 review comments, the authors being `User` or `Bot`, and REST
      gave `user.login` on reviews and review comments; on a pull
      request whose reviewer was re-requested after reviewing, REST's
      timeline listed a second `review_requested` event for that reviewer,
      dated after the review, as GraphQL's `ReviewRequestedEvent` did
      (cli/cli pull request #15141)
- [x] 0.12 Whether an Igor's worker can run this skill, with a lore clone
      and `inquisitor.json` in reach. It can't, and by the specs of igor PRs #174
      and #175 it still can't once they land, though neither is built to
      check. The implementation builds
      everything except Igor-worker mode, which waits for what igor issue
      #247 lists
- [ ] 0.13 Whether GitHub lets a security advisory's private-fork pull
      request be merged before the advisory is published
- [x] 0.15 That a conditional request answered `304`, sent with the
      person's `gh` login, does not count against the rate limit, as
      GitHub documents (answer-service spec: *The poll reads every GitHub
      question source*). Done 2026-11-26 with gh 2.103.2's login: five
      `GET repos/<owner>/<repo>/issues` requests sent with the last
      response's `ETag` in `If-None-Match` each answered `304` with
      `x-ratelimit-used` unchanged, as `GET rate_limit` confirmed after,
      and the next request without it answered `200` and raised
      `x-ratelimit-used` by 1
- [ ] 0.16 How the answer service finds, on Linear with the person's key,
      mentions of the person and of the relay, and the line each is on,
      which tells whether it is a tag line, and replies to a relay
      comment, in a subscribed team; that it can post a comment as the
      linear-app identity with a host command and learn the comment's URL;
      that the identity can edit its own comment; and that Linear marks a
      comment's author as an app user in a form no person's account can
      take on. The task also finds whether the
      person's key can read when an issue was assigned, which *An item
      that asks the person something is shown once* compares with when
      the item's questions were answered. Measured 2026-11-19 as an app
      identity on a test issue: a host command's GraphQL `commentCreate` returns the
      comment's `id` and `url`, while the Linear MCP's tools return only
      the `id`; the identity edits its own comment; a reply holds its
      parent's id; and an app user's comment has `user.app` `true` and a
      null `botActor`, the 5 test comments among the team's 77, the other
      72 having `user.app` `false`; and a comment mentioning the identity
      holds the mention in `body` only as `@<displayName>`, the user's id
      only in `bodyData`, as a `suggestion_userMentions` node with
      `attrs.id`. Measured 2026-11-22, for the delete
      *An automatic post is deleted when another relay post came first*
      needs: an app user called the GraphQL mutation `commentDelete`,
      through Linear's MCP server, on its own comment on a test issue;
      it returned success, and the issue then listed no comments. Not
      measured: mentions of the person, the line each mention is on, an
      assignment's time,
      anything read with the person's key, and that no person's account
      can have `user.app` `true`, which only the schema's description says
- [ ] 0.17 That a `discord-bot` identity, as merged in shared-skills PR #1,
      can read a subscribed channel's history and threads, see a mention
      of the answer service's person by user id, and a reply to a
      message of that person's relay, and edit
      its own message; that Discord marks the author of a bot's or a
      webhook's message in a form no person's account can take on; and
      that a relay whose `check` reports
      `messageContent` `true` reads a message that doesn't mention the bot.
      Measured
      2026-11-19 in a test thread: the identity reads a channel's history
      and a thread's, a reply holds a `message_reference` to its message,
      the identity edits its own message and, as *An automatic post is
      deleted when another relay post came first* needs, deletes it, and
      a bot's message has `author.bot` `true`. Not measured: a mention of the person's user
      id, a webhook's message, and the Message Content read
- [x] 0.18 That a command the mod runs with `$.process.run` reaches no
      `PreToolUse` hook, so no post hook, on GitHub, Linear or Discord,
      sees a relay post. Done 2026-11-26, Claude Code 2.1.332, a test mod
      loaded with `--plugin-dir` in a project whose settings held a
      `PreToolUse` hook with matcher `*` logging every call: the mod ran
      `/bin/sh -c 'echo …; gh --version'` through `$.process.run`, which
      exited 0, and the hook logged nothing, while it logged the model's
      own Bash call in the same session
- [x] 0.19 That a mod's timers keep polling every 60 seconds and
      refreshing the lock every 30 seconds while its session is idle or
      has no terminal attached. Done 2026-11-26, Claude Code 2.1.332, a
      test mod in a session run in a detached tmux session, so with no
      terminal attached throughout: over 21 minutes, 12 of them idle with
      no turn and no input, its `$.clock.every` timers of 60 and 30
      seconds fired at intervals of 60.001 to 60.006 and 30.000 to 30.003
      seconds. Also observed 2026-11-26 with the approved prototype, build
      v0.2-9 (commit a16c60d, `scheduleArrival` in `answer-mod/hooks/register.tsx`): its
      new-question alerts, raised only by `$.clock.after` timers, chimed
      and showed while its session sat idle and the person was away
- [x] 0.20 How setup checks, on each surface, that a relay identity can
      post in a given channel: on GitHub, the App installation's access to
      each subscribed repository; on Linear and Discord, whether the
      skill's check reads a team's or channel's permission, or setup must
      read it itself. Done 2026-11-27, reading each skill's `check` at
      48370e0 and running discord-bot's and linear-app's, read-only:
      github-app's `check` reports the installation's `permissions`,
      which cover the whole installation, and its `repositoryNames`,
      every repository on it when there are 100 or fewer, else only their
      count, and its `repo_visible` step reads one repository with the App's token;
      the person's `gh` login cannot list installations (`403`). github-app's
      `check` was not run, since it mints a token and these measurements wrote nothing. linear-app's `check`
      reads no team; its app user, which had commented on a test issue,
      had no team membership and saw two public teams, so posting rests on
      the `write` scope and seeing the team; a private team is not
      measured. discord-bot's `check --channel` computes the bot's
      permissions in the channel and reported `viewChannel`,
      `sendMessages`, `readMessageHistory`, `createPublicThreads` and
      `sendMessagesInThreads` `true` on two channels; it takes no thread,
      which its parent channel's `sendMessagesInThreads` covers
- [x] 0.21 Whether GitHub's API reports, for a comment, the slug of the
      GitHub App that wrote it, in a form no account can take on, such as
      the author login `<slug>[bot]` with type `Bot`, or
      `performed_via_github_app`. The GitHub rules that tell a bot's or an
      App's comment from a person's rest on this fact, relaying on GitHub
      included. Done 2026-11-26 with read-only REST calls on the 100
      newest issue comments of each of cli/cli, microsoft/vscode and
      vercel/next.js: the 174 comments carrying a
      `performed_via_github_app` all had `user.type` `Bot` and a
      `user.login` equal to its `slug` followed by `[bot]`; none of the
      126 without one had type `Bot` or a login ending `[bot]`. GitHub documents that a username holds
      only alphanumeric characters and hyphens, so no account can take on
      `[bot]`
- [ ] 0.23 That the URL an asking agent records as `asked_in`, and the
      handback comment URL an Igor records, equals character for character
      the URL the answer service builds from what it polls, on GitHub,
      Linear and Discord. Compare an issue comment's URL with a pull
      request comment's, `discord.com` with `discordapp.com`, and a Linear URL before and
      after the issue is renamed. Where they differ, define one canonical
      form, which both sides write and compare. Record too whether Linear
      and Discord return a posted question's words unchanged. Whether they
      do decides whether a question asked there matches its logged file
      by hash (the inquisitor spec's *Among files with the same question,
      only the newest answer counts*), and whether task 0.28's lines are
      found. Measured 2026-11-19 on a test
      Linear issue and a test Discord thread:
      - a Discord message's URL is
        `https://discord.com/channels/<guild id>/<channel id>/<message
        id>`, with the message's own `channel_id`; a message that starts
        a thread keeps its parent channel's address, and a reader that
        meets, inside the thread, Discord's placeholder for that message
        follows the placeholder's `message_reference`; `discordapp.com`
        answers 301 to the same path on `discord.com`;
      - a Linear comment's `url` holds the issue's title slug and changes
        when the issue is renamed, so the canonical form drops the slug:
        `https://linear.app/<workspace>/issue/<TEAM>-<n>#comment-<first 8
        hex digits of the comment's id>`;
      - Linear returns a comment's text unchanged, and escapes an issue
        description's (`[` comes back as `\[`); Discord drops whitespace at the end of the whole message, and
        discord-bot rewrites `@name` to `<@id>` before it
        sends.
      Measured 2026-11-26 with read-only calls on cli/cli: REST's
      `html_url` equalled GraphQL's `url` for all 60 issue comments, all
      40 review comments and both reviews read, in the forms
      `https://github.com/<owner>/<repo>/issues/<n>#issuecomment-<id>`,
      `…/pull/<n>#issuecomment-<id>` for a pull request's comment,
      `…/pull/<n>#discussion_r<id>` and `…/pull/<n>#pullrequestreview-<id>`.
      Measured 2026-11-26 on a private repository of this repository's
      owner: `gh issue comment` printed
      `https://github.com/<owner>/<repo>/issues/<n>#issuecomment-<id>`,
      the same string as that comment's REST `html_url` and GraphQL
      `url`. Not measured: the URL `gh pr comment` prints, and an Igor's handback URL
- [ ] 0.25 How GitHub, Linear and Discord each report a relay post refused
      for its text, such as its length, against one refused for lack of
      permission. This is the mapping the answer-service spec's *A pending
      answer that no check returns waits for the person* uses
- [ ] 0.28 Post the lines `Inquisitor: a person must decide this
      (required by spec-trace).` and `Concerns: o/web` in a Linear comment
      and a Discord message, read each back as the answer service would,
      and record whether their words come back unchanged once markup is
      reduced, or the form each surface returns (answer-service spec: *A question with a
      person-required line gets no filter 2 to 4 reply*; *A concerns line
      settles what an agent's question concerns*)
- [ ] 0.29 Whether an Igor's host has Python and the inquisitor skill
      installed for the Igor's own process, not only for its workers, so
      the Igor can run `branch-search` (inquisitor spec: *The Igor reads
      questions branches with the script*)
- [x] 0.30 That `INQUISITOR_ANSWER=1 CLAUDE_CODE_NO_FLICKER=1 claude --name Answers`,
      with `--tools Read,Grep,Glob --strict-mcp-config`, starts Claude Code
      named `Answers` in its fullscreen layout, and that the mod sees
      `INQUISITOR_ANSWER=1` when the session starts and resumes, with the
      tool restriction still in force after the resume
      (answer-service spec: *The script installs the answer mod*;
      *Only a session with the answer marker opens the answer
      service*). Done 2026-11-26, Claude Code 2.1.332, started outside
      any other Claude session: the session was named `Answers` in the
      terminal title and the prompt box, ran on tmux's alternate screen,
      staying on the normal screen without `CLAUDE_CODE_NO_FLICKER=1`, and the mod read the
      marker `1` with the restriction in force. Run again with
      `--resume <id>` added, it kept the id, the marker and the
      restriction; `/resume` inside the session raised no new
      `session.start` and kept the marker and the restriction; a plain
      `claude --resume <id>` kept the name but had no marker, and every
      tool. A session started inside
      another Claude session took that session's name instead. Passing
      `--settings '{"enabledPlugins":{"<id>":false}}'` turned plugins off
      for that session alone: a test mod, the built-in easel plugin and
      the person's two installed mods were gone from it, and
      `claude plugin list --json` still showed them enabled afterwards;
      a `"*"` key turned nothing off. A mod's `$.command.run` of `exit`
      ended its session, raising `session.end` with reason
      `prompt_input_exit`, and the process exited 0. A tool a mod
      registered while the model's turn waited on another tool's call was
      offered within that turn, and the model called it; with the mod
      calling `$.turn.abort` and then `exit` as the tool joined, the
      session ended 32 ms later and the new tool was never called
- [x] 0.31 That GitHub's REST and GraphQL APIs both return a comment's
      `node_id` (GraphQL's `id`), that it is present for every kind of
      comment the answer service replies to (an issue comment, a pull
      request comment and a review comment), and that an edit leaves it
      unchanged (inquisitor spec: *Every miss file is named by one hash*).
      If a check fails, find a GitHub id that passes all three. Done
      2026-11-26 with read-only calls on cli/cli: all 102 comments read
      (40 issue comments, 22 pull request comments, 40 review comments)
      had a REST `node_id` equal to GraphQL's `id`, with GraphQL's
      `databaseId` equal to REST's `id`; the 3 of them edited after
      posting kept that `id`, their `userContentEdits` history hanging
      from it
- [x] 0.33 That the Discord bot token shape in *The credential patterns are
      a closed list of token shapes* matches the relay's real token: run
      the pattern against the token discord-bot holds, printing only
      whether it matched and each part's length, never the token. If it
      does not match, record the shape measured. Done 2026-11-26 on the
      token in discord-bot's keychain entry: the pattern matched it
      whole, as three parts of 26, 6 and 38 URL-safe base64 characters
- [x] 0.34 How Claude Code restricts a session's tools so that its model
      has only its conversation, `propose_reply`, `record_verdict` and
      Read, Grep and Glob: permission settings, a startup option such as
      `--allowedTools`, or a mod's own control. Record whether Claude Code
      enforces it itself rather than through a hook, and what the `answer`
      command must add to start a session so restricted (answer-service
      spec: *The service's model has no shell, no writing tool and no web
      fetch*; *The script installs the answer mod*). Done 2026-11-26,
      Claude Code 2.1.332: `--tools Read,Grep,Glob` leaves exactly those
      built-in tools, so the model cannot run a command; MCP servers' tools
      stay unless `--strict-mcp-config` is added, and another mod's
      registered tool stays even then, as a test mod's did and as the
      built-in easel plugin's did. A mod sees the whole list:
      `$.tool.list()` at `session.start` and a `tool.list` hook, which
      receives the list as `{ value }`, both listed the other mods' tools, each named
      `mcp__<mod or server>__<tool>`; without `--strict-mcp-config`,
      connector tools arrived about 15 seconds after start, and under the
      launcher's flags a mod's tool registered 8 seconds after start
      joined the list, each change seen by the hook; in a session
      started without the flags, the mod saw Bash and the other built-in
      tools
- [ ] 0.35 Whether the person's Linear key reads the GitHub links that
      Linear's GitHub integration puts on a team's issues (answer-service
      spec: *Setup guesses the repositories a Linear or Discord channel
      concerns*)
- [x] 0.37 That a mod can submit a prompt of its own into its session's
      conversation while the person is not typing, have the model answer
      it with a tool call, unattended, and detect when the model's reply in
      that turn has ended; and list every first character on which the
      prompt box runs a submitted prompt as a command (*propose_reply
      refuses a draft the prompt box would run*). Done 2026-11-26, Claude
      Code 2.1.332, a test mod in an idle session with no terminal
      attached: `$.prompt.submit` started a turn, the model called the
      mod's registered tool with the asked input, and the mod's
      `turn.complete` hook fired with `reason` `answer`. For each of the
      95 printable ASCII characters, the mod filled the prompt box with
      that character and a word through `$.prompt.fill`, and a script
      pressed Enter through tmux: only `/` ran as a command when a word followed it
      (`/probe047` never reached the mod's `prompt.submit` hook, while
      `/usr/bin/probe` reached the model); `!`, `#`, `&`
      and every other character reached the model as a plain prompt; a filled
      `!echo … > <file>` reached the model as text, not as a shell
      command
- [ ] 0.38 How the answer service tells that a GitHub App or a Linear
      app user is an Igor's, in a form no other account can take on. A
      slug proves nothing, since anyone can register a GitHub App or
      Linear app with any free name, `igor-` ones included; the task
      finds what igor records that names each Igor's identity, such as
      the App ID or Linear user id in igor issue #160's configuration
      entry, and whether the person's credentials can read it
- [x] 0.39 Whether Claude Code puts an `agentId` on a subagent's or a
      forked conversation's call to a mod's tool (answer-service spec:
      *Claude's draft goes to the prompt box, never to a post*). Done
      2026-11-27, Claude Code 2.1.332, with a throwaway mod logging each
      `tool.call` and `tool.run`, in two `claude -p` runs and one
      interactive run: a `general-purpose` subagent's and a fork's calls
      carried `agentId` at both hooks, and the main conversation's had no
      such key
- [ ] 0.40 Once igor PR #216's task 4.5 reports, whether an Igor worker
      can feed `igor lore-search` the question on standard input, or which
      other way #216 gives the command to take it (inquisitor spec: *In an
      Igor's run, filter 1 searches through igor*)
- [x] 0.41 A way to remove every other plugin's tools from the answer
      session, including a tool registered after start, while those
      plugins stay on (answer-service spec: *The answer mod strips other
      tools from the answer session*). Done 2026-11-26,
      Claude Code 2.1.332, with a test mod registering one tool at start
      and one 6 seconds later, the built-in easel plugin, and a second
      test mod standing in for the answer mod:
      - `--disallowedTools` with `mcp__<plugin>` or `mcp__<plugin>__*`
        removed all of that plugin's tools, the late one included;
        calling one failed with "No such tool available". No rule means
        "every plugin but one": `mcp__*` removed the stand-in's own tool
        too. This way needs each enabled plugin named, and the option
        passed again on every resume: a
        session resumed without it had the tools back, and the model ran
        them
      - the stand-in's `tool.list` hook, keeping only its own tool and
        the allowed built-in tools, removed every other tool, the late
        one and easel's included, at start and on resume, and the
        stand-in's `$.tool.list()` then listed none of them. In a session
        started with no `--tools`, it stripped Bash and Write too, and
        the model could call neither. Another mod
        can add its tool back: a mod loaded before the stand-in, which
        registered a tool and re-added it in its own `tool.list` hook,
        had that tool called by the model; loaded after the stand-in,
        its tool stayed removed. In both orders `$.tool.list()` listed
        the re-added tool, so a check reading that list sees it, and
        refuses in the second order too, though the model could not call
        the tool there
- [x] 0.43 That GitHub's edit history, `userContentEdits`, holds every
      revision of an edited issue, pull request or comment body, the
      original included (inquisitor spec: *A numbered reply stands only
      while its message's items are unchanged*). Done 2026-11-27 with
      read-only calls on igor issue #211 and shared-skills pull request
      #64: every revision, the original included, was there

## 1. Shared post reader

- [x] 1.1 Move prose's body reader, which finds a `gh` or GitHub MCP
      post's body, into `.agents/lib/gh-shell/`, beside the command
      splitter and gh flag tables already there, and build the `gh-post` rules on it. Each
      skill calls it from a thin script, and its behaviour changes only
      as task 1.3 lists
- [x] 1.2 prose's tests pass unchanged, except as task 1.3 allows; add the
      library's own tests beside it,
      each tagged `@scenario gh-post: <Scenario name>` for the `gh-post`
      spec's scenario it checks
- [x] 1.3 The library reads a post only in a canonical form and reports
      every other call that could post as unreadable, giving the
      canonical forms for the hooks' block message (gh-post spec: *The
      reader reads a post only in a canonical form*; *The canonical gh pr
      and gh issue posts are a closed list*; *The canonical gh api posts
      are a closed list*; *A gh api call is a read only in a plain
      form*). It reads a call of github-app's script with the library's
      `app_command`, `app_assignments` and `forget_scripts` (*The reader
      reads posts sent through the github-app skill*), a call prose's
      reader blocks today. It keeps prose's reader's splitting, its block
      on a command other than a data command naming `gh`, and its rule on
      piped input. Change each prose test that expects an off-list form to
      be read, such as `-b hi` or `--body=hi`, to expect it blocked; prose's hook ignores `gh api` today, so the
      `gh api` rules are new checks for it.
- [x] 1.4 discord-bot's `post` and `edit` take `--message-file <path>`,
      reading the text from that file, since a hook never sees standard
      input; its SKILL.md and README say to post with `--message-file`
- [x] 1.5 The library reads discord-bot's `post` and `edit` from
      `--message-file` alone and reports each as a Discord message
      (gh-post spec: *The reader reads discord-bot's post and edit only
      from a message file*), so prose's posting hook reads them too
- [ ] 1.6 The library reads `save_comment`'s `body` and `save_issue`'s
      `description` from the Linear MCP as messages, and every other
      Linear save, create, update or submit call's `summary` and
      `description` as Linear summary text; reports as unreadable a `save_issue` holding `patch`, one
      holding `template` but no `description`, and every Linear save,
      create, update or submit call other than `save_comment` and
      `save_issue` holding a string under a key
      that is neither on the no-text list nor `title`, `name`, `summary`
      or `description` (gh-post spec:
      *The reader reads a Linear MCP comment or issue description*;
      *Another Linear write tool sends no post only when it holds no
      text*)
- [ ] 1.6a The library returns each title a call sets, marked as a
      title: `--title` in a canonical gh pr or gh issue form, `title` in
      a canonical gh api post's JSON or a GitHub MCP tool's input,
      `save_issue`'s `title`; `title` and `name` in any other Linear
      save, create, update or submit call; and discord-bot
      `thread`'s `--name`. `--title`, and any single-dash option word
      holding `t`, join the text options (the options that carry a
      post's text), and a discord-bot `thread` call
      counts as mentioning a gh post verb. prose's posting hook skips
      titles (gh-post spec: *The reader returns each title apart from
      bodies*)
- [ ] 1.7 The library reports whether each post goes through the
      github-app skill's script (gh-post spec: *The reader says whether a
      post goes through the github-app skill*)
- [ ] 1.8 prose's and the inquisitor's `hook.json` post-hook matchers
      include the Linear MCP prefixes the gh-post spec lists
      (`mcp__linear__`, `mcp__plugin_<name>_linear__`,
      `mcp__claude_ai_Linear__`) and `mcp__claude_ai_GitHub__`, so
      each hook sees the calls the reader reads (gh-post spec: *The
      reader reads a Linear MCP comment or issue description*; *The
      reader reads a GitHub MCP tool's body and comment keys*)

## 2. The script

- [x] 2.1 `.agents/skills/inquisitor/scripts/inquisitor.py vet` (first
      call): `--questions`, and `--post` taking a post's body;
      prints the filters and filter 1's search results, and issues a token
- [x] 2.2 `vet --pass <token> --verdicts <file>` (second call): the four
      verdicts and their fields, an `ask`'s related earlier decision, the
      person-required line printed for an `ask` naming the skill that
      requires it (inquisitor spec: *A question another skill requires
      carries a person-required line*), the record line printed for an
      `ask` asked in the session, a `Not recorded: ` line holding only one
      of the reasons listed in the inquisitor spec's scenario *Not
      recorded gives a listed reason* (inquisitor spec: *A question asked in
      the session shows where its answer will be recorded*), the three
      categories recorded by hash only, the refusals, and the records
      the hooks read, each deleted once it is more than 2 hours old
- [ ] 2.2b The `not asked` verdict, accepted only for a question the
      plain reading found and the hiding reading did not, and the
      first call's output marking each such question so the agent knows
      `not asked` is open to it (inquisitor spec: *Only a question the
      hiding reading misses may be not asked*; *Questions in a post are found
      by two readings*)
- [x] 2.3 Filter 1's search. Items marked igor's are applied by
      `igor lore-search`, which igor PR #216 builds.
      - It searches decision documents, issues through `gh`, the
        repository's `questions` branch, and configured lore clones'
        entries and `questions` branch. It reads each `questions`
        branch through GitHub's API, and each lore clone's default
        branch with `git show`, checking none out (inquisitor spec: *A
        questions branch is read through GitHub's API*). Task 7.0 adds igor's scribe's
        decision records; until then the output names them as not
        searched.
      - It matches as plain text, lists answers before input and ranks
        each group by distinct terms matched, showing at most 20 hits in
        all, lore from `igor lore-search` included, and saying when it
        left some out.
      - During an Igor's run it searches lore only through `igor
        lore-search`, passing the question on standard input.
      - It applies the authority rules:
        - scope by the short name outside an Igor, and inside one as
          igor's `scopeMatches` gives it (igor's);
        - a decision record counted only when `accepted`;
        - a change's own decisions counted within that change;
        - a questions-branch `decision` file counted only unchanged and
          when its `answered_by` has write access, the file taken at its
          word for who answered;
        - an answer whose `recorded_in` pins a commit counted for other
          work only once that commit has landed;
        - only the newest answer counting among a question's files on a
          questions branch, by the order of the commits that added them;
        - during an Igor's run, `branch-search`, given the run's item,
          leaving out each file more private than the item (the file's
          visibility set by *A log or miss file is as private as its
          more private repository*) and showing a file about a
          repository other than the item's as input.
      - It reports each source it did not search, and when a fetch last
        updated each clone's remote-tracking default branch.
- [x] 2.3b `branch-search`, which searches one repository's `questions`
      branch and prints its hits as JSON, each labelled by task 2.3's
      checks (inquisitor spec: *The script searches a questions branch and
      prints labelled hits as JSON*). The JSON is the contract with igor,
      whose Igor runs the command for its worker: a test compares the
      output for a fixed branch with a stored copy, field for field, so a
      change to the format fails until the stored copy is changed, which
      waits for igor's agreement
- [x] 2.3c `miss-check`, which takes a repository, a surface and a reply's
      id and says whether that repository's questions branch holds the
      miss file that backs that `Inquisitor: ` reply (inquisitor spec: *The
      script checks whether a miss file backs a reply*). Its JSON is part
      of the contract with igor, under task 2.3b's test
- [x] 2.3d `file-answer`, which takes a repository and a questions-branch
      file name's date and 6-hex-digit suffix and prints only that file's answer, or `null` (inquisitor
      spec: *The script prints one questions-branch file's answer*). Its
      JSON is part of the contract with
      igor, under task 2.3b's test
- [ ] 2.3f The `permission unreadable` reason, in filter 1's labels and
      `branch-search`'s JSON, for a file whose `answered_by`'s write
      access to what its question concerns cannot be read (inquisitor spec: *A permission that
      cannot be read is no write access*; *The JSON's reasons and landed
      values are a closed list*)
- [x] 2.3e `search`, which runs filter 1 alone for the answer service,
      reading only the service's clones and their repositories' issues,
      and prints its results as JSON
      with no token or record (inquisitor spec: *The search command runs
      filter 1 alone for the answer service*; *The search command takes
      its question as the first call does*)
- [x] 2.4 The `log` command, writing one file per question or miss in the
      format of *A log file and a miss file have one format*.
      - `authority` is `decision` or `input`. An agent's own choice
        under filter 3 or 4 gets no file.
      - Every miss file is `misses/<hash>.md` (inquisitor spec: *Every
        miss file is named by one hash*), and nothing is pushed where the
        name is taken. A hash-only miss file, one with empty frontmatter
        and no body, is written only through an option the answer service
        passes (inquisitor
        spec: *A hash-only miss file shows nothing but that it exists*).
      - A log file for a question also asked in a post holds that post's
        URL as `asked_in`, only on a questions branch no more visible than
        the repository it points into. Igor-worker mode
        writes no `asked_in`: the handback comment it would link exists only
        once the Igor posts it, and the Igor writes it.
      - An answer file lists every file it answers in `answers`, refused
        when a named file is not on the branch or already holds an
        answer.
      - Built by igor, not this task: the Igor writes `answers` for a
        later run only for a file it finds by its own record's suffix
        and date.
      - On a questions branch, `repository` only on a file about one
        repository, and `asked_from` on every log and miss file except a
        handled file, a hash-only miss file and a file written during an
        Igor's run. Outside a
        run `asked_from` is the repository holding the current work
        (for an answer file naming files it answers, the most private of
        their `asked_from`), or the branch's own repository once the person
        confirms sending the file somewhere more visible: a file is as
        private as the more private of its branch's repository and its
        `asked_from`, so such a file is read at that branch's visibility
        (inquisitor spec: *The answerer's confirmation can send a record
        somewhere more visible*). On a log or miss file the answer service
        writes, `asked_from` is what the answer service passes to the `log`
        command (answer-service spec: *A miss records who judged it and
        where it was asked from*).
      - A handled file holds only `handled`, the day in UTC on which the
        question was closed, and `closes`, the closed file's name without
        its directory, with no body. It is
        written only through the command's service option, which only the
        answer service passes; a `handled` or `closes` key, or a hash-only
        miss file, is refused without that option.
      - Each answer is written in quote lines:
        - with a github.com `answer_link`, read from the linked comment
          and recorded word for word;
        - with a Linear or Discord `answer_link`, refused without the
          service option; with it, the answer recorded as given and the
          link never fetched, the link written only where the questions
          branch's repository is private and left out elsewhere;
        - any other answer a person gave, without an `answer_link`, in
          their own words as given; without the service option, as `input`
          unless its `answered_by` is the login of the person running the
          session, which for `decision` also needs write access (inquisitor spec: *The log
          command makes an unlinked answer a decision only for the
          session's person*).
      - A file is pushed to the `questions` branch of the repository the
        question is about, or of the team's lore repository for a
        question about a collective. Every commit to a questions branch,
        `cite`'s included, is made through GitHub's Git database API (a
        tree on the branch's head, a commit, then the branch moved
        forward without force), with no clone or checkout, so no HEAD
        moves, and adds no file whose path the branch holds (inquisitor
        spec: *A question is pushed to the questions branch of what it
        concerns*). The command commits again on the new head when
        GitHub refuses the move because the branch moved,
        and keeps the file pending, pushing it with the next file for
        that branch, when it cannot push otherwise; called with its
        service option, which the answer service passes on every push, it
        keeps no pending copy and reports why the push failed.
      - A picker question's file is pushed once answered, and a record
        more visible than its source only once the person answering
        confirmed the warning, then with no link into the source.
      - The secret scan, over raw markdown with link targets included,
        the visibility refusal, and the refusal of an empty answer
        (inquisitor spec: *The log command refuses an empty answer*).
      - Without its service option, in a folder no git repository
        holds, it refuses a file whose `asked_from` would be the current
        work's repository (inquisitor spec: *The log command refuses
        outside a git repository*). Its confirmation option sends only an
        answered log file or a miss file somewhere more visible (inquisitor
        spec: *The answerer's confirmation can send a record somewhere more
        visible*).
      - It refuses, saying why, a question holding a line that is exactly
        `## Rephrased question`, `## Discussion` or `## Answer`.
      - `misses`, listing the misses by filter for a review.
- [x] 2.4b `cite`, pushing a citation file in the format of *A citation
      file has one format* (`entry` and `date`, no `run`), one for each stop or cite, to the
      `questions` branch of the lore repository holding the entry, when
      filter 1 stops a question with a lore entry, or when the person in
      the answer service cites an `active` entry in scope by naming it in
      a reason 2 decline with filter 1 or by agreeing to it as a shown
      recorded answer. Its commit names no person. Its callers do not call it for a question
      with a category, nor for a cited entry that is out of scope or not
      `active`; it does not check these itself. A push it cannot make stays pending as `log`'s does,
      except when called with the service option `log` also takes,
      which the answer service passes (inquisitor spec: *The answer
      service's files are never kept pending*). During an Igor's run it pushes nothing; igor PR #216's
      *An Igor publishes the citations its worker reports* covers it
- [ ] 2.5 One markdown parser in `qtext` both builds a question's text
      and finds a post's questions, by each of the two readings, for the two calls, the post hook and
      the answer service alike: a line classifier (code fence, `>` line,
      list item, heading, bold label, colon label, record lines, prose's
      footer) and an inline reducer that reads each line once, left to
      right. An open-questions section begins only at a label that names
      questions or a deferral label (inquisitor spec: *A question's text
      and hash are built one way*; *Inline markup is reduced to its text
      one way*; *A question in a post is a listed item or a sentence
      ending in a question mark*; *Questions in a post are found by two
      readings*; *A sentence and a question's terms are defined*)
- [x] 2.6 `tag`, choosing whom a post's question tags: the first candidate
      with write access, starting with the approver of the related earlier
      decision the second call recorded; else the login configured for
      the person running the session, if it equals the account `gh` is
      logged in as. With a person in the session:
      - no login configured: ask through the picker instead;
      - the login has no write access: tag no one;
      - the login has write access: tag the login when the post goes
        out as a GitHub App, which a post does only when the agent
        passes the identity of the github-app command the post goes
        through (inquisitor spec: *A post goes out as a GitHub App only
        through github-app's commands*), recording that identity with
        the question's verdict (*A tag made for an App's post goes out
        only through github-app*); otherwise ask through the picker
        instead.

      A session with no person in it tags the login only when it has
      write access and the post goes out as a GitHub App, and otherwise
      tags no one. The tag, or when tagging no one the fixed line of *A
      question no candidate can decide turns to the session's login*, goes
      on the question's tag line, which the
      question's hash leaves out (inquisitor spec: *A tag line names the
      person a posted question tags*; *A question's text and hash are
      built one way*)
- [ ] 2.7 `lore`, opening a lore pull request of one of three kinds: a
      new entry, a promotion from the `questions` branch, or a lesson
      from misses, for which the agent gives it the miss files the lesson
      draws on. It makes the branch, the commit and the pull request
      through GitHub's API, with no clone (inquisitor spec: *The lore
      command opens its pull request through GitHub's API*). It refuses an id outside igor's id rule. It refuses a lore
      repository more visible than the entry's source unless given the
      confirmation option, which the agent passes only once the person
      confirms (inquisitor spec: *A lore pull request goes to a more
      visible lore repository only once confirmed*; *A person can confirm
      a generalized lore entry for a more visible lore repository*). During an
      Igor's run it opens nothing and writes the entry into the run's
      report for the Igor to propose, as igor PR #216 is asked to. It
      reuses a leftover `inquisitor/lore-<id>` branch only as *A leftover
      lore branch is reused only after its pull requests closed unmerged*
      allows. All of it is built but the Igor's-run part
- [x] 2.8 A test pinned to an igor commit that checks the lore entry
      format `lore` copies: the `entries/<id>.md` path, the id pattern and
      the frontmatter fields igor's lore store requires (inquisitor spec:
      *A proposed lore entry's path, fields and id follow igor's rules*)
- [x] 2.9 The `log` command's input file, kept and refused as the two
      calls' files are (inquisitor spec: *The log command takes its input
      in a private file*)

## 3. Hooks

- [ ] 3.1 `scripts/check-ask.sh`: `PreToolUse` on `AskUserQuestion` (Claude Code
      only), checking verdicts, blocking with exit 2, and failing open,
      including when it can't read its records
- [ ] 3.2 `scripts/check-post.sh`: `PreToolUse` on Bash, the GitHub MCP
      tools and the Linear MCP's tools, through
      `.agents/lib/gh-shell/`. Every check below applies to a Discord or
      Linear message the reader returns too. It blocks a post holding a
      question tagged for a github-app identity unless the post goes
      through github-app's script (inquisitor spec: *A tag made for an
      App's post goes out only through github-app*). It blocks a post in which a
      question whose `ask` names a requiring skill lacks its
      person-required line, or another question carries one. It blocks every post holding
      a question whose latest verdict record gives it a category (inquisitor spec: *The post hook blocks a post holding a
      question with a category*); blocks a post with a
      question when it can't read its records; blocks a question whose raw
      markdown matches the credential patterns; passes an untagged
      question under a deferral label whose `deferred` verdict is less
      than 2 hours old; blocks an item under a deferral label
      without a `deferred` verdict, even with `ask` (*An item listed as
      deferred needs a deferred verdict*); and blocks
      every other unvetted question (inquisitor spec: *Questions in posts
      pass the same filters*). It blocks a call any of whose titles holds
      a question by the plain reading, telling the agent where to ask it
      instead (*A title holding a question is refused*), and a call whose
      Linear summary text holds a question the hiding reading finds
      (*A question in Linear summary text is refused*)
- [ ] 3.3 `hook.json` with both hooks, `"default": "enabled"`

## 4. Tests

- [ ] 4.1 One test file per module, `scripts/test_<module>.py`, standard
      library only, each test tagged `@scenario <capability>: <Scenario
      name>` for the scenario it checks
- [ ] 4.2 Every scenario but the expected gaps has a tagged test:
      `spec_trace.py report --include-changes` marks only the expected
      gaps `none`. A scenario about what the agent does is tagged on a
      test that checks SKILL.md states the rule. An expected gap is a
      scenario only igor's unbuilt work can make pass, or one whose rule
      waits on an open measuring task. It gets no test, not even a skipped
      one, and is listed by name under this task
- [ ] 4.3 Once igor provides `igor lore-search` and a role's `commands`
      can list the skill's script, build Igor-worker mode, write a tagged
      test for each expected gap, and remove it from task 4.2's list;
      do the same for a gap whose rule waited on a measuring task, once
      that task is measured and the rule built.
      The archive waits for this, because archiving moves the scenarios
      under `openspec/specs/`, where spec-trace's CI fails on an untagged
      scenario (task 7.0)
- [ ] 4.4 New Python passes `pyright --strict`, and the answer mod
      TypeScript's strictest settings; `.github/workflows/checks.yml` runs
      pyright, every test and spec-check's checks on pushes and pull requests

## 5. Docs and registration

- [ ] 5.1 `SKILL.md`: the filters, the two calls, writing a question at the
      privacy of what it concerns, writing its answers as a numbered
      `label: effect` list (answer-service spec: *An agent's question
      offers the options its numbered list gives*), posting no more publicly than that,
      that the person is accountable for what is posted as their relay
      and where, since no hook checks where a relay post goes
      (answer-service spec: *The person answers for what their relay posts*), the
      questions other skills require a person to decide (the agent runs
      only filters 1 and 3 on them), the
      person-required line and a picker question's record line copied
      exactly from the second call, the concerns line beside a question in
      a post or message, preparing,
      holding a question that blocks no step until the round's end while
      going on with its recommended answer, batching and tagging, the order with prose, logging answers and
      misses, the three categories recorded by hash only, what a headless
      session does (no picker, an Igor worker asking only in its handback
      comment, stopping only work that needs a categorized or held-back
      question's answer and what its report then says, and an Igor worker
      raising igor's flag for a categorized question, listing once each
      category its worker run met and marking those of the questions it
      stopped on), describing no weakness in public text before its
      advisory is published, reviewing misses, and lessons by scope
- [ ] 5.2 `README.md`: what the skill is for, `inquisitor.json` and
      `.inquisitor/reviewers`, what to say to the agent, and troubleshooting a
      blocked picker or post, and, while github-app or linear-app hands
      a relay's token to a command that can print it, the warning that any
      agent can print it and post `User says: ` (answer-service spec:
      *The README warns that a relay's token can be printed*). While
      task 0.6 or 0.38 is open, it says no comment counts as a
      handback; while task 0.16 is
      not done, that Linear stays off; and while task 0.17 is not done,
      that Discord stays off.
- [ ] 5.3 A row in the README's skills table, and `inquisitor` in its list of
      skills that turn on a hook
- [ ] 5.4 `manage-skills` installs it and wires its hooks: check with
      `skills.py install inquisitor` and `skills.py doctor`
- [ ] 5.5 github-app's `SKILL.md`: every example that runs `python3 $G`
      sets `G` in the same command, or writes the script's full path, so
      the post hooks don't block it
- [ ] 5.6 `README.md` says each of the following. Setup suggests a rule blocking
      force pushes to a `questions` branch and its deletion, which only an
      admin can set. Without it, anyone with write access can rewrite or
      delete the branch; with it, a writer can still push a handled file
      that hides a question from the person (the answer-service decision
      record's *Rationale: Setup suggests a rule guarding each questions
      branch*). spec-trace's workflow skips pushes to the `questions`
      branch (task 5.9), since that branch holds none of the project's
      files. A
      repository owner must make any other workflow that checks those
      files on push skip that branch too, or it fails there.
- [ ] 5.7 Change bug-hunter's SKILL.md so that Step 9 runs each
      recommendation in its report through the inquisitor skill's four
      filters before asking about it: a root cause, a finding too large
      for the change, anything left unresolved when the run aborted, and
      a property from the hunt (Step 3) worth keeping as a permanent
      guard. The builder sets when each kind passes a filter, and those
      conditions are reviewed with the implementation
- [ ] 5.8 Add to bug-hunter's SKILL.md the inquisitor spec's rules for a
      weakness whose advisory is unpublished. When the advisory's publisher
      says the private fork merges only at publication, the regression
      test lands in the private fork, and fork commit messages may
      describe the weakness. Without that, the test lands nowhere until publication, and then on a
      public branch (*Before publication, a weakness's test and
      description reach only the private fork*). Commit messages on a
      public branch never describe the weakness before publication (*A
      weakness is not described in public text before its advisory is
      published*)
- [x] 5.9 Bring shared-skills PR #101's commit 7b6ffa3 (branch
      `spec-trace-skip-questions`) onto this branch, by cherry-pick or, if
      spec-trace's README or SKILL.md has changed since, by reapplying it:
      the workflow template in spec-trace's README skips pushes to
      `questions`, and the README and SKILL.md say why. Once this change merges, close #101 as included.
      Done by reapplying 7b6ffa3 to main's current README and SKILL.md
      (41d7c3e)

## 6. The answer service

- [x] 6.0 Build on discord-bot as shared-skills PR #1 merged it.
      The Discord relay posts with no header option and with mention
      rewriting on, because discord-bot always posts that way. discord-bot's `read` drops each message's
      `author.bot` and reply reference, which the answer service needs to
      tell a bot's message and a reply to a relay post, as task 0.17 found
      on 2026-11-19; this task changes `read` to return both, and whether
      a message is flagged `IS_CROSSPOST` (answer-service spec: *An
      agent's question comes from a bot account or a log file*)
- [x] 6.0b discord-bot's `read` drops each message with no text and no
      attachments, the placeholder for a thread's first message included.
      Change it so that, meeting that placeholder inside a thread, it
      follows the placeholder's `message_reference` and returns the
      thread's first message in its place, still dropping any other such
      message, such as an embed-only one (answer-service spec: *A Discord
      thread is read with its first message*)
- [ ] 6.0a The answer service's logic is a Python core in the skill's
      scripts: polling, state, records and pushes, reusing the script's
      one question-hash and file-format code. The TypeScript answer mod
      does the UI, timers, tools, the answer marker and the tool
      stripping, calling the core through JSON commands
- [x] 6.1 The answer mod, built in the skill's `answer-mod/` folder from the tag
      `answer-mod-approved-v0.2-9` on shared-skills (build v0.2-9,
      commit a16c60d), the only build the mod starts from. It descends
      from v0.1-33 (`answer-session-ui-approved-v0.1-33`, commit fc3c35f)
      and v0.1-30 (`answer-session-ui-approved-v0.1-30`, commit c9c6eb5)
      and builds on both, keeping declining and the list of questions
      answered or handled for the person. The mod takes its questions
      from task 6.3's polls instead of the prototype's made-up ones.
      Compared with v0.1-33, v0.2-9 drops the answer field and the
      pickers inside the mod's panel, so answers are typed in the prompt
      box and reasons and filters are chosen from numbered lists. It
      adds:
      - posts drawn as Markdown;
      - long text cut by the terminal with an ellipsis, and `(v)iew all`
        in the key row only while something that key would show whole is
        cut;
      - a transcript row for each question acted on, whose `view` opens
        that question;
      - a bar, holding a dot per question and a tally, that fits its
        width and has no title;
      - new-question alerts: a chime for each poll that finds any, a
        toast and a notification for each question naming who asks and
        where, and the question's dot marked and `N new` in the tally
        until the question is shown;
      - `q` leaving Claude Code, unlisted in the key row to save room,
        with the opening message saying `Ctrl+C twice to leave.`

      Four rules decide what is built:
      - (a) Keep v0.2-9's layout and interaction: the band, which is the mod's panel above the prompt box,
        the keys, the prompt-box flow and the declining screens. Changes
        needed to wire them to real data are fine; restyling or
        reorganising them is not.
      - (b) Where the prototype disagrees with the spec, the spec wins.
        The known cases:
        - `User asks: ` for a clarifying question;
        - the `Rephrased question: ` and `Discussion: ` lines in the
          relay post;
        - `Recorded answer: see the record below.` with
          `Recorded in: <URL>`, quoting nothing;
        - the fixed `Inquisitor: ` texts, and reason 2's line
          `The person chose this filter.`;
        - previews that show the `Re: <URL>` line;
        - two decline reasons, the prototype's first two merged as
          reason 1, "Nothing to answer: the conversation is over, or it
          isn't a question"; under
          it declining closes only that question, and every later message
          in its thread that the answer service's four question sources name is a new question, where the
          prototype ends the thread;
        - reopening offered only for a thread copy declined with nothing
          posted, on its own machine, where the prototype offers it for
          any decline under its first two reasons;
        - the handled file pushed naming each questions-branch file a
          closed question was shown from, or that holds it through
          `asked_in`, which the prototype does not write;
        - a recorded answer the person agreed to and posted shown as
          answered for the person, where the prototype shows it as
          answered by the person's own relay post;
        - a question's state read from the latest relay post in its
          thread, whatever its prefix and whichever machine posted it,
          where the prototype reads only the person's `User says: ` post,
          local state deciding only what the spec leaves to it, such as a
          question declined with nothing posted;
        - agreeing to a recorded answer writing no answer file, whether
          a reason 2 decline with filter 1 on an agent's question or a
          post on a person's question, where the
          prototype treats it as its own path and logs the recorded answer
          in a new file;
        - the question on screen kept in the state folder, not the mod's
          `$.store`, so a restarted session opens on it.
      - (c) A screen the spec needs that v0.2-9 lacks is designed in this
        task from the prototype's existing patterns, in no new visual
        style, with no prototype round of its own: setup, the lock
        message, where an answer will be recorded and the warning when
        that place is more visible than the thread, the pick of another
        place, a post's failure, discord-bot's warnings, why no miss was
        logged, a channel that is off, the rate-limit notice, and the
        pending list of answers not yet relayed, which reuses the
        approved queue's screens
      - (d) The screens v0.1-33 added to v0.1-30 are taken as v0.2-9
        has them, each in the one place it shows them: the thread's
        replies since the question, including when the asker withdraws
        it; filter 1's recorded answer shown with the
        question, a questions-branch question included; and the wording
        and placement of the notice for a post held back because a reply
        arrived
- [ ] 6.2 The `answer_service` section of `inquisitor.json`, and setup:
      the person's GitHub login, without which it does not complete; the
      candidates; each relay check; saving the file with the person's
      own keys kept; a failed identity's surface or a failed channel left
      off and checked again at each opening; the Linear key stored in
      the keychain by a command the person runs, never through the prompt
      (*The person's Linear key never passes through the prompt*); each Linear or Discord channel's `repos`, guessed from its
      history (answer-service spec: *Setup guesses the repositories a
      Linear or Discord channel concerns*); the check that each subscribed or
      lore repository's `questions` branch takes the person's direct push,
      and the suggested rule blocking its force pushes and deletion;
      and the optional step that creates a lore repository, its clone and its
      configuration entry
- [ ] 6.3 Polling: the four question sources (answer-service spec: *A
      question asked of the person comes from one of four sources*), only
      while open, the catch-up on opening, 60 seconds, poll positions,
      `ETag`s and the wait after a rate-limit refusal (*The poll reads
      every GitHub question source*), reading every subscribed and lore
      repository's questions branch through GitHub's API and fetching
      every configured lore repository's default branch about every 60
      seconds,
      and a subscribed repository's default branch when filter 1 is
      about to check a question placed in it. The `search` command reads
      only these branches and clones, and issues only of their
      repositories (answer-service spec: *The answer service's
      filter 1 reads only subscribed and lore repositories*)
- [ ] 6.4 Relaying: posts with the four reserved prefixes through the
      relay identity's skill as host commands, or on Linear the service's own
      HTTP request, carrying the token linear-app's `token` command prints,
      held only in memory and never in a command's arguments, the `Re: ` line on GitHub
      and Linear posts, post ids, editing in place, the thread read before
      a question is shown and before each post, the thread read after each
      automatic post and that post deleted when another relay post
      came first (answer-service spec: *An automatic post is deleted
      when another relay post came first*), the preview showing where
      the answer will be recorded; the person's pick of another place in
      it (answer-service spec: *The person can pick another place in the
      preview*); for an Igor's question on a more private repository, the
      preview's line saying the answer also reaches the run on its item
      (answer-service spec: *The preview says when an answer also reaches
      a more visible item's run*); an answer whose last line
      starts `Re: `, which a reader would take for the post's own `Re: ` line, sent back for rewording,
      and answer files pushed as *An answer is recorded by a new log
      file* and *An edit to a questions-branch answer pushes a new log
      file* set;
      discord-bot's warnings shown after each Discord relay post and edit;
      and, off GitHub, the relayed text logged with the relay post's URL
      as an unfetched `answer_link`
- [ ] 6.5 State: the state folder, a question's state read from its
      thread, closed questions, discussion records deleted once their
      question is answered or closed, the question on screen, and the lock,
      which a second session reports and offers to take over
- [ ] 6.6 The discussion's context, `propose_reply` (refusing a call as
      *Claude's draft goes to the prompt box, never to a post* and
      *propose_reply refuses a draft the prompt box would run* say, and filling the record's URL for a filter 1
      decline), `record_verdict` and the code's checks of each call
      (answer-service spec: *The model's judgements reach the service's
      code only through record_verdict*), the core listing each message
      awaiting judgement at every poll until its turn ends, with the mod
      keeping no queue of its own (*A message awaits judgement until its
      turn ends*), and the rephrased answer's
      post. SKILL.md tells an agent
      that records an answer from a relay post to log its rephrasing and
      summary
- [ ] 6.6a The session's tool restriction, as task 0.34 found it: the
      model gets only its conversation, `propose_reply`, `record_verdict`
      and Read, Grep and Glob (answer-service spec: *The service's model
      has no shell, no writing tool and no web fetch*), the mod's
      check of the session's tools and its ending the session when a
      tool joins (*The answer service opens only beside its own tools*;
      *A tool joining an open answer service ends the session*); the
      `answer` launcher (*The answer launcher starts a restricted
      session*); the mod's `tool.list` hook stripping other tools (*The
      answer mod strips other tools from the answer session*); the script's
      `install-mod` and `uninstall-mod` commands
      (*The script installs the answer mod*); and the mod opening the
      answer service only in a session `answer` started, by the marker
      task 0.30 confirmed (*Only a
      session with the answer marker opens the answer service*). SKILL.md
      tells an agent using the skill, when the person wants to answer the questions asked
      of them, to offer to install the answer mod and then to tell them
      to run `answer`
- [ ] 6.7 prose's SKILL.md says that a relay post gets
      no prose pass, because it is the person's words, and an automatic
      post none, because its text is fixed
- [ ] 6.8 Tests, each tagged `@scenario answer-service: <Scenario name>`,
      and the README's section on the answer service:
      installing the answer mod with `install-mod`, then running `answer`,
      and running `uninstall-mod` before uninstalling the skill, so no link
      outlives the skill's folder; that the answer session strips other
      plugins' tools, and that a tool another mod adds back keeps the
      answer service closed, the service naming the tool;
      setup; what to do when a relay check fails, and that no post but
      the answer service's starts with a reserved prefix
- [x] 6.9 The repository's owner's approval, by use, of the screens prototyped after the
      first approved build: declining a question, the choice of filter
      under "the inquisitor should have handled it" (reason 2) and the
      exact post shown before it goes out, and the list of questions answered and handled for
      the person. Done: build v0.1-30, tagged
      `answer-session-ui-approved-v0.1-30` on shared-skills
- [ ] 6.10 The answer service's handling of incoming questions, SKILL.md's
      guidance on its automatic replies, and, for each scenario this task
      builds, a test tagged `@scenario <capability>: <Scenario name>`.
      - Built in this task:
        - filter 1 on every incoming question not placed `other`, except an item question, run through the script's
          `search` command, and the `Recorded answer: ` post;
        - placing a question asked on Linear or Discord (answer-service
          spec: *A Linear or Discord question is placed by what it
          concerns*; *A channel's repositories place its questions*), and placing an agent's question by its concerns line
          (*A concerns line settles what an agent's question concerns*);
        - filters 2 to 4 and the three fixed `Inquisitor: ` texts, and a
          question carrying a person-required line always shown to the
          person unless filter 1 answers it, the line found by its fixed
          wording after markup is reduced;
        - declining with its two reasons, the second only on an agent's
          question, and reason 2's posts;
        - the misses on the questions branch, none for reason 1, for
          a person's question or for an item question, and a miss against filter 1
          for an agent's question the answer service answers by itself;
        - a `Recorded answer: ` post the answer service makes without
          the person, but no `Inquisitor: ` post, on a relayed question:
          one a bot account posted starting `User says: ` or
          `User asks: ` (answer-service spec: *A relayed question is a
          person's question*);
        - no automatic post that repeats an automatic post made earlier
          in its chain of replies;
        - a questions-branch question asked in a post answered in its
          thread and by a log file;
        - a refused post turning off a channel no check can read;
        - the post hook's block of a tool-call post that starts with a
          reserved prefix.
      - SKILL.md tells an agent to act on a `Recorded answer: ` reply only
        once filter 1 counts its record, and on an `Inquisitor: ` reply
        only when no other skill requires a person to decide the question
        and a miss file backs the reply on the branch its question's
        concerns line names, named by a hash of the reply's surface and id
        and either naming a `said_by` or hash-only (inquisitor spec: *A
        hash-only miss file shows nothing but that it exists*).
- [ ] 6.11 Decide at implementation, and add to the spec as a
      requirement with a scenario or, if no test can check it, to the
      answer-service decision record as an entry with evidence: how the
      service handles an asker's reply that revises a question's options
      (answer-service spec: *An agent's question offers the options its
      numbered list gives*)
## 7. Archive

- [ ] 7.0 Archive only after igor PR #216 has merged, since filter 1's
      search in an Igor worker depends on it, igor PR #202 has set the
      path of the scribe's records, and task 4.3 has tagged every expected
      gap, since spec-trace's CI fails on an untagged scenario once
      archived. Make filter 1 search the scribe's records
      where igor PR #202 puts them, in the repository a question concerns
      and in the lore repository. Point the spec's
      links to igor PR #216's lore-firing spec at igor's
      `openspec/specs/lore-firing/spec.md` on main
- [ ] 7.1 Archive with `openspec archive` and no flags. This pull request already
      edits the decision records, `openspec/specs/inquisitor/decisions.md`,
      `openspec/specs/answer-service/decisions.md` and
      `openspec/specs/gh-post/decisions.md`, and archiving leaves them as
      they are. Write no `.agents/skills/inquisitor/DECISIONS.md`. Point
      each decision record's link to tasks.md at the archived tasks.md
