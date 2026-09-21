#!/usr/bin/env bash
# Stage only AGENTS.md-permitted solution source files for the automated PR.
# Deny-by-default: anything not on the allowlist is skipped (not pushed).
# Dangerous secret paths abort the job.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=path_rules.sh
source "${SCRIPT_DIR}/path_rules.sh"

# Remove junk so it does not linger
find . -name .DS_Store -type f -delete 2>/dev/null || true
find . -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
find . -name '*.pyc' -type f -delete 2>/dev/null || true

# Bot sandbox restore must never look like a product change
rm -rf .cursor

git reset >/dev/null 2>&1 || true

dangerous=""
skipped=""
staged=""

while IFS= read -r line; do
  [ -z "$line" ] && continue

  status="${line:0:2}"
  path="${line:3}"
  path="${path#\"}"
  path="${path%\"}"

  # Renames show as "old -> new"
  if [[ "$path" == *" -> "* ]]; then
    path="${path##* -> }"
  fi

  if is_dangerous "$path"; then
    dangerous="${dangerous}${path}"$'\n'
    continue
  fi

  if ! is_allowed "$path"; then
    skipped="${skipped}${path}"$'\n'
    # Discard tracked modifications to non-solution files so they are not pushed
    if [ "$status" != "??" ] && [ "$status" != "A " ]; then
      git checkout -- "$path" 2>/dev/null || true
    fi
    continue
  fi

  git add -- "$path"
  staged="${staged}${path}"$'\n'
done < <(git status --porcelain)

if [ -n "$dangerous" ]; then
  printf '%s' "$dangerous" > /tmp/dangerous-files.txt
  echo "Dangerous files were produced and must not be committed:"
  printf '%s' "$dangerous"
  exit 2
fi

if [ -n "$skipped" ]; then
  echo "Skipping non-solution files (not pushed):"
  printf '%s' "$skipped"
fi

if [ -z "$(git diff --cached --name-only)" ]; then
  echo "No solution source files to commit."
  echo "has_solution_changes=false"
  if [ -n "${GITHUB_OUTPUT:-}" ]; then
    echo "has_solution_changes=false" >> "$GITHUB_OUTPUT"
  fi
  exit 0
fi

echo "Staging solution files:"
git diff --cached --name-only
echo "has_solution_changes=true"
if [ -n "${GITHUB_OUTPUT:-}" ]; then
  echo "has_solution_changes=true" >> "$GITHUB_OUTPUT"
fi
