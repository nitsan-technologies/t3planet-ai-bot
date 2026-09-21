#!/usr/bin/env python3
"""Format the draft pull request body from triage and resolve reports."""

from __future__ import annotations

import os

from parse_sections import (
    BOT_HEADER,
    changed_files_from_head,
    fallback,
    parse_sections,
    read_text,
    write_text,
)


def main() -> None:
    issue_number = os.environ["ISSUE_NUMBER"]
    issue_title = os.environ.get("ISSUE_TITLE") or ""
    output_path = os.environ.get("PR_BODY_PATH", "/tmp/pr-body.md")
    title_path = os.environ.get("PR_TITLE_PATH", "/tmp/pr-title.txt")

    resolve_text = read_text("/tmp/resolve-result.txt")
    triage_text = read_text("/tmp/triage-result.txt")
    resolve_sections = parse_sections(resolve_text)
    triage_sections = parse_sections(triage_text)

    changed_files = changed_files_from_head()

    problem = fallback(
        resolve_sections.get("PROBLEM") or triage_sections.get("SUMMARY"),
        "GitHub Issue #" + issue_number + "\n\n**" + issue_title + "**",
    )
    root_cause = fallback(
        resolve_sections.get("ROOT_CAUSE") or triage_sections.get("ROOT_CAUSE"),
        "See the analysis in this Pull Request.",
    )
    changes = fallback(
        resolve_sections.get("CHANGES_MADE"),
        "Automated changes were committed for this issue.",
    )
    files = fallback(
        changed_files or resolve_sections.get("FILES_CHANGED"),
        "See the Pull Request diff.",
    )
    tests_executed = fallback(
        resolve_sections.get("TESTS_EXECUTED"),
        "See the Pull Request for test details.",
    )
    test_results = fallback(resolve_sections.get("TEST_RESULTS"), "")
    tests = tests_executed if not test_results else tests_executed + "\n\n" + test_results

    project_tests = read_text("/tmp/project-test-status.txt")
    if project_tests:
        tests = tests + "\n\n### Project suite (Actions)\n\n" + project_tests

    body = "\n".join(
        [
            BOT_HEADER,
            "",
            "### 📋 Problem",
            "",
            problem,
            "",
            "### 🔎 Root Cause",
            "",
            root_cause,
            "",
            "### 🛠️ Changes",
            "",
            changes,
            "",
            "### 📁 Files Changed",
            "",
            "```",
            files,
            "```",
            "",
            "### 🧪 Tests",
            "",
            tests,
            "",
            "### 🚀 Review",
            "",
            "Please review the changes before merging.",
            "",
            "Relates to #" + issue_number,
        ]
    )

    write_text(output_path, body)

    # Write title via Python so the workflow never expands ISSUE_TITLE in bash.
    title = f"Fix #{issue_number}: {issue_title}".replace("\n", " ").strip()
    write_text(title_path, title)


if __name__ == "__main__":
    main()
