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

# Pre-seed Claude Code's first-run state so a detached session doesn't block on
# interactive prompts: the onboarding wizard (theme picker), the workspace-trust
# dialog, and the "detected a custom API key — use it?" prompt. We DECLINE the
# ANTHROPIC_API_KEY so the top-level session authenticates with the mounted Max
# subscription (Remote Control needs subscription auth, and the API key would
# otherwise take precedence and bill per-token); the MCP-server child still
# inherits ANTHROPIC_API_KEY from the environment, which is what it needs.
# Merge into ~/.claude.json (in HOME, not the mounted config dir) every start.
VER="$(claude --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"
ANTHROPIC_SUFFIX="$(printf %s "${ANTHROPIC_API_KEY:-}" | tail -c 20)"
python3 - "$HOME/.claude.json" "$DENARIO_WORK_DIR" "${VER:-2.1.161}" "$ANTHROPIC_SUFFIX" <<'PY'
import json, sys
path, workdir, ver, suffix = sys.argv[1:5]
try:
    d = json.load(open(path))
except Exception:
    d = {}
d["hasCompletedOnboarding"] = True
d.setdefault("lastOnboardingVersion", ver)
d.setdefault("theme", "dark")
p = d.setdefault("projects", {}).setdefault(workdir, {})
p["hasTrustDialogAccepted"] = True
p["hasCompletedProjectOnboarding"] = True
if suffix:
    car = d.setdefault("customApiKeyResponses", {})
    car.setdefault("approved", [])
    rej = car.setdefault("rejected", [])
    if suffix not in rej:
        rej.append(suffix)
json.dump(d, open(path, "w"), indent=2)
print("[entrypoint] seeded ~/.claude.json (onboarding+trust; declined API key ...%s)" % (suffix[-6:] or "none"))
PY

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
# --plugin-dir must point at the PLUGIN directory (with .claude-plugin/plugin.json
# + .mcp.json), NOT the marketplace root — the root loads no MCP servers.
# Launch in DEFAULT permission mode (no flag). IMPORTANT: passing a
# --permission-mode (auto or bypassPermissions) shows a one-time consent screen
# that blocks BEFORE Remote Control registers, so the session never appears in
# the dashboard — an unanswerable deadlock. Default mode connects Remote Control
# first; the human driver then switches to auto mode in-session (Shift+Tab) from
# claude.ai/code, which is answerable because the session is live. Set
# CLAUDE_PERMISSION_MODE only if you understand it re-introduces the startup gate.
exec claude --remote-control "$SCIENTIST_NAME" \
  --plugin-dir /opt/denario-plugin/plugins/denario \
  ${CLAUDE_PERMISSION_MODE:+--permission-mode "$CLAUDE_PERMISSION_MODE"} \
  ${CLAUDE_EXTRA_ARGS:-}
