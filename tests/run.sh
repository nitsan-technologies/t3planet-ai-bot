#!/usr/bin/env bash
# Basic unit/integration checks for T3Planet AI Bot triage scripts (F10).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPTS="${ROOT}/scripts/issue_triage"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

PASS=0
FAIL=0

assert_eq() {
  local name="$1" expected="$2" actual="$3"
  if [ "$expected" = "$actual" ]; then
    echo "PASS  $name"
    PASS=$((PASS + 1))
  else
    echo "FAIL  $name (expected='$expected' actual='$actual')"
    FAIL=$((FAIL + 1))
  fi
}

assert_exit() {
  local name="$1" expected="$2"
  shift 2
  set +e
  "$@" >/dev/null 2>&1
  local code=$?
  set -e
  assert_eq "$name" "$expected" "$code"
}

echo "=== detect_result.sh ==="
check_detect() {
  local name="$1" expect="$2" body="$3"
  printf '%s\n' "$body" > "$TMP/triage.txt"
  unset GITHUB_ENV || true
  local out got
  out="$(bash "${SCRIPTS}/detect_result.sh" "$TMP/triage.txt")"
  got="$(printf '%s\n' "$out" | sed -n 's/^Detected classification: //p' | tail -n 1)"
  assert_eq "detect:$name" "$expect" "$got"
}

check_detect same-line VALID_ISSUE 'RESULT: VALID_ISSUE
SUMMARY: x'
check_detect two-line VALID_ISSUE 'RESULT:
VALID_ISSUE
SUMMARY: x'
check_detect not-issue NOT_AN_ISSUE 'RESULT: NOT_AN_ISSUE'
check_detect needs NEEDS_INFORMATION 'RESULT: NEEDS_INFORMATION'
check_detect substring-trap REVIEW_REQUIRED 'This is not a VALID_ISSUE at all.'
check_detect missing REVIEW_REQUIRED 'SUMMARY: hello only'

echo ""
echo "=== verify_test_report.sh ==="
check_verify() {
  local name="$1" expect_exit="$2" results="$3"
  cat > "$TMP/resolve.txt" <<EOF
PROBLEM:
x
ROOT_CAUSE:
x
FILES_CHANGED:
- a.php
CHANGES_MADE:
x
TESTS_EXECUTED:
existing suite or none
TEST_RESULTS:
$results
EOF
  assert_exit "verify:$name" "$expect_exit" bash "${SCRIPTS}/verify_test_report.sh" "$TMP/resolve.txt"
}

check_verify failure-mode 0 'N/A — no suite. Matches the failure mode of class_alias reload.'
check_verify real-failures 1 'FAILURES! Tests: 3, Assertions: 5, Failures: 1'
check_verify zero-failures 0 'Tests: 3, Assertions: 5, Failures: 0'
check_verify tests-failed 1 'PHPUnit tests failed with exit code 1.'

echo ""
echo "=== path_rules.sh (allowlist / dangerous) ==="
# shellcheck source=../scripts/issue_triage/path_rules.sh
source "${SCRIPTS}/path_rules.sh"

check_path() {
  local name="$1" kind="$2" path="$3" expect="$4"
  set +e
  if [ "$kind" = allow ]; then
    is_allowed "$path"
  else
    is_dangerous "$path"
  fi
  local code=$?
  set -e
  # expect 0 = match (true), 1 = no match
  assert_eq "path:$name" "$expect" "$code"
}

check_path classes-php allow Classes/Service/Foo.php 0
check_path credential-class allow Classes/CredentialValidator.php 0
check_path dockerfile allow Dockerfile 1
check_path docs allow Documentation/Index.rst 1
check_path vendor allow vendor/autoload.php 1
check_path composer allow composer.json 0
check_path env-nested dangerous Configuration/.env 0
check_path credentials-json dangerous auth/credentials.json 0
check_path pem dangerous foo.pem 0
check_path not-secret dangerous Classes/Foo.php 1

echo ""
echo "=== run_existing_project_tests.sh ==="
mkdir -p "$TMP/proj_none"
(
  cd "$TMP/proj_none"
  assert_exit "project-tests:no-suite" 0 bash "${SCRIPTS}/run_existing_project_tests.sh"
)

mkdir -p "$TMP/proj_suite/Tests"
(
  cd "$TMP/proj_suite"
  assert_exit "project-tests:suite-no-runner" 1 bash "${SCRIPTS}/run_existing_project_tests.sh"
)

echo ""
echo "===== SUMMARY: ${PASS} passed, ${FAIL} failed ====="
if [ "$FAIL" -ne 0 ]; then
  exit 1
fi
