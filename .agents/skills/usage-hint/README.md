# usage-hint

Shows your Claude subscription usage at the end of the hint line under the
prompt in Claude Code:

```
? for shortcuts  5h 60% ⇡ 12p · 7d 18% ⇣ Fri 9a
```

`5h` and `7d` are the five-hour and weekly windows: how much of each you have
used, and when it resets. A reset today shows only its time (`3p`, `3:07p`);
a later one adds the weekday (`Fri 9a`).

The arrow is your pace. Even pace is the share of the window already gone by:
two hours into a five-hour window is 40%. `⇡` means you have used more than
that, so at this rate you'll hit the limit before it resets; `⇣` means less.
Within 5 points of even pace there is no arrow.

It sends no requests and costs nothing. Claude Code already receives these
figures with every response, and the mod reads them from there.

This is a Claude Code mod, not a skill: once it's installed, there is nothing
to ask the agent and no command to run. Other agents don't load it.

## Install

Ask your agent:

> "Install the usage-hint mod"

It is linked into `~/.claude/skills/` only. A new Claude Code session loads it;
the one you installed it from may not. This needs the shared skills set up
first; see the [repository's README](../../../README.md#install).

## What to expect

- **Blank at first.** A new session has no figures until its first response
  comes back, so the usage appears after your first message.
- **Figures update as you work, not on a timer.** They change when a response
  reports a window moving a whole point, and hold still while the session is
  idle; the arrow still follows the clock. Usage from your other sessions
  shows up here at this session's next response.
- **Only the account this session is logged into.**
- **Nothing off a subscription.** With API-key billing or a third-party
  provider there are no figures, and the hint line is left as it is.
- **Cut at the edge.** On a narrow terminal the text is cut where the row
  ends rather than wrapping.

## Uninstall

Ask your agent to "uninstall the usage-hint mod".
