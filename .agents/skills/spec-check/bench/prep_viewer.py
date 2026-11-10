"""Lay out an iteration for skill-creator's eval viewer
(eval-viewer/generate_review.py): an outputs/ folder in each run, holding
report.md and changes.patch, and an eval_metadata.json in each case.

    python3 -I prep_viewer.py <iteration-dir>
"""

from __future__ import annotations

import json
import pathlib
import shutil
import sys
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
RUBRICS: dict[str, Any] = json.loads((HERE / "rubrics.json").read_text())


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: python3 -I prep_viewer.py <iteration-dir>")
    for i, ev in enumerate(sorted(pathlib.Path(sys.argv[1]).glob("eval-*"))):
        case = ev.name.removeprefix("eval-")
        rub = RUBRICS["cases"].get(case)
        if rub is None:
            continue
        (ev / "eval_metadata.json").write_text(json.dumps({
            "eval_id": i, "eval_name": case, "prompt": RUBRICS["prompt"],
            "assertions": rub["must"] + rub["must_not"] + RUBRICS["common_must_not"]}, indent=1))
        for run in ev.glob("*/run-*"):
            out = run / "outputs"
            out.mkdir(exist_ok=True)
            for name in ("report.md", "changes.patch"):
                if (run / name).exists():
                    shutil.copy(run / name, out / name)


if __name__ == "__main__":
    main()
