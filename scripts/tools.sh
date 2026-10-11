#!/usr/bin/env bash
# Run any command in the tools container from a repo subdirectory:
#   scripts/tools.sh backend uv add httpx
#   scripts/tools.sh frontend npm install some-package
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

main() {
  if [[ $# -lt 2 ]]; then
    echo "usage: scripts/tools.sh <backend|frontend|.> <command...>" >&2
    exit 1
  fi
  tools_with_db "$@"
}

main "$@"
