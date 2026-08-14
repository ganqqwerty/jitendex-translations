#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 SQLITE_BACKUP REPORT_JSON" >&2
  echo "set JITENDEX_POSTGRES_URL; unfinished production sources are refused" >&2
  exit 2
fi

repo_root=$(cd "$(dirname "$0")/.." && pwd)
exec python3 "$repo_root/scripts/migrate_sqlite_to_postgresql.py" \
  "$1" --postgres-url-env JITENDEX_POSTGRES_URL --report "$2"
