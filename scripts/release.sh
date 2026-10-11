#!/usr/bin/env bash
# Build the image for linux/amd64 and linux/arm64 and push it to Docker Hub as
# davidhfrankelcodes/runpad:<version> and :latest, then tag the commit v<version>.
# The version is the one in backend/pyproject.toml; bump it (and frontend/package.json)
# in a commit before releasing. Requires `docker login` as an account that can push.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

IMAGE="davidhfrankelcodes/runpad"
PLATFORMS="linux/amd64,linux/arm64"
BUILDER="runpad-release"

fail() {
  echo "error: $*" >&2
  exit 1
}

project_version() {
  sed -n 's/^version = "\(.*\)"$/\1/p' "$ROOT/backend/pyproject.toml" | head -n 1
}

frontend_version() {
  sed -n 's/^  "version": "\(.*\)",$/\1/p' "$ROOT/frontend/package.json" | head -n 1
}

check_release() {
  local version="$1"
  [[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] \
    || fail "version '$version' in backend/pyproject.toml is not MAJOR.MINOR.PATCH"
  [[ "$(frontend_version)" == "$version" ]] \
    || fail "frontend/package.json has version $(frontend_version), backend has $version"
  [[ -z "$(git -C "$ROOT" status --porcelain)" ]] \
    || fail "the working tree has uncommitted changes"
  [[ "$(git -C "$ROOT" branch --show-current)" == "main" ]] || fail "not on main"
  if git -C "$ROOT" rev-parse -q --verify "refs/tags/v$version" >/dev/null; then
    fail "tag v$version already exists; bump the version first"
  fi
  if docker buildx imagetools inspect "$IMAGE:$version" >/dev/null 2>&1; then
    fail "$IMAGE:$version is already on Docker Hub; bump the version first"
  fi
}

# Multi-platform builds need a docker-container builder, and arm64 emulation (QEMU)
# unless the host is arm64.
prepare_builder() {
  if ! docker buildx inspect "$BUILDER" >/dev/null 2>&1; then
    docker buildx create --name "$BUILDER" --driver docker-container >/dev/null
  fi
  local platforms
  platforms="$(docker buildx inspect --bootstrap "$BUILDER" | sed -n 's/^Platforms: *//p')"
  for platform in ${PLATFORMS//,/ }; do
    if ! tr ',' '\n' <<<"$platforms" | tr -d ' *' | grep -qx "$platform"; then
      echo "error: builder $BUILDER cannot build $platform (it supports: $platforms)." >&2
      echo "Install emulation once with:" >&2
      echo "  docker run --privileged --rm tonistiigi/binfmt --install arm64" >&2
      exit 1
    fi
  done
}

build_and_push() {
  local version="$1" revision="$2"
  docker buildx build "$ROOT" \
    --builder "$BUILDER" \
    --platform "$PLATFORMS" \
    --label "org.opencontainers.image.title=runpad" \
    --label "org.opencontainers.image.version=$version" \
    --label "org.opencontainers.image.revision=$revision" \
    --label "org.opencontainers.image.created=$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --tag "$IMAGE:$version" \
    --tag "$IMAGE:latest" \
    --push
}

verify_push() {
  local version="$1" manifest
  manifest="$(docker buildx imagetools inspect "$IMAGE:$version")"
  for platform in ${PLATFORMS//,/ }; do
    grep -q "Platform: *$platform\$" <<<"$manifest" \
      || fail "$IMAGE:$version has no $platform image"
  done
}

main() {
  local version revision
  version="$(project_version)"
  revision="$(git -C "$ROOT" rev-parse HEAD)"

  echo "[1/6] Checking release $version..."
  check_release "$version"

  echo "[2/6] Running checks..."
  "$ROOT/scripts/check.sh"

  echo "[3/6] Preparing the $PLATFORMS builder..."
  prepare_builder

  echo "[4/6] Building and pushing $IMAGE:$version and :latest..."
  build_and_push "$version" "$revision"

  echo "[5/6] Verifying the pushed platforms..."
  verify_push "$version"

  echo "[6/6] Tagging v$version..."
  git -C "$ROOT" tag -a "v$version" -m "runpad $version"

  echo "Released $IMAGE:$version ($PLATFORMS)."
  echo "Push the tag with: git push origin v$version"
}

main "$@"
