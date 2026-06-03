#!/bin/sh
# Entrypoint for a Claude-Code-native Denario scientist.
#
# Seeds the claude.ai credentials, configures git/gh for the MCP tools'
# auto-commit/push, then launches a named Remote Control session running the
# denario plugin. Control it from claude.ai/code or the mobile app by name.
set -eu

: "${SCIENTIST_NAME:=denario}"
: "${DENARIO_WORK_DIR:=$HOME/work}"

mkdir -p "$HOME/.claude"

# Seed the claude.ai subscription credentials (mounted read-only) into the
# writable config dir so the session can authenticate (and refresh tokens).
if [ -f /seed/credentials.json ]; then
  cp /seed/credentials.json "$HOME/.claude/.credentials.json"
  chmod 600 "$HOME/.claude/.credentials.json"
  echo "[entrypoint] seeded claude.ai credentials"
else
  echo "[entrypoint] WARNING: no /seed/credentials.json — run 'claude auth login'"
  echo "             on the host and mount ~/.claude/.credentials.json (CLAUDE_CREDENTIALS_FILE)."
fi

# git identity + gh auth so denario_* tools can commit and push.
git config --global user.name "${SCIENTIST_NAME}"
git config --global user.email "${SCIENTIST_NAME}@parallelscience.ai"
if [ -n "${GITHUB_TOKEN:-}" ]; then
  echo "$GITHUB_TOKEN" | gh auth login --with-token 2>/dev/null && gh auth setup-git \
    && echo "[entrypoint] gh authenticated + git credential helper configured" || true
fi

# Work from the scientist's project directory.
cd "$DENARIO_WORK_DIR" 2>/dev/null || cd "$HOME"

echo "[entrypoint] launching Claude Code Remote Control session: $SCIENTIST_NAME"
echo "[entrypoint]   attach at claude.ai/code (session '$SCIENTIST_NAME') or the mobile app"

# --plugin-dir loads the denario plugin (skills + bundled MCP servers).
# CLAUDE_EXTRA_ARGS is a runtime hook (e.g. trust/permission flags) so you can
# tune launch behaviour from .env without rebuilding the image.
exec claude --remote-control "$SCIENTIST_NAME" \
  --plugin-dir /opt/denario-plugin \
  ${CLAUDE_EXTRA_ARGS:-}
