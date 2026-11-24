## Before gate one is approved

- [x] G.1 The repository's owner approves the prototype build covering thread replies and
      the recorded answer shown beside the question, and task 6.1 names
      the approved build's tag. Done: build v0.1-33, tagged
      `answer-session-ui-approved-v0.1-33`

Gate two: the tasks below follow on this branch once the repository's owner approves the
spec.

## 0. Measure before building

Record each result on its task's line below, and as Evidence in the
decision record of each capability whose requirement cites or waits on
it. Task 0.29's result goes in igor issue #247's body instead, since it
is a fact about igor's host. In the same commit, drop the task from
design.md's Open Questions unless its result leaves a choice to the
repository's owner, and rewrite each requirement and scenario that waits on that
task to its result: drop its wait, and drop or restate a scenario written
for before the result, such as *Nothing is relayed on GitHub before task
0.21*. spec-trace fails CI on a scenario no test tags, and no test can
check such a scenario once the task is done. Numbers 0.22, 0.24, 0.26, 0.27, 0.32
and 0.36 have no task, so that the other tasks keep their numbers.

- [ ] 0.1 A `PreToolUse` hook with matcher `AskUserQuestion` fires before the
      picker opens
- [ ] 0.2 Its exit 2 blocks the picker, and its stderr reaches the model
- [ ] 0.3 The hook's `tool_input` carries `questions[].question` and
      `questions[].options[].label`, and how many questions one picker call
      takes
- [ ] 0.4 `gh api repos/<owner>/<repo>/collaborators/<login>/permission` works
      for a caller without push access and when `<login>` is an App's
      `<slug>[bot]`, or fails in a way the script can tell from "no access"
- [ ] 0.5 The GitHub login of the last person to commit to a file can be
      found from the repository's commits on GitHub, such as the
      `author.login` that `gh api repos/<owner>/<repo>/commits?path=<file>`
      returns, or the script must skip that candidate
- [ ] 0.6 Record, once igor PR #216 gives it, the form of the fixed
      marker on igor's handback comments on GitHub and on Linear, a marker that no text the
      Igor quotes from its item can produce, by which the answer session
      tells a handback from the Igor's other comments. On GitHub and on
      Linear, *A handback is an Igor's comment holding igor's marker*
      waits on it
- [ ] 0.7 How the script can learn which login a post goes out as, when the
      agent posts through the github-app skill's script
- [ ] 0.8 Whether the script can find the approver of the pull request that
      added a decision, from a spec or decision record file through blame, the
      commit and its pull request's reviews
- [ ] 0.9 How the script tells a session with a person in it from a
      headless run, such as an Igor worker or `claude -p`, and whether a
      headless session that is not an Igor worker can post. The script
      reads from `IGOR_RUN` whether it runs in an Igor's run and whether
      that run is a worker's or the Igor's own; once igor builds it, check
      that igor sets `IGOR_RUN` as igor PR #216 specifies
- [ ] 0.10 Whether the agent can open, and write in, a repository's private
      security advisory, and what access that needs
- [ ] 0.11 GitHub's API gives a comment's or review's text and author
      (inquisitor spec: *The log command takes answered_by from the linked
      comment*). Measured 2026-11-04 for an issue comment's author only: GraphQL's
      `IssueComment` has `author { login }`. Measured 2026-11-23 for an
      App's issue comment: GraphQL gives `author { __typename: "Bot",
      login: "<slug>" }`, without `[bot]`, and REST's `user.login` gives
      `<slug>[bot]`; task 0.21 still checks that no account can take on
      that form. If a review or review comment has no author, that
      requirement needs another source for `answered_by` before it is
      built. Not measured: a review and a
      review comment, for which GitHub documents the same `author` through
      GraphQL's `Comment` interface. The task also checks that
      re-requesting a review adds a new `review_requested` timeline
      event, by which *An item that asks the person something is shown
      once* dates a request. If it does not, a request counts as made
      when a poll first finds it pending. A review re-requested while the
      first request is still pending then keeps that first date, before
      the answers, and is not shown as an item question
- [x] 0.12 Whether an Igor's worker can run this skill, with a lore clone
      and `inquisitor.json` in reach. It can't, and by the specs of igor PRs #174
      and #175 it still can't once they land, though neither is built to
      check. The implementation builds
      everything except Igor-worker mode, which waits for what igor issue
      #247 lists
- [ ] 0.13 Whether GitHub lets a security advisory's private-fork pull
      request be merged before the advisory is published. Until it
      shows the merge waits, fork commit messages describe the weakness
      only on the word of the person who will publish the advisory
- [ ] 0.14 Whether an Igor worker's `gh` can post, from a login stored in
      the home directory igor gives it rather than in its environment;
      if it can, the login is a breach to report to igor
- [ ] 0.15 That a conditional request answered `304`, sent with the
      person's `gh` login, does not count against the rate limit, as
      GitHub documents (answer-session spec: *The poll reads every GitHub
      question source*). If it does count, the `ETag`s save none of the
      limit, and a person with many subscriptions meets the rate-limit
      wait more often, with their agents' `gh` calls refused too until
      the reset; the repository's owner then decides whether the poll
      changes
- [ ] 0.16 How the answer session finds, on Linear with the person's key,
      mentions of the person and of the relay, and the line each is on,
      which tells whether it is a tag line, and replies to a relay
      comment, in a subscribed team; that it can post a comment as the
      linear-app identity with a host command and learn the comment's URL;
      that the identity can edit its own comment; and that Linear marks a
      comment's author as an app user in a form no person's account can
      take on. If any fails, Linear
      stays off and the README says so. The task also finds whether the
      person's key can read when an issue was assigned, which *An item
      that asks the person something is shown once* compares with when
      the item's questions were answered. If it cannot, Linear stays on,
      and an assignment counts as made when a poll first finds it, so one
      first found after those answers is shown as an item question. Measured 2026-11-19 as an app
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
      of the answer session's person by user id, and a reply to a
      message of that person's relay, and edit
      its own message; that Discord marks the author of a bot's or a
      webhook's message in a form no person's account can take on; and
      that a relay whose `check` reports
      `messageContent` `true` reads a message that doesn't mention the bot.
      If any fails, Discord stays off and the README says so. Measured
      2026-11-19 in a test thread: the identity reads a channel's history
      and a thread's, a reply holds a `message_reference` to its message,
      the identity edits its own message and, as *An automatic post is
      deleted when another relay post came first* needs, deletes it, and
      a bot's message has `author.bot` `true`. Not measured: a mention of the person's user
      id, a webhook's message, and the Message Content read
- [ ] 0.18 That a command the mod runs with `$.process.run` reaches no
      `PreToolUse` hook, so no post hook, on GitHub, Linear or Discord,
      sees a relay post. If a hook does
      see it, record it and stop for the repository's owner
- [ ] 0.19 That a mod's timers keep polling every 60 seconds and
      refreshing the lock every 30 seconds while its session is idle or
      has no terminal attached, as when the Claude app starts it from its
      list of sessions. If they stop, record that and pause until the
      repository's owner decides: a live session's lock would go stale and another
      session would take it without asking
- [ ] 0.20 How setup checks, on each surface, that a relay identity can
      post in a given channel. On GitHub, setup reads the App
      installation's access to each subscribed repository itself, since
      github-app's `check` reads only the identity's configured
      repositories. On Linear and Discord, record whether the skill's
      check reads a team's or channel's permission or setup must. Where no
      check can, setup runs the skill's own check only, and a post a
      channel refuses later turns that channel off
- [ ] 0.21 Whether GitHub's API reports, for a comment, the slug of the
      GitHub App that wrote it, in a form no account can take on, such as
      the author login `<slug>[bot]` with type `Bot`, or
      `performed_via_github_app`. These are not built until it is
      measured:
      - on GitHub, the answer-session's *Relay posts start with a
        reserved prefix*;
      - on GitHub, the question state *The thread is the durable record
        of an answer* reads from relay posts, which needs relay posts
        recognised;
      - task 6.4's GitHub relaying, which is every requirement that posts
        through the relay on GitHub and needs that question state;
      - on GitHub, each rule that tells a bot account's comment by its
        `[bot]` author login: *A
        handback is an Igor's comment holding igor's marker*, *An
        agent's question comes from a bot account or a log file*, *A
        relayed question is a person's question*, and, in the inquisitor
        spec, *An agent logs a bot's comment only as input* and the rule of
        *The log command takes answered_by from the linked comment* that
        writes `authority: input` for a bot's comment;
      - on GitHub, the rules that must tell whether an agent or a person
        asked:
        *Whom a message reaches is set by its mentions*, *Each item of a
        bot's message reaches the person its tag line mentions*, *A bot's
        message to a relay reaches the relay's person*, the
        automatic `Inquisitor: ` reply of *A clear filter 2 to 4 failure
        gets its fixed reply by itself*, and every miss a decline logs (*A decline for
        the inquisitor logs a miss once it takes effect*).

      The three GitHub replies task 0.31 names wait on task 0.31 as well,
      since their miss files are named by the reply's `node_id`.

      If GitHub reports which App wrote a comment, the rules above are
      built as the spec states them; if not,
      the repository's owner decides what to build
- [ ] 0.23 That the URL an asking agent records as `asked_in`, and the
      handback comment URL an Igor records, equals character for character
      the URL the answer session builds from what it polls, on GitHub,
      Linear and Discord. Compare an issue comment's URL with a pull
      request comment's, `discord.com` with `discordapp.com`, and a Linear URL before and
      after the issue is renamed. Where they differ, define one canonical
      form, which both sides write and compare. Record too whether Linear
      and Discord return a posted question's words unchanged. Whether they
      do decides whether a question asked there matches its logged file
      by hash (the inquisitor spec's *Among files with the same question,
      only the newest answer counts*), and whether task 0.28's lines are
      found. A miss file is named by its reply's id, so it does not
      depend on it. Measured 2026-11-19 on a test
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
      Not measured: every GitHub comparison, and an Igor's handback URL
- [ ] 0.25 How GitHub, Linear and Discord each report a relay post refused
      for its text, such as its length, against one refused for lack of
      permission. This is the mapping the answer-session spec's *A pending
      answer that no check returns waits for the person* uses
- [ ] 0.28 Post the lines `Inquisitor: a person must decide this
      (required by spec-trace).` and `Concerns: o/web` in a Linear comment
      and a Discord message, read each back as the answer session would,
      and record whether their words come back unchanged once markup is
      reduced. If not, record the form each surface returns, which the
      answer session then matches (answer-session spec: *A question with a
      person-required line gets no filter 2 to 4 reply*; *A concerns line
      settles what an agent's question concerns*)
- [ ] 0.29 Whether an Igor's host has Python and the inquisitor skill
      installed for the Igor's own process, not only for its workers, so
      the Igor can run `branch-search` (inquisitor spec: *The Igor reads
      questions branches with the script*), and whether the Igor's App
      token can read a collaborator's permission. Without the first, the
      call fails and the worker's search names each questions branch as
      not searched; without the second, every hit is `input`
- [ ] 0.30 That `CLAUDE_CODE_NO_FLICKER=1 claude --name Answers '/answer'`
      starts Claude Code named `Answers`, in its fullscreen layout, and
      runs `/answer`, with the tool restriction task 0.34 finds added
      (answer-session spec: *Setup installs the answer
      command*). If a part fails, the requirement's command line is
      changed to what works before it is built
- [ ] 0.31 That GitHub's REST and GraphQL APIs both return a comment's
      `node_id` (GraphQL's `id`), that it is present for every kind of
      comment the answer session replies to (an issue comment, a pull
      request comment and a review comment), and that an edit leaves it
      unchanged (inquisitor spec: *Every miss file is named by one hash*).
      Until it is measured, no miss file is named by a GitHub reply's
      `node_id`. So three GitHub replies to an agent's question are not
      built: the reply a person's decline posts, the automatic
      `Inquisitor: ` reply, and filter 1's `Recorded answer: ` reply. If a check fails,
      the GitHub id that names a miss file is changed to one the
      measurement shows passes these three checks, before miss files are
      named on GitHub
- [ ] 0.33 That the Discord bot token shape in *The credential patterns are
      a closed list of token shapes* matches the relay's real token: run
      the pattern against the token discord-bot holds, printing only
      whether it matched and each part's length, never the token. If it
      does not match, the pattern is changed to the shape measured
- [ ] 0.34 How Claude Code restricts a session's tools so that its model
      has only its conversation, `propose_reply`, `record_verdict` and
      Read, Grep and Glob: permission settings, a startup option such as
      `--allowedTools`, or a mod's own control. Record whether Claude Code
      enforces it itself rather than through a hook, and what the `answer`
      command must add to start a session so restricted. Until then, *The
      session's model has no shell, no writing tool and no web fetch* and
      the `answer` command's line in
      *Setup installs the answer command* are not built (answer-session
      spec). If no control Claude Code enforces exists, the design falls
      back to hooks and the change cannot be built as written: record it
      and stop for the repository's owner
- [ ] 0.35 Whether the person's Linear key reads the GitHub links that
      Linear's GitHub integration puts on a team's issues. If not, setup's
      guess for a Linear team names nothing, and setup asks the person
      (answer-session spec: *Setup guesses the repositories a Linear or
      Discord channel concerns*).
- [ ] 0.37 That a mod can submit a prompt of its own into its session's
      conversation while the person is not typing, have the model answer
      it with a tool call, unattended, and detect when the model's reply in
      that turn has ended. If it cannot,
      record it and stop building the mod: the answer session is then
      designed as a standalone UI, not a Claude Code mod, and prototyped
      for the owner's approval. If it can, also list every first character
      on which the prompt box runs a submitted prompt as a command;
      *propose_reply refuses a draft the prompt box would run* refuses each
- [ ] 0.38 How the answer session tells, with the person's Linear key,
      that a Linear app user is an Igor's, in a form no other app user can
      take on, as the `igor-` slug tells an Igor's App on GitHub: for
      example by the user id of the Linear identity an Igor is configured
      with, or by a name igor requires of its Linear app. Task 0.16
      measured that Linear marks an app user's comment, with `user.app`
      `true`; which app user is an Igor's is not measured. On Linear, *A handback is an Igor's comment holding igor's
      marker* is built only once this is measured. If
      no such form exists, no Linear comment is a handback for good
- [ ] 0.39 Whether Claude Code puts an `agentId` on a subagent's or a
      forked conversation's call to a mod's tool. If not, nothing refuses
      such a call: its `propose_reply` draft still lands only in the
      prompt box, and its `record_verdict` call can still only pick among
      the actions the code offers (answer-session spec: *Claude's draft
      goes to the prompt box, never to a post*)

## 1. Shared post reader

- [ ] 1.1 Move prose's body reader, which finds a `gh` or GitHub MCP
      post's body, into `.agents/lib/gh-shell/`, beside the command
      splitter and gh flag tables already there, and build the `gh-post` rules on it. Each
      skill calls it from a thin script, and its behaviour changes only
      as task 1.3 lists
- [ ] 1.2 prose's tests pass unchanged, except as task 1.3 allows; add the
      library's own tests beside it,
      each tagged `@scenario gh-post: <Scenario name>` for the `gh-post`
      spec's scenario it checks
- [ ] 1.3 The library also handles the following, with tests for each in
      prose's and the library's tests. prose's existing tests pass
      unchanged, except any test expecting a case of the first item below
      to be blocked: change it to expect the case let through. Only that
      item lets through what prose's hook blocks today; prose's hook
      ignores `gh api`, so the `gh api` items are new checks for it.
      - It reads a call of github-app's script with the library's
        `app_command`, `app_assignments` and `forget_scripts`, as the
        `gh-post` spec's *The reader reads posts sent through the
        github-app skill and gh api* says, and judges a line holding such a call exactly as the same
        line with the command made directly; prose's reader blocks such
        posts today.
      - It counts a `gh api` call as mentioning a gh post verb only when
        the call can write, as the `gh-post` spec's *A gh api call writes
        by its method, fields, input or a mutation* says: `-X` or
        `--method` in each form gh accepts and in any case, fields and
        `--input` with and without `--method GET`, the
        `X-HTTP-Method-Override` header, a GraphQL mutation, a query from
        standard input or a file, and a method or endpoint the shell
        builds, each with a test, and a read piped into `python3 -c`
        passing. Check each case against `gh api --help` and gh's
        behaviour, not only this list.
      - It reads an unquoted `--body` or `-b` of one word holding no `$`,
        backtick, `*`, `?`, `[`, `{`, `~` or `\`, such as `--body hi`,
        `-bhi` or `--body=hi`, as that word, as prose's reader does
        today.
      - It reads `gh api` comment bodies given by `-f body=`,
        `--raw-field body=`, `-F body=` or `--field body=` (with or
        without `@<file>`), or by `--input`, a review's
        `comments[][body]` fields, and every `body` argument of the
        GraphQL mutations that post text to an issue or pull request. A
        field taken from a file, by `@<file>` or `--input`, is readable
        only when that write is the whole command line. A write to an
        endpoint other than an issue's or pull request's, or a mutation
        off that list, is no post.
      - It blocks as unreadable a `gh api` write to an endpoint or
        mutation it reads whose body it can't read, a GraphQL query it
        can't read or parse, and a review whose comments it can't read.
      - It keeps prose's reader's block, as unreadable, on a command
        other than a data command that names `gh` in its arguments, such
        as `sh -c`, on a line that mentions a gh post verb (gh-post spec:
        *A line whose simple commands send no text is no post*), and on
        piped input as *Input to a no-post line reaches only data
        commands* says.

## 2. The script

- [ ] 2.1 `.agents/skills/inquisitor/scripts/inquisitor.py vet` (first
      call): `--questions`, and `--post` taking a post's body;
      prints the filters and filter 1's search results, and issues a token
- [ ] 2.2 `vet --pass <token> --verdicts <file>` (second call): the four
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
- [ ] 2.3 Filter 1's search. Items marked igor's are applied by
      `igor lore-search`, which igor PR #216 builds.
      - It searches decision documents, issues through `gh`, the
        repository's `questions` branch, and configured lore clones'
        entries and `questions` branch. It fetches each `questions`
        branch before searching it, and reads every branch it searches
        with `git show`, checking none out. Task 7.0 adds igor's scribe's
        decision records; until then the output names them as not
        searched.
      - It matches as plain text and ranks by terms matched, with a cap
        it reports.
      - During an Igor's run it searches lore only through `igor
        lore-search`, passing the question on standard input, or the
        other way igor PR #216 gives the command if its task 4.5 finds a
        worker cannot.
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
- [ ] 2.3b `branch-search`, which searches one repository's `questions`
      branch and prints its hits as JSON, each labelled by task 2.3's
      checks (inquisitor spec: *The script searches a questions branch and
      prints labelled hits as JSON*). The JSON is the contract with igor,
      whose Igor runs the command for its worker: a test compares the
      output for a fixed branch with a stored copy, field for field, so a
      change to the format fails until the stored copy is changed, which
      waits for igor's agreement
- [ ] 2.3c `miss-check`, which takes a repository, a surface and a reply's
      id and says whether that repository's questions branch holds the
      miss file that backs that `Inquisitor: ` reply (inquisitor spec: *The
      script checks whether a miss file backs a reply*). Its JSON is part
      of the contract with igor, under task 2.3b's test
- [ ] 2.3d `file-answer`, which takes a repository and a questions-branch
      file name's date and 6-hex-digit suffix and prints only that file's answer, or `null` (inquisitor
      spec: *The script prints one questions-branch file's answer*). Its
      JSON is part of the contract with
      igor, under task 2.3b's test
- [ ] 2.3e `search`, which runs filter 1 alone for the answer session,
      reading only the session's clones and their repositories' issues,
      and prints its results as JSON
      with no token or record (inquisitor spec: *The search command runs
      filter 1 alone for the answer session*; *The search command takes
      its question as the first call does*)
- [ ] 2.4 The `log` command, writing one file per question or miss in the
      format of *A log file and a miss file have one format*.
      - `authority` is `decision` or `input`. An agent's own choice
        under filter 3 or 4 gets no file.
      - Every miss file is `misses/<hash>.md` (inquisitor spec: *Every
        miss file is named by one hash*), and nothing is pushed where the
        name is taken. A hash-only miss file, one with empty frontmatter
        and no body, is written only through an option the answer session
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
        confirms sending the file somewhere more visible. Since a file
        is as private as the more private of its branch's repository
        and its `asked_from`, it is then read at that branch's
        visibility (inquisitor spec: *The answerer's
        confirmation can send a record somewhere more visible*); on a log or
        miss file the answer session writes, it is the `asked_from` the
        answer session passes to the `log` command (answer-session spec: *A miss records who judged it and where it
        was asked from*).
      - A handled file holds only `handled`, the day in UTC, and
        `closes`, the closed file's name or, for a question with a
        category, that name's SHA-256, with no body. It is
        written only through the command's session option, which only the
        answer session passes; a `handled` or `closes` key, or a hash-only
        miss file, is refused without that option.
      - Each answer is written in quote lines:
        - with a github.com `answer_link`, read from the linked comment
          and recorded word for word;
        - with a Linear or Discord `answer_link`, refused without the
          session option; with it, the answer recorded as given and the
          link never fetched, the link written only where the questions
          branch's repository is private and left out elsewhere;
        - any other answer a person gave, without an `answer_link`, in
          their own words as given; without the session option, as `input`
          unless its `answered_by` is the login of the person running the
          session, which for `decision` also needs write access (inquisitor spec: *The log
          command makes an unlinked answer a decision only for the
          session's person*).
      - A file is pushed to the `questions` branch of the repository the
        question is about, or of the team's lore repository for a
        question about a collective. Every commit to a questions branch,
        `cite`'s included, is written with git's plumbing (`hash-object`,
        `mktree`, `commit-tree`) and pushed by its commit id, with no
        checkout, so no HEAD moves (inquisitor spec: *A question is pushed
        to the questions branch of what it concerns*). The command
        fetches and pushes again when rejected because the branch moved,
        and keeps the file pending, pushing it with the next file for
        that branch, when it cannot push otherwise; called with its
        session option, which the answer session passes on every push, it
        keeps no pending copy and reports why the push failed.
      - A picker question's file is pushed once answered, and a record
        more visible than its source only once the person answering
        confirmed the warning, then with no link into the source.
      - The secret scan, over raw markdown with link targets included, and
        the visibility refusal.
      - It refuses, saying why, a question holding a line that is exactly
        `## Rephrased question`, `## Discussion` or `## Answer`.
      - `misses`, listing the misses by filter for a review.
- [ ] 2.4b `cite`, pushing a citation file in the format of *A citation
      file has one format* (`entry` and `date`, no `run`) once to the
      `questions` branch of the lore repository holding the entry, when
      filter 1 stops a question with a lore entry, or when the person in
      the answer session cites an `active` entry in scope by naming it in
      a reason 2 decline with filter 1. Its commit names no person. It sends none for a question with a category,
      none where *A lore entry that stops a question gets a citation
      file* bars it by visibility, and none for a cited entry not `active` or out
      of scope. A push it cannot make stays pending as `log`'s does,
      except when called with the session option `log` also takes,
      which the answer session passes (inquisitor spec: *The answer
      session's files are never kept pending*). During an Igor's run it pushes nothing; igor PR #216's
      *An Igor publishes the citations its worker reports* covers it
- [ ] 2.5 The question finder for posts, one function the post hook also
      calls, finding questions in a post's body, with an
      open-questions section begun only by a label that names questions
      or a deferral label
- [ ] 2.6 `tag`, choosing whom a post's question tags: the first candidate
      with write access, starting with the approver of the related earlier
      decision the second call recorded; else the login configured for
      the person running the session, if it equals the account `gh` is
      logged in as. With a person in the session:
      - no login configured: ask through the picker instead;
      - the login has no write access: tag no one;
      - it has write access: tag it when the post goes out as someone
        else; when it goes out as that login, or the script can't tell,
        ask through the picker instead.

      A session with no person in it tags the login only when it has
      write access and the post goes out as someone else, and otherwise
      tags no one. The tag, or when tagging no one the fixed line of *A
      question no candidate can decide turns to the session's login*, goes
      on the question's tag line, which the
      question's hash leaves out (inquisitor spec: *A tag line names the
      person a posted question tags*; *A question's text and hash are
      built one way*)
- [ ] 2.7 `lore`, opening a lore pull request, or a promotion from the
      `questions` branch, or refusing it by visibility or by an id outside
      igor's id rule. During an Igor's run it opens nothing and writes the
      entry into the run's report for the Igor to propose, as igor PR
      #216 is asked to
- [ ] 2.8 A test pinned to an igor commit that checks the lore entry
      format `lore` copies: the `entries/<id>.md` path, the id pattern and
      the frontmatter fields igor's lore store requires (inquisitor spec:
      *A proposed lore entry's path, fields and id follow igor's rules*)
- [ ] 2.9 The `log` command's input file, kept and refused as the two
      calls' files are (inquisitor spec: *The log command takes its input
      in a private file*)

## 3. Hooks

- [ ] 3.1 `scripts/check-ask.sh`: `PreToolUse` on `AskUserQuestion` (Claude Code
      only), checking verdicts, blocking with exit 2, and failing open,
      including when it can't read its records
- [ ] 3.2 `scripts/check-post.sh`: `PreToolUse` on Bash and the GitHub MCP
      tools, through `.agents/lib/gh-shell/`. It blocks a post in which a
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
      pass the same filters*)
- [ ] 3.3 `hook.json` with both hooks, `"default": "enabled"`

## 4. Tests

- [ ] 4.1 `scripts/test_inquisitor.py`, standard library only, each test tagged
      `@scenario inquisitor: <Scenario name>` for the scenario it checks
- [ ] 4.2 Every scenario but the expected gaps has a tagged test:
      `spec_trace.py report --include-changes` marks only the expected
      gaps `none`. A scenario about what the agent does is tagged on a
      test that checks SKILL.md states the rule. An expected gap is a
      scenario only igor's unbuilt work can make pass, or one whose rule
      waits on a measuring task such as 0.21 or 0.31. It gets no test, not even a skipped
      one, and is listed by name under this task
- [ ] 4.3 Once igor provides `igor lore-search` and a role's `commands`
      can list the skill's script, build Igor-worker mode, write a tagged
      test for each expected gap, and remove it from task 4.2's list;
      do the same for a gap whose rule waited on a measuring task, once
      that task is measured and the rule built.
      The archive waits for this, because archiving moves the scenarios
      under `openspec/specs/`, where spec-trace's CI fails on an untagged
      scenario (task 7.0)

## 5. Docs and registration

- [ ] 5.1 `SKILL.md`: the filters, the two calls, writing a question at the
      privacy of what it concerns, posting no more publicly than that,
      that the person is accountable for what is posted as their relay
      and where, since no hook checks where a relay post goes
      (answer-session spec: *The person answers for what their relay posts*), the
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
      agent can print it and post `User says: ` (answer-session spec:
      *The README warns that a relay's token can be printed*).
- [ ] 5.3 A row in the README's skills table, and `inquisitor` in its list of
      skills that turn on a hook
- [ ] 5.4 `manage-skills` installs it and wires its hooks: check with
      `skills.py install inquisitor` and `skills.py doctor`
- [ ] 5.5 github-app's `SKILL.md`: every example that runs `python3 $G`
      sets `G` in the same command, or writes the script's full path, so
      the post hooks don't block it
- [ ] 5.6 `README.md` says that setup suggests a rule blocking force
      pushes to a `questions` branch and its deletion, which only an admin
      can set; that without it anyone with write access can rewrite or
      delete the branch; and that with it a writer can still push a handled
      file that hides a question from the person (the inquisitor decision record's constraint on guarding a
      `questions` branch); and that spec-trace's workflow skips pushes to
      the `questions` branch (task 5.9), which holds none of the project's files; a
      repository owner must make any other workflow that checks those
      files on push skip that branch too, or it fails there
- [ ] 5.7 Change bug-hunter's SKILL.md so that Step 9 runs each
      recommendation in its report through the inquisitor skill's four
      filters before asking about it: a root cause, a finding too large
      for the change, anything left unresolved when the run aborted, and
      a property from the hunt (Step 3) worth keeping as a permanent
      guard. The builder sets when each kind passes a filter, and those
      conditions are reviewed with the implementation
- [ ] 5.8 Add to bug-hunter's SKILL.md the inquisitor spec's rules for a
      weakness whose advisory is unpublished. Task 0.13 measures whether
      GitHub can merge the advisory's private-fork pull request before
      publication. When it shows the merge waits, or the advisory's
      publisher says it does, the regression test lands in the private
      fork, and fork commit messages may describe the weakness. Without
      either, the test lands nowhere until publication, and then on a
      public branch (*Before publication, a weakness's test and
      description reach only the private fork*). Commit messages on a
      public branch never describe the weakness before publication (*A
      weakness is not described in public text before its advisory is
      published*)
- [ ] 5.9 Bring shared-skills PR #101's commit 7b6ffa3 (branch
      `spec-trace-skip-questions`) onto this branch, by cherry-pick or, if
      spec-trace's README or SKILL.md has changed since, by reapplying it:
      the workflow template in spec-trace's README skips pushes to
      `questions`, and the README and SKILL.md say why. Once this change merges, close #101 as included

## 6. The answer session

- [ ] 6.0 Build on discord-bot as shared-skills PR #1 merged it.
      The Discord relay posts with no header option and with mention
      rewriting on, because discord-bot always posts that way. discord-bot's `read` drops each message's
      `author.bot` and reply reference, which the answer session needs to
      tell a bot's message and a reply to a relay post, as task 0.17 found
      on 2026-11-19; this task changes `read` to return both
- [ ] 6.1 The mod, built into the inquisitor skill from the tag
      `answer-session-ui-approved-v0.1-33` on shared-skills (build v0.1-33,
      commit fc3c35f), the only build the mod
      starts from. It descends
      from v0.1-30 (`answer-session-ui-approved-v0.1-30`, commit c9c6eb5)
      and contains all of it, including declining and the list of
      questions answered or handled for the person. The mod takes its
      questions from task 6.3's polls instead of the prototype's made-up
      ones. Four rules decide what is built:
      - (a) Keep the approved screens' layout and interaction: the band, which is the mod's panel above the prompt box,
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
          in its thread that the answer session's four question sources name is a new question, where the
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
        - agreeing to a recorded answer as a reason 2 decline with filter
          1, writing no answer file, where the
          prototype treats it as its own path and logs the recorded answer
          in a new file;
        - the question on screen kept in the state folder, not the mod's
          `$.store`, so a restarted session opens on it.
      - (c) A screen the spec needs that v0.1-33 lacks is designed in this
        task from the prototype's existing patterns, in no new visual
        style, with no prototype round of its own: setup, the lock
        message, where an answer will be recorded and the warning when
        that place is more visible than the thread, the pick of another
        place, a post's failure, discord-bot's warnings, why no miss was
        logged, a channel that is off, the rate-limit notice, and the
        pending list of answers not yet relayed, which reuses the
        approved queue's screens
      - (d) The screens v0.1-33 added to v0.1-30 are taken as that build
        has them, each in the one place it shows them: the thread's
        replies since the question, including when the asker withdraws
        it; filter 1's recorded answer shown with the
        question, a questions-branch question included; and the wording
        and placement of the notice for a post held back because a reply
        arrived
- [ ] 6.2 The `answer_session` section of `inquisitor.json`, and setup:
      the person's GitHub login, without which it does not complete; the
      candidates; each relay check; saving the file with the person's
      own keys kept; a failed identity's surface or a failed channel left
      off and checked again at each opening; the Linear key in the
      keychain; each Linear or Discord channel's `repos`, guessed from its
      history (answer-session spec: *Setup guesses the repositories a
      Linear or Discord channel concerns*); `~/.local/bin/answer`; the check that each subscribed or
      lore repository's `questions` branch takes the person's direct push,
      and the suggested rule blocking its force pushes and deletion;
      and the optional step that creates a lore repository, its clone and its
      configuration entry
- [ ] 6.3 Polling: the four question sources (answer-session spec: *A
      question asked of the person comes from one of four sources*), only
      while open, the catch-up on opening, 60 seconds, poll positions,
      `ETag`s and the wait after a rate-limit refusal (*The poll reads
      every GitHub question source*), and fetching every subscribed
      repository's questions branch and every configured lore
      repository's questions and default branches at each poll, and a
      subscribed repository's default branch when filter 1 is about to
      check a question placed in it. The `search` command reads only
      branches fetched so, and issues only
      of these repositories (answer-session spec: *The answer session's
      filter 1 reads only subscribed and lore repositories*)
- [ ] 6.4 Relaying: posts with the four reserved prefixes through the
      relay identity's skill as host commands, or on Linear the session's own
      HTTP request, carrying the token linear-app's `token` command prints,
      held only in memory and never in a command's arguments, the `Re: ` line on GitHub
      and Linear posts, post ids, editing in place, the thread read before
      a question is shown and before each post, the thread read after each
      automatic post and that post deleted when another relay post
      came first (answer-session spec: *An automatic post is deleted
      when another relay post came first*), the preview showing where
      the answer will be recorded; the person's pick of another place in
      it (answer-session spec: *The person can pick another place in the
      preview*); for an Igor's question on a more private repository, the
      preview's line saying the answer also reaches the run on its item
      (answer-session spec: *The preview says when an answer also reaches
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
      (answer-session spec: *The model's judgements reach the session's
      code only through record_verdict*), and the rephrased answer's
      post. SKILL.md tells an agent
      that records an answer from a relay post to log its rephrasing and
      summary
- [ ] 6.6a The session's tool restriction, as task 0.34 found it: the
      model gets only its conversation, `propose_reply`, `record_verdict`
      and Read, Grep and Glob, and the answer session opens in no other
      session
      (answer-session spec: *The session's model has no shell, no writing
      tool and no web fetch*)
- [ ] 6.7 prose's SKILL.md says that a relay post gets
      no prose pass, because it is the person's words, and an automatic
      post none, because its text is fixed
- [ ] 6.8 Tests, each tagged `@scenario answer-session: <Scenario name>`,
      and the README's section on the answer session: setup, the `answer`
      command, what to do when a relay check fails, and that no post but
      the answer session's starts with a reserved prefix
- [x] 6.9 The repository's owner's approval, by use, of the screens prototyped after the
      first approved build: declining a question, the choice of filter
      under "the inquisitor should have handled it" (reason 2) and the
      exact post shown before it goes out, and the list of questions answered and handled for
      the person. Done: build v0.1-30, tagged
      `answer-session-ui-approved-v0.1-30` on shared-skills
- [ ] 6.10 The answer session's handling of incoming questions, SKILL.md's
      guidance on its automatic replies, and, for each scenario this task
      builds, a test tagged `@scenario <capability>: <Scenario name>`.
      - Built in this task:
        - filter 1 on every incoming question not placed `other`, except an item question, run through the script's
          `search` command, and the `Recorded answer: ` post;
        - placing a question asked on Linear or Discord (answer-session
          spec: *A Linear or Discord question is placed by what it
          concerns*; *A channel's repositories place its questions*), and placing an agent's question by its concerns line
          (*A concerns line settles what an agent's question concerns*);
        - filters 2 to 4 and the three fixed `Inquisitor: ` texts, and a
          question carrying a person-required line always shown to the
          person unless filter 1 answers it, the line found by its fixed
          wording after markup is reduced;
        - declining with its two reasons, and reason 2's posts;
        - the misses on the questions branch, none for reason 1, for
          a person's question or for an item question, and a miss against filter 1
          for an agent's question the answer session answers by itself;
        - a `Recorded answer: ` post the answer session makes without
          the person, but no `Inquisitor: ` post, on a relayed question:
          one a bot account posted starting `User says: ` or
          `User asks: ` (answer-session: *A relayed question is a
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
- [ ] 6.11 Decide at implementation, and when each choice is made, add
      it to the spec as a requirement with a scenario or, if no test can
      check it, to the answer-session decision record as an entry with
      evidence: how a question's options, the choices it offers
      with what each would change, are parsed from its thread; and how the
      session handles an asker's reply that revises those options. Agreeing
      to a shown recorded answer is already decided, as are agreeing to a
      suggested verdict and citing a lore entry (answer-session spec:
      *Filters 2 to 4 only suggest a verdict on other questions*; *A
      person's cite of an active entry in scope pushes a citation file*)
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
      `openspec/specs/answer-session/decisions.md` and
      `openspec/specs/gh-post/decisions.md`, and archiving leaves them as
      they are. Write no `.agents/skills/inquisitor/DECISIONS.md`. Point
      each decision record's link to tasks.md at the archived tasks.md
