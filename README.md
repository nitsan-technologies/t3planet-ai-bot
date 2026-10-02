# <img src="assets/bot-icon.png" alt="" width="40" height="40" align="absmiddle" /> T3Planet AI Bot

T3Planet AI Bot reviews GitHub Issues with Cursor, classifies them, asks for missing information when needed, and opens a **draft pull request** when a code fix is required.

## How it works

1. Someone opens an issue (or a collaborator adds the `t3planet-ai` label, or a user replies on an issue labeled `needs-information`).
2. The bot **triages** the issue: `VALID_ISSUE`, `NOT_AN_ISSUE`, or `NEEDS_INFORMATION`. If the AI answer has no clear classification, the result is `REVIEW_REQUIRED` and no fix is attempted.
3. For a valid issue, it implements a minimal fix on branch `ai/fix-issue-<number>` and opens a **draft PR**.
4. A human reviews and merges. The bot does not merge PRs. Review and approval happen on the GitHub pull request.

ClickUp tracking is optional and **off by default**. It only copies status into ClickUp after GitHub has already finished. It never approves, blocks, or changes the AI run. See [Optional ClickUp tracking](#optional-clickup-tracking).

**Contents:** [Requirements](#requirements) · [Setup](#setup) · [When the bot runs](#when-the-bot-runs) · [Optional ClickUp tracking](#optional-clickup-tracking) · [Privacy and data](#privacy-and-data) · [Troubleshooting](#troubleshooting) · [Versioning](#versioning-tags) · [Inputs](#inputs) · [Secrets](#secrets)

## Requirements

- A GitHub repository with GitHub Actions enabled. The bot runs on GitHub-hosted `ubuntu-latest` runners.
- A Cursor account with an API key.
- Optional: a ClickUp workspace and a personal API token, only if you use ClickUp tracking.
- Private repositories: the bot repository is public, so no extra access setting is needed.

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
  bot:
    # Prefer a release tag over @main in production (see Versioning below).
    uses: nitsan-technologies/t3planet-ai-bot/.github/workflows/bot.yml@main
    secrets:
      CURSOR_API_KEY: ${{ secrets.CURSOR_API_KEY }}
    with:
      bot_ref: main
      base_branch: main
```

[`bot.yml`](.github/workflows/bot.yml) is the single entry point. It decides which job each event needs, so the caller only lists its triggers and settings.

Copy-paste example: [`examples/caller-workflow.yml`](examples/caller-workflow.yml)

`bot.yml` is not in `v1.0.0`. With `@v1.0.0`, call `issue-resolver.yml` directly and keep the trigger conditions in the caller, as shown in that release's README.

### 4. Labels

- `needs-information` is created by the bot the first time it needs it.
- `t3planet-ai` is the retry label. Create it once under **Issues → Labels → New label** if you want collaborators to be able to re-run the bot on an issue.

### 5. Check it works

Open a test issue that describes a small, clear bug. Within a few minutes the **Actions** tab shows a run, and the issue gets a bot comment with the triage result. For a valid issue, a draft pull request from `ai/fix-issue-<number>` follows.

## When the bot runs

| Trigger | Behavior |
|---------|----------|
| Issue **opened** | Triage (and fix if valid). Any GitHub user who can open an issue can start a run. |
| Label **`t3planet-ai`** added | Re-run triage/fix (useful to retry). |
| Comment on an issue with **`needs-information`** | Re-evaluate with the new details (bot comments are ignored). |

The bot opens **draft** pull requests only. A human reviews and merges; the bot never merges.

## Optional configuration

- **Project rules:** add an `AGENTS.md` at the root of your repository for project-specific notes (see [`examples/AGENTS.md`](examples/AGENTS.md)). The bot always loads its own rules ([`AGENTS.md`](AGENTS.md)) first, then your file if present.
- **`base_branch`:** set if the default branch is not `main`.
- **`cursor_agent_version`:** pin or upgrade the Cursor CLI lab build (see Inputs).


## Optional ClickUp tracking

ClickUp is **off** unless you turn it on. With the default settings the bot never calls the ClickUp API, and triage, labels, branches, and draft pull requests behave as they do today.

ClickUp tracking is not part of `v1.0.0`. Use a release that includes it (from `v1.1.0`), or `@main` while testing.

ClickUp is a **status board only**:

- The bot writes a task, a status (In Progress or Done), a comment, and optional assignees. That is the whole integration.
- It never asks for approval in ClickUp, never waits for a ClickUp status, and never reads ClickUp back.
- Changing, reassigning, or closing a task in ClickUp does nothing to GitHub. Review and merge stay on the pull request.
- The AI job does not know ClickUp exists. It finishes first, on its own runner. The ClickUp job starts afterwards, on a fresh runner, with read-only GitHub permissions.
- A ClickUp error, timeout, or missing setting is logged and ignored. It does not fail the workflow, hide an AI result, or block a pull request. Pull request events use a separate job, so they cannot cancel an AI run.

When you enable it, GitHub stays the source of truth. One GitHub issue maps to one ClickUp task. The bot finds that task only inside the configured list, by:

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
| `clickup_enabled` | workflow input | Set to `true` to turn tracking on. Default `false`. In `bot.yml` it is a boolean. When calling `issue-resolver.yml` directly it is a string, where `"true"`, `"1"`, `"yes"`, and `"on"` turn it on. |
| `CLICKUP_API_TOKEN` | Actions secret | Required. A ClickUp personal API token. Never commit it. |
| `CLICKUP_TEAM_ID` | repository variable passed as input `clickup_team_id` (or a secret with the same name) | Required. The workspace (team) id. |
| `CLICKUP_LIST_ID` | repository variable passed as input `clickup_list_id` (or a secret with the same name) | Required. The list that should hold the tasks. |
| `CLICKUP_ASSIGNEES` | Actions secret (recommended) or repository variable passed as input `clickup_assignees` | Optional. Emails or ClickUp user ids, comma separated (up to 10), assigned to each new task. |

If ClickUp is enabled but any of the token, team id, or list id is missing, the bot skips tracking and does not call the API.

### Set up ClickUp step by step

1. **Token.** In ClickUp open your avatar → **Settings → Apps → API Token** and generate a token. In the GitHub repository, add it under **Settings → Secrets and variables → Actions → Secrets** as `CLICKUP_API_TOKEN`. Tasks and comments are created as the user who owns the token, so a shared service account is a good choice.
2. **Team id.** Open ClickUp in the browser. The first number in the URL is the workspace (team) id, for example `https://app.clickup.com/<team_id>/home`. Add it under **Variables** as `CLICKUP_TEAM_ID`.
3. **List id.** Open the list that should hold the tasks. The number after `/li/` in the URL is the list id, for example `https://app.clickup.com/<team_id>/v/li/<list_id>`. Add it under **Variables** as `CLICKUP_LIST_ID`.
4. **Statuses.** The list needs a status the bot can match, case-insensitively, for **In Progress** (or Doing) and **Done** (or Complete / Closed). If there is no match, the bot logs the statuses it found and still adds the comment.
5. **Assignees (optional).** See [Assignees](#assignees).
6. **Workflow.** Update the caller as shown in [Enable](#enable).

### Assignees

Set `CLICKUP_ASSIGNEES` to the people who should own new tasks, for example:

```text
dev@example.com, 12345678
```

- Each entry is either the **email a person uses to log in to ClickUp** (case does not matter) or their numeric **ClickUp user id**. Members and their emails are listed in ClickUp under **Settings → People**.
- Every entry must be a member of the workspace in `CLICKUP_TEAM_ID`. Entries that match nobody are skipped and logged with the email masked, for example `d***@example.com`.
- If ClickUp still rejects the assignees, the bot creates the task unassigned instead of failing.
- Assignees are set only when the bot **creates** a task. Later runs never change them, so a person you reassign in ClickUp stays assigned.
- The token's own user is not assigned unless you list it.

**Store it as a secret.** GitHub shows repository variables in plain text in workflow logs, and logs of public repositories are public. A secret named `CLICKUP_ASSIGNEES` is masked in logs. Pass it under `secrets:` and leave out the `clickup_assignees` input:

```yaml
secrets:
  CURSOR_API_KEY: ${{ secrets.CURSOR_API_KEY }}
  CLICKUP_API_TOKEN: ${{ secrets.CLICKUP_API_TOKEN }}
  CLICKUP_ASSIGNEES: ${{ secrets.CLICKUP_ASSIGNEES }}
```

If both are set, the `clickup_assignees` input wins.

### Enable

On the caller that already runs the bot, add the triggers and settings:

```yaml
on:
  issues:
    types: [opened, labeled, closed]
  issue_comment:
    types: [created]
  pull_request:
    types: [opened, edited, synchronize, reopened, closed, ready_for_review, converted_to_draft]
  pull_request_review:
    types: [submitted, edited]

jobs:
  bot:
    uses: nitsan-technologies/t3planet-ai-bot/.github/workflows/bot.yml@main
    secrets:
      CURSOR_API_KEY: ${{ secrets.CURSOR_API_KEY }}
      CLICKUP_API_TOKEN: ${{ secrets.CLICKUP_API_TOKEN }}
      CLICKUP_ASSIGNEES: ${{ secrets.CLICKUP_ASSIGNEES }}
    with:
      bot_ref: main
      base_branch: main
      clickup_enabled: true
      clickup_team_id: ${{ vars.CLICKUP_TEAM_ID }}
      clickup_list_id: ${{ vars.CLICKUP_LIST_ID }}
```

GitHub does not allow `secrets` inside `with:`, so pass the ids as variables (or as secrets under `secrets:`). The pull request and issue-close triggers are only needed for ClickUp.

To check the setup, open a test issue. The run's **Sync ClickUp tracking** job log shows each ClickUp call, and the task appears in the list as `[gh:<owner>/<repo>#<number>] <issue title>`.

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

`bot.yml` sends pull request events and issue closes to a separate reusable workflow, [`.github/workflows/clickup-sync.yml`](.github/workflows/clickup-sync.yml). That job is skipped when `clickup_enabled` is not true.

This workflow **only updates existing tasks**. It never creates one, so closing an old issue or merging an unrelated pull request adds nothing to ClickUp.

- pull request opened, edited, new commits, draft or ready for review → comment with the pull request URL
- pull request review → comment on the task
- pull request merged → status Done, plus the merge commit
- GitHub issue closed → status Done, plus a close comment

A pull request is matched to the issue from the branch `ai/fix-issue-<number>`, or from `Fixes #n` / `Relates to #n` in the pull request title or body. Unlinked pull requests are ignored.

The commented triggers in [`examples/caller-workflow.yml`](examples/caller-workflow.yml) show what to uncomment.

The bot's own draft pull request does not start a sync run, because GitHub does not trigger workflows for pull requests opened with the workflow token. Its link reaches ClickUp through the issue run instead.

### Disable

Set `clickup_enabled` to `false`, or stop passing it. You do not need a ClickUp token. Existing ClickUp tasks are left as they are.

## Privacy and data

- **Cursor:** the issue title, body, and comments, plus the repository code, are sent to Cursor for triage and fixes.
- **GitHub:** the bot writes comments, labels, a branch, and a draft pull request. It never posts ClickUp links, ids, or assignee details on GitHub.
- **ClickUp (only when enabled):** the task holds the issue title and link, the classification, the branch, the pull request link, and a short AI summary (at most 1000 characters). The issue body is not copied.
- **Logs:** tokens and secrets are masked. Assignee emails printed by the bot are masked. Repository variables are shown in plain text, so keep personal data such as emails in secrets.
- **Docs and examples:** use placeholders such as `dev@example.com` and `<team_id>`. Never commit real tokens, emails, or ids.

## Troubleshooting

| Symptom | Likely cause |
|---------|--------------|
| Run fails when pushing or opening the pull request | Workflow permissions are read-only. See [Setup step 1](#1-allow-github-actions-to-write-to-the-repo). |
| Run fails at the Cursor step | `CURSOR_API_KEY` is missing, misspelled, or expired. |
| GitHub rejects the workflow with an unknown input or file | The pinned tag is older than that feature. See [Versioning](#versioning-tags). |
| No run for pull request events | The caller does not list the `pull_request` / `pull_request_review` triggers. |
| Log: `ClickUp disabled; skipping` | `clickup_enabled` is not `true`. |
| Log: `ClickUp enabled but missing required settings` | The token secret, team id, or list id is not set or not passed to the workflow. |
| Log: `team ... is not accessible to this token` | The team id is wrong, or the token's user is not in that workspace. |
| Log: `ClickUp list has no status for ...` | Add an In Progress / Done status to the list. The comment is still added. |
| Log: `skipped assignees that are not workspace members` | The email is not the person's ClickUp login, or they are not a member. Check **Settings → People** in ClickUp. |
| No ClickUp comment for the bot's own draft pull request | Expected. GitHub does not trigger workflows for pull requests opened with the workflow token. The link is added by the issue run. |

A green run does not prove ClickUp worked. ClickUp errors are logged and the run stays successful when the AI job succeeded, so check the **Sync ClickUp tracking** job log.

## Tests

- **Bot scripts:** run `bash tests/run.sh` (also runs in CI on this repo). It includes the ClickUp tests, which use a local mock server and never call the real ClickUp API.
- **Consumer extensions:** if the project already has `Tests/`, `tests/`, or `phpunit.xml`, the bot reviews them by running `vendor/bin/phpunit` (or `phpunit`) after a fix. If a suite exists but phpunit is not installed in the Actions job, the run fails and no PR is opened.

## Versioning (tags)

`@main` always uses the latest bot code. That is fine for trying things out, but a change on `main` can break callers without warning.

For production, use a **release tag**. `v1.1.0` is the first release planned to include `bot.yml` and ClickUp:

```yaml
uses: nitsan-technologies/t3planet-ai-bot/.github/workflows/bot.yml@v1.1.0
with:
  bot_ref: v1.1.0
  base_branch: main
```

| Ref | Meaning |
|-----|---------|
| `@main` | Always latest — good for testing |
| `@v1.1.0` | Fixed release — recommended for production |

Keep `uses: ...@<ref>` and `bot_ref` on the same value, and bump both when you want an upgrade.

Only use files and inputs that exist in the release you pin. `v1.0.0` has no `bot.yml` and no `clickup_*` inputs, so GitHub rejects a caller that uses them with that tag.

## Inputs

Inputs of `bot.yml`:

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| `bot_ref` | string | `main` | Branch or tag of this repo used to load scripts and rules. Keep equal to the ref in `uses:` |
| `base_branch` | string | `main` | Default branch of the calling repository |
| `clickup_enabled` | boolean | `false` | Set to `true` to mirror progress into ClickUp |
| `clickup_team_id` | string | empty | ClickUp workspace id. Required only when ClickUp is enabled |
| `clickup_list_id` | string | empty | ClickUp list id. Required only when ClickUp is enabled |
| `clickup_assignees` | string | empty | Emails or ClickUp user ids, comma separated, assigned to new ClickUp tasks. Prefer the `CLICKUP_ASSIGNEES` secret |

When calling `issue-resolver.yml` directly, the same inputs exist, except that `clickup_enabled` is a string, plus:

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| `cursor_agent_version` | string | `2026.08.25-3e8eec8` | Pinned Cursor agent CLI lab version |

## Secrets

| Secret | Required | Description |
|--------|----------|-------------|
| `CURSOR_API_KEY` | Yes | Cursor API key used for triage and fixes |
| `CLICKUP_API_TOKEN` | Only with ClickUp | ClickUp personal API token |
| `CLICKUP_TEAM_ID` | No | Alternative to the `clickup_team_id` input |
| `CLICKUP_LIST_ID` | No | Alternative to the `clickup_list_id` input |
| `CLICKUP_ASSIGNEES` | No | Alternative to the `clickup_assignees` input. Masked in logs, so recommended for emails |

## License

MIT
