#!/usr/bin/env python3
"""Turn the issue resolver's job outputs into one ClickUp update.

The outputs come from a runner where the AI agent could run code, so every
value is validated against the GitHub context of this run before it is used.
"""

from __future__ import annotations

import re
from typing import Mapping, Optional

from clickup_client import clean
from clickup_task import IssueRef, Plan, truncate

RESULTS = {"VALID_ISSUE", "NOT_AN_ISSUE", "NEEDS_INFORMATION", "REVIEW_REQUIRED"}
SUMMARY_LIMIT = 1000


def issue_from_env(env: Mapping[str, str]) -> Optional[IssueRef]:
    repo = clean(env.get("GITHUB_REPOSITORY"))
    number = clean(env.get("ISSUE_NUMBER"))
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo) or not number.isdigit():
        print("ClickUp sync skipped: GitHub repository or issue number is missing.")
        return None
    return IssueRef(repo, number, env.get("ISSUE_TITLE") or "")


def valid_result(value: Optional[str]) -> str:
    result = clean(value).upper()
    return result if result in RESULTS else ""


def valid_branch(value: Optional[str], issue: IssueRef) -> str:
    branch = clean(value)
    return branch if branch == "ai/fix-issue-%s" % issue.number else ""


def valid_pr_url(value: Optional[str], issue: IssueRef) -> str:
    url = clean(value)
    pattern = r"https://github\.com/%s/pull/\d+" % re.escape(issue.repo)
    return url if re.fullmatch(pattern, url) else ""


def footer(issue: IssueRef, run_url: str) -> str:
    lines = ["GitHub issue: %s" % issue.url]
    if run_url:
        lines.append("Workflow run: %s" % run_url)
    return "\n".join(lines)


def compose(lines: list, issue: IssueRef, run_url: str) -> str:
    return "\n".join(lines + ["", footer(issue, run_url)])


def triage_lines(result: str, summary: str) -> list:
    lines = ["AI triage: %s" % result]
    if summary:
        lines.extend(["", "Summary (AI-generated):", summary])
    return lines


def plan_valid_issue(env, issue, summary, outcome, run_url) -> Plan:
    branch = valid_branch(env.get("BRANCH_NAME"), issue)
    pr_url = valid_pr_url(env.get("PR_URL"), issue)
    lines = triage_lines("VALID_ISSUE", summary) + [""]
    status_kind = None
    if pr_url:
        existing = clean(env.get("PR_ALREADY_EXISTS")).lower() == "true"
        if branch:
            lines.append("Branch: %s" % branch)
        label = "Pull request (already open)" if existing else "Draft pull request"
        lines.append("%s: %s" % (label, pr_url))
        status_kind = "in_progress"
    elif outcome == "failure":
        lines.append("The AI fix did not complete. No pull request was opened.")
    else:
        lines.append("The AI did not produce a code change. No pull request was opened.")
    return Plan(
        comment=compose(lines, issue, run_url),
        create=True,
        status_kind=status_kind,
        classification="VALID_ISSUE",
        branch=branch or None,
        pr_url=pr_url or None,
    )


def build_plan(env: Mapping[str, str], issue: IssueRef) -> Optional[Plan]:
    outcome = clean(env.get("RESOLVE_OUTCOME")).lower()
    if outcome in {"cancelled", "skipped"}:
        print("ClickUp sync skipped: resolver job was %s." % outcome)
        return None
    result = valid_result(env.get("RESULT"))
    summary = truncate(clean(env.get("TRIAGE_SUMMARY")), SUMMARY_LIMIT)
    run_url = clean(env.get("GITHUB_RUN_URL"))

    if not result:
        if outcome != "failure":
            print("ClickUp sync skipped: no triage result.")
            return None
        lines = ["T3Planet AI Bot failed before triage finished."]
        return Plan(comment=compose(lines, issue, run_url))

    if result == "VALID_ISSUE":
        return plan_valid_issue(env, issue, summary, outcome, run_url)

    if result == "NOT_AN_ISSUE":
        lines = triage_lines(result, summary) + ["", "Closed in ClickUp; no code change is needed."]
        return Plan(
            comment=compose(lines, issue, run_url),
            status_kind="done",
            classification=result,
        )

    lines = triage_lines(result, summary) + ["", "Waiting for more information on GitHub."]
    return Plan(comment=compose(lines, issue, run_url), create=True, classification=result)
