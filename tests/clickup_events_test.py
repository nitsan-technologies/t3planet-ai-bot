#!/usr/bin/env python3
"""ClickUp GitHub-event, export, and workflow wiring tests. HTTP goes to a local mock only."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from clickup_mock import ROOT, SCRIPTS, Checker, MockClickUp, base_env, enabled_env, make_task, run_sync

import clickup_events  # noqa: E402

check = Checker()


def run_event(base, event_name, payload, **extra):
    tmp = tempfile.mkdtemp(prefix="clickup-event-")
    try:
        path = Path(tmp) / "event.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        extra.setdefault("GITHUB_EVENT_PATH", str(path))
        env = enabled_env(base, EVENT_NAME=event_name, **extra)
        env.pop("ISSUE_NUMBER", None)
        env.pop("ISSUE_TITLE", None)
        return run_sync(["github-event"], env)
    finally:
        shutil.rmtree(tmp)


def pr_payload(action="closed", merged=True, head="ai/fix-issue-7", title="Fix #1: wrong", body="Relates to #1"):
    return {
        "action": action,
        "repository": {"full_name": "acme/widgets"},
        "pull_request": {
            "html_url": "https://github.com/acme/widgets/pull/40",
            "title": title,
            "body": body,
            "draft": False,
            "merged": merged,
            "merge_commit_sha": "abc123deadbeef",
            "head": {"ref": head, "sha": "headsha"},
        },
    }


def test_link_parsing():
    link = clickup_events.linked_issue_number
    check("link:branch-wins", link({"head": {"ref": "ai/fix-issue-9"}, "title": "Fix #3", "body": "Fixes #4"}) == "9")
    check("link:relates", link({"head": {"ref": "feature/x"}, "title": "Update", "body": "Relates to #15"}) == "15")
    check("link:fixes-title", link({"head": {"ref": "feature/x"}, "title": "Fix #7: login", "body": ""}) == "7")
    check("link:none", link({"head": {"ref": "feature/x"}, "title": "docs", "body": "no link"}) == "")


def test_events_update_existing_task():
    mock = MockClickUp()
    base = mock.start()
    try:
        mock.tasks["cu7"] = make_task("cu7", "[gh:acme/widgets#7] Login broken",
                                      "t3planet-github-issue:acme/widgets#7\n", "In Progress")
        result = run_event(base, "pull_request", pr_payload())
        check("merge:exit", result.returncode == 0, result.stdout + result.stderr)
        check("merge:done", any(h["body"].get("status") == "Done" for h in mock.puts("cu7")), str(mock.puts()))
        check("merge:sha", "abc123deadbeef" in mock.comment_text())
        check("merge:name-kept", mock.tasks["cu7"]["name"] == "[gh:acme/widgets#7] Login broken")
        check("merge:no-create", mock.creates() == [])

        mock.hits.clear()
        mock.comments.clear()
        review = pr_payload(action="submitted", merged=False, title="Fix #7: login", body="")
        review["review"] = {"state": "approved", "body": "Looks good", "user": {"login": "alice"}}
        run_event(base, "pull_request_review", review)
        text = mock.comment_text()
        check("review:comment", "alice" in text and "approved" in text and "Looks good" in text, text)
        check("review:not-done", not any(h["body"].get("status") == "Done" for h in mock.puts()))

        before = len(mock.hits)
        run_event(base, "pull_request", pr_payload(head="chore/readme", title="chore", body="no issue"))
        check("unlinked-pr:no-http", len(mock.hits) == before)

        closed = {"action": "closed", "repository": {"full_name": "acme/widgets"},
                  "issue": {"number": 7, "title": "Login broken", "state_reason": "completed", "pull_request": {"url": "x"}}}
        before = len(mock.hits)
        run_event(base, "issues", closed)
        check("issue-pr-close:skipped", len(mock.hits) == before)

        closed["issue"].pop("pull_request")
        mock.tasks["cu7"]["status"] = {"status": "In Progress", "type": "custom"}
        mock.comments.clear()
        run_event(base, "issues", closed)
        check("issue-closed:done", any(h["body"].get("status") == "Done" for h in mock.puts("cu7")))
        check("issue-closed:comment", "GitHub issue #7 was closed (completed)" in mock.comment_text())
    finally:
        mock.stop()


def test_events_never_create_tasks():
    mock = MockClickUp()
    base = mock.start()
    try:
        closed = {"action": "closed", "repository": {"full_name": "acme/widgets"},
                  "issue": {"number": 3, "title": "Old issue", "state_reason": "completed"}}
        result = run_event(base, "issues", closed)
        check("old-issue-close:no-create", result.returncode == 0 and mock.creates() == [] and mock.comments == [])
        run_event(base, "pull_request", pr_payload(head="feature/x", title="Docs", body="Fixes #5"))
        check("unknown-issue-merge:no-create", mock.creates() == [] and mock.comments == [] and mock.puts() == [])
        result = run_event(base, "pull_request", pr_payload(), GITHUB_EVENT_PATH="/nonexistent/event.json")
        check("missing-payload:exit-0", result.returncode == 0)
    finally:
        mock.stop()


def test_export_run_summary():
    tmp = tempfile.mkdtemp(prefix="clickup-export-")
    try:
        triage = Path(tmp) / "triage.txt"
        triage.write_text("RESULT: VALID_ISSUE\nSUMMARY: Broken login.\npr_url=https://evil\nANALYSIS: x\n", encoding="utf-8")
        output = Path(tmp) / "out.txt"
        env = base_env({
            "GITHUB_OUTPUT": str(output),
            "TRIAGE_RESULT_PATH": str(triage),
            "RESULT": "VALID_ISSUE",
            "BRANCH_NAME": "ai/fix-issue-12",
            "PR_URL": "https://github.com/acme/widgets/pull/8\nresult=NOT_AN_ISSUE",
            "PR_ALREADY_EXISTS": "false",
        })
        result = subprocess.run([sys.executable, str(SCRIPTS / "export_run_summary.py")],
                                env=env, text=True, capture_output=True, check=False)
        text = output.read_text(encoding="utf-8") if output.exists() else ""
        lines = text.splitlines()
        check("export:exit", result.returncode == 0, result.stderr)
        check("export:single-result", [l for l in lines if l.startswith("result=")] == ["result=VALID_ISSUE"], text)
        check("export:pr-flattened", "pr_url=https://github.com/acme/widgets/pull/8 result=NOT_AN_ISSUE" in lines, text)
        check("export:summary-delimited", "triage_summary<<T3PLANET_EOF_" in text and "Broken login." in text, text)
    finally:
        shutil.rmtree(tmp)


def job_block(workflow: str, job: str) -> str:
    block = []
    inside = False
    for line in workflow.split("\njobs:\n", 1)[1].splitlines():
        if re.match(r"^  [A-Za-z_][\w-]*:\s*$", line):
            inside = line.strip() == job + ":"
            continue
        if inside:
            block.append(line)
    return "\n".join(block)


def test_wiring():
    resolver = (ROOT / ".github/workflows/issue-resolver.yml").read_text(encoding="utf-8")
    sync = (ROOT / ".github/workflows/clickup-sync.yml").read_text(encoding="utf-8")
    example = (ROOT / "examples/caller-workflow.yml").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    resolve_job = job_block(resolver, "resolve")
    clickup_job = job_block(resolver, "clickup")
    check("wiring:token-not-in-ai-job", "CLICKUP" not in resolve_job and "clickup_hook" not in resolve_job)
    check("wiring:clickup-job-needs-resolve", "needs: resolve" in clickup_job and "!cancelled()" in clickup_job)
    check("wiring:clickup-job-read-only", "contents: read" in clickup_job and "write" not in clickup_job)
    check("wiring:clickup-job-continue", "continue-on-error: true" in clickup_job and "run-summary" in clickup_job)
    check("wiring:export-always", "id: summary" in resolve_job and "export_run_summary.py" in resolve_job)
    check("wiring:default-off", 'default: "false"' in resolver.split("clickup_enabled:", 1)[1][:300])
    check("wiring:resolver-not-pr-triggered", "pull_request:" not in resolver.split("jobs:", 1)[0])
    check("wiring:sync-no-env-payload", "toJson(github.event)" not in sync)
    check("wiring:sync-read-only", "issues: write" not in sync and "contents: read" in sync)
    check("wiring:sync-skipped-unless-enabled", "inputs.clickup_enabled)" in sync.split("jobs:", 1)[1])
    for name, text in (("example", example), ("readme", readme)):
        check("wiring:no-secrets-in-with:%s" % name, "clickup_team_id: ${{ secrets" not in text
              and "clickup_list_id: ${{ secrets" not in text)
    check("wiring:example-off", 'clickup_enabled: "false"' in example)
    check("wiring:no-github-marker", "t3planet-clickup-task" not in readme + resolver)
    joined = "".join(p.read_text(encoding="utf-8") for p in SCRIPTS.glob("clickup_*.py"))
    check("wiring:no-hardcoded-token", "pk_" not in joined + resolver + sync + example)
    if shutil.which("ruby"):
        for path in (ROOT / ".github/workflows/issue-resolver.yml", ROOT / ".github/workflows/clickup-sync.yml",
                     ROOT / "examples/caller-workflow.yml"):
            result = subprocess.run(["ruby", "-ryaml", "-e", "YAML.load_file(ARGV[0])", str(path)],
                                    capture_output=True, text=True)
            check("yaml:%s" % path.name, result.returncode == 0, result.stderr[-300:])


def main() -> int:
    test_link_parsing()
    test_events_update_existing_task()
    test_events_never_create_tasks()
    test_export_run_summary()
    test_wiring()
    print("\n===== CLICKUP EVENTS: %s passed, %s failed =====" % (check.passed, check.failed))
    return 1 if check.failed else 0


if __name__ == "__main__":
    sys.exit(main())
