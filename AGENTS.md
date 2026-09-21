# AI Issue Resolver Rules

Canonical rules for **T3Planet AI Bot**. This file lives in
[`nitsan-technologies/t3planet-ai-bot`](https://github.com/nitsan-technologies/t3planet-ai-bot).

Calling repositories do **not** need their own `AGENTS.md` unless they want
project-specific extras. If a calling repo has `AGENTS.md`, follow both:
bot rules first, then project rules.

## General

- Never modify `main` directly.
- Always work only on the existing issue branch (`ai/fix-issue-<number>`).
- Keep changes minimal and scoped to the reported issue.
- Do not make unrelated changes or refactoring.
- Follow the existing project architecture and coding style.
- Do not modify bot tooling, workflows, or this rules file from a consumer fix.
- Do not modify `.github/workflows/` or `.github/scripts/` in the consumer repo
  unless the issue is explicitly about those files.

## Issue Triage

Before changing code:

1. Read the complete GitHub Issue and relevant comments.
2. Read these bot rules (and the project `AGENTS.md` if present).
3. Inspect the relevant repository code.
4. Determine whether the reported behavior is actually incorrect.
5. Do not guess when information is missing.

## Classification

Every issue must be classified as exactly one of:

### VALID_ISSUE

A real bug, defect, regression, or valid development request requiring a code change.

### NOT_AN_ISSUE

The current behavior is correct, or the request is a question, support request, or documentation request.

Do not modify code.

### NEEDS_INFORMATION

The issue may be valid, but there is not enough information to safely investigate or implement a fix.

Do not modify code.

## VALID_ISSUE

When the issue is valid:

1. Identify the root cause.
2. Implement the smallest correct solution in **permitted solution/source files only**.
3. Follow the existing architecture and coding style.
4. Prefer editing existing product code over adding new files.
5. Run existing project tests if available. Do not invent new test suites or smoke runners.
6. Review the final diff.
7. Leave the workspace clean.

## Permitted files (may be changed / committed)

Only product/solution source should be part of the automated PR.

### Typically allowed

| Area | Examples |
|------|----------|
| PHP classes | `Classes/**/*.php` |
| TYPO3 configuration | `Configuration/**/*` |
| Frontend assets owned by the extension | `Resources/Private/**/*`, `Resources/Public/**/*` |
| Extension entrypoints | `ext_localconf.php`, `ext_tables.php`, `ext_emconf.php` |
| Extension metadata needed for the fix | `composer.json` only when the issue requires it |

### Prefer

- Fix the existing file that causes the bug
- Smallest diff that solves the reported issue

## Not permitted (do not create / do not push)

Even if created locally for debugging, these must not be committed by the bot:

| Area | Examples |
|------|----------|
| Git ignore / git meta | `.gitignore`, `.gitattributes` |
| Tests | `Tests/**`, `tests/**`, phpunit smoke runners, `*smoke*` |
| Docs / license / rules | `README.md`, `LICENSE`, `AGENTS.md`, `Documentation/**` (unless the issue is explicitly docs) |
| CI / bot tooling | `.github/**`, `.cursor/**` |
| Secrets / env | `.env`, `.env.*`, `*.key`, `*.pem`, credential files |
| Junk / temp | `.DS_Store`, `__pycache__/`, `*.pyc`, `*.log`, `tmp/`, `temp/` |
| Dependencies | `node_modules/**`, vendor install noise |

GitHub Actions enforces this at commit time with an **allowlist**: only
`Classes/`, `Configuration/`, `Resources/Private/`, `Resources/Public/`,
extension entrypoints (`ext_*.php` / related), and `composer.json` may be
staged. Everything else is skipped and not pushed.

## Git and GitHub Actions

GitHub Actions owns all git and GitHub operations.

- Never run `git commit`, `git push`, `git checkout`, or branch creation.
- Never run `gh` (issues, PRs, comments, labels).
- Never merge a Pull Request.
- Never modify the GitHub Issue title, description, labels, or comments.
- Never switch to `main`.

## Pull Request report

Return exactly:

- PROBLEM
- ROOT_CAUSE
- FILES_CHANGED (solution source files only)
- CHANGES_MADE
- TESTS_EXECUTED
- TEST_RESULTS

Do not claim tests passed unless they were actually executed.

## Issue

Never modify the original GitHub Issue title or description.

Only GitHub Actions may add comments when communication with the reporter is required.
