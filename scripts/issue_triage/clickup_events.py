#!/usr/bin/env python3
"""Map pull request and issue-close events onto an existing ClickUp task.

This path only updates tasks the issue resolver already created. It never
creates a task, so closing an old issue or merging an unrelated pull request
does not add anything to ClickUp.
"""

from __future__ import annotations

import json
import os
import re
from typing import Mapping, Optional, Tuple

from clickup_client import clean
from clickup_task import IssueRef, Plan, truncate

ISSUE_LINK = re.compile(
    r"(?i)\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?|relates to)\s+#(\d+)\b"
)
BRANCH_LINK = re.compile(r"ai/fix-issue-(\d+)")
PR_LABELS = {
    "opened": "Pull request opened",
    "edited": "Pull request updated",
    "synchronize": "New commits were pushed to the pull request",
    "reopened": "Pull request reopened",
    "ready_for_review": "Pull request is ready for review",
    "converted_to_draft": "Pull request converted to draft",
}


def linked_issue_number(pr: dict) -> str:
    head = ((pr.get("head") or {}).get("ref") or "").strip()
    branch_match = BRANCH_LINK.fullmatch(head)
    if branch_match:
        return branch_match.group(1)
    for blob in (pr.get("title") or "", pr.get("body") or ""):
        match = ISSUE_LINK.search(blob)
        if match:
            return match.group(1)
    return ""


def load_payload(env: Mapping[str, str]) -> Optional[dict]:
    path = clean(env.get("CLICKUP_EVENT_PATH")) or clean(env.get("GITHUB_EVENT_PATH"))
    if not path or not os.path.isfile(path):
        print("ClickUp github-event: no event payload file; skipping.")
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError) as exc:
        print("ClickUp github-event: could not read event payload: %s" % exc)
        return None
    return payload if isinstance(payload, dict) else None


def repo_of(payload: dict, env: Mapping[str, str]) -> str:
    return clean((payload.get("repository") or {}).get("full_name")) or clean(
        env.get("GITHUB_REPOSITORY")
    )


def issue_closed_plan(payload: dict, repo: str) -> Optional[Tuple[IssueRef, Plan]]:
    issue = payload.get("issue") or {}
    if issue.get("pull_request"):
        print("ClickUp sync skipped: issues event is a pull request.")
        return None
    number = str(issue.get("number") or "")
    if not number.isdigit():
        return None
    ref = IssueRef(repo, number, issue.get("title") or "")
    reason = clean(issue.get("state_reason"))
    suffix = " (%s)" % reason if reason else ""
    text = "GitHub issue #%s was closed%s.\n%s" % (number, suffix, ref.url)
    return ref, Plan(comment=text, status_kind="done")


def review_text(payload: dict, pr_url: str) -> str:
    review = payload.get("review") or {}
    user = (review.get("user") or {}).get("login") or "someone"
    state = review.get("state") or "commented"
    text = "Pull request review by %s: %s." % (user, state)
    body = truncate(review.get("body") or "", 2000).strip()
    if body:
        text += "\n\n" + body
    return text + "\n\n" + pr_url


def pull_request_plan(event: str, action: str, payload: dict, repo: str):
    pr = payload.get("pull_request") or {}
    number = linked_issue_number(pr)
    if not number:
        print("ClickUp sync skipped: pull request is not linked to a GitHub issue.")
        return None
    ref = IssueRef(repo, number)
    pr_url = pr.get("html_url") or ""
    if event == "pull_request_review":
        return ref, Plan(comment=review_text(payload, pr_url), pr_url=pr_url or None)
    if action == "closed" and pr.get("merged"):
        sha = pr.get("merge_commit_sha") or ""
        text = "Pull request merged: %s" % pr_url
        if sha:
            text += "\nMerge commit: https://github.com/%s/commit/%s" % (repo, sha)
        return ref, Plan(comment=text, status_kind="done", pr_url=pr_url or None)
    if action == "closed":
        return ref, Plan(comment="Pull request closed without merge: %s" % pr_url)
    label = PR_LABELS.get(action, "Pull request event %s" % (action or "unknown"))
    if action == "opened" and pr.get("draft"):
        label = "Draft pull request opened"
    text = "%s: %s" % (label, pr_url)
    head_sha = (pr.get("head") or {}).get("sha") or ""
    if action == "synchronize" and head_sha:
        text += "\nHead: %s" % head_sha
    return ref, Plan(comment=text, pr_url=pr_url or None)


def build_plan(env: Mapping[str, str]) -> Optional[Tuple[IssueRef, Plan]]:
    payload = load_payload(env)
    if payload is None:
        return None
    event = clean(env.get("EVENT_NAME")) or clean(env.get("GITHUB_EVENT_NAME"))
    action = clean(payload.get("action")) or clean(env.get("EVENT_ACTION"))
    repo = repo_of(payload, env)
    if not repo:
        print("ClickUp sync skipped: repository is unknown.")
        return None
    if event == "issues":
        if action != "closed":
            print("ClickUp sync skipped: issues action %s is not closed." % (action or "unknown"))
            return None
        return issue_closed_plan(payload, repo)
    if event in {"pull_request", "pull_request_review"} and payload.get("pull_request"):
        return pull_request_plan(event, action, payload, repo)
    print("ClickUp sync skipped: unsupported event %s." % (event or "unknown"))
    return None
