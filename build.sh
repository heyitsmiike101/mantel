#!/usr/bin/env bash
# Build the multi-architecture image (amd64 + arm64) so it runs on a normal PC,
# a NAS, and a Raspberry Pi from the same tag.
#
#   ./build.sh                      build both architectures, keep them local
#   ./build.sh --push ghcr.io/you/family-calendar
#                                   build and push a multi-arch manifest
#
# Requires the buildx plugin and, on an x86 host, QEMU for the arm64 leg:
#   docker run --privileged --rm tonistiigi/binfmt --install arm64
set -euo pipefail
cd "$(dirname "$0")"

APP_VERSION="$(tr -d '[:space:]' < VERSION)"
BUILD_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
PLATFORMS="${PLATFORMS:-linux/amd64,linux/arm64}"
BUILDER="${BUILDER:-famcal}"

PUSH=0
IMAGE="family-calendar"
if [ "${1:-}" = "--push" ]; then
  PUSH=1
  IMAGE="${2:?usage: ./build.sh --push <registry/image>}"
fi

if ! docker buildx inspect "$BUILDER" >/dev/null 2>&1; then
  echo "Creating buildx builder '$BUILDER'..."
  docker buildx create --name "$BUILDER" --driver docker-container >/dev/null
fi

echo "Building ${IMAGE}:${APP_VERSION} for ${PLATFORMS}..."

args=(
  --builder "$BUILDER"
  --platform "$PLATFORMS"
  --build-arg "APP_VERSION=${APP_VERSION}"
  --build-arg "BUILD_TIME=${BUILD_TIME}"
  --tag "${IMAGE}:${APP_VERSION}"
  --tag "${IMAGE}:latest"
)

if [ "$PUSH" -eq 1 ]; then
  args+=(--push)
else
  # A multi-platform result cannot be loaded into the local image store, so a
  # local build stays in the build cache. Use --push, or build a single platform
  # with PLATFORMS=linux/amd64, if you need a runnable local image.
  args+=(--output "type=image,push=false")
fi

docker buildx build "${args[@]}" .

echo
echo "Built ${IMAGE}:${APP_VERSION} for ${PLATFORMS}"
[ "$PUSH" -eq 1 ] && echo "Pushed. Pi and PC both pull the same tag." || true
