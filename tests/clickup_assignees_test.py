#!/usr/bin/env python3
"""ClickUp assignee tests. HTTP goes to a local mock only."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from clickup_mock import Checker, MockClickUp, enabled_env, run_sync

import clickup_assignees  # noqa: E402

check = Checker()

MEMBERS = [
    {"user": {"id": 101, "email": "dev.one@example.com"}},
    {"user": {"id": "202", "email": "Dev.Two@Example.com"}},
    {"user": {"id": "not-a-number", "email": "broken@example.com"}},
    "garbage",
]


def run_env(base, **extra):
    data = {
        "RESOLVE_OUTCOME": "success",
        "RESULT": "VALID_ISSUE",
        "BRANCH_NAME": "ai/fix-issue-12",
        "PR_URL": "https://github.com/acme/widgets/pull/8",
        "PR_ALREADY_EXISTS": "false",
        "TRIAGE_SUMMARY": "Null pointer on login.",
    }
    data.update(extra)
    return enabled_env(base, **data)


def with_mock(test):
    def wrapper():
        mock = MockClickUp()
        base = mock.start()
        try:
            test(mock, base)
        finally:
            mock.stop()
    wrapper.__name__ = test.__name__
    return wrapper


def test_parse_and_resolve():
    spec = clickup_assignees.parse_spec(" dev.one@example.com, 202\nDEV.ONE@example.com,, ")
    check("parse:dedupe", spec == ["dev.one@example.com", "202"], str(spec))
    check("parse:empty", clickup_assignees.parse_spec("") == [] and clickup_assignees.parse_spec(None) == [])
    many = ",".join(str(n) for n in range(30))
    check("parse:limit", len(clickup_assignees.parse_spec(many)) == clickup_assignees.MAX_ASSIGNEES)

    ids, unknown = clickup_assignees.resolve(
        ["DEV.ONE@EXAMPLE.COM", "dev.two@example.com", "101", "999", "ghost@example.com", "broken@example.com"],
        MEMBERS,
    )
    check("resolve:ids", ids == [101, 202], str(ids))
    check("resolve:unknown", unknown == ["999", "ghost@example.com", "broken@example.com"], str(unknown))
    check("resolve:no-members", clickup_assignees.resolve(["101"], None) == ([], ["101"]))
    check("mask:email", clickup_assignees.mask("ghost@example.com") == "g***@example.com")
    check("mask:id", clickup_assignees.mask("101") == "101")


@with_mock
def test_assigns_on_create(mock, base):
    env = run_env(base, CLICKUP_ASSIGNEES="dev.one@example.com, 202, ghost@example.com")
    result = run_sync(["run-summary"], env)
    creates = mock.creates()
    body = creates[0]["body"] if creates else {}
    check("create:assignees", body.get("assignees") == [101, 202], str(body))
    check("create:logs-unknown-masked", "g***@example.com" in result.stdout, result.stdout)
    check("create:no-raw-email", "ghost@example.com" not in result.stdout, result.stdout)

    run_sync(["run-summary"], env)
    check("rerun:no-second-create", len(mock.creates()) == 1)
    check("rerun:assignees-untouched", not any("assignees" in h["body"] for h in mock.puts()), str(mock.puts()))


@with_mock
def test_no_assignees_configured(mock, base):
    run_sync(["run-summary"], run_env(base))
    creates = mock.creates()
    check("none:created", len(creates) == 1)
    check("none:no-field", creates and "assignees" not in creates[0]["body"], str(creates))


@with_mock
def test_only_unknown_assignees(mock, base):
    run_sync(["run-summary"], run_env(base, CLICKUP_ASSIGNEES="ghost@example.com, 999"))
    creates = mock.creates()
    check("unknown:created", len(creates) == 1 and len(mock.tasks) == 1, str(creates))
    check("unknown:no-field", creates and "assignees" not in creates[0]["body"], str(creates))


@with_mock
def test_rejected_assignees_still_create(mock, base):
    mock.reject_assignees = True
    result = run_sync(["run-summary"], run_env(base, CLICKUP_ASSIGNEES="dev.one@example.com"))
    creates = mock.creates()
    check("reject:retried", len(creates) == 2 and "assignees" not in creates[1]["body"], str(creates))
    check("reject:one-task", len(mock.tasks) == 1)
    check("reject:logged", "creating the task unassigned" in result.stdout, result.stdout)
    check("reject:comment", "AI triage: VALID_ISSUE" in mock.comment_text(), mock.comment_text())


@with_mock
def test_sync_never_creates(mock, base):
    with tempfile.TemporaryDirectory() as tmp:
        event = Path(tmp) / "event.json"
        event.write_text(json.dumps({
            "action": "closed",
            "repository": {"full_name": "acme/widgets"},
            "issue": {"number": 12, "title": "Login broken"},
        }))
        env = enabled_env(base, CLICKUP_ASSIGNEES="dev.one@example.com",
                          EVENT_NAME="issues", GITHUB_EVENT_PATH=str(event))
        run_sync(["github-event"], env)
    check("sync:no-create", mock.creates() == [], str(mock.hits))


def main() -> int:
    for test in (
        test_parse_and_resolve,
        test_assigns_on_create,
        test_no_assignees_configured,
        test_only_unknown_assignees,
        test_rejected_assignees_still_create,
        test_sync_never_creates,
    ):
        test()
    print("\n===== CLICKUP ASSIGNEES: %s passed, %s failed =====" % (check.passed, check.failed))
    return 1 if check.failed else 0


if __name__ == "__main__":
    sys.exit(main())
