# Brief: the inquisitor's answer-session UI (continue the prototype)

You're continuing a UI prototype with Adam. Read this, then load the mod and ask him what to change.

## What it is

The **answer session** is part of the `inquisitor` skill in adamstallard/shared-skills (spec: PR #25, branch `spec/inquisitor`, `openspec/changes/inquisitor/`; read it with `gh pr view 25 --json title,body,comments`). The inquisitor filters every question an agent is about to ask a person; questions that survive are relayed from subscribed channels (GitHub repos, Linear teams, Discord channels), asked by agents running the inquisitor or by people. In an **answer session** the user does nothing but answer them, in one immersive UI; each answer is posted back by a per-surface personal relay app account, prefixed "User says: ". Replies or mentions directed at the relay account count as new questions.

The UI is a **Claude Code mod** (plugin with a hooks module). This is a prototype with made-up questions; nothing is posted.

## Process rule (Adam's decision)

UI is **not specified**. Iterate on the prototype until Adam approves it by using it; then it goes **straight to an implementation PR** in shared-skills (into the inquisitor skill). Non-UI parts of the answer session — subscribing to channels, finding questions asked of him, relay accounts, setup — go through the normal spec PR → implementation PR process, separately. Don't write requirements about layout or interaction.

## Where everything is

- `~/answer-session-prototype/` is a local git repository (no remote); commit each iteration plainly, without prose or bug-hunter passes (Adam's decision: those run on the implementation PR).
- `~/answer-session-prototype/answer-session/` — the mod: `.claude-plugin/plugin.json`, `hooks/hooks.json`, `hooks/register.tsx`, `types/index.d.ts` (the `$.state` contract), `tests/answer-session.test.tsx`.
- `~/answer-session-prototype/sim/` — an Ink-based terminal mock that renders the pane to text (the official test kit lays out but doesn't paint). `npm install` once, then `./build.sh && node out/run.mjs 120x40 "t|What is it?"`; actions are `|`-separated: `type:<text>` puts text in the prompt box, `enter:<text>` or bare text presses Enter on it, `tick` fires pending timers; env `SLOW=1`, `MODEL_FAIL=1`, `PLACEMENT=inline`. It prints the prompt box under the pane and, after the frame, what each Enter did. Its padding is an approximation.
- `~/answer-session-prototype/captures/` — renders of each state from before input moved to the prompt box (dock 175×49, discussion, rephrased, ask-the-asker, returned, main-screen notice).
- Mod authoring docs and the API types: load the `plugin-authoring` skill; grep its `types/claude-code.d.ts` for `ButtonProps`, `InputProps`, `Pane: {`, `$.command.run`, `$.model.complete`, `$.store`.

## Load and check it

- In a new session: `claude --plugin-dir ~/answer-session-prototype/answer-session` (or copy it under the session's dev-mods folder when the plugin-authoring skill offers hot reloading).
- Real answer session: `CLAUDE_CODE_NO_FLICKER=0 INQUISITOR_ANSWER_SESSION=1 claude --plugin-dir ~/answer-session-prototype/answer-session` opens straight into the pane on the main screen. A background session can't show the main screen: it always uses fullscreen while attached. In any session, `/answer` opens it (registered `immediate`, so it runs mid-turn). Unasked, the engine seats a pane only from 144 columns (110 once opened before); below that, `/answer`.
- After every change: `claude plugin validate <mod>` (the author warning and the plugin directory's README and LICENSE checks are fine), `claude plugin test <mod>` (19 pass), and a type-check: `tsc -p <mod>` once the engine has loaded the mod and laid `.claude-plugin/types/`; before that, a tsconfig outside the mod using the options in the header of the plugin-authoring skill's `types/claude-code.d.ts`.

## What's built (and why)

- **Main screen at any width, on trial** (Adam, 2026-10-20). Fullscreen was the only layout until then; the docked view needs 110 columns, below which the engine caps a pane at half the screen. On the main screen the pane sits above the prompt box and asks for the terminal's full height; the earlier conversation scrolls off the top. Fullscreen still works: from 110 columns the pane docks floor to ceiling beside the engine's 24-column strip, and transcript and chrome components draw nothing while it is open. Under 110 columns in fullscreen, the pane says it has half the screen. If the main screen wins, the fullscreen code (hiding, the `/tui fullscreen` restart record in `$.store`) goes.
- **All input is in the prompt box, Enter confirms** (Adam, 2026-10-20). The pane opens without the keyboard and has no text fields or hotkeys. `intent()` reads the box's text against the screen: a digit chooses an option, one letter is a command (the key row lists them: `t` talk it through, `d` defer, `c` cite, `o` original, `p`/`n` previous/next, and in a discussion `r`, `a`, `b`, `k`/`j`), anything longer is an answer, or in a discussion a message to the model. The pane previews it live from a copy of the box (`prompt.edit` and `prompt.change` hooks into `$.state` `prompt`): the chosen option's `▌`, the post, and "Enter: …" in the key row. The `prompt.submit` hook does it and drops the prompt, so nothing reaches the model; its drop reason, which the person sees, says what was done. Slash commands and the engine's own prompts pass. A click on an option or a key-row item does the same as typing it. The model's ask-the-asker draft and a citation are put in the box with `$.prompt.fill`, the draft only into an empty box.
- **One focused screen** (inbox and triage layouts were dropped: they invited rubber-stamping). Top bar: progress dots (● relayed, ◐ deferred, ○ new, ◉ current, ◇ discussing, ◌ waiting for the asker), "1 of 8" and tallies; the engine's own close mark is the only close. Body in a centred column ≤ 88 wide: source + link + age; asker; the question (bold, spaced); context; related decision / "possibly answered". Options as separate blocks: `1: Label` bold, ★ recommended on the first, a dim indented `→ effect` under each; "Or type your own answer in the prompt box" (for a person's question, "Reply to <name>"). A relay preview shows exactly what will post ("WILL POST ON GITHUB AS adam-relay[bot]" / "│ User says: …"). Height-fitted: on short screens, labels, gaps and context give way before anything scrolls.
- **Discuss just this question** (`t`): the question stays pinned; the options area becomes a discussion with the session's model (`$.model.complete`, no streaming), which explains and helps him decide, not answers for him. What Enter will send shows under the exchange. `r` rephrases and asks again (marked "↻ Rephrased after your discussion", `o` shows the original; the real skill would log the rephrasing and a one-line summary with the answer). `b` back without changes. The queue resumes exactly where it was.
- **Ask the asker** (`a`, from the discussion): the model drafts a clarifying question into the prompt box, to edit there; the pane previews the post in the question's thread; on Enter the question is marked waiting and the queue moves on; the prototype simulates the reply after ~25 s and the question returns with the reply quoted (and revised options for agent questions).
- **Questions**: 8 made-up ones, including four real ones from igor PR #216, a free-form Linear question, a "possibly answered" one, and a reply to the relay account.

## Known limits

- Unverified in a live session: whether the engine clears the prompt box after a dropped prompt, and where the drop reason shows.
- The top bar's right end shows the build (`BUILD`, `v0.1-N`, N the commit count once committed: bump it with every commit) and the layout (fullscreen or main screen, docked or not).
- Claude Code 2.1.305 docks the pane at about 45% of the terminal's width (62 of 140 columns) whatever `columns` asks, also on `/answer`; nothing in `~/.claude.json` stores a width. Under 110 columns in fullscreen the pane is capped at half the height. Both caps reapply on every resize; asking again after a resize changed nothing (tested in tmux).
- Resizing the main screen in JetBrains' 2025 terminal leaves overlapping frames on the left (Adam, 2026-10-20). tmux redraws cleanly, so it is most likely how that terminal re-wraps lines; untested against a plain session without the mod.
- Tests can't raise `prompt.edit`, `prompt.change` or the engine's close (`ui.close`), and a test hook can't call `$`: the live preview and the close hook are untested. Tests drive Enter through `$.prompt.submit`.
- The host's scan refuses `$` passed through a value (`cmd.run($)`) or to a function whose name is reused: commands are data, and `runCommand` dispatches them.
- A mod's own calls skip its own hooks.
- A hot reload clears timers (a simulated asker reply pending during a reload stays waiting).
- Not hideable: the prompt box, fullscreen's 24-column strip (prompt box, welcome header), the pane's close-mark row, toasts, permission and AskUserQuestion dialogs, a status line.
- Desktop and mobile surfaces are out of scope for now.

## Next

1. Have Adam try it on the main screen (command above) and ask what to change; iterate (the sim helps you check spacing before he looks). Settle main screen versus fullscreen, then remove the loser's code.
2. When he approves the UI: open an implementation PR in shared-skills adding it to the inquisitor skill (coordinate with PR #25, whose implementation is gate two of that PR — ask Adam whether the UI PR builds on `spec/inquisitor` or waits for it to merge). Follow the repo's AGENTS.md and the bug-hunter and prose skills for the commit and PR.
3. Separately, the answer session's non-UI parts (channel subscription and polling, relay accounts, setup) become their own OpenSpec change.
