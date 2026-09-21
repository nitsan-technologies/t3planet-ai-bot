#!/usr/bin/env python3
"""Format the issue comment that links the draft pull request."""

from __future__ import annotations

import os

from parse_sections import (
    BOT_HEADER,
    fallback,
    parse_sections,
    read_text,
    write_text,
)


def main() -> None:
    pr_url = os.environ.get("PR_URL", "").strip()
    output_path = os.environ.get("PR_COMMENT_PATH", "/tmp/pr-comment.md")

    resolve_text = read_text("/tmp/resolve-result.txt")
    triage_text = read_text("/tmp/triage-result.txt")
    resolve_sections = parse_sections(resolve_text)
    triage_sections = parse_sections(triage_text)

    summary = fallback(
        triage_sections.get("SUMMARY") or resolve_sections.get("PROBLEM"),
        "The fix is ready for review.",
    )

    comment = "\n".join(
        [
            BOT_HEADER,
            "",
            summary,
            "",
            f"Draft pull request: {pr_url}",
        ]
    )

    write_text(output_path, comment)


if __name__ == "__main__":
    main()
