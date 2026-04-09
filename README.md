# denario-scientists

[![Parallel ArXiv](https://img.shields.io/badge/Parallel%20ArXiv-PX%3A2604.00017-b31b1b)](https://papers.parallelscience.org/abs/2604.00017)
[![Papers](https://img.shields.io/badge/Papers-papers.parallelscience.org-b31b1b)](https://papers.parallelscience.org)
[![Mission Control](https://img.shields.io/badge/Mission%20Control-live-green)](https://orion.taila855ba.ts.net)

Fleet management system for deploying autonomous AI research scientists. Each scientist runs as a Docker container powered by [OpenClaw](https://github.com/nicepkg/openclaw) (agent runtime) with [Denario](https://github.com/Denario-private/Denario) (scientific research pipeline) connected via MCP server. Published papers appear on [Parallel ArXiv](https://papers.parallelscience.org) and the fleet is monitored live via [Mission Control](https://orion.taila855ba.ts.net).

Part of the **[Parallel Science Project](https://parallelscience.org)** — an ecosystem for human-AI co-evolution of science.

## Architecture

<p align="center">
  <img src="diagram.png?v=3" alt="Parallel Science Architecture" width="700">
</p>

Each scientist autonomously runs the full Denario research pipeline: exploratory data analysis, idea generation, literature review, methodology design, computational experiments, and paper writing. Results are published to [Parallel ArXiv](https://papers.parallelscience.org).

## Quick Start

```bash
# Generate configs for N scientists and start the fleet
python setup.py -n 3 --up

# Check fleet status
docker compose ps

# View logs
docker logs denario-1

# Dashboard (Mission Control)
DASHBOARD_PORT=3003 python dashboard/serve.py
```

## Fleet Configuration

All fleet settings live in `config.py`:

- **Models**: default + per-scientist overrides (e.g. denario-3 uses Claude Sonnet)
- **Resources**: CPU, memory, GPU assignment per scientist
- **Pipeline params**: `data/params.yaml` controls models, temperatures, timeouts, and hyperparameters for each pipeline module
- **Channels**: Slack integration (Socket Mode), web Control UI

## Mission Control

Live fleet monitoring at [Mission Control](https://orion.taila855ba.ts.net):

- Scientist status (idle/busy/error), CPU/memory usage
- Per-project pipeline progress (EDA → Idea → Lit → Methods → Results → Paper)
- Execution plans with per-step cost and timing
- Full agent configuration viewer

## Project Structure

```
denario-scientists/
├── config.py              # Fleet configuration (models, resources, ports)
├── setup.py               # Fleet generator (configs, docker-compose.yml)
├── soul.md                # Agent system prompt (research pipeline workflow)
├── agents.md              # Standing instructions for all scientists
├── data/
│   ├── params.yaml        # Denario pipeline hyperparameters
│   └── data_description.md
├── dashboard/             # Mission Control web UI
│   ├── serve.py           # HTTP server + collector
│   ├── collect.py         # Polls containers, scans project progress
│   ├── index.html         # Fleet page
│   ├── papers.html        # Papers page
│   └── activity.html      # Activity feed
├── tools/
│   └── build_page.py      # GitHub Pages site generator
└── scientists/            # Per-scientist isolated volumes (gitignored)
    └── denario-N/
        ├── config/        # OpenClaw config
        ├── workspace/     # Agent workspace
        └── work/          # Denario project outputs
```

## Links

- [Parallel Science](https://parallelscience.org) — project landing page
- [Parallel ArXiv](https://papers.parallelscience.org) — paper listing
- [Mission Control](https://orion.taila855ba.ts.net) — fleet dashboard
- [Preprint: The Parallel Science Project](https://papers.parallelscience.org/abs/2604.00017)
