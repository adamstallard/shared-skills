# Brief: the inquisitor's answer-session UI (continue the prototype)

You're continuing a UI prototype with Adam. Read this, then load the mod and ask him what to change.

## What it is

The **answer session** is part of the `inquisitor` skill in adamstallard/shared-skills (spec: PR #25, branch `spec/inquisitor`, `openspec/changes/inquisitor/`; read it with `gh pr view 25 --json title,body,comments`). The inquisitor filters every question an agent is about to ask a person; questions that survive are relayed from subscribed channels (GitHub repos, Linear teams, Discord channels), asked by agents running the inquisitor or by people. In an **answer session** the user does nothing but answer them, in one immersive UI; each answer is posted back by a per-surface personal relay app account, prefixed "User says: ". Replies or mentions directed at the relay account count as new questions.

The UI is a **Claude Code mod** (plugin with a hooks module). This is a prototype with made-up questions; nothing is posted.

## Process rule (Adam's decision)

UI is **not specified**. Iterate on the prototype until Adam approves it by using it; then it goes **straight to an implementation PR** in shared-skills (into the inquisitor skill). Non-UI parts of the answer session — subscribing to channels, finding questions asked of him, relay accounts, setup — go through the normal spec PR → implementation PR process, separately. Don't write requirements about layout or interaction.

## Where everything is

- `~/answer-session-prototype/answer-session/` — the mod: `.claude-plugin/plugin.json`, `hooks/hooks.json`, `hooks/register.tsx`, `types/index.d.ts` (the `$.state` contract), `tests/answer-session.test.tsx`.
- `~/answer-session-prototype/sim/` — an Ink-based terminal mock that renders the pane to text (the official test kit lays out but doesn't paint). `npm install` once, then `./build.sh && node out/run.mjs 175x49 "1"`; actions are `|`-separated: a hotkey (`t`, `1`, …), `say@<key prefix>:<text>`, `edit@<key prefix>:<text>`, `tick`; env `SLOW=1`, `MODEL_FAIL=1`. Its Input box and padding are approximations.
- `~/answer-session-prototype/captures/` — renders of each state (dock 175×49, discussion, rephrased, ask-the-asker, returned, main-screen notice).
- Mod authoring docs and the API types: load the `plugin-authoring` skill; grep its `types/claude-code.d.ts` for `ButtonProps`, `InputProps`, `Pane: {`, `$.command.run`, `$.model.complete`, `$.store`.

## Load and check it

- In a new session: `claude --plugin-dir ~/answer-session-prototype/answer-session` (or copy it under the session's dev-mods folder when the plugin-authoring skill offers hot reloading).
- Real answer session: `CLAUDE_CODE_NO_FLICKER=1 INQUISITOR_ANSWER_SESSION=1 claude --plugin-dir ~/answer-session-prototype/answer-session` — opens straight into the pane, in the fullscreen layout. In any session, `/answer` opens it (registered `immediate`, so it runs mid-turn).
- After every change: `claude plugin validate <mod>` (author warning is fine), `claude plugin test <mod>` (19 pass), and a type-check (the mod's own `tsconfig.json` extends `.claude-plugin/types/tsconfig.json`, which the engine lays when it loads the mod; `tsc -p <mod>`).

## What's built (and why)

- **Fullscreen only** (Adam's decision). In Claude Code's fullscreen (alternate-screen) layout the pane docks as a sidebar floor to ceiling, width = terminal − 24 (the engine always keeps 24 columns for the conversation; read from the binary). While the pane is open in fullscreen, transcript and chrome components (messages, tool calls, notices, spinner…) draw nothing; PromptHint reads "answer session · ctrl+x tab returns to it". On the main screen there's no hiding: a notice plus a plain pane, and `f: switch to fullscreen` runs `/tui fullscreen` via `$.command.run`, saving state in `$.store` so the pane reopens where he left off after the restart (untested end to end — the restart can't run in tests).
- **One focused screen** (inbox and triage layouts were dropped: they invited rubber-stamping). Top bar: progress dots (● relayed, ◐ deferred, ○ new, ◉ current, ◇ discussing, ◌ waiting for the asker), "1 of 8", `x: close` (**tests only** — the real session won't have it). Body in a centred column ≤ 88 wide: source + link + age; asker; the question (bold, spaced); context; related decision / "possibly answered". Options as separate blocks: `1: Label` bold, ★ recommended on the first, a dim indented `→ effect` under each, an accent `▌` on the chosen one; `w: Or answer in your own words` as one more option. A relay preview shows exactly what will post ("WILL POST ON GITHUB AS adam-relay[bot]" / "│ User says: …"); choose → preview → Enter (or `s`) relays; typed text previews live. Human questions get "Reply to <name>" with a larger field. Height-fitted: on short screens, labels, gaps and context give way before anything scrolls. Key hints pinned at the bottom.
- **Discuss just this question** (`t`): the question stays pinned; the options area becomes a discussion with the session's model (`$.model.complete`, no streaming), which explains and helps him decide, not answers for him. `r` rephrases and asks again (marked "↻ Rephrased after your discussion", `o` shows the original; the real skill would log the rephrasing and a one-line summary with the answer). `b` back without changes. The queue resumes exactly where it was.
- **Ask the asker** (`a`, from the discussion): the model drafts a clarifying question; editable; preview of the post in the question's thread; on send the question is marked waiting and the queue moves on; the prototype simulates the reply after ~25 s and the question returns with the reply quoted (and revised options for agent questions).
- **Questions**: 8 made-up ones, including four real ones from igor PR #216, a free-form Linear question, a "possibly answered" one, and a reply to the relay account.

## Known limits

- While a text field has focus, letters type; Tab leaves the field (Esc returns the keyboard to the prompt, so it can't mean "back").
- A mod's own calls skip its own hooks (found by the tests); the close button and `f` do their work directly.
- A hot reload clears timers (a simulated asker reply pending during a reload stays waiting).
- Not hideable: the 24-column strip (prompt box, welcome header), the pane's close-mark row, toasts, permission and AskUserQuestion dialogs, a status line.
- Desktop and mobile surfaces are out of scope for now.

## Next

1. Load it in fullscreen and ask Adam what to change; iterate (sim captures help you check spacing before he looks).
2. When he approves the UI: open an implementation PR in shared-skills adding it to the inquisitor skill (coordinate with PR #25, whose implementation is gate two of that PR — ask Adam whether the UI PR builds on `spec/inquisitor` or waits for it to merge). Follow the repo's AGENTS.md and the bug-hunter and prose skills for the commit and PR.
3. Separately, the answer session's non-UI parts (channel subscription and polling, relay accounts, setup) become their own OpenSpec change.
