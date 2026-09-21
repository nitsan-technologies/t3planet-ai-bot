#!/usr/bin/env bash
set -euo pipefail

RESULT_FILE="${1:-/tmp/resolve-result.txt}"

echo "Checking Cursor test report..."

if [ ! -s "$RESULT_FILE" ]; then
  echo "ERROR: Cursor resolution report is empty."
  exit 1
fi

extract_section() {
  local heading="$1"

  awk -v heading="$heading" '
    {
      line = $0
    }
    tolower(line) ~ "^" tolower(heading) ":" {
      found = 1
      sub("^[^:]+:[[:space:]]*", "")
      if ($0 != "") print
      next
    }
    found && /^[A-Z_]+:/ { exit }
    found { print }
  ' "$RESULT_FILE"
}

if ! grep -Eiq '^TESTS_EXECUTED:' "$RESULT_FILE"; then
  echo "ERROR: Cursor did not provide TESTS_EXECUTED."
  exit 1
fi

if ! grep -Eiq '^TEST_RESULTS:' "$RESULT_FILE"; then
  echo "ERROR: Cursor did not provide TEST_RESULTS."
  exit 1
fi

TESTS_EXECUTED="$(extract_section "TESTS_EXECUTED")"
TEST_RESULTS="$(extract_section "TEST_RESULTS")"

if [ -z "$(printf '%s' "$TESTS_EXECUTED" | tr -d '[:space:]')" ]; then
  echo "ERROR: TESTS_EXECUTED is empty."
  exit 1
fi

if [ -z "$(printf '%s' "$TEST_RESULTS" | tr -d '[:space:]')" ]; then
  echo "ERROR: TEST_RESULTS is empty."
  exit 1
fi

# Detect real test-runner failure signals only.
# Ignore narrative words such as "failure mode", class names like
# ErrorHandler, and explanations that no suite exists.
if printf '%s\n' "$TEST_RESULTS" | awk '
  {
    line = tolower($0)

    # Strip common non-failure narratives before matching.
    gsub(/failure[[:space:]]+modes?/, " ", line)
    gsub(/this[[:space:]]+failure[[:space:]]+mode/, " ", line)
    gsub(/error[[:space:]]*handler/, " ", line)
    gsub(/errorhandler/, " ", line)
    gsub(/not[[:space:]]+a[[:space:]]+(test[[:space:]]+)?(failed|failure|failures|error|errors)/, " ", line)
    gsub(/no[[:space:]]+(test[[:space:]]+)?(failed|failure|failures|error|errors)/, " ", line)
    gsub(/without[[:space:]]+(any[[:space:]]+)?(failed|failure|failures|error|errors)/, " ", line)
    gsub(/0[[:space:]]*(failed|failure|failures|error|errors)/, " ", line)
    gsub(/(failed|failure|failures|error|errors)[[:space:]]*:[[:space:]]*0/, " ", line)
    gsub(/n\/?a/, " ", line)

    # Positive failure signals from real runners / clear claims.
    if (line ~ /(^|[[:space:][:punct:]])(failures?|failed|errors?)[[:space:]]*:[[:space:]]*[1-9][0-9]*/) {
      found = 1
    }
    if (line ~ /(^|[[:space:][:punct:]])failures!/) {
      found = 1
    }
    if (line ~ /(^|[[:space:][:punct:]])[0-9]+[[:space:]]+(tests?[[:space:]]+)?failed/) {
      found = 1
    }
    if (line ~ /(tests?[[:space:]]+)?(failed|not[[:space:]]+passed|unsuccessful)/) {
      # Require test context for bare "failed", or keep explicit phrases.
      if (line ~ /tests?[[:space:]]+(failed|not[[:space:]]+passed|unsuccessful)/ \
          || line ~ /(failed|not[[:space:]]+passed|unsuccessful)[[:space:]]+tests?/ \
          || line ~ /test[[:space:]]+run[[:space:]]+(failed|was[[:space:]]+unsuccessful)/ \
          || line ~ /(assertion|phpunit|unit[[:space:]]+test).*(failed|failure|failures|error|errors)/ \
          || line ~ /(failed|failure|failures|error|errors).*(assertion|phpunit|unit[[:space:]]+test)/) {
        found = 1
      }
    }
  }
  END {
    exit found ? 0 : 1
  }
'; then
  echo ""
  echo "ERROR: Cursor reported test failures."
  echo "No Pull Request will be created."
  exit 1
fi

echo ""
echo "========== TEST REPORT =========="
echo "$TEST_RESULTS"
echo "================================="

echo "Test report accepted."
