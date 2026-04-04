#!/usr/bin/env bash
set -euo pipefail

# Redeploy Denario Scientists fleet.
# Pulls latest code, regenerates configs, rebuilds images, and restarts containers.
#
# Usage:
#   ./redeploy.sh          # redeploy with default scientist count (from config.py)
#   ./redeploy.sh -n 2     # redeploy with 2 scientists

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PARENT_DIR="$(dirname "$SCRIPT_DIR")"

# Pass all arguments through to setup.py (e.g., -n 2)
SETUP_ARGS="$@"

# Source repos used as Docker build contexts
REPOS=(
  "$SCRIPT_DIR"
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
echo "=== Regenerating configs ==="
cd "$SCRIPT_DIR"
python setup.py --reset $SETUP_ARGS

echo ""
echo "=== Rebuilding and restarting fleet ==="
docker compose down
docker compose build --no-cache
docker compose up -d

echo ""
echo "=== Waiting for health checks ==="
sleep 10
docker compose ps

echo ""
echo "=== Done ==="
