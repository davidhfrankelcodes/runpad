#!/usr/bin/env bash
# Run every check required before a task is done: ruff, pytest, eslint, and the frontend build.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

main() {
  require_env

  echo "[1/5] Checking format and lint for backend (ruff)..."
  tools backend bash -c "uv run ruff format --check . && uv run ruff check ."

  echo "[2/5] Testing backend (pytest)..."
  tools_with_db backend uv run pytest -q

  echo "[3/5] Installing frontend dependencies..."
  tools frontend npm ci --no-audit --no-fund

  echo "[4/5] Linting frontend (eslint)..."
  tools frontend npm run --silent lint

  echo "[5/5] Building frontend (tsc + vite)..."
  tools frontend npm run --silent build

  echo "All checks passed."
}

main "$@"
