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
      headless run, such as an Igor worker or `claude -p`, and
      whether a headless session that is not an Igor worker can post.
      Whether it runs in an Igor's run, and whether that is a worker's
      run or the Igor's own, it reads from
      `IGOR_RUN` (decision 235); once igor builds it, check that igor
      sets it as igor PR #216 specifies
- [ ] 0.10 Whether the agent can open, and write in, a repository's private
      security advisory, and what access that needs
- [ ] 0.11 GitHub's API gives a comment's or review's author, and whether a
      commit's signature is verified and for which account, as decision 78
      needs
- [x] 0.12 Whether an Igor's worker can run this skill, with a lore clone and
      `inquisitor.json` in reach, as the spec assumed before decision
      144 moved a worker's lore search into igor, measured before this pull request or
      igor PR #216 lands (decision 141). It can't today, measured from
      igor's code; read from igor PRs #174's and #175's specs, not checked
      since neither is built, it can't once they land either; design.md, *What task 0.12
      measured*, gives the evidence. Gate two builds
      everything except Igor-worker mode, which waits for igor to give the
      worker what proposal.md's *Still open* names
- [ ] 0.13 Whether GitHub lets a security advisory's private-fork pull
      request be merged before the advisory is published, as decision 108
      needs. Until this shows the merge waits for publication, fork commit
      messages describe no weakness (decision 127)
- [ ] 0.14 Whether an Igor worker's `gh` can post, from a login stored in
      the home directory igor gives it rather than in its environment, as
      decision 126 assumes it can't
- [ ] 0.15 Which reasons GitHub's notifications endpoint gives, read with
      the person's `gh` login, for a mention, a review request, an
      assignment and a later comment in a thread the person was mentioned
      in, and that a conditional request answered `304` does not count
      against the rate limit. Until then the answer session also reads the
      comments of each subscribed repository since its poll position
- [ ] 0.16 How the answer session finds, on Linear with the person's key,
      mentions of the person and of the relay, and replies to a relay
      comment, in a subscribed team; that the answer session can post a
      comment as the linear-app identity with a command it runs on the
      host, and learn that comment's URL; and that the linear-app
      identity can edit its own comment. If any of these fails, Linear
      stays off and the README says so
- [ ] 0.17 That a `discord-bot` identity can read a subscribed channel's
      history and threads, see a mention of the person's user id and a
      reply to the relay's message, and that the relay can edit its own
      message, with discord-bot as merged in shared-skills PR #1. Reading the content
      of a message that doesn't mention the bot needs Discord's privileged
      Message Content intent, which PR #1 turns on for reading and its
      `check` reports as `messageContent` (decision 238); record that a
      relay whose `check` reports `true` reads such a message. If it
      can't read them, Discord stays off and the README says so
- [ ] 0.18 That a command the mod runs with `$.process.run`, the mod API's
      call that runs a host command, reaches no
      `PreToolUse` hook, so neither post hook sees a relay post (decision
      170). If a `PreToolUse` hook does see such a command, record it and
      stop: decision 170 needs Adam again
- [ ] 0.19 That a mod's timers keep polling every 60 seconds and
      refreshing the lock every 30 seconds while its session is idle or
      runs as a Claude Code background session, and how a session tells
      that it is one, so that the lock can record it. If they stop, a holder that is still alive would let its
      lock go stale, and another session would take it without asking;
      record that, and stop for Adam
- [ ] 0.20 How setup checks, on each surface, that a relay identity can
      post in a given channel. On GitHub, github-app's `check` reads only
      the identity's own configured repositories, so setup reads the App
      installation's access to each subscribed repository itself. On
      Linear and Discord, record whether the skill's own check reads a
      team's or channel's permission, or setup must read it itself. Where
      no check can, setup runs the skill's own check only, and a post a
      channel refuses later turns that channel off (decision 211)
- [ ] 0.21 That GitHub's API reports, for a comment, the slug of the
      GitHub App that wrote it, which the relay file names (decision 216),
      in a form no account can take on: such as the author login
      `<slug>[bot]` with the type `Bot`, or the comment's
      `performed_via_github_app`. Until this task shows GitHub does, no
      comment counts as a relayed answer, and an agent treats an
      `Inquisitor: ` reply as input. If GitHub does not, both stay so for
      good, record that, and stop for Adam
- [ ] 0.22 What a reader needs to tie a relay file to its person
      (decision 225): that GitHub's API gives, for the newest commit that
      changed `relays/<login>.yaml`, the merged pull request it came from
      and that pull request's author, after a merge commit, a squash and a
      rebase alike, such as through `commits/<sha>/pulls`; and whether a
      commit GitHub signs itself, from its web editor or its contents API,
      is verified for an account other than its author's, which would let
      anyone with push access make a commit verified for another person.
      This applies to decision 78's signature proof as well. Also record
      how a reader tells a signature GitHub made from the person's own,
      such as GraphQL's `wasSignedByGitHub`; if it can't, no signature
      counts. Task 0.11
      measures the rest of reading a signature. If the pull request can't
      be read, only a signature proves the file. Until this task shows
      GitHub never verifies such a commit for someone who didn't make it,
      a signature GitHub made itself proves nothing

## 1. Shared post reader

- [ ] 1.1 Move prose's `gh` and GitHub MCP body reader into `.agents/lib/gh-post/`,
      called from a thin script in each skill, with no change in behaviour
- [ ] 1.2 prose's tests pass unchanged; add the library's own tests beside it,
      each tagged `@scenario gh-post: <Scenario name>` for the `gh-post`
      spec's scenario it checks
- [ ] 1.3 The library also handles the following. prose's existing tests
      still pass unchanged, except a test that expects one of these to
      pass, which now expects it blocked: an inline-code command naming
      `gh`, a title built by the shell, or a title edit chained to another
      command; add tests for each to prose's and the
      library's tests.
      - It reads a post's title, as a literal word, from `--title` or
        `-t`, a `gh api` `title` field under `issues` or `pulls`, the
        `title` argument of the GraphQL mutations that create or update
        an issue or pull request, and a GitHub MCP `title` key, and
        reports a call whose title it can't read as unreadable (decision
        206), and a title edit chained to another command as unreadable.
        prose's hook lets a call with a title and no body through, and
        prose's `DECISIONS.md` section *`--title` is not prose here* says
        that a title is now read
      - It reads `python3 <github-app script> gh pr|issue …` posts,
        including `python3 $G …` only when the same command assigns `G`.
      - It reads `gh api` comments whose body is given by `-f body=`,
        `--raw-field body=`, `-F body=` or `--field body=` (with or
        without `@<file>`), or by `--input`, and a review's
        `comments[][body]` fields.
      - It reports whether a post creates an issue.
      - It reads every `body` argument of the GraphQL mutations that post
        text to an issue or pull request (decision 132), and reports any
        other mutation as no post, or as unreadable when it has a `body`.
      - It blocks as unreadable a `gh api` call that writes (its method
        `POST`, `PATCH` or `PUT`, given or implied by fields, or a GraphQL
        mutation) whose body it can't read, a GraphQL query it can't parse,
        and a review whose comments it can't read.
      - It applies the closed list of gh post verbs, and blocks as
        unreadable, as prose's reader does today, a command that names
        `gh` in another command's arguments, such as `sh -c`, or that
        pipes into a command other than a data command.
      - It blocks as unreadable a data command given code to run, such
        as `python3 -c`, `node -e` or `git -c`, whose arguments name
        `gh`, and treats `python3` or `node` reading its program from a
        pipe or heredoc as no data command (decision 139). prose's hook
        blocks these too, so a prose test that expects one of them to
        pass is changed to expect it blocked
      - As part of this task, once the reader has moved, prose's
        `DECISIONS.md` section on the allow-list points at
        the library's list instead of restating it, and its section *A
        command that runs no gh post is not a post* no longer says that
        `python3 - <<'EOF'`, `node -e` and `git -c` are outside the
        hook's reach (decision 139)

## 2. The script

- [ ] 2.1 `.agents/skills/inquisitor/scripts/inquisitor.py vet` (first call):
      `--questions` and `--post`, which takes a post's body and title, printing the filters and filter 1's search
      results, issuing a token
- [ ] 2.2 `vet --pass <token> --verdicts <file>` (second call): the four
      verdicts and their fields, the three categories recorded by hash only,
      the refusals, and the records the hooks read, each deleted once it is
      more than 2 hours old except a `deferred` record without a category
- [ ] 2.3 Filter 1's search over decision documents, issues through `gh`, the
      repository's question log and misses, and configured lore clones' entries and
      `questions` branch, fetched and read with `git show`, matched as
      plain text and ranked by terms matched, with a cap it reports
      (decision 229), and during an Igor's run lore only through `igor
      lore-search` (decisions 133 and 229); the authority
      rules, with scope as igor's `scopeMatches` gives it inside an Igor
      and by the short name outside one, and a decision record counted
      only when `accepted`, a change's own decisions within that change, and
      a questions-branch `decision` file only with its writer proven by a
      linked comment or a verified signature (decision 78), the comment
      holding the file's answer when its text equals the file's answer
      once both are reduced (decision 236),
      a relayed answer only from an App the person's `relays/<login>.yaml`
      lists, counted only when its last change came from that person
      (decisions 216, 224 and 225), never from a slug starting with
      `igor-` (decision 232), only the
      newest answer counting among a question's files there (decision
      220), a file's visibility taken from the more private of its
      `repository` and `asked_from` (decision 221), and, during an Igor's
      run, a file about a repository other than the
      item's shown as input (decision 214), while an
      `agent` file on a questions branch is always input; each source not searched; when
      each clone's remote-tracking default branch was last updated by a
      fetch
- [ ] 2.4 The `log` command, writing one file per question or miss in the
      format of *A log file and a miss file have one format*, with an
      `authority` of `decision`, `input` or `agent`, and `answered_by: agent` for an agent's choice,
      an answer with a github.com `answer_link` read from the linked
      comment and recorded word for word (decision 236), an answer with
      a Linear or Discord `answer_link` recorded as given, its link
      never fetched (decision 248) and written only into a private lore
      repository (decision 251), and any answer a person
      gave without an `answer_link` in their own words as given
      (decision 240), each in quote lines
      (decision 239's item 1): in the
      repository's `.inquisitor/` for a
      question about it (by a pull request when it is not the repository
      holding the current work), or pushed to the team's lore repository's
      `questions` branch for a question about the organization or project,
      fetching and pushing again when rejected; the secret scan and the
      visibility refusal; `misses`, listing the misses by filter for a review
- [ ] 2.4b `cite`, pushing a citation file in the format of *A citation
      file has one format* (`entry` and `date`, no `run`) to the
      lore repository's `questions` branch when filter 1 stops a question
      with a lore entry, or when the person answers in the answer session
      by citing one (decision 257), committed unsigned with `git -c
      commit.gpgsign=false`. It sends none for a question with a
      category, and none to a lore repository more visible than the
      repository the question concerns. During an Igor's run it pushes
      nothing, and the citation is handled as igor PR #216's *An
      Igor publishes the citations its worker reports* says
- [ ] 2.5 The question finder for posts, as one function the post hook also
      calls, finding questions in a post's title and body, with an
      open-questions section begun only by a label that names questions
      or a deferral label (decision 204)
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
      `questions` branch, or refusing it by visibility, by an id outside
      igor's id rule, or, during an Igor's run, by an id reported only as
      "id taken"
- [ ] 2.8 `relay-notice.yml`, the workflow template a lore repository
      carries to mention a relay file's person, modelled on igor PR #171's
      `templates/seat-notice.yml` (decision 228)
- [ ] 2.9 The `log` command's input file, refused unless it has mode 0600
      in a private directory (decision 230); the post reader's git forms
      that run a command (`rebase -x`, `submodule foreach`, `bisect run`)
      as code to run, and a `gh` alias or extension as unreadable
      (decision 230)

## 3. Hooks

- [ ] 3.1 `scripts/check-ask.sh`: `PreToolUse` on `AskUserQuestion` (Claude Code
      only), checking verdicts, blocking with exit 2, and failing open,
      including when it can't read its records
- [ ] 3.2 `scripts/check-post.sh`: `PreToolUse` on Bash and the GitHub MCP tools,
      through `.agents/lib/gh-post/`, blocking a post that holds a question
      with a category (by the spec's *Some questions are recorded by hash
      only*), blocking a post with a question when it can't read
      its records, passing a `deferred` question that tags no one in an
      open-questions section or a new issue, and letting an Igor's handback comment through as
      far as task 0.6 finds the hook can tell that comment apart from other
      posts
- [ ] 3.3 `hook.json` with both hooks, `"default": "enabled"`

## 4. Tests

- [ ] 4.1 `scripts/test_inquisitor.py`, standard library only, each test tagged
      `@scenario inquisitor: <Scenario name>` for the scenario it checks
- [ ] 4.2 Every scenario but the expected gaps has a tagged test: of
      this change's scenarios, `spec_trace.py report --include-changes`
      marks only the expected gaps `none`, meaning no tagged test. A
      scenario about what the agent does is tagged on a test that checks
      SKILL.md states the rule. An expected gap is a scenario that only
      igor's unbuilt work can make pass, since task 0.12 measured that
      an Igor worker can't run the skill: it gets no test, not
      even a skipped one, and design.md's *Expected gaps* lists it by name
      (decision 249)
- [ ] 4.3 Once igor provides `igor lore-search` and a role's `commands`
      can list the skill's script, build Igor-worker mode, write a tagged
      test for each expected gap, and remove it from design.md's list.
      Archiving with a gap still untagged would fail spec-trace's CI, so
      the archive waits for this task (task 7.0, decision 253)

## 5. Docs and registration

- [ ] 5.1 `SKILL.md`: the filters, the two calls, writing a question at the
      privacy of what it concerns, posting no more publicly than that, the
      questions other skills require a person to decide, preparing, batching and tagging, the order
      with prose, logging answers and misses, the three categories recorded
      by hash only, what a headless session does (no picker, an Igor
      worker asking only in its handback comment, stopping on a
      categorized question, and an Igor worker raising igor's flag
      for a categorized question, listing once each category its worker run met
      and marking those of the questions it stopped on), describing no
      weakness in public text before its advisory is published, reviewing
      misses, and lessons by scope
- [ ] 5.2 `README.md`: what the skill is for, `inquisitor.json` and
      `.inquisitor/reviewers`, what to say to the agent, and troubleshooting a
      blocked picker or post. Until github-app refuses `token` for an
      identity marked as a relay, it says that any agent on the person's
      machine can print a relay App's token and post `User says: ` unseen
      (decision 233)
- [ ] 5.3 A row in the README's skills table, and `inquisitor` in its list of
      skills that turn on a hook
- [ ] 5.4 `manage-skills` installs it and wires its hooks: check with
      `skills.py install inquisitor` and `skills.py doctor`
- [ ] 5.5 github-app's `SKILL.md`: every example that runs `python3 $G`
      sets `G` in the same command, or writes the script's full path, so
      the post hooks don't block it (decision 135)
- [ ] 5.6 prose's file filter skips files under `.inquisitor/`, so prose's
      pass never rewrites a log or miss file, which quotes a question and a
      person's words exactly (decision 134). It ships with the skill,
      which writes such files from gate two on

## 6. The answer session

- [ ] 6.0 Build on discord-bot as shared-skills PR #1 merged it
      (decision 165). The Discord relay posts with no header option and
      with mention rewriting on, as discord-bot always posts (decisions
      230 and 246)
- [ ] 6.1 The mod, built into the inquisitor skill from the tag
      `answer-session-ui-approved-v0.1-30` on shared-skills (build v0.1-30,
      commit c9c6eb5; `ui-approved-v0.1-30` in Adam's local prototype
      repository, `~/answer-session-prototype`). The tag includes
      declining and the list of questions answered or handled for the
      person. The mod takes its questions from the polls of task 6.3
      instead of the prototype's made-up ones. Four rules decide what is
      built (decision 254):
      - (a) Keep the approved screens' layout and interaction: the band,
        the keys, the prompt-box flow and the declining screens. Changes
        needed to wire them to real data are fine; restyling or
        reorganising them is not.
      - (b) Where the prototype disagrees with the spec, the spec wins.
        The known cases: `User asks: ` for a clarifying question; the
        `Rephrased question: ` and `Discussion: ` lines in the relay
        post; `Recorded answer: see the record below.` with
        `Recorded in: <URL>`, quoting nothing; the fixed `Inquisitor: `
        texts, and reason 3's line `The person chose this filter.`;
        previews that show the `Re: <URL>` line; reason 1's wording, under
        which only the asker's unthreaded follow-up stops counting;
        reopening a declined question keeping its logged miss (decision
        255); and the question that was on screen, kept in the state
        folder so a restarted session opens on it, not in the mod's
        `$.store`
      - (c) A screen the spec needs that v0.1-30 lacks is designed at
        implementation, in this task, from the prototype's existing patterns, in no new visual style:
        setup, the lock message, the relay notice, a post's failure and
        discord-bot's warnings, why no miss was logged, and a channel
        that is off
      - (d) A screen Adam approves separately is taken from its own
        approved tag. One separately approved build, being prototyped,
        will cover two screens: thread replies, and the recorded answer
        shown beside the question
- [ ] 6.2 The `answer_session` section of `inquisitor.json`, and setup:
      the candidates, each relay check, saving the file with the person's
      own keys kept, a failed identity's surface or a failed channel left
      off and checked again at each opening, the Linear key in the
      keychain, `~/.local/bin/answer`, the pull request writing the
      person's `relays/<login>.yaml` in each serving lore repository
      (decision 224), and the one adding `relay-notice.yml` where it is
      missing. Filter 1, and every check that reads a comment's author,
      reads that file from the lore clone's default branch, and counts it
      only when its last change came from its person (decision 225)
- [ ] 6.3 Polling: the four sources, only while open, the catch-up on
      opening, 60 seconds or GitHub's `X-Poll-Interval`, conditional
      requests, poll positions, and the lore questions branches
- [ ] 6.4 Relaying: posts with the four reserved prefixes through the
      relay identity's skill as host commands, post ids, editing in place,
      the thread read before a question is shown and before each post, and
      a questions-branch question answered by a new log file, and a new
      log file again when its relayed answer is edited (decision 220);
      discord-bot's warnings shown after each Discord relay post and each
      edit of one (decisions 247 and 252); and, off GitHub, the relayed
      text logged with the relay post's URL as an unfetched
      `answer_link` (decision 248)
- [ ] 6.5 State: the state folder, a question's state read from its
      thread, closed questions, discussion records deleted once their
      question is answered or closed, the question on screen, and the lock,
      which a second session reports and offers to take over
- [ ] 6.6 The discussion's context, `propose_reply`, and the rephrased
      answer's post. SKILL.md tells an agent that records an answer from a
      relay post to log its rephrasing and summary
- [ ] 6.7 prose's SKILL.md and `DECISIONS.md` say that a relay post is
      the person's words and gets no prose pass (decision 170), and that an
      automatic post, whose text is fixed, gets
      none either (decision 200)
- [ ] 6.8 Tests, each tagged `@scenario answer-session: <Scenario name>`,
      and the README's section on the answer session: setup, the `answer`
      command, what to do when a relay check fails, and that no post but
      the answer session's starts with a reserved prefix
- [x] 6.9 Adam's approval, by use, of the screens prototyped after the
      first approved build (decisions 147 and 226): declining a question,
      with its three reasons, reason 3's choice of filter and the exact
      post shown before it goes out (decision 209), and the list of
      questions answered and handled for the person. Adam approved build
      v0.1-30 by use on 2026-10-20 (decision 231), tagged
      `answer-session-ui-approved-v0.1-30` on shared-skills
- [ ] 6.10 Filter 1 on every incoming question and the `Recorded answer: `
      post; filters 2 to 4 and the three fixed `Inquisitor: ` texts;
      declining with its three reasons, and reason 3's posts; the misses
      on the questions branch, with `filter: "source <n>"` and
      `said: "not a question"` for the second reason, a miss against
      filter 1 for an agent's question it answers by itself, and no
      second miss for the same question; a recorded answer by itself on a
      relayed question, and no `Inquisitor: ` post on one (decision 223),
      and no automatic post that repeats an automatic post made earlier in
      its chain of replies (decision 219); a
      questions-branch question asked in a post answered in its thread
      and by a log file; a refused post turning off a channel no check
      can read; the post hook's block of a
      tool-call post that starts with a reserved prefix (decision 203). SKILL.md tells an agent how to
      act on a `Recorded answer: ` or `Inquisitor: ` reply: a recorded
      answer only once filter 1 counts its record, and an `Inquisitor: `
      reply only when it names filter 2, or names filter 3 or 4 and its
      last line apart from a `Re: ` line says the person chose it, which
      reason 3's posts add (decision 234; the line is decision 239's
      item 6)
- [ ] 6.11 Decide at implementation, with no requirement added
      (decision 256), and record each choice in design.md while the
      change is open: how a question's options are parsed from its
      thread; `propose_reply`, the tool Claude calls to put a draft reply in the
      prompt box, refusing a call from a subagent (Adam confirmed this);
      a draft's privacy, beyond the existing rule that the draft is
      written at the privacy of what the question concerns; an asker's
      reply revising the options; what agreeing with a suggested verdict
      and citing a lore entry post, each within the reserved-prefix rules
      of *Four reserved prefixes mark the answer session's posts*, though
      citing always also pushes a citation file (decision 257);
      Claude's draft, through `propose_reply`, filling the place the person
      gives when declining under reason 3 with filter 1, that is, the URL of
      the record for the `Recorded in: ` line (Adam confirmed this,
      since the draft lands in the prompt box for the person to confirm),
      the post keeping its fixed form; and the relay notice's UI, the notice shown for the comment GitHub Actions
      posts when a pull request changes the person's relay file,
      under task 6.1's rule (c)

## 7. Archive

- [ ] 7.0 Archive only after igor PR #216 has merged, since filter 1's
      search in an Igor worker depends on it, and after task 4.3 has
      tagged every expected gap, since spec-trace's CI fails on an
      untagged scenario once archived (decision 253). If igor PR #202 has by then
      said where the scribe's records live, both in the repository a
      question concerns and in the lore repository, make filter 1 search
      those places (decisions 63, 66 and 109). Until #202 says so, filter 1
      searches `docs/decisions/` in the repository a question concerns,
      and no lore repository's decision records. Once #216 has merged,
      point the spec's links to *An Igor publishes the citations its worker
      reports*, *An Igor publishes the questions-branch files its worker
      reports* and *An Igor runs its worker's lore searches* at igor's
      `openspec/specs/lore-firing/spec.md` on main, and
      its link to *Transcripts and outcomes are captured to the state
      branch* at igor's `openspec/specs/task-execution/spec.md` on main
- [ ] 7.1 Say in prose's and bug-hunter's `DECISIONS.md` that the
      inquisitor's commits to a lore `questions` branch are machine records,
      exempt from their trailers, and say in prose's `DECISIONS.md` why its
      file filter skips files under `.inquisitor/` (task 5.6): they are
      records quoted word for word (decision 134)
- [ ] 7.2 Fold this change's lasting reasoning, from proposal.md and
      design.md, into a new `.agents/skills/inquisitor/DECISIONS.md`,
      the answer session's included, and
      fold the reasoning for moving the post reader into prose's
      `DECISIONS.md`, as `AGENTS.md` says
