#!/usr/bin/env bash
set -euo pipefail

STAGE="${1:?usage: run_cursor.sh <triage|resolve> <prompt-path> <result-path>}"
PROMPT_FILE="${2:?prompt path required}"
RESULT_FILE="${3:?result path required}"
PROMPT_SIZE_LIMIT="${PROMPT_SIZE_LIMIT:-81920}"
LOG_TAIL_LINES="${LOG_TAIL_LINES:-80}"

if [ -z "${CURSOR_API_KEY:-}" ]; then
  echo "CURSOR_API_KEY is not set."
  echo "No Pull Request will be created."
  exit 1
fi

if [ ! -s "$PROMPT_FILE" ]; then
  echo "Prompt file is missing or empty: ${PROMPT_FILE}"
  exit 1
fi

if ! command -v cursor-agent >/dev/null 2>&1; then
  echo "cursor-agent is not installed or not on PATH."
  exit 1
fi

printf '%s\n' "$STAGE" > /tmp/cursor-stage.txt

if [ -n "${GITHUB_ENV:-}" ]; then
  echo "CURSOR_STAGE=${STAGE}" >> "$GITHUB_ENV"
fi

prompt_size="$(wc -c < "$PROMPT_FILE" | tr -d '[:space:]')"

if [ "$prompt_size" -gt "$PROMPT_SIZE_LIMIT" ]; then
  echo "Prompt is ${prompt_size} bytes; invoking via prompt file path."
  invoke_prompt="Read and follow the prompt file at ${PROMPT_FILE} exactly."
else
  invoke_prompt="$(cat "$PROMPT_FILE")"
fi

echo "Starting Cursor ${STAGE}..."

set +e

cursor-agent \
  -p \
  --trust \
  --output-format text \
  "$invoke_prompt" \
  > "$RESULT_FILE" 2>&1

CURSOR_EXIT_CODE=$?

set -e

printf '%s\n' "$CURSOR_EXIT_CODE" > /tmp/cursor-exit-code.txt

echo "Cursor exit code: ${CURSOR_EXIT_CODE}"
echo ""
echo "========== CURSOR ${STAGE} (last ${LOG_TAIL_LINES} lines) =========="
if [ -f "$RESULT_FILE" ]; then
  tail -n "$LOG_TAIL_LINES" "$RESULT_FILE"
else
  echo "(no output file)"
fi
echo "=============================================================="

if [ "$CURSOR_EXIT_CODE" -ne 0 ]; then
  echo "Cursor ${STAGE} failed."
  echo "No Pull Request will be created."
  exit 1
fi

if [ ! -s "$RESULT_FILE" ]; then
  echo "Cursor returned an empty ${STAGE} response."
  echo "No Pull Request will be created."
  exit 1
fi
