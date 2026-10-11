#!/usr/bin/env bash
# Run backend tests against the compose db. Extra arguments go to pytest.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

main() {
  require_env
  echo "[1/1] Running pytest..."
  tools_with_db backend uv run pytest "$@"
}

main "$@"
