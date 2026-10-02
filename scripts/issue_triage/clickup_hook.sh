#!/usr/bin/env bash
# ClickUp is optional tracking. Never fail the GitHub Actions job.
set +e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export BOT_SCRIPTS="${BOT_SCRIPTS:-$SCRIPT_DIR}"
python3 "${BOT_SCRIPTS}/clickup_sync.py" "$@"
code=$?
if [ "$code" -ne 0 ]; then
  echo "ClickUp sync exited ${code}; GitHub workflow continues."
fi
exit 0
