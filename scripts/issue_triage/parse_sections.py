#!/usr/bin/env python3
"""Shared helpers for Cursor issue-triage workflow scripts."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

HEADING_RE = re.compile(
    r"(?im)^(RESULT|SUMMARY|ANALYSIS|ROOT_CAUSE|RECOMMENDATION|"
    r"REQUIRED_INFORMATION|PROPOSED_SOLUTION|PROBLEM|FILES_CHANGED|"
    r"CHANGES_MADE|TESTS_EXECUTED|TEST_RESULTS)\s*:"
)

BOT_ICON_URL = (
    "https://raw.githubusercontent.com/nitsan-technologies/t3planet-ai-bot/"
    "main/assets/bot-icon.png"
)

# Inline img + strong (no table) so GitHub does not draw a bordered box.
# align=absmiddle vertically centers the icon with the title text.
BOT_HEADER = (
    f'<img src="{BOT_ICON_URL}" width="22" height="22" '
    f'align="absmiddle" alt="" /> '
    "<strong>T3Planet AI Bot</strong>"
)


def parse_sections(text: str) -> dict[str, str]:
    matches = list(HEADING_RE.finditer(text))
    sections: dict[str, str] = {}

    for i, match in enumerate(matches):
        key = match.group(1).upper()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[key] = text[start:end].strip()

    return sections


def read_text(path: str | Path) -> str:
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def write_text(path: str | Path, content: str) -> None:
    Path(path).write_text(content.strip() + "\n", encoding="utf-8")


def fallback(value: str | None, default: str) -> str:
    value = (value or "").strip()
    return value if value else default


def bullet_list(text: str) -> str:
    lines = []

    for raw in text.splitlines():
        line = raw.strip()

        if not line:
            continue

        if line.startswith(("-", "*", "•")):
            lines.append("- " + line.lstrip("-*•").strip())
        else:
            lines.append("- " + line)

    return (
        "\n".join(lines)
        if lines
        else "- Additional details are required to investigate this issue."
    )


def load_comments(path: str | Path = "/tmp/issue-comments.json") -> list[dict]:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return []


def format_comments(comments: list[dict], empty_message: str) -> str:
    comment_context = []

    for comment in comments:
        user = comment.get("user") or {}
        login = user.get("login") or "unknown"
        body = comment.get("body") or ""
        comment_context.append(f"@{login}:\n{body}")

    comments_text = "\n\n---\n\n".join(comment_context)
    return comments_text if comments_text else empty_message


def changed_files_from_head() -> str:
    return subprocess.check_output(
        [
            "git",
            "diff-tree",
            "--no-commit-id",
            "--name-only",
            "-r",
            "HEAD",
        ],
        text=True,
    ).strip()
