# <img src="assets/bot-icon.png" alt="" width="40" height="40" align="absmiddle" /> T3Planet AI Bot

T3Planet AI Bot reviews GitHub Issues with Cursor, classifies them, asks for missing information when needed, and opens a **draft pull request** when a code fix is required.

## How it works

1. Someone opens an issue (or a collaborator adds the `t3planet-ai` label, or a user replies on an issue labeled `needs-information`).
2. The bot **triages** the issue: `VALID_ISSUE`, `NOT_AN_ISSUE`, or `NEEDS_INFORMATION`.
3. For a valid issue, it implements a minimal fix on branch `ai/fix-issue-<number>` and opens a **draft PR**.
4. A human reviews and merges. The bot does not merge PRs.

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

## License

MIT
