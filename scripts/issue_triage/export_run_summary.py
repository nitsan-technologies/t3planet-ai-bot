#!/usr/bin/env python3
"""Expose the resolver outcome as job outputs for the ClickUp job.

Values are flattened to one line, and the triage summary uses a random
delimiter so its text cannot inject extra outputs. The ClickUp job still
validates everything, because this runner also ran the AI agent.
"""

from __future__ import annotations

import os
import secrets
import sys

from parse_sections import parse_sections, read_text

FIELDS = (
    ("result", "RESULT"),
    ("branch", "BRANCH_NAME"),
    ("pr_url", "PR_URL"),
    ("pr_already_exists", "PR_ALREADY_EXISTS"),
)
SUMMARY_LIMIT = 1000


def one_line(value: str) -> str:
    return " ".join((value or "").split())[:500]


def main() -> int:
    output = os.environ.get("GITHUB_OUTPUT")
    if not output:
        print("GITHUB_OUTPUT is not set; nothing exported.")
        return 0
    triage_path = os.environ.get("TRIAGE_RESULT_PATH") or "/tmp/triage-result.txt"
    summary = parse_sections(read_text(triage_path)).get("SUMMARY", "")[:SUMMARY_LIMIT]
    delimiter = "T3PLANET_EOF_" + secrets.token_hex(16)
    lines = ["%s=%s" % (key, one_line(os.environ.get(name, ""))) for key, name in FIELDS]
    lines.append("triage_summary<<%s" % delimiter)
    lines.append(summary.replace(delimiter, ""))
    lines.append(delimiter)
    with open(output, "a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
