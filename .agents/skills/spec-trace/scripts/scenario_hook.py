#!/usr/bin/env python3
"""spec-trace's hook, run after the agent writes or edits a file.

When the file is an OpenSpec spec (openspec/specs/**/spec.md, or
openspec/changes/<name>/specs/**/spec.md) in a repository that has neither
adopted nor declined spec-trace, it tells the agent to ask the user which.
Otherwise it prints nothing.

Usage: scenario_hook.py --host claude|cursor   (hook payload on stdin)

The work is in spec_trace.py (hook_message). This file only reports it the way
each host reads it. It never blocks and fails open: any error means silence.
"""

import json
import os
import sys


def main(argv):
    host = argv[argv.index("--host") + 1] if "--host" in argv[:-1] else None
    try:
        raw = sys.stdin.read()
        # Most writes are not specs: skip importing the checker for them.
        if "spec.md" not in raw:
            return 0
        sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
        import spec_trace
        message = spec_trace.hook_message(json.loads(raw))
    except Exception:  # noqa: BLE001 - a hook that crashes must stay quiet
        return 0
    if not message:
        return 0
    if host == "claude":
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                                 "additionalContext": message}}))
    elif host == "cursor":
        print(json.dumps({"additional_context": message}))
    else:
        print(message, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
