#!/usr/bin/env python3
"""ClickUp config, safety, and run-summary tests. HTTP goes to a local mock only."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from clickup_mock import SCRIPTS, Checker, MockClickUp, base_env, enabled_env, make_task, run_sync

import clickup_client  # noqa: E402

check = Checker()


def valid_pr_env(base, **extra):
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


def test_config():
    for value, expected in (("true", True), (" YES ", True), ("false", False), ("", False), ("maybe", False)):
        check("enabled:%r" % value, clickup_client.is_enabled({"CLICKUP_ENABLED": value}) is expected)
    check("enabled:missing", not clickup_client.is_enabled({}))
    partial = {"CLICKUP_ENABLED": "true", "CLICKUP_API_TOKEN": "x" * 12, "CLICKUP_TEAM_ID": "", "CLICKUP_LIST_ID": "1"}
    check("config:incomplete", clickup_client.load_config(partial) is None)
    resolve = clickup_client.resolve_api_base
    check("api-base:default", resolve("") == clickup_client.DEFAULT_API_BASE)
    check("api-base:clickup", resolve("https://api.clickup.com/api/v2/") == "https://api.clickup.com/api/v2")
    check("api-base:loopback", resolve("http://127.0.0.1:8080/api/v2") == "http://127.0.0.1:8080/api/v2")
    for bad in ("https://evil.example/api/v2", "http://api.clickup.com/api/v2", "https://api.clickup.com.evil.io/x"):
        check("api-base:reject:%s" % bad, resolve(bad) == clickup_client.DEFAULT_API_BASE)


@with_mock
def test_disabled_makes_no_requests(mock, base):
    cases = [
        {},
        {"CLICKUP_ENABLED": "false", "CLICKUP_API_TOKEN": "test-token", "CLICKUP_TEAM_ID": "team1", "CLICKUP_LIST_ID": "list1"},
        {"CLICKUP_ENABLED": "true", "CLICKUP_API_TOKEN": "test-token", "CLICKUP_TEAM_ID": "team1"},
        {"CLICKUP_ENABLED": "true", "CLICKUP_TEAM_ID": "team1", "CLICKUP_LIST_ID": "list1"},
    ]
    for index, extra in enumerate(cases):
        for command in ("run-summary", "github-event"):
            env = valid_pr_env(base)
            for key in ("CLICKUP_ENABLED", "CLICKUP_API_TOKEN", "CLICKUP_TEAM_ID", "CLICKUP_LIST_ID"):
                env.pop(key, None)
            env.update(extra)
            result = run_sync([command], env)
            check("disabled:%s:%s" % (index, command), result.returncode == 0 and mock.hits == [], result.stdout[-200:])


def test_failures_exit_zero():
    result = run_sync(["run-summary"], valid_pr_env("http://127.0.0.1:9"))
    out = result.stdout + result.stderr
    check("api-down:exit-0", result.returncode == 0 and "ClickUp sync error:" in out and "test-token" not in out, out[-300:])

    mock = MockClickUp(token="super-secret-token")
    base = mock.start()
    try:
        result = run_sync(["run-summary"], valid_pr_env(base))
        out = result.stdout + result.stderr
        check("auth-error:redacted", result.returncode == 0 and "super-secret-token" not in out and "[redacted]" in out, out[-300:])
        check("auth-error:no-create", mock.creates() == [])
    finally:
        mock.stop()

    mock = MockClickUp()
    mock.fail_create = True
    base = mock.start()
    try:
        result = run_sync(["run-summary"], valid_pr_env(base))
        check("http-500:exit-0", result.returncode == 0 and "HTTP 500" in result.stdout, result.stdout)
    finally:
        mock.stop()

    mock = MockClickUp(team_id="999")
    base = mock.start()
    try:
        result = run_sync(["run-summary"], valid_pr_env(base))
        check("wrong-team:no-create", mock.creates() == [] and "not accessible" in result.stdout, result.stdout)
    finally:
        mock.stop()


@with_mock
def test_valid_issue_with_pr(mock, base):
    result = run_sync(["run-summary"], valid_pr_env(base))
    task = next(iter(mock.tasks.values()), {})
    check("pr:exit", result.returncode == 0, result.stdout + result.stderr)
    check("pr:one-task", len(mock.creates()) == 1 and task.get("name", "").startswith("[gh:acme/widgets#12] Login broken"))
    check("pr:in-progress", any(h["body"].get("status") == "In Progress" for h in mock.puts()), str(mock.puts()))
    text = mock.comment_text()
    for needle in ("AI triage: VALID_ISSUE", "Null pointer on login.", "Branch: ai/fix-issue-12",
                   "Draft pull request: https://github.com/acme/widgets/pull/8",
                   "https://github.com/acme/widgets/actions/runs/1"):
        check("pr:comment:%s" % needle[:24], needle in text, text)
    description = task.get("description", "")
    check("pr:meta", "t3planet-pr:https://github.com/acme/widgets/pull/8" in description
          and "t3planet-branch:ai/fix-issue-12" in description
          and "t3planet-classification:VALID_ISSUE" in description, description)
    check("pr:single-comment", len(mock.comments) == 1)

    mock.comments.clear()
    result = run_sync(["run-summary"], valid_pr_env(base, PR_ALREADY_EXISTS="true"))
    check("rerun:no-second-task", result.returncode == 0 and len(mock.creates()) == 1 and len(mock.tasks) == 1)
    check("rerun:already-open", "Pull request (already open)" in mock.comment_text(), mock.comment_text())


@with_mock
def test_valid_issue_without_pr(mock, base):
    run_sync(["run-summary"], valid_pr_env(base, RESOLVE_OUTCOME="failure", PR_URL="", BRANCH_NAME="ai/fix-issue-12"))
    check("fail:comment", "did not complete" in mock.comment_text(), mock.comment_text())
    check("fail:no-status", not any("status" in h["body"] for h in mock.puts()), str(mock.puts()))
    mock.comments.clear()
    run_sync(["run-summary"], valid_pr_env(base, PR_URL=""))
    check("no-change:comment", "did not produce a code change" in mock.comment_text(), mock.comment_text())
    check("no-change:same-task", len(mock.tasks) == 1)


@with_mock
def test_other_results(mock, base):
    run_sync(["run-summary"], valid_pr_env(base, RESULT="NOT_AN_ISSUE", PR_URL="", BRANCH_NAME=""))
    check("not-issue:no-create", mock.creates() == [] and mock.comments == [] and mock.puts() == [])

    run_sync(["run-summary"], valid_pr_env(base, RESULT="NEEDS_INFORMATION", PR_URL="", BRANCH_NAME=""))
    check("needs-info:create", len(mock.creates()) == 1 and "Waiting for more information" in mock.comment_text())

    run_sync(["run-summary"], valid_pr_env(base, RESULT="NOT_AN_ISSUE", PR_URL="", BRANCH_NAME=""))
    check("not-issue:existing-done", any(h["body"].get("status") == "Done" for h in mock.puts()), str(mock.puts()))

    mock.comments.clear()
    run_sync(["run-summary"], valid_pr_env(base, RESULT="", RESOLVE_OUTCOME="failure", PR_URL=""))
    check("pre-triage-fail:comment", "failed before triage" in mock.comment_text(), mock.comment_text())

    before = len(mock.hits)
    run_sync(["run-summary"], valid_pr_env(base, RESULT="", RESOLVE_OUTCOME="cancelled"))
    check("cancelled:no-http", len(mock.hits) == before)

    mock.tasks.clear()
    run_sync(["run-summary"], valid_pr_env(base, RESULT="", RESOLVE_OUTCOME="failure"))
    check("pre-triage-fail:no-create", len(mock.creates()) == 1)


@with_mock
def test_spoofed_outputs_are_ignored(mock, base):
    env = valid_pr_env(
        base,
        PR_URL="https://github.com/evil/repo/pull/1",
        BRANCH_NAME="main",
        CLICKUP_TASK_ID="victim",
    )
    run_sync(["run-summary"], env)
    text = mock.comment_text()
    task = next(iter(mock.tasks.values()), {})
    check("spoof:pr-ignored", "evil/repo" not in text and "evil/repo" not in task.get("description", ""), text)
    check("spoof:branch-ignored", "Branch: main" not in text and "t3planet-branch:main" not in task.get("description", ""))
    check("spoof:no-in-progress", not any(h["body"].get("status") for h in mock.puts()))
    mock.tasks.clear()
    mock.comments.clear()
    run_sync(["run-summary"], valid_pr_env(base, RESULT="HACKED"))
    check("spoof:bad-result-skips", mock.creates()[1:] == [] and mock.comments == [])


@with_mock
def test_cannot_hijack_other_tasks(mock, base):
    victim = make_task("victim", "[gh:acme/widgets#99] Customer task",
                       "t3planet-github-issue:acme/widgets#99\nNotes:\nconfidential", "In Progress")
    other = make_task("other12", "[gh:acme/widgets#12] Login broken",
                      "t3planet-github-issue:acme/widgets#12\n")
    mock.tasks.update({"victim": victim, "other12": other})
    run_sync(["run-summary"], valid_pr_env(base, ISSUE_NUMBER="1", BRANCH_NAME="ai/fix-issue-1",
                                           CLICKUP_TASK_ID="victim"))
    check("hijack:victim-untouched", mock.tasks["victim"]["name"] == "[gh:acme/widgets#99] Customer task"
          and mock.puts("victim") == [])
    check("hijack:no-prefix-collision", mock.puts("other12") == [] and len(mock.creates()) == 1,
          "issue #1 must not reuse the task for #12")
    check("hijack:comments-on-own-task", all(c["task_id"] not in {"victim", "other12"} for c in mock.comments))


@with_mock
def test_missing_status_still_comments(mock, base):
    mock.statuses = [{"status": "to do", "type": "open"}]
    run_sync(["run-summary"], valid_pr_env(base))
    check("missing-status:no-status", not any("status" in h["body"] for h in mock.puts()), str(mock.puts()))
    check("missing-status:comment", "Draft pull request" in mock.comment_text())


def test_hook_never_fails():
    tmp = tempfile.mkdtemp(prefix="clickup-hook-")
    try:
        (Path(tmp) / "clickup_sync.py").write_text("import sys\nsys.exit(2)\n", encoding="utf-8")
        result = subprocess.run(
            ["bash", str(SCRIPTS / "clickup_hook.sh"), "run-summary"],
            env=base_env({"BOT_SCRIPTS": tmp}),
            text=True,
            capture_output=True,
            check=False,
        )
        check("hook:masks-exit", result.returncode == 0 and "exited 2" in result.stdout, result.stdout)
    finally:
        shutil.rmtree(tmp)


def main() -> int:
    for test in (
        test_config,
        test_disabled_makes_no_requests,
        test_failures_exit_zero,
        test_valid_issue_with_pr,
        test_valid_issue_without_pr,
        test_other_results,
        test_spoofed_outputs_are_ignored,
        test_cannot_hijack_other_tasks,
        test_missing_status_still_comments,
        test_hook_never_fails,
    ):
        test()
    print("\n===== CLICKUP: %s passed, %s failed =====" % (check.passed, check.failed))
    return 1 if check.failed else 0


if __name__ == "__main__":
    sys.exit(main())
