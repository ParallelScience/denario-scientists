#!/usr/bin/env bash
set -euo pipefail

# Redeploy Denario Scientists fleet.
#
# Usage:
#   ./redeploy.sh -n 2              # quick: reset configs + restart containers
#   ./redeploy.sh --build -n 2      # full: pull code, rebuild images, restart
#   ./redeploy.sh --full-reset -n 2 # wipe everything and redeploy fresh

if echo "$@" | grep -qE -- "(^| )(-h|--help)( |$)"; then
  cat <<'HELP'
Usage: ./redeploy.sh [options]

By default: regenerates configs and restarts containers (fast, no rebuild).
With --build: also pulls latest code and rebuilds Docker images.

Options:
  -n, --scientists N    Number of scientists to deploy (default: from config.py)
  --model MODEL         Override default LLM model
  --build               Pull code and rebuild Docker images (slow)
  --reset               Reset configs only (default behavior)
  --full-reset          Wipe everything including work dirs and start fresh

Examples:
  ./redeploy.sh -n 2              # quick restart with updated configs
  ./redeploy.sh --build -n 2      # full rebuild from latest source
  ./redeploy.sh --full-reset -n 2 # wipe all data and redeploy fresh
HELP
  exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PARENT_DIR="$(dirname "$SCRIPT_DIR")"

# Check for --build flag
DO_BUILD=false
SETUP_ARGS=""
for arg in "$@"; do
  if [ "$arg" = "--build" ]; then
    DO_BUILD=true
  else
    SETUP_ARGS="$SETUP_ARGS $arg"
  fi
done

# If --full-reset is passed, use it; otherwise default to --reset
if echo "$SETUP_ARGS" | grep -q -- "--full-reset"; then
  RESET_FLAG=""
else
  RESET_FLAG="--reset"
fi

if $DO_BUILD; then
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
fi

echo ""
echo "=== Regenerating configs ==="
cd "$SCRIPT_DIR"
python setup.py $RESET_FLAG $SETUP_ARGS

if $DO_BUILD; then
  echo ""
  echo "=== Rebuilding and restarting fleet ==="
  docker compose down
  docker compose build --no-cache
  docker compose up -d
else
  echo ""
  echo "=== Restarting fleet ==="
  docker compose restart
fi

echo ""
echo "=== Waiting for health checks ==="
sleep 10
docker compose ps

echo ""
echo "=== Done ==="
