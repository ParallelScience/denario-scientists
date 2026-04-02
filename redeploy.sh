#!/usr/bin/env bash
set -euo pipefail

# Redeploy Denario Scientists fleet.
# Pulls latest code for all source dependencies, rebuilds images, and restarts containers.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PARENT_DIR="$(dirname "$SCRIPT_DIR")"

# Source repos used as Docker build contexts
REPOS=(
  "$PARENT_DIR/ag2"
  "$PARENT_DIR/cmbagent"
  "$PARENT_DIR/Denario"
  "$PARENT_DIR/openclaw"
)

echo "=== Pulling latest code ==="
for repo in "${REPOS[@]}"; do
  if [ -d "$repo/.git" ]; then
    echo "  Pulling $(basename "$repo")..."
    git -C "$repo" pull --ff-only
  else
    echo "  Skipping $(basename "$repo") (not a git repo)"
  fi
done

echo ""
echo "=== Rebuilding and restarting fleet ==="
cd "$SCRIPT_DIR"

docker compose down
docker compose build --no-cache
docker compose up -d

echo ""
echo "=== Waiting for health checks ==="
sleep 10
docker compose ps

echo ""
echo "=== Done ==="
