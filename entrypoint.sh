#!/bin/sh
# 1. Copy workspace bootstrap files (before gateway creates defaults)
# 2. Patch MCP server env with container API keys
# 3. Start the gateway

WORKSPACE="/home/node/.openclaw/workspace"
CONFIG="/home/node/.openclaw/openclaw.json"

# Copy bootstrap files from /app/bootstrap/ (baked into image or mounted)
# into the workspace BEFORE the gateway runs, so OpenClaw's writeFileIfMissing
# sees them and doesn't overwrite with defaults.
if [ -d /app/bootstrap ]; then
  # Copy all files including dotfiles (e.g. .gitignore)
  for f in /app/bootstrap/* /app/bootstrap/.*; do
    [ -f "$f" ] || continue
    target="$WORKSPACE/$(basename "$f")"
    cp -f "$f" "$target"
  done
  echo "[entrypoint] Installed bootstrap files into workspace"
fi

# Patch MCP env with actual API keys from container environment
if [ -f "$CONFIG" ]; then
  node -e "
    const fs = require('fs');
    const cfg = JSON.parse(fs.readFileSync('$CONFIG', 'utf8'));
    const servers = cfg.mcp?.servers || {};
    for (const [name, server] of Object.entries(servers)) {
      if (!server.env) server.env = {};
      const keys = [
        'ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'GEMINI_API_KEY',
        'GOOGLE_API_KEY', 'GOOGLE_GEMINI_API_KEY'
      ];
      for (const key of keys) {
        if (process.env[key]) {
          server.env[key] = process.env[key];
        }
      }
    }
    fs.writeFileSync('$CONFIG', JSON.stringify(cfg, null, 2));
    console.log('[entrypoint] Patched MCP env with API keys');
  "
fi

# Configure git identity for this scientist
git config --global user.name "${SCIENTIST_NAME:-denario}"
git config --global user.email "${SCIENTIST_NAME:-denario}@parallelscience.ai"

# Authenticate gh CLI and configure git to use it for HTTPS credentials
if [ -n "$GITHUB_TOKEN" ]; then
  echo "$GITHUB_TOKEN" | gh auth login --with-token 2>/dev/null
  gh auth setup-git
  echo "[entrypoint] GitHub CLI authenticated + git credential helper configured"
fi

# Run auto-pair in background
sh /app/auto-pair.sh &

# Start cancel watcher if Slack tokens are set
if [ -n "$SLACK_APP_TOKEN" ] && [ -n "$SLACK_BOT_TOKEN" ]; then
  /opt/denario-venv/bin/python /app/cancel-watcher.py >> /tmp/cancel-watcher.log 2>&1 &
  echo "[entrypoint] Started cancel watcher"
fi

exec node dist/index.js gateway --bind lan --port 18789 --allow-unconfigured
