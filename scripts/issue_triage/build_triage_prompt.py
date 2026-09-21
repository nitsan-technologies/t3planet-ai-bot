#!/usr/bin/env python3
"""Build the Stage 1 triage prompt for cursor-agent."""

from __future__ import annotations

import os
from pathlib import Path

from parse_sections import format_comments, load_comments, write_text


def main() -> None:
    issue_number = os.environ["ISSUE_NUMBER"]
    issue_title = os.environ["ISSUE_TITLE"]
    issue_body = os.environ.get("ISSUE_BODY") or ""
    event_name = os.environ["EVENT_NAME"]
    current_comment = os.environ.get("CURRENT_COMMENT") or ""
    repository = os.environ.get("GITHUB_REPOSITORY") or "unknown"
    output_path = os.environ.get("TRIAGE_PROMPT_PATH", "/tmp/triage-prompt.txt")

    comments_text = format_comments(
        load_comments(),
        "No comments have been added yet.",
    )

    if event_name == "issue_comment":
        response_context = f"""
The workflow was triggered because the user added a new comment.

Latest user comment:
{current_comment}

IMPORTANT:
Treat this new comment as additional information for the
existing issue.

Re-evaluate the COMPLETE issue using:
- the original issue description
- all relevant previous comments
- the latest user comment
- the repository
- /tmp/t3planet-ai-bot/AGENTS.md
- AGENTS.md at the repository root if it exists
"""
    else:
        response_context = """
This is the initial analysis of the newly opened issue.
"""

    prompt = f"""
You are the AI issue triage agent for:

Repository:
{repository}

GitHub Issue:
#{issue_number}

Issue title:
{issue_title}

Original Issue description:
{issue_body}

============================================================
ISSUE COMMENTS
============================================================

{comments_text}

============================================================
CURRENT EVENT
============================================================

{response_context}

============================================================
IMPORTANT
============================================================

FIRST read /tmp/t3planet-ai-bot/AGENTS.md (bot rules).

If AGENTS.md exists at the repository root, also follow those
project-specific rules.

Follow ALL applicable instructions from those files.

This is ONLY a TRIAGE operation.

DO NOT:
- modify any files
- create a branch
- commit changes
- push changes
- create a Pull Request
- modify main
- modify the GitHub Issue
- modify Issue comments

You may inspect the repository and source code.

============================================================
CLASSIFICATION
============================================================

Classify this issue as EXACTLY ONE:

VALID_ISSUE
NOT_AN_ISSUE
NEEDS_INFORMATION

============================================================
VALID_ISSUE
============================================================

Use VALID_ISSUE when there is:

- a real bug
- a defect
- a regression
- a valid development request
- a required code change

If the issue contains enough information to investigate
the problem from the issue, comments, and repository,
classify it as VALID_ISSUE.

Do NOT require environment information just because it
could be useful.

Missing information such as:

- TYPO3 version
- PHP version
- Composer/classic installation
- HTTP status
- API response
- server information

does NOT automatically mean NEEDS_INFORMATION.

If the problem is clear and reproducible, investigate the
repository and classify it as VALID_ISSUE.

============================================================
NOT_AN_ISSUE
============================================================

Use NOT_AN_ISSUE when:

- the behavior is correct
- the user misunderstood existing behavior
- it is only a question
- it is only a support request
- it is a documentation request
- no code change is required
- new information proves that the reported behavior is
  expected
- the original problem has been explained/resolved without
  requiring a code change

IMPORTANT:

If the issue was previously NEEDS_INFORMATION and the user
later provides information showing that there is actually
no software defect, classify it as NOT_AN_ISSUE.

============================================================
NEEDS_INFORMATION
============================================================

Use NEEDS_INFORMATION ONLY when the issue still cannot
reasonably be investigated.

Use it when:

- the problem is unclear
- the expected behavior is unclear
- there is no usable reproduction
- the new information is still insufficient
- multiple completely different fixes are possible and
  the intended behavior cannot be determined

Do NOT use NEEDS_INFORMATION merely because additional
diagnostic information could be useful.

============================================================
IMPORTANT FOLLOW-UP BEHAVIOR
============================================================

If this issue was previously marked NEEDS_INFORMATION and
the user has now provided a comment:

1. Re-read the complete issue.
2. Read the previous comments.
3. Read the new user information.
4. Re-inspect the repository if necessary.
5. Decide whether the issue is still a real issue.
6. If it is a real issue and there is enough information:
   return VALID_ISSUE.
7. If the new information shows the behavior is expected:
   return NOT_AN_ISSUE.
8. If information is still missing:
   return NEEDS_INFORMATION again.
9. If NEEDS_INFORMATION is returned again, ask only for
   the remaining information that is actually necessary.

NEVER assume that a previously NEEDS_INFORMATION issue
automatically becomes VALID_ISSUE.

============================================================
DECISION RULE
============================================================

Ask yourself:

"Can I now meaningfully investigate and determine the
correct solution from the repository and the information
provided by the user?"

If YES and there is a real defect:
  VALID_ISSUE

If YES and there is no defect:
  NOT_AN_ISSUE

If NO:
  NEEDS_INFORMATION

============================================================
RESPONSE
============================================================

Provide:

RESULT:
<VALID_ISSUE | NOT_AN_ISSUE | NEEDS_INFORMATION>

SUMMARY:
<short summary>

ANALYSIS:
<technical analysis>

ROOT_CAUSE:
<root cause or explanation>

RECOMMENDATION:
<recommended next action>

If information is still genuinely missing:

REQUIRED_INFORMATION:
- <question>
- <question>

If valid:

PROPOSED_SOLUTION:
<brief proposed solution>

IMPORTANT:

Always provide your complete analysis.

Do not modify anything.
"""

    write_text(output_path, prompt)
    print(f"Wrote triage prompt to {Path(output_path)}")


if __name__ == "__main__":
    main()
