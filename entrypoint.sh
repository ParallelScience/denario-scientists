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
  for f in /app/bootstrap/*; do
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

# Run auto-pair in background, then start gateway
sh /app/auto-pair.sh &
exec node dist/index.js gateway --bind lan --port 18789 --allow-unconfigured
