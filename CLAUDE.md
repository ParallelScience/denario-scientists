# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A fleet management system for deploying autonomous AI research scientist agents. Each scientist runs as a Docker container powered by OpenClaw (agent runtime) with Denario (scientific research pipeline) connected via MCP server. Scientists can be interacted with via Slack or a web Control UI.

## Dependencies

This repo has no pip dependencies itself. It generates Docker configurations that build from sibling repos:

```
../openclaw    → OpenClaw gateway (Node/TypeScript, Docker build context)
../ag2         → AG2 multi-agent framework (installed in container venv)
../cmbagent    → Research backend (installed in container venv)
../Denario     → Research assistant + MCP server (installed in container venv)
```

All four sibling repos must exist. The Dockerfile uses `additional_contexts` to pull them in at build time.

## Commands

```bash
# Generate configs for N scientists (default: 1, set in config.py)
python setup.py -n 2

# Generate configs AND build/start containers
python setup.py -n 2 --up

# Reset configs and regenerate (keeps work dirs)
python setup.py --reset -n 2

# Full reset: wipe configs, sessions, and work dirs
python setup.py --full-reset -n 2

# Override the default LLM model
python setup.py -n 1 --model anthropic/claude-sonnet-4-6

# Rebuild and redeploy from latest source (pulls all sibling repos + self)
./redeploy.sh

# Standard docker compose operations
docker compose up -d
docker compose down
docker compose logs -f denario-1
docker compose ps

# Tail Denario MCP tool logs (detailed pipeline output)
docker exec denario-1 tail -f /tmp/denario-mcp.log

# Cancel a running operation from Slack: type "stop", "cancel", "abort", or "kill"
# The cancel-watcher.py (independent Slack listener) kills the MCP server
# and restarts the container (OpenClaw does not auto-respawn MCP processes).
# cancel-watcher.py is mounted read-only; changes take effect on container restart.

# Tail cancel watcher logs
docker exec denario-1 tail -f /tmp/cancel-watcher.log
```

## Architecture

### Fleet Generation Pipeline

`setup.py` is the central orchestrator. Running it:
1. Copies `soul.md`, `agents.md`, and `bootstrap/.gitignore` into `bootstrap/` (as `SOUL.md`, `AGENTS.md`, `.gitignore`)
2. Creates per-scientist directories under `scientists/denario-N/` with `config/`, `workspace/`, and `work/` subdirs
3. Generates `openclaw.json` config for each scientist (model, MCP server, Slack, plugins)
4. Ensures `.env` has gateway auth tokens for each scientist
5. Generates `docker-compose.yml` from the fleet config

### Container Internals

The Dockerfile extends OpenClaw with a Python 3.12 venv containing the full Denario stack (ag2 → cmbagent → Denario). On startup, `entrypoint.sh`:
1. Copies bootstrap files (`SOUL.md`, `AGENTS.md`, `.gitignore`) into the workspace before the gateway writes defaults
2. Patches `openclaw.json` MCP server entries with container API keys
3. Configures git identity and authenticates `gh` CLI (if `GITHUB_TOKEN` is set)
4. Starts the OpenClaw gateway

### Key File Roles

- **`config.py`** — Single source of truth: number of scientists, default model, port allocation, resource limits (CPU/memory defaults + per-scientist overrides via `RESOURCE_OVERRIDES`), GPU assignment (`GPU_ASSIGNMENT`), MCP server path. Default: 4 CPUs / 8 GB per scientist; denario-3 gets 32 CPUs / 64 GB + GPU 0 (NVIDIA RTX PRO 6000 Blackwell, 96 GB VRAM)
- **`soul.md`** — Agent system prompt: defines the Denario research pipeline workflow, tool usage, reporting rules. Gets installed as `SOUL.md` in each scientist's workspace
- **`agents.md`** — Standing instructions loaded at every agent session: tool usage notes, shell capabilities, lessons learned. Gets installed as `AGENTS.md`
- **`data/params.yaml`** — Single source of truth for all Denario pipeline configuration: models, temperatures, and hyperparameters (max_n_steps, max_n_attempts, code_execution_timeout, enable_vlm_review) for EDA and Analysis modules. Mounted read-only into containers at `/home/node/data/`. Also used by `Denario/tests/denario_test/` via relative path.
- **`data/data_description.md`** — Schema and physics documentation for the bundled damped oscillator dataset
- **`tools/build_page.py`** — Generates GitHub Pages site (`docs/index.html`) from `paper.tex`. Mounted read-only at `/home/node/tools/`
- **`tools/page_template.html`** — HTML template with `{{TITLE}}`, `{{AUTHOR}}`, `{{DATE}}`, `{{TIME}}`, `{{GITHUB_URL}}`, `{{ABSTRACT}}` placeholders

### Port Scheme

Scientist `denario-i` gets:
- Gateway: `BASE_GATEWAY_PORT + i - 1` (default base: 18796)
- Bridge: `BASE_BRIDGE_PORT + i - 1` (default base: 18806)

Control UI accessible at `http://localhost:{gateway_port}/#token={token}`

### Per-scientist Isolation

Each scientist gets isolated volumes:
- `scientists/<name>/config/` → `/home/node/.openclaw` (OpenClaw config + agent state)
- `scientists/<name>/workspace/` → `/home/node/.openclaw/workspace` (workspace files)
- `scientists/<name>/work/` → `/home/node/work` (Denario project outputs)
- `./data/` → `/home/node/data:ro` (shared read-only data)
- `./tools/` → `/home/node/tools:ro` (shared read-only tooling)

Slack integration is enabled only on denario-1 (Socket Mode).

### Dashboard (Mission Control)

`dashboard/` contains a public fleet monitoring site served at `dashboard.parallelscience.org`.

- **`collect.py`** — Runs every 10s, polls Docker containers and scans `scientists/*/work/projects/` for pipeline progress. Detects busy status via MCP log recency (`/tmp/denario-mcp.log` mtime < 60s) and high CPU usage. Parses project titles from `paper.tex` (preferred) or `idea.md` (fallback). Aggregates per-project costs from three sources: log files (`logs/{stage}_iter{N}.log`), CMBAgent JSON cost reports (`Iteration*/experiment_output/{planning,control}/cost/`), and EDA/compare_plans reports. Writes `status.json`.
- **`serve.py`** — HTTP server (default port 3001, override with `DASHBOARD_PORT`) + collector loop. Start with `DASHBOARD_PORT=3003 python dashboard/serve.py`.
- **`index.html`** — Fleet page: scientist cards with status, resources, per-project cost badge, pipeline progress bar (EDA → Idea → Lit → Methods → Results → Paper), expandable plan execution table (per-step cost/time/status).
- **`papers.html`** — Latest 20 completed papers with title, scientist, date, total project cost. Links to `papers.parallelscience.org` for full archive.
- **`activity.html`** — Summary stats (running/busy/projects/papers/total fleet cost) + chronological event feed (last 50).
- **`shared.js`** / **`style.css`** — Shared utilities and dark theme (EB Garamond headings, JetBrains Mono body, #0a0a0a background).

Tailscale funnel: port 10000 → localhost:3003. DNS CNAME `dashboard.parallelscience.org → orion.taila855ba.ts.net`.

### Generated Files (gitignored)

- `docker-compose.yml` — Generated by `setup.py`, do not edit manually
- `scientists/` — Per-scientist config, workspace, and work directories
- `dashboard/status.json` — Generated by `collect.py`, do not edit manually
- `.env` — API keys and gateway tokens

## Environment Variables

Required in `.env`:
- `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` — LLM providers (at least one needed)
- `DENARIO_<N>_TOKEN` — per-scientist gateway tokens (auto-generated by setup.py)

Optional:
- `GEMINI_API_KEY`, `GOOGLE_API_KEY`, `GOOGLE_GEMINI_API_KEY`
- `GITHUB_TOKEN` — GitHub PAT for publishing research projects to the org (fine-grained, scoped to `ParallelScience` with repo Administration + Contents permissions)
- `GITHUB_ORG` — GitHub org name (default: `ParallelScience`)
- `ELEVENLABS_API_KEY` — ElevenLabs TTS API key (voice ID configured in setup.py)
- `SLACK_BOT_TOKEN_<N>`, `SLACK_APP_TOKEN_<N>` — per-scientist Slack app tokens (e.g. `SLACK_BOT_TOKEN_1`, `SLACK_APP_TOKEN_2`)
- `DATA_DIR` — override shared data mount (default: `./data`)
- `TZ` — timezone (default: UTC)
