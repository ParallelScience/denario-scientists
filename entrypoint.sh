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

# Denario MCP job state (denario_job_* tools): keep it on the per-container
# work volume, OUTSIDE every project git repo (the default would be
# <project_dir>/.denario_jobs) and outside ~/.denario — that directory is ONE
# host dir mounted into every scientist container, so a registry there would
# be shared across containers and hold container-local paths. Set before the
# MCP env allow-list below is built, so the MCP server subprocess inherits it.
if [ -z "$DENARIO_JOBS_DIR" ]; then
  export DENARIO_JOBS_DIR=/home/node/work/.denario_jobs
fi
mkdir -p "$DENARIO_JOBS_DIR" 2>/dev/null || echo "[entrypoint] WARNING: could not create $DENARIO_JOBS_DIR"
echo "[entrypoint] DENARIO_JOBS_DIR=$DENARIO_JOBS_DIR"

# Patch MCP env with actual API keys from container environment
if [ -f "$CONFIG" ]; then
  node -e "
    const fs = require('fs');
    const cfg = JSON.parse(fs.readFileSync('$CONFIG', 'utf8'));
    const servers = cfg.mcp?.servers || {};
    for (const [name, server] of Object.entries(servers)) {
      if (!server.env) server.env = {};
      // This list is the ONLY thing the MCP server subprocess sees: OpenClaw
      // starts stdio servers with mcp.servers.<name>.env, not the container
      // env. Anything set in compose but missing here is silently unset for
      // the pipeline (DENARIO_GIT=on read as "auto", Langfuse tracing off).
      const keys = [
        'ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'GEMINI_API_KEY',
        'GOOGLE_API_KEY', 'GOOGLE_GEMINI_API_KEY', 'MINIMAX_API_KEY',
        'NVIDIA_API_KEY', 'ZAI_API_KEY', 'VLLM_API_KEY',
        'MATERIALS_API_KEY', 'MP_API_KEY', 'PERPLEXITY_API_KEY',
        'GITHUB_TOKEN', 'GITHUB_ORG', 'DENARIO_GIT', 'ELEVENLABS_API_KEY',
        'LANGFUSE_BASE_URL', 'LANGFUSE_HOST', 'LANGFUSE_PUBLIC_KEY', 'LANGFUSE_SECRET_KEY',
        'SCIENTIST_NAME',
        // Denario MCP job model: DENARIO_JOBS_DIR (set above) holds the job
        // state and the registry (<DENARIO_JOBS_DIR>/registry.jsonl) on the
        // per-container work volume; HOME is the fallback the server would use
        // without it (~/.denario/jobs — a SHARED mount here, hence the export).
        // DENARIO_JOB_REGISTRY / DENARIO_JOB_WAIT_MAX / DENARIO_JOB_STALE_S are
        // optional knobs.
        'HOME', 'DENARIO_JOBS_DIR', 'DENARIO_JOB_REGISTRY',
        'DENARIO_JOB_WAIT_MAX', 'DENARIO_JOB_STALE_S',
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
