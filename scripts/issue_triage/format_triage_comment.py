#!/usr/bin/env python3
"""Format the issue comment for a Stage 1 triage result."""

from __future__ import annotations

import os

from parse_sections import BOT_HEADER, bullet_list, fallback, parse_sections, read_text, write_text


def main() -> None:
    result = os.environ.get("RESULT", "REVIEW_REQUIRED").strip()
    triage_path = os.environ.get("TRIAGE_RESULT_PATH", "/tmp/triage-result.txt")
    output_path = os.environ.get("ISSUE_COMMENT_PATH", "/tmp/issue-comment.md")

    triage_text = read_text(triage_path)
    sections = parse_sections(triage_text)

    explanation = fallback(
        sections.get("ANALYSIS") or sections.get("ROOT_CAUSE") or sections.get("SUMMARY"),
        triage_text or "No explanation was returned.",
    )
    required_information = fallback(
        sections.get("REQUIRED_INFORMATION"),
        "Please provide more information about the issue.",
    )

    if result == "NOT_AN_ISSUE":
        comment = "\n".join(
            [
                BOT_HEADER,
                "",
                "**No code change is needed.**",
                "",
                explanation,
            ]
        )
    elif result == "NEEDS_INFORMATION":
        comment = "\n".join(
            [
                BOT_HEADER,
                "",
                "**More information is needed:**",
                "",
                bullet_list(required_information),
                "",
                "Reply with these details and I will check the issue again.",
            ]
        )
    else:
        comment = "\n".join(
            [
                BOT_HEADER,
                "",
                "I could not classify this issue automatically. A maintainer should review it.",
                "",
                explanation,
            ]
        )

    write_text(output_path, comment)


if __name__ == "__main__":
    main()
