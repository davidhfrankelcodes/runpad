#!/usr/bin/env bash
# Autogenerate an Alembic migration from model changes: scripts/migration.sh "describe change"
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

main() {
  if [[ $# -ne 1 ]]; then
    echo "usage: scripts/migration.sh \"describe change\"" >&2
    exit 1
  fi
  require_env

  echo "[1/2] Upgrading the dev database to head..."
  tools_with_db backend uv run alembic upgrade head

  echo "[2/2] Generating migration..."
  tools_with_db backend uv run alembic revision --autogenerate -m "$1"
}

main "$@"
