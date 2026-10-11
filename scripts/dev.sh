#!/usr/bin/env bash
# Start the dev stack: backend with reload on :8080, Vite on :5173, Postgres on :5432.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

main() {
  require_env
  echo "[1/1] Starting app, db, and web (frontend at http://localhost:5173)..."
  compose up --build "$@"
}

main "$@"
