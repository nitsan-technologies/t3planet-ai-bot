#!/usr/bin/env python3
"""Small ClickUp API client used by the ClickUp tracking jobs.

Nothing in this module talks to the network unless a caller builds a
ClickUpClient. load_config() returns None when tracking is off or incomplete,
and callers must stop there.

The API base can only point at api.clickup.com or a local test server, so a
tampered environment cannot redirect the token to another host.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping, Optional

DEFAULT_API_BASE = "https://api.clickup.com/api/v2"
_CLICKUP_HOST = "api.clickup.com"
_TEST_HOSTS = {"127.0.0.1", "localhost"}
_TRUTHY = {"1", "true", "yes", "on"}


_RETRYABLE = {429, 500, 502, 503, 504}
_DEFAULT_RETRY_DELAYS = (1.0, 2.0)
_RETRY_AFTER_CAP = 8.0
TASK_PAGE_CAP = 10
TASK_PAGE_SIZE = 100


class ClickUpError(Exception):
    def __init__(self, message: str, status: Optional[int] = None, retry_after: Optional[float] = None) -> None:
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after


@dataclass(frozen=True)
class ClickUpConfig:
    token: str
    team_id: str
    list_id: str
    api_base: str
    assignees: str = ""


def clean(value: Optional[str]) -> str:
    return (value or "").strip()


def is_enabled(env: Optional[Mapping[str, str]] = None) -> bool:
    source = os.environ if env is None else env
    return clean(source.get("CLICKUP_ENABLED")).lower() in _TRUTHY


def resolve_api_base(value: Optional[str]) -> str:
    """Return the ClickUp API base, refusing any host except ClickUp or loopback."""
    raw = clean(value)
    if not raw:
        return DEFAULT_API_BASE
    parsed = urllib.parse.urlparse(raw)
    host = (parsed.hostname or "").lower()
    if parsed.scheme == "https" and host == _CLICKUP_HOST:
        return raw.rstrip("/")
    if parsed.scheme == "http" and host in _TEST_HOSTS:
        return raw.rstrip("/")
    print(
        "ClickUp ignored CLICKUP_API_BASE: only https://api.clickup.com "
        "or a local test server is allowed."
    )
    return DEFAULT_API_BASE


def retry_delays(env: Optional[Mapping[str, str]] = None) -> tuple:
    """Seconds to wait before each retry. CLICKUP_RETRY_DELAYS overrides this in tests."""
    source = os.environ if env is None else env
    raw = clean(source.get("CLICKUP_RETRY_DELAYS"))
    if not raw:
        return _DEFAULT_RETRY_DELAYS
    values = []
    for part in raw.split(","):
        try:
            values.append(min(_RETRY_AFTER_CAP, max(0.0, float(part))))
        except ValueError:
            continue
    return tuple(values[:4]) or _DEFAULT_RETRY_DELAYS


def _can_retry(method: str, exc: "ClickUpError") -> bool:
    if exc.status == 429:
        return True
    return method.upper() == "GET" and exc.status in _RETRYABLE


def retry_after_seconds(header: Optional[str]) -> Optional[float]:
    if header and header.strip().isdigit():
        return min(_RETRY_AFTER_CAP, float(header.strip()))
    return None


def redact(message: str, token: str) -> str:
    if token and len(token) >= 8 and token in message:
        return message.replace(token, "[redacted]")
    return message


def load_config(env: Optional[Mapping[str, str]] = None) -> Optional[ClickUpConfig]:
    """Return settings only when tracking is explicitly enabled and complete.

    Disabled, empty, missing, or partial configuration returns None so the
    caller does not open an HTTP client.
    """
    source = os.environ if env is None else env
    if not is_enabled(source):
        print("ClickUp disabled; skipping (no API calls).")
        return None
    token = clean(source.get("CLICKUP_API_TOKEN"))
    team_id = clean(source.get("CLICKUP_TEAM_ID"))
    list_id = clean(source.get("CLICKUP_LIST_ID"))
    missing = [
        name
        for name, value in (
            ("CLICKUP_API_TOKEN", token),
            ("CLICKUP_TEAM_ID", team_id),
            ("CLICKUP_LIST_ID", list_id),
        )
        if not value
    ]
    if missing:
        print(
            "ClickUp enabled but missing required settings: "
            + ", ".join(missing)
            + "; skipping (no API calls)."
        )
        return None
    return ClickUpConfig(
        token=token,
        team_id=team_id,
        list_id=list_id,
        api_base=resolve_api_base(source.get("CLICKUP_API_BASE")),
        assignees=clean(source.get("CLICKUP_ASSIGNEES")),
    )


class ClickUpClient:
    def __init__(self, config: ClickUpConfig, timeout: float = 20.0) -> None:
        self.config = config
        self.timeout = timeout
        self._statuses: Optional[list] = None
        self._team: Optional[dict] = None

    def request(
        self,
        method: str,
        path: str,
        body: Optional[dict] = None,
        query: Optional[dict] = None,
    ) -> Any:
        """Call the ClickUp API.

        HTTP 429 is retried for every call. HTTP 5xx is retried for GET only:
        a create or comment that failed with 500 may already have been saved.
        """
        delays = retry_delays()
        for attempt, delay in enumerate(delays):
            try:
                return self._request_once(method, path, body, query)
            except ClickUpError as exc:
                if not _can_retry(method, exc):
                    raise
                wait = delay if exc.retry_after is None else exc.retry_after
                print(
                    "ClickUp %s %s failed with HTTP %s; retrying in %ss (%s/%s)."
                    % (method, path, exc.status, wait, attempt + 1, len(delays))
                )
                time.sleep(wait)
        return self._request_once(method, path, body, query)

    def _request_once(
        self,
        method: str,
        path: str,
        body: Optional[dict] = None,
        query: Optional[dict] = None,
    ) -> Any:
        url = self.config.api_base + path
        if query:
            parts = []
            for key, value in query.items():
                if isinstance(value, (list, tuple)):
                    for item in value:
                        parts.append((key, str(item)))
                elif value is not None:
                    parts.append((key, str(value)))
            if parts:
                url += "?" + urllib.parse.urlencode(parts)
        data = None
        headers = {
            "Authorization": self.config.token,
            "Accept": "application/json",
        }
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        print(f"ClickUp {method} {path}")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                payload = exc.read().decode("utf-8", errors="replace")[:500]
                parsed = json.loads(payload)
                if isinstance(parsed, dict):
                    detail = str(parsed.get("err") or parsed.get("error") or "")[:300]
            except (OSError, ValueError, UnicodeError):
                detail = ""
            message = f"ClickUp {method} {path} failed with HTTP {exc.code}"
            if detail:
                message += ": " + detail
            headers = getattr(exc, "headers", None)
            raise ClickUpError(
                redact(message, self.config.token),
                status=exc.code,
                retry_after=retry_after_seconds(headers.get("Retry-After") if headers else None),
            ) from None
        except urllib.error.URLError as exc:
            reason = redact(str(exc.reason), self.config.token)
            raise ClickUpError(f"ClickUp {method} {path} failed: {reason}") from None
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            raise ClickUpError(f"ClickUp {method} {path} returned invalid JSON") from None

    def ensure_team(self) -> dict:
        if self._team is not None:
            return self._team
        data = self.request("GET", "/team")
        teams = data.get("teams") if isinstance(data, dict) else None
        if not isinstance(teams, list):
            raise ClickUpError("ClickUp /team response did not include teams")
        wanted = self.config.team_id
        for team in teams:
            if isinstance(team, dict) and str(team.get("id")) == wanted:
                self._team = team
                return team
        raise ClickUpError(
            f"ClickUp team {wanted} is not accessible to this token. Skipping."
        )

    def team_members(self) -> list:
        members = self.ensure_team().get("members")
        return members if isinstance(members, list) else []

    def get_list(self) -> dict:
        data = self.request("GET", f"/list/{urllib.parse.quote(self.config.list_id)}")
        return data if isinstance(data, dict) else {}

    def list_task_pages(
        self,
        max_pages: int = TASK_PAGE_CAP,
        newest_first: bool = True,
        stop_when=None,
    ):
        """Page this list. Newest first by default.

        ClickUp has no name search, so the list id is the only server filter.
        Newest-first keeps recent bot mirrors in the first pages on large lists.
        stop_when(batch) may end the scan early when a match is already found.
        Returns (pages, complete). complete is false when the page cap or an
        error stops the scan early.
        """
        pages = []
        complete = False
        list_id = urllib.parse.quote(self.config.list_id)
        query = {
            "page": 0,
            "include_closed": "true",
            "subtasks": "true",
            "order_by": "created",
        }
        if newest_first:
            query["reverse"] = "true"
        for page in range(max_pages):
            query["page"] = page
            try:
                data = self.request(
                    "GET",
                    "/list/%s/task" % list_id,
                    query=query,
                )
            except ClickUpError as exc:
                print("ClickUp task lookup stopped: %s" % exc)
                return pages, False
            if not isinstance(data, dict):
                print("ClickUp task lookup stopped: response was not an object.")
                return pages, False
            raw = data.get("tasks")
            batch = [item for item in raw or [] if isinstance(item, dict)]
            pages.append(batch)
            if stop_when and stop_when(batch):
                return pages, True
            if not batch or data.get("last_page") is True or len(batch) < TASK_PAGE_SIZE:
                complete = True
                break
        if not complete:
            print("ClickUp task lookup stopped after %s full pages." % len(pages))
        return pages, complete

    def create_task(self, name: str, description: str, assignees: Optional[list] = None) -> dict:
        body = {
            "name": name,
            "description": description,
            "markdown_content": description,
            "notify_all": False,
        }
        if assignees:
            body["assignees"] = list(assignees)
        data = self.request(
            "POST",
            f"/list/{urllib.parse.quote(self.config.list_id)}/task",
            body=body,
        )
        return data if isinstance(data, dict) else {}

    def update_task(self, task_id: str, fields: dict) -> dict:
        data = self.request(
            "PUT",
            f"/task/{urllib.parse.quote(task_id)}",
            body=fields,
        )
        return data if isinstance(data, dict) else {}

    def add_comment(self, task_id: str, text: str) -> dict:
        data = self.request(
            "POST",
            f"/task/{urllib.parse.quote(task_id)}/comment",
            body={"comment_text": text, "notify_all": False},
        )
        return data if isinstance(data, dict) else {}

    def statuses(self) -> list:
        if self._statuses is None:
            raw = self.get_list().get("statuses") or []
            self._statuses = list(raw)
        return self._statuses

    def resolve_status(self, kind: str) -> Optional[str]:
        """Map in_progress or done onto a status name that exists on the list."""
        wanted = {
            "in_progress": ["in progress", "inprogress", "doing"],
            "done": ["done", "complete", "completed", "closed"],
        }.get(kind, [])
        found = []
        for item in self.statuses():
            if not isinstance(item, dict):
                continue
            name = str(item.get("status") or "").strip()
            if name:
                found.append((name, str(item.get("type") or "").lower()))
        for name, _typ in found:
            if name.lower() in wanted:
                return name
        if kind == "done":
            for name, typ in found:
                if typ in {"closed", "done"}:
                    return name
        if kind == "in_progress":
            for name, typ in found:
                if typ == "custom" and "progress" in name.lower():
                    return name
        have = ", ".join(name for name, _typ in found) or "(none)"
        print(
            f"ClickUp list has no status for {kind} (have: {have}). Status was not changed."
        )
        return None
