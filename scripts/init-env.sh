#!/usr/bin/env bash
# Create .env with freshly generated secrets. Refuses to touch a .env that has content.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

random_hex() {
  od -An -N"$1" -tx1 /dev/urandom | tr -d ' \n'
}

main() {
  local env_file="$ROOT/.env"
  if [[ -s "$env_file" ]]; then
    echo "error: $env_file already has content; edit it by hand (see .env.example)." >&2
    exit 1
  fi

  echo "[1/1] Writing $env_file..."
  cat > "$env_file" <<ENV
POSTGRES_PASSWORD=$(random_hex 24)
RUNPAD_SECRET_KEY=$(random_hex 32)
ENV
  echo "Done. Keep RUNPAD_SECRET_KEY safe: losing it makes stored secrets unreadable."
}

main "$@"
