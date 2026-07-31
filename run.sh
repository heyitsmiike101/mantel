#!/usr/bin/env bash
# Build and start Mantel. Run this after every `git pull`.
set -euo pipefail
cd "$(dirname "$0")"

export APP_VERSION="$(tr -d '[:space:]' < VERSION)"
export BUILD_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

echo "Building Mantel v${APP_VERSION}..."
docker compose up -d --build

echo
echo "Mantel v${APP_VERSION} is running at http://localhost:${PORT:-8080}"
echo "Open screens will pick up this version automatically within a minute."
