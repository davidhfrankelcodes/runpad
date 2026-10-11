#!/usr/bin/env bash
# Apply database migrations, then hand off to the container command (uvicorn).
set -euo pipefail

main() {
  echo "[1/2] Applying database migrations..."
  alembic upgrade head

  echo "[2/2] Starting: $*"
  exec "$@"
}

main "$@"
