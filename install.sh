#!/usr/bin/env bash
# Installs the manage-skills skill, which installs everything else.
#
# It goes into every install target the script knows about — today
# ~/.agents/skills/ (the cross-tool location) and ~/.claude/skills/ (Claude
# Code's user-level skills directory). Nothing is written inside this repo.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$here/.agents/skills/manage-skills/scripts/skills.py" bootstrap
