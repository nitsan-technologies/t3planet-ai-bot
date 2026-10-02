#!/usr/bin/env python3
"""Entry point for ClickUp tracking. Failures are logged, never raised.

GitHub stays the source of truth and ClickUp only mirrors progress. Commands:

  run-summary   record the issue resolver's outcome (runs in its own job)
  github-event  record pull request activity or an issue close on an existing task

This process exits 0 even when ClickUp is down or misconfigured.
"""

from __future__ import annotations

import os
import sys

import clickup_events
import clickup_summary
from clickup_client import ClickUpClient, load_config, redact
from clickup_task import execute

COMMANDS = ("run-summary", "github-event")


def plan_for(command: str):
    env = os.environ
    if command == "github-event":
        return clickup_events.build_plan(env)
    issue = clickup_summary.issue_from_env(env)
    if issue is None:
        return None
    plan = clickup_summary.build_plan(env, issue)
    return (issue, plan) if plan else None


def main(argv: list) -> int:
    token = ""
    try:
        if len(argv) != 2 or argv[1] not in COMMANDS:
            print("Usage: clickup_sync.py <%s>" % "|".join(COMMANDS))
            return 0
        config = load_config()
        if config is None:
            return 0
        token = config.token
        planned = plan_for(argv[1])
        if planned is None:
            return 0
        issue, plan = planned
        client = ClickUpClient(config)
        client.ensure_team()
        execute(client, issue, plan)
    except Exception as exc:
        print("ClickUp sync error: " + redact(str(exc), token))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
