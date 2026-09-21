#!/usr/bin/env bash
# Run an existing project test suite when one is already present.
# Does not create new tests. Exit codes:
#   0 = skipped (no suite) or tests passed
#   1 = suite exists and tests failed, or suite exists and runner is missing
set -euo pipefail

STATUS_FILE="${PROJECT_TEST_STATUS_PATH:-/tmp/project-test-status.txt}"

has_suite=false
if [ -d Tests ] || [ -d tests ]; then
  has_suite=true
fi
if [ -f phpunit.xml ] || [ -f phpunit.xml.dist ]; then
  has_suite=true
fi

if [ "$has_suite" != true ]; then
  msg="No existing project test suite found (no Tests/, tests/, or phpunit.xml). Skipped."
  echo "$msg"
  printf '%s\n' "$msg" > "$STATUS_FILE"
  exit 0
fi

echo "Existing project tests detected. Reviewing by running them..."

runner=""
if [ -x vendor/bin/phpunit ]; then
  runner="vendor/bin/phpunit"
elif command -v phpunit >/dev/null 2>&1; then
  runner="phpunit"
fi

if [ -z "$runner" ]; then
  msg="Existing tests were found, but phpunit is not available in this environment (no vendor/bin/phpunit). Cannot review the suite here."
  echo "ERROR: $msg"
  printf '%s\n' "$msg" > "$STATUS_FILE"
  exit 1
fi

echo "Running: ${runner}"
set +e
"${runner}"
code=$?
set -e

if [ "$code" -ne 0 ]; then
  msg="Existing project tests failed (exit ${code}). No Pull Request will be created."
  echo "ERROR: $msg"
  printf '%s\n' "$msg" > "$STATUS_FILE"
  exit 1
fi

msg="Existing project tests passed via ${runner}."
echo "$msg"
printf '%s\n' "$msg" > "$STATUS_FILE"
exit 0
