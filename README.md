# <img src="assets/bot-icon.png" alt="" width="40" height="40" align="absmiddle" /> T3Planet AI Bot

T3Planet AI Bot reviews GitHub Issues with Cursor, classifies them, asks for missing information when needed, and opens a **draft pull request** when a code fix is required.

## How it works

1. Someone opens an issue (or a collaborator adds the `t3planet-ai` label, or a user replies on an issue labeled `needs-information`).
2. The bot **triages** the issue: `VALID_ISSUE`, `NOT_AN_ISSUE`, or `NEEDS_INFORMATION`.
3. For a valid issue, it implements a minimal fix on branch `ai/fix-issue-<number>` and opens a **draft PR**.
4. A human reviews and merges. The bot does not merge PRs.

ClickUp tracking is optional and **off by default**. The GitHub flow above does not call ClickUp unless you enable it. See [Optional ClickUp tracking](#optional-clickup-tracking).

## Setup

Do these in **every** repository that uses the bot.

### 1. Allow GitHub Actions to write to the repo

The bot needs permission to comment on issues, create branches, and open draft pull requests.

1. Open the repository on GitHub.
2. Go to **Settings → Actions → General**.
3. Scroll to **Workflow permissions**.
4. Choose **Read and write permissions**.
5. Check **Allow GitHub Actions to create and approve pull requests**.
6. Click **Save**.

Without this, the workflow can run but will fail when it tries to push code or open a PR.

### 2. Add your Cursor API key

The bot uses Cursor to read the issue and write the fix. You must store your API key as a repository secret (it is never committed to git).

1. Get an API key from the [Cursor dashboard](https://cursor.com/dashboard/api).
2. In the repository, go to **Settings → Secrets and variables → Actions**.
3. Click **New repository secret**.
4. Name: `CURSOR_API_KEY`
5. Value: paste your Cursor API key.
6. Click **Add secret**.

Use exactly the name `CURSOR_API_KEY` — the workflow looks for that name.

### 3. Caller workflow

Create `.github/workflows/t3planet-ai-bot.yml`:

```yaml
name: T3Planet AI Bot

on:
  issues:
    types: [opened, labeled]
  issue_comment:
    types: [created]

permissions:
  contents: write
  issues: write
  pull-requests: write

jobs:
  resolve:
    if: |
      (
        github.event_name == 'issues' &&
        github.event.action == 'opened'
      ) ||
      (
        github.event_name == 'issues' &&
        github.event.action == 'labeled' &&
        github.event.label.name == 't3planet-ai'
      ) ||
      (
        github.event_name == 'issue_comment' &&
        !github.event.issue.pull_request &&
        github.event.comment.user.type != 'Bot' &&
        contains(github.event.issue.labels.*.name, 'needs-information')
      )
    # Prefer a release tag over @main in production (see Versioning below).
    uses: nitsan-technologies/t3planet-ai-bot/.github/workflows/issue-resolver.yml@main
    secrets:
      CURSOR_API_KEY: ${{ secrets.CURSOR_API_KEY }}
    with:
      bot_ref: main
      base_branch: main
      # ClickUp tracking stays off unless this is "true". See below.
      clickup_enabled: "false"
```

Copy-paste example: [`examples/caller-workflow.yml`](examples/caller-workflow.yml)

## When the bot runs

| Trigger | Behavior |
|---------|----------|
| Issue **opened** | Triage (and fix if valid). Any GitHub user who can open an issue can start a run. |
| Label **`t3planet-ai`** added | Re-run triage/fix (useful to retry). |
| Comment on an issue with **`needs-information`** | Re-evaluate with the new details (bot comments are ignored). |

The bot opens **draft** pull requests only. A human reviews and merges; the bot never merges.

## Optional configuration

- **Project rules:** add a local [`AGENTS.md`](AGENTS.md). The bot always loads the bot rules first, then your file if present.
- **`base_branch`:** set if the default branch is not `main`.
- **`cursor_agent_version`:** pin or upgrade the Cursor CLI lab build (see Inputs).


## Optional ClickUp tracking

ClickUp is **off** unless you turn it on. With the default settings the bot never calls the ClickUp API, and triage, labels, branches, and draft pull requests behave as they do today.

When you enable it, GitHub stays the source of truth and ClickUp only mirrors progress. One GitHub issue maps to one ClickUp task. The bot finds that task only inside the configured list, by:

- the task name prefix `[gh:<owner>/<repo>#<number>]`, or
- a marker line in the task description, `t3planet-github-issue:<owner>/<repo>#<number>`

The bot does not post ClickUp links on GitHub issues. If the ClickUp API returns an error or is unreachable, the bot logs it and the GitHub workflow continues.

### Security model

- The ClickUp token is used only in a separate job that runs **after** the AI job, on a fresh runner. It is never present on the machine where the AI agent runs.
- That job reads the AI job's outcome (classification, branch, pull request URL, short summary) from job outputs and validates each value: the branch must be `ai/fix-issue-<number>`, and the pull request URL must belong to the same repository.
- API calls only go to `https://api.clickup.com`.
- Pull requests from forks do not sync, because GitHub does not pass secrets to fork pull request runs.

### Settings

| Name | Where | When enabled |
|------|--------|----------------|
| `clickup_enabled` | workflow input | Set to `true` to turn tracking on. Default `false`. `1`, `yes`, and `on` also turn it on. Empty, `false`, or any other value leaves it off. |
| `CLICKUP_API_TOKEN` | Actions secret | Required. A ClickUp personal API token. Never commit it. |
| `CLICKUP_TEAM_ID` | repository variable passed as input `clickup_team_id` (or a secret with the same name) | Required. The workspace (team) id. |
| `CLICKUP_LIST_ID` | repository variable passed as input `clickup_list_id` (or a secret with the same name) | Required. The list that should hold the tasks. |

If ClickUp is enabled but any of the token, team id, or list id is missing, the bot skips tracking and does not call the API.

The list should have a status the bot can match, case-insensitively, for **In Progress** (a draft pull request is open) and **Done** (or Complete / Closed). If the list has no matching status, the bot logs that and still adds the comment.

Create the token in ClickUp under **Settings → Apps** and store it as the Actions secret `CLICKUP_API_TOKEN`. Store the ids under **Settings → Secrets and variables → Actions → Variables**.

### Enable

On the caller that already runs the bot:

```yaml
with:
  bot_ref: main
  base_branch: main
  clickup_enabled: "true"
  clickup_team_id: ${{ vars.CLICKUP_TEAM_ID }}
  clickup_list_id: ${{ vars.CLICKUP_LIST_ID }}
secrets:
  CURSOR_API_KEY: ${{ secrets.CURSOR_API_KEY }}
  CLICKUP_API_TOKEN: ${{ secrets.CLICKUP_API_TOKEN }}
```

GitHub does not allow `secrets` inside `with:`, so pass the ids as variables (or as secrets under `secrets:`).

### What is synced after each issue run

When the AI job finishes, the ClickUp job records one update:

| Outcome | ClickUp |
|---------|---------|
| Valid issue, draft pull request opened (or already open) | Create the task if needed, status In Progress, comment with triage summary, branch, and pull request |
| Valid issue, fix failed or produced no change | Create the task if needed, comment explaining that no pull request was opened |
| Needs information / review required | Create the task if needed, comment with the triage summary |
| Not an issue | No new task. If a task already exists, status Done with a comment |
| Run failed before triage | Comment on an existing task only |

Comments include the GitHub issue link and the workflow run link. The triage summary is AI-generated and capped at 1000 characters.

### Pull request reviews, merges, and issue close

`issue-resolver.yml` is only called for issue events, so pull request activity is handled by a separate reusable workflow, [`.github/workflows/clickup-sync.yml`](.github/workflows/clickup-sync.yml). It is not used unless a caller opts in, and the job is skipped when `clickup_enabled` is not true.

This workflow **only updates existing tasks**. It never creates one, so closing an old issue or merging an unrelated pull request adds nothing to ClickUp.

- pull request opened, edited, new commits, draft or ready for review → comment with the pull request URL
- pull request review → comment on the task
- pull request merged → status Done, plus the merge commit
- GitHub issue closed → status Done, plus a close comment

A pull request is matched to the issue from the branch `ai/fix-issue-<number>`, or from `Fixes #n` / `Relates to #n` in the pull request title or body. Unlinked pull requests are ignored.

The commented job in [`examples/caller-workflow.yml`](examples/caller-workflow.yml) shows the triggers to uncomment.

### Disable

Set `clickup_enabled` to `"false"`, or stop passing it. You do not need a ClickUp token. Existing ClickUp tasks are left as they are.

## Tests

- **Bot scripts:** run `bash tests/run.sh` (also runs in CI on this repo).
- **Consumer extensions:** if the project already has `Tests/`, `tests/`, or `phpunit.xml`, the bot reviews them by running `vendor/bin/phpunit` (or `phpunit`) after a fix. If a suite exists but phpunit is not installed in the Actions job, the run fails and no PR is opened.

## Versioning (tags)

`@main` always uses the latest bot code. That is fine for trying things out, but a change on `main` can break callers without warning.

For production, use a **release tag** (for example `v1.0.0`) once tags are published:

```yaml
uses: nitsan-technologies/t3planet-ai-bot/.github/workflows/issue-resolver.yml@v1.0.0
with:
  bot_ref: v1.0.0
  base_branch: main
```

| Ref | Meaning |
|-----|---------|
| `@main` | Always latest — good for testing |
| `@v1.0.0` | Fixed release — recommended for production |

Until the first tag exists, keep using `@main`. After tags are cut, switch callers to the tag and bump it when you want upgrades.

## Inputs

| Input | Default | Description |
|-------|---------|-------------|
| `bot_ref` | `main` | Branch or tag of this repo used to load scripts and rules |
| `base_branch` | `main` | Default branch of the calling repository |
| `cursor_agent_version` | `2026.08.25-3e8eec8` | Pinned Cursor agent CLI lab version |
| `clickup_enabled` | `false` | Set to `true` to mirror progress into ClickUp. Off by default |
| `clickup_team_id` | empty | ClickUp workspace id. Required only when ClickUp is enabled |
| `clickup_list_id` | empty | ClickUp list id. Required only when ClickUp is enabled |

## License

MIT
