# Shared helpers for scripts/. Source this file; do not run it directly.
# shellcheck shell=bash

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Files created in the bind-mounted repo are owned by the invoking user, not root.
export RUNPAD_UID RUNPAD_GID
RUNPAD_UID="$(id -u)"
RUNPAD_GID="$(id -g)"

# The development stack. docker-compose.yaml only runs the published image.
compose() {
  docker compose --project-directory "$ROOT" -f "$ROOT/docker-compose.dev.yaml" "$@"
}

require_env() {
  if ! grep -qs '^POSTGRES_PASSWORD=.\+' "$ROOT/.env" \
    || ! grep -qs '^RUNPAD_SECRET_KEY=.\+' "$ROOT/.env"; then
    echo "error: .env is missing POSTGRES_PASSWORD or RUNPAD_SECRET_KEY." >&2
    echo "Run scripts/init-env.sh to generate one." >&2
    exit 1
  fi
}

# Run a command in the tools container. The first argument is the working
# directory relative to the repo root.
tools() {
  local workdir="$1"
  shift
  compose --progress quiet run --rm --build --no-deps -w "/repo/$workdir" tools "$@"
}

# Same as tools, but starts the db service first (tests, migrations).
tools_with_db() {
  local workdir="$1"
  shift
  compose --progress quiet run --rm --build -w "/repo/$workdir" tools "$@"
}
