#!/usr/bin/env bash
# Regenerate frontend/src/api/schema.ts from the backend's OpenAPI schema.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

main() {
  echo "[1/2] Installing frontend dependencies..."
  tools frontend npm install --no-audit --no-fund

  echo "[2/2] Generating API types..."
  tools frontend npm run --silent gen:api
}

main "$@"
