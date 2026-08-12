#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 SQLITE_BACKUP" >&2
  exit 2
fi

sqlite_db=$1
repo_root=$(cd "$(dirname "$0")/.." && pwd)
pg_container=${PG_CONTAINER:-jitendex-postgres}
pg_database=${PGDATABASE:-jitendex}
pg_user=${PGUSER:-jitendex}

if [[ ! -f "$sqlite_db" ]]; then
  echo "SQLite backup does not exist: $sqlite_db" >&2
  exit 2
fi

if [[ $(docker inspect --format '{{.State.Health.Status}}' "$pg_container") != healthy ]]; then
  echo "PostgreSQL container is not healthy: $pg_container" >&2
  exit 2
fi

target_tables=$(docker exec "$pg_container" psql -At -U "$pg_user" -d "$pg_database" \
  -c "SELECT COUNT(*) FROM pg_tables WHERE schemaname='public';")
if [[ "$target_tables" != 0 ]]; then
  echo "PostgreSQL public schema is not empty; refusing to overwrite it" >&2
  exit 2
fi

docker exec -i "$pg_container" psql -v ON_ERROR_STOP=1 -U "$pg_user" -d "$pg_database" \
  < "$repo_root/postgres/schema.sql"

tables=(
  schema_meta
  source_snapshot
  kaishi_note
  article
  selection_candidate
  selection_decision
  run
  translation_unit
  batch
  batch_item
  attempt
  translation
  review
  validation_issue
  audit_event
  export
  export_file
  run_article
  attempt_cost_report
  jitendex_tag
  jitendex_tag_translation_history
  frequency_source
  frequency_term
  frequency_article
  translation_canonicalization_history
)

for table_name in "${tables[@]}"; do
  columns=$(sqlite3 -readonly "$sqlite_db" \
    "SELECT group_concat(name, ',') FROM pragma_table_info('$table_name');")
  if [[ -z "$columns" ]]; then
    echo "Missing SQLite table: $table_name" >&2
    exit 2
  fi
  expected=$(sqlite3 -readonly "$sqlite_db" "SELECT COUNT(*) FROM \"$table_name\";")
  echo "loading $table_name ($expected rows)"
  sqlite3 -readonly -csv "$sqlite_db" "SELECT $columns FROM \"$table_name\";" \
    | docker exec -i "$pg_container" psql -v ON_ERROR_STOP=1 -U "$pg_user" -d "$pg_database" \
      -c "\\copy $table_name ($columns) FROM STDIN WITH (FORMAT csv, NULL '')"
  actual=$(docker exec "$pg_container" psql -At -U "$pg_user" -d "$pg_database" \
    -c "SELECT COUNT(*) FROM $table_name;")
  if [[ "$actual" != "$expected" ]]; then
    echo "Row-count mismatch for $table_name: SQLite=$expected PostgreSQL=$actual" >&2
    exit 1
  fi
done

docker exec -i "$pg_container" psql -v ON_ERROR_STOP=1 -U "$pg_user" -d "$pg_database" \
  < "$repo_root/postgres/post_load.sql"

echo "migration complete"
