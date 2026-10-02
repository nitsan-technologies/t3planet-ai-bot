#!/usr/bin/env python3
"""Local ClickUp API mock and helpers for the ClickUp tests. No live API calls."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts" / "issue_triage"
sys.path.insert(0, str(SCRIPTS))


class Checker:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0

    def __call__(self, name: str, ok: bool, detail: str = "") -> None:
        if ok:
            print("PASS  %s" % name)
            self.passed += 1
        else:
            print("FAIL  %s %s" % (name, detail))
            self.failed += 1


def base_env(extra=None) -> dict:
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "LANG": os.environ.get("LANG", "C"),
        "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    if extra:
        env.update(extra)
    return env


def enabled_env(api_base: str, **extra) -> dict:
    data = {
        "CLICKUP_ENABLED": "true",
        "CLICKUP_API_TOKEN": "test-token",
        "CLICKUP_TEAM_ID": "team1",
        "CLICKUP_LIST_ID": "list1",
        "CLICKUP_API_BASE": api_base,
        "GITHUB_REPOSITORY": "acme/widgets",
        "ISSUE_NUMBER": "12",
        "ISSUE_TITLE": "Login broken",
        "GITHUB_RUN_URL": "https://github.com/acme/widgets/actions/runs/1",
    }
    data.update(extra)
    return base_env(data)


def run_sync(args, env, timeout=30):
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "clickup_sync.py")] + list(args),
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def make_task(task_id, name, description="", status="to do"):
    return {
        "id": task_id,
        "name": name,
        "description": description,
        "text_content": description,
        "url": "https://app.clickup.com/t/%s" % task_id,
        "list": {"id": "list1"},
        "date_created": "1700000000%03d" % len(task_id),
        "status": {"status": status, "type": "custom"},
    }


class MockClickUp:
    def __init__(self, token="test-token", team_id="team1"):
        self.token = token
        self.team_id = team_id
        self.statuses = [
            {"status": "to do", "type": "open"},
            {"status": "In Progress", "type": "custom"},
            {"status": "Done", "type": "closed"},
        ]
        self.members = [
            {"user": {"id": 101, "username": "Dev One", "email": "dev.one@example.com"}},
            {"user": {"id": 202, "username": "Dev Two", "email": "Dev.Two@Example.com"}},
        ]
        self.tasks = {}
        self.comments = []
        self.hits = []
        self.fail_create = False
        self.reject_assignees = False
        self.seq = 0
        self._httpd = None
        self._thread = None

    def creates(self):
        return [h for h in self.hits if h["method"] == "POST" and h["path"] == "/list/list1/task"]

    def puts(self, task_id=None):
        return [
            h for h in self.hits
            if h["method"] == "PUT" and (task_id is None or h["path"] == "/task/%s" % task_id)
        ]

    def comment_text(self):
        return "\n".join(item["text"] for item in self.comments)

    def start(self) -> str:
        mock = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, fmt, *args):
                return

            def do_GET(self):
                self._handle("GET")

            def do_POST(self):
                self._handle("POST")

            def do_PUT(self):
                self._handle("PUT")

            def _send(self, code, payload):
                data = json.dumps(payload).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(data)

            def _handle(self, method):
                parsed = urlparse(self.path)
                rel = parsed.path[len("/api/v2"):] if parsed.path.startswith("/api/v2") else parsed.path
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b""
                body = json.loads(raw.decode("utf-8")) if raw else {}
                auth = self.headers.get("Authorization")
                mock.hits.append(
                    {"method": method, "path": rel, "query": parse_qs(parsed.query), "body": body}
                )
                if auth != mock.token:
                    self._send(401, {"err": "Token invalid %s" % (auth or "")})
                    return
                self._send(*mock.route(method, rel, body))

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        host, port = self._httpd.server_address
        return "http://%s:%s/api/v2" % (host, port)

    def route(self, method, rel, body):
        if method == "GET" and rel == "/team":
            return 200, {"teams": [{"id": self.team_id, "name": "Workspace", "members": self.members}]}
        if method == "GET" and rel == "/list/list1":
            return 200, {"id": "list1", "statuses": self.statuses}
        if method == "GET" and rel == "/list/list1/task":
            return 200, {"tasks": list(self.tasks.values()), "last_page": True}
        if method == "POST" and rel == "/list/list1/task":
            if self.fail_create:
                return 500, {"err": "create failed"}
            known = {m["user"]["id"] for m in self.members}
            wanted = body.get("assignees") or []
            if wanted and (self.reject_assignees or any(uid not in known for uid in wanted)):
                return 400, {"err": "Assignee not found"}
            self.seq += 1
            task = make_task("cu%s" % self.seq, body.get("name"), body.get("description") or "")
            task["assignees"] = [{"id": uid} for uid in wanted]
            self.tasks[task["id"]] = task
            return 200, task
        parts = rel.split("/")
        if len(parts) >= 3 and parts[1] == "task":
            task = self.tasks.get(parts[2])
            if task is None:
                return 404, {"err": "Task not found"}
            if method == "POST" and rel.endswith("/comment"):
                self.comments.append({"task_id": parts[2], "text": body.get("comment_text")})
                return 200, {"id": "c%s" % len(self.comments)}
            if method == "PUT":
                for key in ("name", "description"):
                    if key in body:
                        task[key] = body[key]
                if "description" in body:
                    task["text_content"] = body["description"]
                if "status" in body:
                    task["status"] = {"status": body["status"], "type": "custom"}
                return 200, task
        return 404, {"err": "not found %s" % rel}

    def stop(self):
        if self._httpd is not None:
            self._httpd.shutdown()
            self._thread.join(timeout=5)
            self._httpd.server_close()
