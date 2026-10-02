#!/usr/bin/env python3
"""Find, create, and update the one ClickUp task that mirrors a GitHub issue.

A task belongs to an issue only when it is in the configured list and its name
prefix or a description marker line names that exact issue. Task ids from
GitHub comments or environment variables are never trusted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from clickup_client import ClickUpClient, ClickUpError

BOILERPLATE = "GitHub is the source of truth. This ClickUp task only tracks progress."
OWNED_PREFIXES = (
    "GitHub issue:",
    "Title:",
    "Classification:",
    "Branch:",
    "Pull request:",
    BOILERPLATE,
)
META_KEYS = ("t3planet-classification", "t3planet-branch", "t3planet-pr")
NAME_LIMIT = 240
COMMENT_LIMIT = 8000


class IssueRef:
    def __init__(self, repo: str, number: str, title: str = "") -> None:
        self.repo = repo
        self.number = str(number)
        self.title = title or ""

    @property
    def prefix(self) -> str:
        return "[gh:%s#%s]" % (self.repo, self.number)

    @property
    def marker(self) -> str:
        return "t3planet-github-issue:%s#%s" % (self.repo, self.number)

    @property
    def url(self) -> str:
        return "https://github.com/%s/issues/%s" % (self.repo, self.number)


@dataclass
class Plan:
    """What one sync run should record on the issue's task."""

    comment: str
    create: bool = False
    status_kind: Optional[str] = None
    classification: Optional[str] = None
    branch: Optional[str] = None
    pr_url: Optional[str] = None


def truncate(text: str, limit: int) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[: limit - 15].rstrip() + "\n...[truncated]"


def task_description(task: dict) -> str:
    return task.get("description") or task.get("text_content") or ""


def task_matches(task: dict, issue: IssueRef) -> bool:
    if (task.get("name") or "").startswith(issue.prefix):
        return True
    return any(line.strip() == issue.marker for line in task_description(task).splitlines())


def parse_meta(text: str) -> dict:
    meta = {}
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped.startswith("t3planet-") or ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        meta[key] = value.strip()
    return meta


def extra_notes(existing: str) -> list:
    notes = []
    for line in (existing or "").splitlines():
        stripped = line.strip()
        if not stripped or stripped == "Notes:" or stripped.startswith("t3planet-"):
            continue
        if stripped.startswith(OWNED_PREFIXES):
            continue
        notes.append(line)
    return notes


def title_from_name(name: str, issue: IssueRef) -> str:
    if (name or "").startswith(issue.prefix):
        return name[len(issue.prefix):].strip()
    return ""


def render_description(issue: IssueRef, title: str, meta: dict, existing: str) -> str:
    lines = [
        "GitHub issue: %s" % issue.url,
        "Title: %s" % (title or "GitHub issue #%s" % issue.number),
        "Classification: %s" % (meta.get("t3planet-classification") or "pending"),
        "Branch: %s" % (meta.get("t3planet-branch") or "-"),
        "Pull request: %s" % (meta.get("t3planet-pr") or "-"),
        "",
        BOILERPLATE,
    ]
    notes = extra_notes(existing)
    if notes:
        lines.extend(["", "Notes:"])
        lines.extend(notes)
    lines.extend(["", issue.marker])
    for key in META_KEYS:
        if meta.get(key):
            lines.append("%s:%s" % (key, meta[key]))
    return "\n".join(lines) + "\n"


def task_name(issue: IssueRef, title: str) -> str:
    label = " ".join((title or "GitHub issue #%s" % issue.number).split())
    prefix = issue.prefix + " "
    if len(prefix) + len(label) > NAME_LIMIT:
        label = label[: NAME_LIMIT - len(prefix)].rstrip()
    return prefix + label


def current_status(task: dict) -> str:
    status = task.get("status")
    if isinstance(status, dict):
        return str(status.get("status") or "")
    return status if isinstance(status, str) else ""


def find_task(client: ClickUpClient, issue: IssueRef) -> Optional[dict]:
    matches = [task for task in client.list_tasks() if task_matches(task, issue)]
    if not matches:
        return None
    matches.sort(key=lambda task: str(task.get("date_created") or ""))
    if len(matches) > 1:
        print(
            "ClickUp found %s tasks for %s#%s; using the oldest (%s)."
            % (len(matches), issue.repo, issue.number, matches[0].get("id"))
        )
    return matches[0]


def plan_meta(plan: Plan, existing: str) -> dict:
    meta = parse_meta(existing)
    for key, value in (
        ("t3planet-classification", plan.classification),
        ("t3planet-branch", plan.branch),
        ("t3planet-pr", plan.pr_url),
    ):
        if value:
            meta[key] = value
    return meta


def create_task(client: ClickUpClient, issue: IssueRef, plan: Plan) -> dict:
    description = render_description(issue, issue.title, plan_meta(plan, ""), "")
    created = client.create_task(task_name(issue, issue.title), description)
    if not created.get("id"):
        raise ClickUpError("ClickUp create task returned no id")
    created.setdefault("description", description)
    print("ClickUp created task %s for %s#%s." % (created["id"], issue.repo, issue.number))
    return created


def changed_fields(issue: IssueRef, task: dict, plan: Plan, status: Optional[str]) -> dict:
    existing = task_description(task)
    title = issue.title or title_from_name(task.get("name") or "", issue)
    description = render_description(issue, title, plan_meta(plan, existing), existing)
    fields = {}
    if existing.strip() != description.strip():
        fields["description"] = description
        fields["markdown_content"] = description
    name = task_name(issue, title)
    if (task.get("name") or "") != name:
        fields["name"] = name
    if status and current_status(task).lower() != status.lower():
        fields["status"] = status
    return fields


def resolve_status(client: ClickUpClient, kind: Optional[str]) -> Optional[str]:
    if not kind:
        return None
    try:
        return client.resolve_status(kind)
    except ClickUpError as exc:
        print("ClickUp status lookup failed: %s" % exc)
        return None


def execute(client: ClickUpClient, issue: IssueRef, plan: Plan) -> None:
    task = find_task(client, issue)
    if task is None:
        if not plan.create:
            print("ClickUp has no task for %s#%s; nothing to update." % (issue.repo, issue.number))
            return
        task = create_task(client, issue, plan)
    task_id = str(task.get("id") or "")
    fields = changed_fields(issue, task, plan, resolve_status(client, plan.status_kind))
    if fields:
        try:
            client.update_task(task_id, fields)
        except ClickUpError as exc:
            print("ClickUp update failed: %s" % exc)
    if plan.comment:
        try:
            client.add_comment(task_id, truncate(plan.comment, COMMENT_LIMIT))
        except ClickUpError as exc:
            print("ClickUp comment failed: %s" % exc)
