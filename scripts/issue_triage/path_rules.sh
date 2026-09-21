#!/usr/bin/env bash
# Path rules shared by staging and unit tests.
# Allowlist matches AGENTS.md permitted solution files.

is_dangerous() {
  local path="$1"
  local base
  base="$(basename "$path")"

  case "$path" in
    .env|.env.*|*/.env|*/.env.*)
      return 0
      ;;
  esac

  case "$base" in
    *.key|*.pem|.env|.env.*)
      return 0
      ;;
    credentials|credentials.json|credentials.yml|credentials.yaml|credential.json)
      return 0
      ;;
  esac

  return 1
}

is_allowed() {
  local path="$1"

  case "$path" in
    Classes|Classes/*|*/Classes/*)
      return 0
      ;;
    Configuration|Configuration/*|*/Configuration/*)
      return 0
      ;;
    Resources/Private|Resources/Private/*|Resources/Public|Resources/Public/*|*/Resources/Private/*|*/Resources/Public/*)
      return 0
      ;;
    ext_localconf.php|ext_tables.php|ext_emconf.php|ext_tables.sql|ext_conf_template.txt)
      return 0
      ;;
    ext_icon.gif|ext_icon.png|ext_icon.svg)
      return 0
      ;;
    composer.json)
      return 0
      ;;
  esac

  return 1
}
