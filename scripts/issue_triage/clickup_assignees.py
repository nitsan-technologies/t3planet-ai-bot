#!/usr/bin/env python3
"""Resolve CLICKUP_ASSIGNEES (emails or ClickUp user ids) to workspace members.

Only people who are members of the configured workspace are assigned. ClickUp
rejects a task create that names an unknown user, so unknown entries are
skipped and logged instead of being sent.
"""

from __future__ import annotations

import re
from typing import Iterable, List, Tuple

MAX_ASSIGNEES = 10


def parse_spec(raw: str) -> List[str]:
    """Split a comma or whitespace separated list, dropping blanks and duplicates."""
    items: List[str] = []
    seen = set()
    for part in re.split(r"[,\s]+", raw or ""):
        value = part.strip()
        key = value.lower()
        if value and key not in seen:
            seen.add(key)
            items.append(value)
    return items[:MAX_ASSIGNEES]


def mask(entry: str) -> str:
    """Hide most of an email so public workflow logs do not expose it."""
    if "@" not in entry:
        return entry
    local, _, domain = entry.partition("@")
    return "%s***@%s" % (local[:1], domain)


def member_users(members: Iterable) -> List[dict]:
    users = []
    for member in members or []:
        user = member.get("user") if isinstance(member, dict) else None
        if isinstance(user, dict) and str(user.get("id") or "").isdigit():
            users.append(user)
    return users


def resolve(spec: List[str], members: Iterable) -> Tuple[List[int], List[str]]:
    """Return (ClickUp user ids to assign, entries that matched nobody)."""
    by_id = {}
    by_email = {}
    for user in member_users(members):
        user_id = int(user["id"])
        by_id[str(user_id)] = user_id
        email = str(user.get("email") or "").strip().lower()
        if email:
            by_email[email] = user_id
    ids: List[int] = []
    unknown: List[str] = []
    for entry in spec:
        user_id = by_id.get(entry) if entry.isdigit() else by_email.get(entry.lower())
        if user_id is None:
            unknown.append(entry)
        elif user_id not in ids:
            ids.append(user_id)
    return ids, unknown
