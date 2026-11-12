## Before gate one is approved

- [x] G.1 The repository's owner approves the prototype build covering thread replies and
      the recorded answer shown beside the question, and task 6.1's rule
      (d) names its tag. Done: build v0.1-33, tagged
      `answer-session-ui-approved-v0.1-33`

Gate two: the tasks below follow on this branch once the repository's owner approves the
spec.

## 0. Measure before building

Record each result that a requirement rests on as Evidence in its
capability's decision record, and the rest in design.md: *What the hook
relies on, not yet measured* for 0.1 to 0.3, both *Configuration* and *Facts measured
before building* for 0.4, *Facts measured
before building* for 0.5 to 0.14, and *Facts the answer session relies on*
for 0.15 to 0.28, including a result that
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
- [ ] 0.6 Record, from igor PR #216, the form of the fixed marker on igor's
      handback comments, a marker that no text the Igor quotes from its
      item can produce, by which the answer session tells a handback from
      the Igor's other comments (design.md: *igor's handback marker*)
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
- [x] 0.11 GitHub's API gives a comment's or review's author, and whether a
      commit's signature is verified and for which account (design.md: *A
      questions-branch decision needs a proven writer*). It does: GraphQL's
      `IssueComment` has `author { login }`, `createdAt` and
      `lastEditedAt`, and a commit's `signature { isValid state signer {
      login } wasSignedByGitHub }`, which for a merge commit on
      shared-skills' main read `VALID`, signed by GitHub's `web-flow`
      (2026-11-04). A person's own signature was not queried (task 0.22
      covers it). Reviews and review comments were not queried; GitHub
      documents the same `author`, `createdAt` and `lastEditedAt` on them
      through GraphQL's `Comment` interface. A comment is dated by
      `lastEditedAt`, or `createdAt` if never edited, and REST's
      `updated_at` is never read (design.md: *The newest proven answer
      counts*)
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
      design.md's *An Igor worker asks only in its handback comment*
      assumes it can't
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
      and that the identity can edit its own comment. If any fails, Linear
      stays off and the README says so
- [ ] 0.17 That a `discord-bot` identity, as merged in shared-skills PR #1,
      can read a subscribed channel's history and threads, see a mention
      of the person's user id and a reply to the relay's message, and edit
      its own message; and that a relay whose `check` reports
      `messageContent` `true` reads a message that doesn't mention the bot
      (design.md: *The Discord relay needs the Message Content intent*).
      If it can't, Discord stays off and the README says so
- [ ] 0.18 That a command the mod runs with `$.process.run` reaches no
      `PreToolUse` hook, so no post hook, on GitHub, Linear or Discord,
      sees a relay post (design.md:
      *A relay post gets no prose pass and no vetting*). If a hook does
      see it, record it and stop for the repository's owner
- [ ] 0.19 That a mod's timers keep polling every 60 seconds and
      refreshing the lock every 30 seconds while its session is idle or
      runs as a Claude Code background session, and how a session tells
      that it is one, so the lock can record it. If they stop, record it
      and stop for the repository's owner: a live holder's lock would go stale and another
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
      `performed_via_github_app` (design.md: *Only a listed relay App
      speaks for a person on GitHub*). These are not built until it is
      measured:
      - the inquisitor's *A relayed answer counts as its person's own
        comment*, with the relayed-answer proof of a questions-branch
        file's writer;
      - the inquisitor's *An Inquisitor reply is acted on only from a
        writer's relay App* and *A relay App's automatic post is no one's
        answer*;
      - on GitHub, the answer-session's *Relay posts start with a
        reserved prefix* and the relay-App attribution in *A relayed
        question is a person's question*;
      - on GitHub, the question state *The thread is the durable record
        of an answer* reads from relay posts, which needs relay posts
        recognised;
      - task 6.4's GitHub relaying, which needs that question state;
      - on GitHub, each rule that reads a `[bot]` author login: *A
        handback is an igor- App's comment holding igor's marker*, *An
        agent's question comes from a bot account or a log file* and *A
        relay-notice comment is shown as a notice*;
      - on GitHub, the rules that need to tell an agent's question:
        *Whom a message reaches is set by its mentions* and the
        automatic `Inquisitor: ` reply of *Filters 2 to 4 judge every
        incoming question*.

      If
      GitHub reports it, they are built as the spec states them; if not,
      the repository's owner decides what to build
- [ ] 0.22 What a reader needs to tie a relay file to its person
      (design.md: *Who last changed a relay file ties it to its person*):
      that GitHub's API gives, for the newest commit that changed
      `relays/<login>.yaml`, the merged pull request it came from and its
      author, after a merge commit, a squash and a rebase alike, such as
      through `commits/<sha>/pulls`; whether a commit GitHub signs itself,
      from its web editor or contents API, is verified for an account
      other than its author's, which would let anyone with push access
      make a commit verified for another person, and which also bears on *A questions-branch
      decision needs a proven writer*; and how a reader tells a signature
      GitHub made from the person's own, such as GraphQL's
      `wasSignedByGitHub`. If it can't tell, no signature counts. If the
      pull request can't be read, only a signature proves the file. Until
      this shows GitHub never verifies such a commit for someone who
      didn't make it, a signature GitHub made proves nothing
- [ ] 0.23 That the URL an asking agent records as `asked_in` (design.md:
      *A log file follows its thread message by exact link*), and the
      handback comment URL an Igor records (design.md: *Each Igor log file
      follows its own handback comment*), equals character for character
      the URL the answer session builds from what it polls, on GitHub,
      Linear and Discord. Compare an issue comment's URL with a pull
      request comment's, `html_url` with the notifications API's URL,
      `discord.com` with `discordapp.com`, and a Linear URL before and
      after the issue is renamed. Where they differ, define one canonical
      form both sides
      write and compare. Until measured, the asking agent records the URL
      its post command returns, and the answer session compares it as
      written
- [ ] 0.24 How setup can tell ahead of time that a commit the script
      pushes to a lore questions branch will be verified for the person
      (design.md: *Setup checks questions-branch commits are the
      person's*): git's `commit.gpgsign` and `user.signingkey` in the lore
      clone, the signing keys GitHub lists for the account, and whether
      the committer email is a verified address there; and that the `log`
      command, run with github-app's `GIT_AUTHOR_*`, `GIT_COMMITTER_*` and
      `GIT_CONFIG_*` settings removed, commits as the person in a project
      wired for an App. Until measured, setup shows the check as not
      checked
- [ ] 0.25 How GitHub, Linear and Discord each report a relay post refused
      for its text, such as its length, against one refused for lack of
      permission. This is the mapping the answer-session spec's *A refusal
      the session cannot place waits for the person* uses
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
- [ ] 0.27 List the tools of the Linear MCP servers an agent may have
      wired, such as Linear's own, and check that every tool named `get_…`,
      `list_…` or `search_…` only reads. If one writes, linear-app's post
      hook lists the reading tools by name instead (answer-session spec:
      *The Linear and Discord post hooks pass only the relay's readable posts*)
- [ ] 0.28 Post the line `Inquisitor: a person must decide this
      (required by spec-trace).` in a Linear comment and a Discord message,
      read each back as the answer session would, and record whether its
      words come back unchanged once markup is reduced. If not, record the
      form each surface returns, which the answer session then matches
      (answer-session spec: *A question with a person-required line gets
      no filter 2 to 4 reply*)

## 1. Shared post reader

- [ ] 1.1 Move prose's body reader, which finds a `gh` or GitHub MCP
      post's body, into `.agents/lib/gh-shell/`, beside the command
      splitter and gh flag tables already there, and build the `gh-post` rules on it. Each
      skill calls it from a thin script, and its behaviour changes only
      as tasks 1.3 and 2.9 list
- [ ] 1.2 prose's tests pass unchanged, except as task 1.3 allows; add the
      library's own tests beside it,
      each tagged `@scenario gh-post: <Scenario name>` for the `gh-post`
      spec's scenario it checks
- [ ] 1.3 The library also handles the following, with tests for each in
      prose's and the library's tests. prose's existing tests pass
      unchanged, except any existing test that expects a case blocked
      below or by task 2.9 to pass: change that test to expect the case
      blocked.
      - It reads a post's title, as a literal word, from `--title` or
        `-t`, a `gh api` `title` field under `issues` or `pulls`, the
        `title` argument of the GraphQL mutations that create or update
        an issue or pull request, and a GitHub MCP `title` key. A title it
        can't read, one built by the shell, and a title edit chained to
        another command are unreadable (design.md: *A post's title is read
        and vetted*).
      - It reads `python3 <github-app script> gh pr|issue|api …` posts,
        including `python3 $G …` only when the same command assigns `G`,
        and judges a line holding such a call exactly as the same line
        with the `gh` call made directly and no `G` assignment.
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
        only when that write is the whole command line. Any other mutation
        is no post, or unreadable when it has a `body` (design.md: *The
        reader reads gh api writes, REST and GraphQL*).
      - It reports whether a post creates an issue.
      - It blocks as unreadable a `gh api` call that writes, as the
        `gh-post` spec's *A gh api call writes by its method, fields,
        input or a mutation* says, whose body it can't read, a GraphQL query it can't parse,
        and a review whose comments it can't read.
      - It applies the closed list of gh post verbs, and blocks as
        unreadable, as prose's reader does today, a command that names
        `gh`, followed by another word, in another command's arguments,
        such as `sh -c`, unless that command is a data command given no
        code (gh-post spec: *The reader reads only gh's own top-level
        commands*), or that
        pipes into a command other than a data command.
      - On a line that mentions a gh post verb, it blocks as unreadable
        an interpreter with a code flag anywhere among its words, such as
        `python3 -W ignore -c`, `node -pe` or `perl -e`, and input from a
        pipe or heredoc reaching `python`, `python3` or `node` (design.md:
        *Code given on the command line beside a gh post verb*).

## 2. The script

- [ ] 2.1 `.agents/skills/inquisitor/scripts/inquisitor.py vet` (first
      call): `--questions`, and `--post` taking a post's body and title;
      prints the filters and filter 1's search results, and issues a token
- [ ] 2.2 `vet --pass <token> --verdicts <file>` (second call): the four
      verdicts and their fields, an `ask`'s related earlier decision, the
      person-required line printed for an `ask` naming the skill that
      requires it (inquisitor spec: *A question another skill requires
      carries a person-required line*), the
      three categories recorded by hash only, the refusals, and the records
      the hooks read, each deleted once it is more than 2 hours old
- [ ] 2.3 Filter 1's search. Items marked igor's are applied by
      `igor lore-search`, which igor PR #216 builds.
      - It searches decision documents, issues through `gh`, the
        repository's question log and misses, and configured lore
        clones' entries, `questions` branch and decision records at igor
        PR #202's path, fetched and read with `git show`.
      - It matches as plain text and ranks by terms matched, with a cap
        it reports.
      - During an Igor's run it searches lore only through `igor
        lore-search` (design.md: *Filter 1 in an Igor's run searches
        through `igor lore-search`*).
      - It applies the authority rules:
        - scope by the short name outside an Igor, and inside one as
          igor's `scopeMatches` gives it (igor's);
        - a decision record counted only when `accepted`;
        - a change's own decisions counted within that change;
        - a questions-branch `decision` file counted only with its
          writer proven by a linked comment or a verified signature
          (design.md: *A questions-branch decision needs a proven
          writer*), the comment holding the answer when its text equals
          the file's once both are reduced (design.md: *A linked comment
          holds the answer only when the texts are equal*);
        - a relayed answer counted only from an App the person's
          `relays/<login>.yaml` lists, and only when that file's last
          change came from that person, and never from a slug starting with `igor-`
          (design.md: *Only a listed relay App speaks for a person on
          GitHub*; *An Igor's App is never a relay App*);
        - only the newest answer counting among a question's files on a
          questions branch, a signature dated no later than when this
          machine first fetched its commit (design.md: *The newest proven
          answer counts*);
        - a file's visibility taken from the more private of whichever
          of `repository` and `asked_from` it holds (design.md: *Every
          questions-branch file names where it was asked from*);
        - during an Igor's run, a file about a repository other than the
          item's shown as input (igor's; design.md: *Questions-branch
          files and `project:` entries in a run's search*);
        - an `agent` file on a questions branch always input.
      - It reports each source it did not search, and when a fetch last
        updated each clone's remote-tracking default branch.
- [ ] 2.4 The `log` command, writing one file per question or miss in the
      format of *A log file and a miss file have one format*.
      - `authority` is `decision`, `input` or `agent`, with
        `answered_by: agent` for an agent's choice.
      - A log file for a question also asked in a post holds that post's
        URL as `asked_in`: a Linear or Discord one only in a private lore
        repository, a GitHub one only in a lore repository no more visible
        than the repository it points into (design.md: *`answer_link` and
        `asked_in` are withheld where they would leak*). Igor-worker mode
        writes no `asked_in`, because each Igor log file follows its own
        handback comment (design.md: *Each Igor log file follows its own
        handback comment*).
      - An answer file names the file it answers in `answers`, refused
        when the named file is not on the branch or already holds an
        answer (design.md: *An answer file names the file it answers*).
      - Built by igor, not this task: the Igor writes `answers` for a
        later run only for a file it finds by its own record's suffix
        and date (design.md: *A later run names the answered file from
        the Igor's record*).
      - On a questions branch, `repository` only on a file about one
        repository, and `asked_from` on every log and miss file except a
        handled file and a file written during an Igor's run. Outside a
        run it is the repository holding the current work; on a log or
        miss file the answer session writes, it is the `asked_from` the
        answer session passes to the `log` command (design.md: *Every
        questions-branch file names where it was asked from*;
        answer-session spec: *A miss records who judged it and where it
        was asked from*).
      - A handled file holds only `handled` and `closes`, the closed
        file's name, with no body (design.md: *The answer session writes
        a handled file on every close of a questions-branch file*). It is
        written only through the command's handled option, which only the
        answer session passes; a `handled` or `closes` key is refused
        without it; the command does not check its caller.
      - Each answer is written in quote lines (design.md: *A log file's
        answer is written as quote lines*):
        - with a github.com `answer_link`, read from the linked comment
          and recorded word for word;
        - with a Linear or Discord `answer_link`, recorded as given, its
          link never fetched, and only where the lore repository is
          private; elsewhere the file is written without the link
          (design.md: *Questions-branch answers relayed on Linear or
          Discord*);
        - any other answer a person gave, without an `answer_link`, in
          their own words as given (design.md: *A logged answer is the
          person's own words*).
      - A file goes in the repository's `.inquisitor/` for a question
        about it, by a pull request when it is not the repository
        holding the current work; or it is pushed to the team's lore
        repository's `questions` branch for a question about the
        organization or project, fetching and pushing again when
        rejected because the branch moved, and logging nothing when
        rejected otherwise.
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
      cite pushes a citation file*). It commits with
      `git -c commit.gpgsign=false`, so a person's signing setup never
      signs a citation with their key (design.md: *A citation's commit
      names no person*). It sends none for a question with a category,
      none to a lore repository more visible than the repository the
      question concerns, and none for a cited entry not `active` or out
      of scope. During an Igor's run it pushes nothing; igor PR #216's
      *An Igor publishes the citations its worker reports* covers it
- [ ] 2.5 The question finder for posts, one function the post hook also
      calls, finding questions in a post's title and body, with an
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
      tags no one
- [ ] 2.7 `lore`, opening a lore pull request, or a promotion from the
      `questions` branch, or refusing it by visibility or by an id outside
      igor's id rule. During an Igor's run it opens nothing and writes the
      entry into the run's report for the Igor to propose, as igor PR
      #216 is asked to (design.md: *A
      general answer is proposed as a provisional lore entry*)
- [ ] 2.8 `relay-notice.yml`, a lore repository's workflow template,
      modelled on the `templates/seat-notice.yml` that igor PR #171
      specifies (design.md:
      *A notice workflow mentions a relay file's person*)
- [ ] 2.9 Two refusals not built in tasks 1.3 and 2.4:
      - the `log` command's input file, refused unless it has mode 0600
        in a private directory;
      - in the post reader, on a line that mentions a gh post verb, `git`
        read as a data command only when its first word after `git` is an
        allowlisted subcommand and none of its words gives code to run, any
        other use, such as `git -C . status`, unreadable; and a `gh`
        alias or extension, such as `gh co`, unreadable on every line
        (design.md: *Which commands the reader judges, and which are
        unreadable*). Add tests for each to prose's and the library's
        tests

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
      only through the picker or its advisory*); blocks a post with a
      question when it can't read its records; blocks a question whose raw
      markdown matches the credential patterns; passes a `deferred`
      question less than 2 hours old that tags no one in an open-questions
      section or a new issue; and vets every post it sees, igor's handback
      included (design.md: *No exemption for an Igor's handback*). In
      the holder, it also blocks a post the reader does not report as
      sent through the github-app skill's script as the person's GitHub
      relay identity, named with `--identity` (answer-session spec:
      *In the holder, the model posts only as the person's relays*)
- [ ] 3.3 `hook.json` with both hooks, `"default": "enabled"`

## 4. Tests

- [ ] 4.1 `scripts/test_inquisitor.py`, standard library only, each test tagged
      `@scenario inquisitor: <Scenario name>` for the scenario it checks
- [ ] 4.2 Every scenario but the expected gaps has a tagged test:
      `spec_trace.py report --include-changes` marks only the expected
      gaps `none`. A scenario about what the agent does is tagged on a
      test that checks SKILL.md states the rule. An expected gap, a scenario only
      igor's unbuilt work can make pass, gets no test, not even a skipped
      one, and is listed by name in design.md's *Expected gaps* under
      *Tracing scenarios to tests*
- [ ] 4.3 Once igor provides `igor lore-search` and a role's `commands`
      can list the skill's script, build Igor-worker mode, write a tagged
      test for each expected gap, and remove it from design.md's list.
      The archive waits for this, because archiving moves the scenarios
      under `openspec/specs/`, where spec-trace's CI fails on an untagged
      scenario (task 7.0)

## 5. Docs and registration

- [ ] 5.1 `SKILL.md`: the filters, the two calls, writing a question at the
      privacy of what it concerns, posting no more publicly than that,
      that the person is accountable for what is posted as their relay
      and where, since no hook checks where a relay post goes
      (answer-session spec: *The person answers for what their relay posts*), the
      questions other skills require a person to decide and the
      person-required line copied exactly from the second call, preparing,
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
      blocked picker or post. It also says that, until github-app refuses
      `token`, `run`, `credential get` and `wire` for an identity marked
      as a relay, any agent on the person's machine can print a relay
      App's token and post `User says: ` unseen by the post hook
      (design.md: *github-app refuses `token`, `run`, `credential get` and
      `wire` for a relay identity*). It says too that uninstalling a
      compromised relay App, or revoking its key, stops it
- [ ] 5.3 A row in the README's skills table, and `inquisitor` in its list of
      skills that turn on a hook
- [ ] 5.4 `manage-skills` installs it and wires its hooks: check with
      `skills.py install inquisitor` and `skills.py doctor`
- [ ] 5.5 github-app's `SKILL.md`: every example that runs `python3 $G`
      sets `G` in the same command, or writes the script's full path, so
      the post hooks don't block it (design.md: *Posts sent through the github-app skill's script*)
- [ ] 5.6 prose's file filter skips files under `.inquisitor/` (inquisitor
      spec: *prose's pass skips files under .inquisitor/*), shipping with the skill,
      because the skill writes `.inquisitor/` files from gate two, this
      change's implementation, on
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

## 6. The answer session

- [ ] 6.0 Build on discord-bot as shared-skills PR #1 merged it
      (design.md: *Discord is in the first version, through discord-bot*).
      The Discord relay posts with no header option and with mention
      rewriting on, because discord-bot always posts that way (design.md:
      *Discord relay posts: no header, mentions
      that ping*)
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
          1, writing no answer file, only the handled file, where the
          prototype treats it as its own path and logs the recorded answer
          in a new file (design.md:
          *Agreeing to a recorded answer is a filter 1 decline*);
        - the question on screen kept in the state folder, not the mod's
          `$.store`, so a restarted session opens on it.
      - (c) A screen the spec needs that v0.1-33 lacks is designed in this
        task from the prototype's existing patterns, in no new visual
        style, with no prototype round of its own: setup, the lock
        message, the relay notice, a post's failure and discord-bot's
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
      the candidates; each relay check; saving the file with the person's
      own keys kept; a failed identity's surface or a failed channel left
      off and checked again at each opening; the Linear key in the
      keychain; `~/.local/bin/answer`; the pull request writing the
      person's `relays/<login>.yaml` in each serving lore repository
      (design.md: *One relay file per person*) and the one adding
      `relay-notice.yml` where missing; and the check, resolving what the
      `log` command would commit with once the github-app variables are
      removed, that commits to each lore questions branch are signed and
      use the person's identity, never an App's, warning how to fix it
      when not (design.md: *Setup checks questions-branch commits are the
      person's*). Filter 1 and every check that reads a comment's author
      read each `relays/<login>.yaml` from the lore clone's default
      branch, counted only when its last change came from its person
      (design.md: *Who last changed a relay file ties it to its person*)
- [ ] 6.3 Polling: the four sources, only while open, the catch-up on
      opening, 60 seconds or GitHub's `X-Poll-Interval`, conditional
      requests, poll positions, and the lore questions branches
- [ ] 6.4 Relaying: posts with the four reserved prefixes through the
      relay identity's skill as host commands, the `Re: ` line on GitHub
      and Linear posts, post ids, editing in place, the thread read before
      a question is shown and before each post, and a questions-branch
      question answered by a new log file, and again by a new one when its
      relayed answer is edited (design.md: *Editing a relay post*);
      discord-bot's warnings shown after each Discord relay post and edit;
      and, off GitHub, the relayed text logged with the relay post's URL
      as an unfetched `answer_link`
- [ ] 6.5 State: the state folder, a question's state read from its
      thread, closed questions, discussion records deleted once their
      question is answered or closed, the question on screen, and the lock,
      which a second session reports and offers to take over
- [ ] 6.6 The discussion's context, `propose_reply` (refusing a call as
      *Claude's draft goes to the prompt box, never to a post* says, and filling the record's URL for a filter 1
      decline), and the rephrased answer's post. SKILL.md tells an agent
      that records an answer from a relay post to log its rephrasing and
      summary
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
        - filter 1 on every incoming question and the `Recorded answer:
          ` post;
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
        only when it names filter 2, or names filter 3 or 4 and its last
        line apart from a `Re: ` line says the person chose it (design.md:
        *What an asking agent does with an automatic reply*; *A post the
        person chose says so*).
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
        - a log file whose link this machine does not read shown on its
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
          answer files naming one file, the newest is its answer and the
          older ones lose in the search too; only an answer file whose
          proof is the person's and whose commit adds it alone counts as
          a named file's answer (design.md: *`answers` decides a named
          file's answer; the search groups by hash*; *A named file's
          answer must be the person's own, added alone*);
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
        - the answer file pushed only after the thread is checked, none
          for an answer held back or dropped, and at once only for one
          whose channel is off or not subscribed, including one whose
          refused post turned it off;
        - no answer file, and a handled file instead, where the lore
          repository is more visible than the thread the answer was given
          in, a Linear or Discord thread counting as private;
        - the `log` command refusing an `answers` that names no file on
          the branch;
        - an answer file holding the question the person saw and naming
          the file it answers (design.md: *An answer file records the
          question the person saw*);
        - a second machine's miss pushed even when a matching one is on
          the branch;
        - a miss for a question a questions-branch file holds copying
          that file's `asked_from`, and its `repository` if it has one;
        - a later run naming a file only from the Igor's own record, by
          its file-name suffix and date, more than one match naming none
          (igor's; design.md: *A later run names the answered file from
          the Igor's record*).
      - For Igor items the tests also cover:
        - every Igor log file following its own handback comment, a link
          followed only from a marked `igor-` App handback in the
          repository the file's `asked_from` names (design.md: *Each Igor
          log file follows its own handback comment*; *igor's handback
          marker*);
        - an item shown only through its newest handback, an older
          unanswered handback passed over with nothing written and its
          file never shown again (design.md: *Only an item's newest
          handback is open*);
        - a bot's message reaching only the first person it mentions,
          and a person's message reaching each (design.md: *A bot's
          question reaches only the first person it mentions*);
        - a handback that mentions no one reaching the assignee, shown to
          no one on an unassigned item and never to this person on an
          item assigned to someone else (design.md: *A handback that
          mentions no one reaches the assignee*).
- [ ] 6.11 Decide at implementation, and when each choice is made, add
      it to the spec as a requirement with a scenario or, if no test can
      check it, to the answer-session decision record as an entry with
      evidence; design.md only links to it (design.md: *Some answer-session
      details are decided at implementation*): how a
      question's options are parsed from its thread; a draft's privacy,
      beyond its being written at the privacy of what the question
      concerns; an asker's reply revising the options; and the UI of the
      notice for the comment GitHub Actions posts when a pull request
      changes the person's relay file, designed from the prototype's
      existing patterns with no prototype round, as task 6.1's rule (c)
      says of a screen v0.1-33 lacks. Agreeing
      to a shown recorded answer is already decided (design.md: *Agreeing
      to a recorded answer is a filter 1 decline*), as are agreeing to a
      suggested verdict and citing a lore entry (answer-session spec:
      *Filters 2 to 4 only suggest a verdict on other questions*; *A
      person cites a lore entry by naming it as an answer or a record*)
- [ ] 6.12 discord-bot's post hook: `PreToolUse` on Bash, which, in the
      holder, blocks any line `.agents/lib/gh-shell/` cannot read that
      names `discord_bot.py` or runs a script of unknown path, and passes
      `post`, `edit` and `thread` only as the Discord relay identity with
      readable text and no reserved prefix, and `delete` only as that
      identity. Registered in
      discord-bot's `hook.json`, with tests (answer-session spec: *In the
      holder, the model posts only as the person's relays*)
- [ ] 6.13 linear-app's post hook: `PreToolUse` on Bash and Linear MCP
      tools, which, in the holder, blocks `token`, `headers`, `wire` and
      any line `.agents/lib/gh-shell/` cannot read that names
      `linear_app.py` or runs a script of unknown path, and passes a
      Linear MCP tool not named `get_…`, `list_…` or `search_…` only
      while Claude Code's MCP configuration shows linear-app wired that
      server to the Linear relay identity, and the tool's text starts
      with no reserved prefix. Registered in linear-app's `hook.json`,
      with tests (answer-session spec: *In the holder, the model posts
      only as the person's relays*)

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
      links to *An Igor publishes the citations its worker reports*, *An
      Igor publishes the questions-branch files its worker reports* and
      *An Igor runs its worker's lore searches* at igor's
      `openspec/specs/lore-firing/spec.md` on main, and its link to
      *Transcripts and outcomes are captured to the state branch* at
      igor's `openspec/specs/task-execution/spec.md` on main
- [ ] 7.1 Archive with `openspec archive` and no flags. This pull request already
      edits the decision records, `openspec/specs/inquisitor/decisions.md`,
      `openspec/specs/answer-session/decisions.md` and
      `openspec/specs/gh-post/decisions.md`, and archiving leaves them as
      they are. Write no `.agents/skills/inquisitor/DECISIONS.md`. Since
      design.md and tasks.md are archived with the change and not read
      again, point each requirement's citation of a measurement task 0.N
      at its measured result, each citation of a design.md section
      whose reason a decision record entry now gives at that entry, and
      each other citation of design.md at the archived design.md
