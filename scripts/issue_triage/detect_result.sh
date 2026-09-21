#!/usr/bin/env bash
set -euo pipefail

RESULT_FILE="${1:-/tmp/triage-result.txt}"

if [ ! -s "$RESULT_FILE" ]; then
  echo "Cursor returned an empty response."
  echo "No Pull Request will be created."
  exit 1
fi

# Prefer "RESULT: VALID_ISSUE" on one line; also accept RESULT: then value on the next line.
# Never invent VALID_ISSUE from free-text substrings.
RESULT=$(
  awk '
    {
      line = $0
      sub(/\r$/, "", line)
    }
    tolower(line) ~ /^[[:space:]]*result:[[:space:]]*(valid_issue|not_an_issue|needs_information)[[:space:]]*$/ {
      sub(/^[^:]+:[[:space:]]*/, "", line)
      gsub(/[[:space:]]/, "", line)
      print toupper(line)
      exit
    }
    tolower(line) ~ /^[[:space:]]*result:[[:space:]]*$/ {
      if (getline nextline <= 0) exit
      sub(/\r$/, "", nextline)
      gsub(/[[:space:]]/, "", nextline)
      value = toupper(nextline)
      if (value == "VALID_ISSUE" || value == "NOT_AN_ISSUE" || value == "NEEDS_INFORMATION") {
        print value
        exit
      }
    }
  ' "$RESULT_FILE"
) || true

if [ -z "$RESULT" ]; then
  RESULT="REVIEW_REQUIRED"
fi

echo "Detected classification: ${RESULT}"

if [ -n "${GITHUB_ENV:-}" ]; then
  echo "RESULT=${RESULT}" >> "$GITHUB_ENV"
fi
