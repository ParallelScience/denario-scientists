#!/bin/sh
# Patch MCP server env in openclaw.json with actual container environment values,
# then start the gateway.

CONFIG="/home/node/.openclaw/openclaw.json"

if [ -f "$CONFIG" ]; then
  # Use node to patch the MCP env block with actual env vars
  node -e "
    const fs = require('fs');
    const cfg = JSON.parse(fs.readFileSync('$CONFIG', 'utf8'));
    const servers = cfg.mcp?.servers || {};
    for (const [name, server] of Object.entries(servers)) {
      if (!server.env) server.env = {};
      // Inject API keys from container environment
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
