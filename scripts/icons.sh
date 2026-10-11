#!/usr/bin/env bash
# Render favicons, app icons, and the GitHub social preview from frontend/icons/*.svg.
# Uses Chromium from the Playwright image, so nothing is installed on the host.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

PLAYWRIGHT_IMAGE="mcr.microsoft.com/playwright/python:v1.63.0-noble"

main() {
  echo "[1/1] Rendering icons into frontend/public and docs/..."
  docker run --rm \
    -v "$ROOT:/repo" -w /repo \
    --user "$RUNPAD_UID:$RUNPAD_GID" -e HOME=/tmp \
    "$PLAYWRIGHT_IMAGE" \
    sh -c 'pip install --quiet --user playwright==1.63.0 2>/dev/null && python frontend/icons/render.py'
  echo "Done. Commit the changed files in frontend/public and docs/."
}

main "$@"
