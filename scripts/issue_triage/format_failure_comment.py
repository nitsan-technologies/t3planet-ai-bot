#!/usr/bin/env python3
"""Format a short issue comment when the Cursor workflow fails."""

from __future__ import annotations

import os
from pathlib import Path

from parse_sections import BOT_HEADER, write_text


def detect_stage() -> str:
    stage = (os.environ.get("CURSOR_STAGE") or "").strip()
    if stage:
        return stage

    try:
        return Path("/tmp/cursor-stage.txt").read_text(encoding="utf-8").strip() or "unknown"
    except FileNotFoundError:
        return "unknown"


def detect_exit_code() -> str:
    code = (os.environ.get("CURSOR_EXIT_CODE") or "").strip()
    if code:
        return code

    try:
        return Path("/tmp/cursor-exit-code.txt").read_text(encoding="utf-8").strip() or "unknown"
    except FileNotFoundError:
        return "unknown"


def main() -> None:
    output_path = os.environ.get("FAILURE_COMMENT_PATH", "/tmp/failure-comment.md")
    stage = detect_stage()
    exit_code = detect_exit_code()
    run_url = (os.environ.get("GITHUB_RUN_URL") or "").strip()

    if stage == "resolve":
        headline = "The automated implementation step failed."
    elif stage == "triage":
        headline = "The automated triage step failed."
    else:
        headline = "The automated issue workflow failed."

    lines = [
        BOT_HEADER,
        "",
        "### Automation Failed",
        "",
        headline,
        "",
        f"**Stage:** `{stage}`",
        "",
        f"**Exit code:** `{exit_code}`",
        "",
    ]

    if run_url:
        lines.extend(
            [
                f"See the [Actions log]({run_url}) for details.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "See the GitHub Actions log for this run for details.",
                "",
            ]
        )

    lines.append(
        "No Pull Request was created. A maintainer can re-run the workflow after checking the failure."
    )

    write_text(output_path, "\n".join(lines))
    print(f"Wrote failure comment to {Path(output_path)}")


if __name__ == "__main__":
    main()
