## Before gate one is approved

- [x] G.1 The repository's owner approves the prototype build covering thread replies and
      the recorded answer shown beside the question, and task 6.1's rule
      (d) names its tag. Done: build v0.1-33, tagged
      `answer-session-ui-approved-v0.1-33`

Gate two: the tasks below follow on this branch once the repository's owner approves the
spec.

## 0. Measure before building

Record each result that a requirement rests on as Evidence in its
capability's decision record, and the rest in the design.md section listed
for its task:

- *What the hook relies on, not yet measured*: 0.1 to 0.3;
- *Configuration* and *Facts measured before building*: 0.4;
- *Facts measured before building*: 0.5, 0.7 to 0.14, 0.33 and 0.35;
- *igor's handback marker*: 0.6 and 0.38;
- *Facts the answer session relies on*: 0.15 to 0.21, 0.23, 0.25, 0.26,
  0.28, 0.30, 0.31, 0.34 and 0.37;
- *What igor must provide*: 0.29.

Record there too any result that contradicts what design.md assumed. In
the same commit, rewrite each requirement and scenario that waits on that
task to its result: drop its wait, and drop or restate a scenario written
for before the result, such as *Nothing is relayed on GitHub before task
0.21*. spec-trace fails CI on a scenario no test tags, and no test can
check such a scenario once the task is done. Numbers 0.22, 0.24, 0.27, 0.32 and
0.36 have no task, so that the other tasks keep their numbers.

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
- [ ] 0.6 Record, once igor PR #216 gives it, the form of the fixed
      marker on igor's handback comments on GitHub and on Linear, a marker that no text the
      Igor quotes from its item can produce, by which the answer session
      tells a handback from the Igor's other comments (design.md: *igor's
      handback marker*)
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
      that igor sets `IGOR_RUN` as igor PR #216 specifies (design.md: *The
      script tells an Igor's run by `IGOR_RUN`*)
- [ ] 0.10 Whether the agent can open, and write in, a repository's private
      security advisory, and what access that needs
- [ ] 0.11 GitHub's API gives a comment's or review's text and author
      (inquisitor spec: *The log command takes answered_by from the linked
      comment*). Measured 2026-11-04 for an issue comment's author only: GraphQL's
      `IssueComment` has `author { login }`. Not measured: a review and a
      review comment, for which GitHub documents the same `author` through
      GraphQL's `Comment` interface
- [x] 0.12 Whether an Igor's worker can run this skill, with a lore clone
      and `inquisitor.json` in reach. It can't, nor once igor PRs #174 and
      #175 land, by their specs, unchecked since neither is built
      (design.md: *What task 0.12 measured*). The implementation builds
      everything except Igor-worker mode, which waits for design.md's
      *What igor must provide*
- [ ] 0.13 Whether GitHub lets a security advisory's private-fork pull
      request be merged before the advisory is published (design.md:
      *Weaknesses stay out of public text until disclosure*). Until it
      shows the merge waits, fork commit messages describe the weakness
      only on the word of the person who will publish the advisory
- [ ] 0.14 Whether an Igor worker's `gh` can post, from a login stored in
      the home directory igor gives it rather than in its environment;
      if it can, the login is a breach to report to igor (design.md:
      *An Igor worker asks only through its Igor*)
- [ ] 0.15 Which reasons GitHub's notifications endpoint gives, read with
      the person's `gh` login, for a mention, a review request, an
      assignment and a later comment in a thread the person was mentioned
      in, and that a conditional request answered `304` does not count
      against the rate limit. Until then the answer session also reads,
      since its poll position, each subscribed repository's new issues and
      pull requests, their comments, reviews and review-thread comments,
      and the review requests and assignments naming the person
- [ ] 0.16 How the answer session finds, on Linear with the person's key,
      mentions of the person and of the relay, and replies to a relay
      comment, in a subscribed team; that it can post a comment as the
      linear-app identity with a host command and learn the comment's URL;
      that the identity can edit its own comment; and that Linear marks a
      comment's author as an app user in a form no person's account can
      take on. If any fails, Linear
      stays off and the README says so. Measured 2026-11-19 as an app
      identity on a test issue: a host command's GraphQL `commentCreate` returns the
      comment's `id` and `url`, while the Linear MCP's tools return only
      the `id`; the identity edits its own comment; a reply holds its
      parent's id; and an app user's comment has `user.app` `true` and a
      null `botActor`, the 5 test comments among the team's 77, the other
      72 having `user.app` `false`. Not measured: mentions of the person or the relay,
      anything read with the person's key, and that no person's account
      can have `user.app` `true`, which only the schema's description says
- [ ] 0.17 That a `discord-bot` identity, as merged in shared-skills PR #1,
      can read a subscribed channel's history and threads, see a mention
      of the person's user id and a reply to the relay's message, and edit
      its own message; that Discord marks the author of a bot's or a
      webhook's message in a form no person's account can take on; and
      that a relay whose `check` reports
      `messageContent` `true` reads a message that doesn't mention the bot
      (design.md: *The Discord relay needs the Message Content intent*).
      If any fails, Discord stays off and the README says so. Measured
      2026-11-19 in a test thread: the identity reads a channel's history
      and a thread's, a reply holds a `message_reference` to its message,
      the identity edits its own message, and a bot's message has
      `author.bot` `true`. Not measured: a mention of the person's user
      id, a webhook's message, and the Message Content read
- [ ] 0.18 That a command the mod runs with `$.process.run` reaches no
      `PreToolUse` hook, so no post hook, on GitHub, Linear or Discord,
      sees a relay post (design.md:
      *A relay post gets no prose pass and no vetting*). If a hook does
      see it, record it and stop for the repository's owner
- [ ] 0.19 That a mod's timers keep polling every 60 seconds and
      refreshing the lock every 30 seconds while its session is idle or
      runs as a Claude Code background session, and how a session tells
      that it is one, so the lock can record it; a session that cannot
      tell counts as a foreground one (answer-session spec: *A Claude
      Code background session has no terminal attached*). If they stop,
      record it
      and stop for the repository's owner: a live session's lock would go stale and another
      session would take it without asking
- [ ] 0.20 How setup checks, on each surface, that a relay identity can
      post in a given channel. On GitHub, setup reads the App
      installation's access to each subscribed repository itself, since
      github-app's `check` reads only the identity's configured
      repositories. On Linear and Discord, record whether the skill's
      check reads a team's or channel's permission or setup must. Where no
      check can, setup runs the skill's own check only, and a post a
      channel refuses later turns that channel off (design.md: *A failed
      relay check turns off only its channel*)
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
      - on GitHub, each rule that reads a `[bot]` author login: *A
        handback is an Igor's comment holding igor's marker* and *An
        agent's question comes from a bot account or a log file*;
      - on GitHub, the rules that need to tell an agent's question:
        *Whom a message reaches is set by its mentions*, *A bot's message
        to a relay reaches the relay's person* and the
        automatic `Inquisitor: ` reply of *Filters 2 to 4 judge every
        incoming question*.

      The three GitHub replies task 0.31 names wait on task 0.31 as well,
      since their miss files are named by the reply's `node_id`.

      If GitHub reports which App wrote a comment, the rules above are
      built as the spec states them; if not,
      the repository's owner decides what to build
- [ ] 0.23 That the URL an asking agent records as `asked_in` (design.md:
      *A log file follows its thread message by exact link*), and the
      handback comment URL an Igor records (design.md: *Each Igor log file
      follows its own handback comment*), equals character for character
      the URL the answer session builds from what it polls, on GitHub,
      Linear and Discord. Compare an issue comment's URL with a pull
      request comment's, `html_url` with the notifications API's URL,
      `discord.com` with `discordapp.com`, and a Linear URL before and
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
- [ ] 0.26 With a mod logging the `agentId` of every call to a tool it
      registers, such as `propose_reply`, let Claude Code's forked side
      conversations, such as the one that guesses the next prompt, run,
      and record whether any of their calls arrives without an `agentId`.
      Record too whether a subagent's call carries one. For forks this
      decides nothing: `propose_reply` refuses a call carrying one and
      takes a call without one as the main conversation's (answer-session
      spec: *Claude's draft goes to the prompt box, never to a post*). If
      any arrives without one, record it in design.md's *Claude drafts a
      reply only into the prompt box*; the rule stands. A subagent's call
      that arrives without one is taken as the main conversation's, as
      the scenario *A subagent cannot call propose_reply* already says,
      and design.md's *Claude drafts a reply only into the prompt box*
      accepts that case as it accepts a fork's: the draft reaches only the
      prompt box, where the person sees it before anything is sent
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
      `node_id`. So three GitHub replies are not built: the person's
      decline that posts a reply, the automatic `Inquisitor: ` reply, and
      filter 1's `Recorded answer: ` reply to an agent's question. If a check fails,
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
      Read, Grep and Glob:
      permission settings, a startup option
      such as `--allowedTools`, or a mod's own control. Record whether
      Claude Code itself enforces it, not a hook, whether a mod can apply
      it to a session already running, and the exact option the `answer`
      command needs. Until then, *The session's model has no shell, no
      writing tool and no web fetch* and the `answer` command's line in
      *Setup installs the answer command* are not built (answer-session
      spec). If no control Claude Code enforces exists, the design falls
      back to hooks and the change cannot be built as written: record it
      and stop for the repository's owner
- [ ] 0.35 That `python3 "$G" gh pr view 12`, run as a Claude Code tool call
      after an earlier call ran `G=/tmp/x.py`, posts nothing and runs no
      script, because each tool call starts a fresh shell. Until then, the
      gh-post spec's scenario *A gh read through an unset G is no post* is
      not built. If `G` carries over, the reader reports that read as
      unreadable instead
- [ ] 0.37 That a mod can submit a prompt of its own into its session's
      conversation while the person is not typing, and have the model
      answer it with a tool call, unattended (design.md: *The model hands
      its judgements to the code through record_verdict*). If it cannot,
      record it and stop building the mod: the answer session is then
      designed as a standalone UI, not a Claude Code mod, and prototyped
      for the owner's approval
- [ ] 0.38 How the answer session tells, with the person's Linear key,
      that a Linear app user is an Igor's, in a form no other app user can
      take on, as the `igor-` slug tells an Igor's App on GitHub: for
      example by the user id of the Linear identity an Igor is configured
      with, or by a name igor requires of its Linear app. Task 0.16
      measured that Linear marks an app user's comment, with `user.app`
      `true`; which app user is an Igor's is not measured. On Linear, *A handback is an Igor's comment holding igor's
      marker* is built only once this is measured. If
      no such form exists, no Linear comment is a handback for good

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
      - It reads `python3 <github-app script> gh pr|issue|api …` posts,
        including `python3 $G …` only when the same command assigns `G`,
        and judges a line holding such a call exactly as the same line
        with the `gh` call made directly and no `G` assignment; prose's
        reader blocks such posts today.
      - It counts a `gh api` call as mentioning a gh post verb only when
        the call can write, as the `gh-post` spec's *A gh api call writes
        by its method, fields, input or a mutation* says: `-X` or
        `--method` in each form gh accepts and in any case, fields and
        `--input` with and without `--method GET`, the
        `X-HTTP-Method-Override` header, a GraphQL mutation, a query from
        standard input or a file, and a method or endpoint the shell
        builds, each with a test, and a read piped into `python3 -c`
        passing. Check each case against `gh api --help` and gh's
        behaviour, not only this list (design.md: *A gh api call counts
        only when it can write*).
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
        off that list, is no post (design.md: *The reader
        reads gh api writes, REST and GraphQL*).
      - It reports whether a post creates an issue.
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
        worker cannot (design.md: *Filter 1 in an Igor's run searches
        through `igor lore-search`*).
      - It applies the authority rules:
        - scope by the short name outside an Igor, and inside one as
          igor's `scopeMatches` gives it (igor's);
        - a decision record counted only when `accepted`;
        - a change's own decisions counted within that change;
        - a questions-branch `decision` file counted only unchanged and
          when its `answered_by` has write access, the file taken at its
          word for who answered (design.md: *A file is trusted for who it
          names*);
        - an answer whose `recorded_in` pins a commit counted for other
          work only once that commit has landed (design.md: *An answer
          recorded on a work branch counts for other work once it
          lands*);
        - only the newest answer counting among a question's files on a
          questions branch, by the order of the commits that added them
          (design.md: *The newest answer counts*);
        - during an Igor's run, `branch-search`, given the run's item,
          leaving out each file more private than the item (the file's
          visibility set by *A log or miss file is as private as its
          more private repository*) and showing a file about a
          repository other than the item's as input (design.md:
          *Questions-branch files and `project:` entries in a run's
          search*).
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
      file's name and prints only that file's answer, or `null` (inquisitor
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
        URL as `asked_in`: a Linear or Discord one only on a private
        repository's questions branch, a GitHub one only on a questions
        branch no more visible than the repository it points into (design.md: *`answer_link` and
        `asked_in` are withheld where they would leak*). Igor-worker mode
        writes no `asked_in`, because each Igor log file follows its own
        handback comment (design.md: *Each Igor log file follows its own
        handback comment*).
      - An answer file lists every file it answers in `answers`, refused
        when a named file is not on the branch or already holds an
        answer (design.md: *An answer file names every file it answers*).
      - Built by igor, not this task: the Igor writes `answers` for a
        later run only for a file it finds by its own record's suffix
        and date (design.md: *A later run names the answered file from
        the Igor's record*).
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
        answer session passes to the `log` command (design.md: *Every
        questions-branch file names where it was asked from*;
        answer-session spec: *A miss records who judged it and where it
        was asked from*).
      - A handled file holds only `handled` and `closes`, the closed
        file's name, or for a question with a category its SHA-256, with
        no body (design.md: *The answer session writes
        a handled file on every close of a questions-branch file*). It is
        written only through the command's session option, which only the
        answer session passes; a `handled` or `closes` key, or a hash-only
        miss file, is refused without it; the command does not check its
        caller.
      - Each answer is written in quote lines (design.md: *A log file's
        answer is written as quote lines*):
        - with a github.com `answer_link`, read from the linked comment
          and recorded word for word;
        - with a Linear or Discord `answer_link`, refused without the
          session option; with it, the answer recorded as given and the
          link never fetched, the link written only where the questions
          branch's repository is private and left out elsewhere (design.md: *An answer given through the answer session counts by its answer file*);
        - any other answer a person gave, without an `answer_link`, in
          their own words as given (design.md: *A logged answer is the
          person's own words*); without the session option, as `input`
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
        confirmed the warning, then with no link into the source
        (design.md: *Nothing goes somewhere more visible than its
        source*).
      - The secret scan, over raw markdown with link targets included, and
        the visibility refusal.
      - It refuses, saying why, a question holding a line that is exactly
        `## Rephrased question`, `## Discussion` or `## Answer`
        (design.md: *The `log` command reads its inputs and the linked
        comments itself*).
      - `misses`, listing the misses by filter for a review.
- [ ] 2.4b `cite`, pushing a citation file in the format of *A citation
      file has one format* (`entry` and `date`, no `run`) once to the
      `questions` branch of the lore repository holding the entry, when
      filter 1 stops a question with a lore entry, or when the person in
      the answer session cites an `active` entry in scope, a reason 2
      decline with filter 1 naming one included (design.md: *A person's
      cite pushes a citation file*). Its commit names no person (design.md: *A citation's commit
      names no person*). It sends none for a question with a category,
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
      or a deferral label (design.md: *What counts as a question in a
      post*)
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
      tags no one. The tag goes on the question's tag line, which the
      question's hash leaves out (inquisitor spec: *A tag line names the
      person a posted question tags*)
- [ ] 2.7 `lore`, opening a lore pull request, or a promotion from the
      `questions` branch, or refusing it by visibility or by an id outside
      igor's id rule. During an Igor's run it opens nothing and writes the
      entry into the run's report for the Igor to propose, as igor PR
      #216 is asked to (design.md: *A
      general answer is proposed as a provisional lore entry*)
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
      a question whose latest verdict record has a category, read from
      that record (inquisitor spec: *A question with a category is asked
      only of the person or in its advisory*); blocks a post with a
      question when it can't read its records; blocks a question whose raw
      markdown matches the credential patterns; passes a `deferred`
      question less than 2 hours old that tags no one in an open-questions
      section or a new issue; and vets
      every post it sees, igor's handback included (design.md: *No exemption for an Igor's handback*)
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
      one, and is listed by name in design.md's *Expected gaps* under
      *Tracing scenarios to tests*
- [ ] 4.3 Once igor provides `igor lore-search` and a role's `commands`
      can list the skill's script, build Igor-worker mode, write a tagged
      test for each expected gap, and remove it from design.md's list;
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
      comment, stopping on a categorized question, and an Igor worker
      raising igor's flag for a categorized question, listing once each
      category its worker run met and marking those of the questions it
      stopped on), describing no weakness in public text before its
      advisory is published, reviewing misses, and lessons by scope
- [ ] 5.2 `README.md`: what the skill is for, `inquisitor.json` and
      `.inquisitor/reviewers`, what to say to the agent, and troubleshooting a
      blocked picker or post, and, while github-app gives out a relay's
      token, the warning that any agent can take it (answer-session spec:
      *The README warns that a relay's token can be printed*).
- [ ] 5.3 A row in the README's skills table, and `inquisitor` in its list of
      skills that turn on a hook
- [ ] 5.4 `manage-skills` installs it and wires its hooks: check with
      `skills.py install inquisitor` and `skills.py doctor`
- [ ] 5.5 github-app's `SKILL.md`: every example that runs `python3 $G`
      sets `G` in the same command, or writes the script's full path, so
      the post hooks don't block it (design.md: *Posts sent through the github-app skill's script*)
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
      guard (design.md: *bug-hunter's Step 9 recommendations go through
      the filters*). These starting rules are input, not decided
      behaviour: the builder sets the final rules, which are reviewed
      with the implementation.

      | Step 9 recommendation | Settle it without asking when | What to do then | Filter |
      |---|---|---|---|
      | A Step 3 property worth keeping as a guard: a property-based check the hunt ran against a stated invariant | The check is bounded in runtime, runs with a fixed seed, and needs no new dependency | Keep it as a test | Cheap to reverse |
      | A finding too large for the change | Always | File it as an issue with its evidence, and report the link | Deferrable |
      | Something left unresolved when a bug-hunter run aborted after its third iteration | A new bug-hunter run over it would be cheap | Record it where the repository keeps open questions, and report it | Deferrable |
      | A root cause | It was already decided or rejected (look it up), or its fix is small and defensible | Fix it, and run bug-hunter's loop over the fix | Already answered; cheap to reverse |

      Only a broad root-cause fix or a design choice, or an abort's
      leftover whose new run is costly, still goes to the person
- [ ] 5.8 Add to bug-hunter's SKILL.md the inquisitor spec's rules for a
      weakness whose advisory is unpublished (design.md: *Weaknesses stay
      out of public text until disclosure*). Task 0.13 measures whether
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

- [ ] 6.0 Build on discord-bot as shared-skills PR #1 merged it
      (design.md: *Discord is in the first version, through discord-bot*).
      The Discord relay posts with no header option and with mention
      rewriting on, because discord-bot always posts that way (design.md:
      *Discord relay posts: no header, mentions
      that ping*). discord-bot's `read` drops each message's
      `author.bot` and reply reference, which the answer session needs to
      tell a bot's message and a reply to a relay post, as task 0.17 found
      on 2026-11-19; this task changes `read` to return both
- [ ] 6.1 The mod, built into the inquisitor skill from the tag
      `answer-session-ui-approved-v0.1-33` on shared-skills (build v0.1-33,
      commit fc3c35f; `ui-approved-v0.1-33` in the repository's owner's local prototype
      repository, `~/answer-session-prototype`), the only build the mod
      starts from. It descends
      from v0.1-30 (`answer-session-ui-approved-v0.1-30`, commit c9c6eb5)
      and contains all of it, including declining and the list of
      questions answered or handled for the person. The mod takes its
      questions from task 6.3's polls instead of the prototype's made-up
      ones. Four rules decide what is built (design.md: *How the approved
      prototype meets the spec*; *The UI is built from prototype build
      v0.1-33*):
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
          isn't a question" (design.md: *Two reasons to decline*); under
          it declining closes only that question, and every later message
          in its thread that the sources name is a new question, where the
          prototype ends the thread (design.md: *Declining with nothing to answer closes only that
          question*);
        - reopening offered only for a thread copy declined with nothing
          posted, on its own machine, where the prototype offers it for
          any decline under its first two reasons (design.md: *Reopening a declined
          question*);
        - the handled file pushed naming each questions-branch file a
          closed question was shown from, or that holds it through
          `asked_in`, which the prototype does not write (design.md:
          *Closing works by exact identity, never
          by matching*);
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
          in a new file (design.md:
          *Agreeing to a recorded answer is a filter 1 decline*);
        - the question on screen kept in the state folder, not the mod's
          `$.store`, so a restarted session opens on it.
      - (c) A screen the spec needs that v0.1-33 lacks is designed in this
        task from the prototype's existing patterns, in no new visual
        style, with no prototype round of its own: setup, the lock
        message, where an answer will be recorded and its warning, a
        post's failure and discord-bot's
        warnings, why no miss was logged, a channel that is off, and the
        pending list, which reuses the approved queue's screens
        (design.md: *An answer that cannot reach its thread is kept
        pending*)
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
      keychain; `~/.local/bin/answer`; the check that each subscribed or
      lore repository's `questions` branch takes the person's direct push,
      and the suggested rule blocking its force pushes and deletion;
      and the optional step that creates a lore repository, its clone and its
      configuration entry (design.md: *Setup checks direct pushes, and can
      create a lore repository*)
- [ ] 6.3 Polling: the four sources, only while open, the catch-up on
      opening, 60 seconds or GitHub's `X-Poll-Interval`, conditional
      requests, poll positions, the questions branch of every
      subscribed repository and configured lore repository, and each
      subscribed repository's default branch. The `search` command reads
      only these fetched branches and the lore clones, and issues only of
      their repositories (answer-session spec: *The answer session's
      filter 1 reads only subscribed and lore repositories*)
- [ ] 6.4 Relaying: posts with the four reserved prefixes through the
      relay identity's skill as host commands, or on Linear the session's own
      HTTP request, carrying the token linear-app's `token` command prints,
      held only in memory and never in a command's arguments, the `Re: ` line on GitHub
      and Linear posts, post ids, editing in place, the thread read before
      a question is shown and before each post, the preview showing where
      the answer will be recorded and, for an Igor's question on a more private repository,
      that the answer also reaches the run on its item (answer-session spec: *The preview
      says when an answer also reaches a more visible item's run*), an answer whose last line
      starts `Re: `, which a reader would take for the post's own `Re: ` line, sent back for rewording,
      and each confirmed answer pushed as a new log file, and again as a new one when its relayed answer
      is edited (design.md: *Editing a relay post*);
      discord-bot's warnings shown after each Discord relay post and edit;
      and, off GitHub, the relayed text logged with the relay post's URL
      as an unfetched `answer_link`
- [ ] 6.5 State: the state folder, a question's state read from its
      thread, closed questions, discussion records deleted once their
      question is answered or closed, the question on screen, and the lock,
      which a second session reports and offers to take over
- [ ] 6.6 The discussion's context, `propose_reply` (refusing a call as
      *Claude's draft goes to the prompt box, never to a post* says, and filling the record's URL for a filter 1
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
      post none, because its text is fixed (design.md: *A relay post gets no
      prose pass and no vetting*; *What the answer session posts by
      itself*)
- [ ] 6.8 Tests, each tagged `@scenario answer-session: <Scenario name>`,
      and the README's section on the answer session: setup, the `answer`
      command, what to do when a relay check fails, and that no post but
      the answer session's starts with a reserved prefix
- [x] 6.9 The repository's owner's approval, by use, of the screens prototyped after the
      first approved build: declining a question, the choice of filter
      under "the inquisitor should have handled it" (reason 2) and the
      exact post shown before it goes out (design.md: *Misses the answer
      session logs*), and the list of questions answered and handled for
      the person. Done: build v0.1-30, tagged
      `answer-session-ui-approved-v0.1-30` on shared-skills
- [ ] 6.10 The answer session's handling of incoming questions, SKILL.md's
      guidance on its automatic replies, and the tests below. igor builds
      the item marked igor's, as igor PR #216 is asked to.
      - Built in this task:
        - filter 1 on every incoming question, run through the script's
          `search` command, and the `Recorded answer: ` post;
        - placing a question asked on Linear or Discord (answer-session
          spec: *A Linear or Discord question is placed by what it
          concerns*), and placing an agent's question by its concerns line
          (*A concerns line settles what an agent's question concerns*);
        - filters 2 to 4 and the three fixed `Inquisitor: ` texts, and a
          question carrying a person-required line always shown to the
          person unless filter 1 answers it, the line found by its fixed
          wording after markup is reduced (design.md: *A question another skill
          requires carries a line the answer session matches*);
        - declining with its two reasons, and reason 2's posts;
        - the misses on the questions branch, none for reason 1
          (design.md: *Messages that are not questions are ignored*;
          *Misses the answer session logs*), and a miss against filter 1
          for an agent's question the answer session answers by itself;
        - a recorded answer by itself on a relayed question, and no
          `Inquisitor: ` post on one (design.md: *Which questions count
          as an agent's*; *Filter 1 runs on every incoming question*);
        - no automatic post that repeats an automatic post made earlier
          in its chain of replies (design.md: *No automatic post repeats
          one in its chain of replies*);
        - a questions-branch question asked in a post answered in its
          thread and by a log file;
        - a refused post turning off a channel no check can read;
        - the post hook's block of a tool-call post that starts with a
          reserved prefix (design.md: *The post hook blocks a reserved
          prefix on GitHub*).
      - SKILL.md tells an agent to act on a `Recorded answer: ` reply only
        once filter 1 counts its record, and on an `Inquisitor: ` reply
        only when a miss file on the branch its question's concerns line
        names backs it: one naming a `said_by`, or a hash-only one, each
        named by a hash of the reply's surface and id
        (design.md: *What an asking agent does with an automatic reply*).
      - The tests cover:
        - the handled file, pushed whenever the answer session closes a
          question a questions-branch file holds, from that branch or
          through `asked_in`, closing exactly the file it names, for good
          (design.md: *The answer session writes a handled file on every
          close of a questions-branch file*);
        - a miss or citation file's push recorded as owed before its post
          and retried at each poll and each opening until it succeeds
          (design.md: *A person's cite pushes a citation file*);
        - a thread copy declined with nothing posted closed on that
          machine only (design.md: *Reopening a declined question*);
        - a log file following its thread message by `asked_in`
          (design.md: *A log file follows its thread message by exact
          link*);
        - a later message in a closed question's thread, a follow-up or
          a reply, shown as a new question, after an answer or a decline
          for either reason (design.md: *Declining with nothing to answer
          closes only that question*);
        - a message that is not really a question ignored, and one that
          reaches the queue declined under reason 1 with no miss, or
          under reason 2 with filter 3's "the agent shouldn't have
          asked", posting nothing, with a filter 3 miss against the
          asking agent;
        - a log file whose `asked_in` links a message this machine has not read, shown on its
          own (design.md: *A link this machine never reads is not
          followed*);
        - a log file with no `asked_in` always shown as its own question,
          never paired with a message (design.md: *A log file without
          `asked_in` is never merged*);
        - an answer that cannot reach its thread kept as answered, not
          relayed, returned to the queue with the answer kept once its
          channel passes its check, and posted only after the person
          approves it again, while another machine asks the question
          again;
        - a pending answer, kept for a reason no check covers (a refused
          text, a reply that arrived or an unsubscribed channel), staying
          on the list, and posted, edited or dropped by the person at any
          time (design.md: *An answer that cannot reach its thread is kept
          pending*);
        - filter 1's search grouping every answer file by hash; among
          answer files naming one file, the newest is its answer and the older ones show as superseded in the search too; only an answer file that names, as `answered_by`, the person the named
          file tags counts as
          a named file's answer (design.md: *`answers` decides a named
          file's answer; the search groups by hash*; *A named file's
          answer must be the person's own*);
        - a file that tags no one answered only by an account with write
          access to what its question concerns: the repository its
          `repository` key names, or else the lore repository;
        - declining with two reasons, the first, nothing to answer
          (design.md: *Two reasons to decline*);
        - a named file still shown, with the answer beside it as input,
          when its answer file does not count (design.md: *A named file
          stays shown until its answer counts*);
        - the relay post first, then the answer file's push, retried at
          each poll and each opening, the owed push recorded in the state
          folder before the post, and the relay post's URL added to that
          record once the post goes out, the record dropped when it never
          went out (design.md: *The push order for a questions-branch
          answer*);
        - every push passing the `log` or `cite` command's session option, so
          that the owed push is the only retry;
        - the answer file pushed only after the thread is checked, none
          for an answer held back or dropped, and at once only for one
          whose channel is off or not subscribed, including one whose
          refused post turned it off;
        - where the questions branch is more visible than the thread the
          answer was given in, a Linear or Discord thread counting as
          private, an answer posted and its file pushed only once the person
          confirmed the warning, and a miss the person has not confirmed
          pushed as a hash-only miss file after a posted reply and, with
          no reply posted, not pushed;
        - the `log` command refusing an `answers` that names a file not
          on the branch;
        - an answer file holding the question the person saw and listing
          every file it answers (design.md: *An answer file records the
          question the person saw*);
        - a second machine's miss not pushed when its name is on the
          branch;
        - a miss for a question a questions-branch file holds copying
          that file's `asked_from`, and its `repository` if it has one;
        - a later run naming a file only from the Igor's own record, by
          its file-name suffix and date, more than one match naming none
          (igor's; design.md: *A later run names the answered file from
          the Igor's record*).
      - For Igor items the tests also cover:
        - every Igor log file following its own handback comment, a link
          followed only from a marked handback by an Igor, on GitHub in
          the repository the file's `asked_from` names (design.md: *Each Igor
          log file follows its own handback comment*; *igor's handback
          marker*);
        - an item shown only through its newest handback, an older
          unanswered handback passed over with nothing written and its
          file never shown again (design.md: *Only an item's newest
          handback is open*);
        - a bot's message reaching only the first person it mentions,
          a mention of a relay identity in a bot's message counting as
          one of the relay's person, and a bot's reply
          to a relay post that mentions no one reaching that relay's
          person, and a person's message reaching each (design.md: *A bot's
          question reaches only the first person it mentions*);
        - a handback that mentions no one reaching the assignee, shown to
          no one on an unassigned item and never to this person on an
          item assigned to someone else (design.md: *A handback that
          mentions no one reaches the assignee*).
- [ ] 6.11 Decide at implementation, and when each choice is made, add
      it to the spec as a requirement with a scenario or, if no test can
      check it, to the answer-session decision record as an entry with
      evidence; design.md only links to that requirement or entry
      (design.md: *Some answer-session details are decided at
      implementation*): how a question's options, the choices it offers
      with what each would change, are parsed from its thread; and how the
      session handles an asker's reply that revises those options. Agreeing
      to a shown recorded answer is already decided (design.md: *Agreeing
      to a recorded answer is a filter 1 decline*), as are agreeing to a
      suggested verdict and citing a lore entry (answer-session spec:
      *Filters 2 to 4 only suggest a verdict on other questions*; *A
      person cites a lore entry by naming it as an answer or a record*)
## 7. Archive

- [ ] 7.0 Archive only after igor PR #216 has merged, since filter 1's
      search in an Igor worker depends on it, igor PR #202 has set the
      path of the scribe's records, and task 4.3 has tagged every expected
      gap, since spec-trace's CI fails on an untagged scenario once
      archived (design.md: *The change is archived only after every
      expected gap is tagged*). Make filter 1 search the scribe's records
      where igor PR #202 puts them, in the repository a question concerns
      and in the lore repository (design.md: *Filter 1 searches igor's
      scribe's records where #202 puts them*; *An answer typed on another
      surface counts only through a decision document*). Point the spec's
      links to igor PR #216's lore-firing spec at igor's
      `openspec/specs/lore-firing/spec.md` on main
- [ ] 7.1 Archive with `openspec archive` and no flags. This pull request already
      edits the decision records, `openspec/specs/inquisitor/decisions.md`,
      `openspec/specs/answer-session/decisions.md` and
      `openspec/specs/gh-post/decisions.md`, and archiving leaves them as
      they are. Write no `.agents/skills/inquisitor/DECISIONS.md`. Since
      design.md and tasks.md are archived with the change and not read
      again, repoint these citations: each requirement's citation of a
      measurement task 0.N, and each decision record's Evidence link to
      tasks.md, at its measured result; each citation of a design.md
      section whose reason a decision record entry now gives, at that
      entry; and each other citation of design.md, at the archived
      design.md
