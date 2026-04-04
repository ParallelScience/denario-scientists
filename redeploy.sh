#!/usr/bin/env bash
set -euo pipefail

# Redeploy Denario Scientists fleet.
# Pulls latest code, regenerates configs, rebuilds images, and restarts containers.
#
# Usage:
#   ./redeploy.sh              # redeploy with default scientist count (from config.py)
#   ./redeploy.sh -n 2         # redeploy with 2 scientists
#   ./redeploy.sh --full-reset -n 2  # wipe everything and redeploy fresh

if echo "$@" | grep -qE -- "(^| )(-h|--help)( |$)"; then
  cat <<'HELP'
Usage: ./redeploy.sh [options]

Pulls latest code from all sibling repos, regenerates configs, rebuilds
Docker images, and restarts the fleet.

Options (passed through to setup.py):
  -n, --scientists N    Number of scientists to deploy (default: from config.py)
  --model MODEL         Override default LLM model
  --reset               Reset configs only (default behavior)
  --full-reset           Wipe everything including work dirs and start fresh

Examples:
  ./redeploy.sh -n 2              # standard redeploy with 2 scientists
  ./redeploy.sh --full-reset -n 2 # wipe all data and redeploy fresh
HELP
  exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PARENT_DIR="$(dirname "$SCRIPT_DIR")"

# If --full-reset is passed, use it; otherwise default to --reset
SETUP_ARGS="$@"
if echo "$SETUP_ARGS" | grep -q -- "--full-reset"; then
  RESET_FLAG=""  # --full-reset is already in SETUP_ARGS
else
  RESET_FLAG="--reset"
fi

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
python setup.py $RESET_FLAG $SETUP_ARGS

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
