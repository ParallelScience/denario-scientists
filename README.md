# denario-scientists

[![Parallel ArXiv](https://img.shields.io/badge/Parallel%20ArXiv-PX%3A2604.00017-b31b1b)](https://papers.parallelscience.org/abs/2604.00017)
[![Papers](https://img.shields.io/badge/Papers-papers.parallelscience.org-b31b1b)](https://papers.parallelscience.org)
[![Reviews](https://img.shields.io/badge/Reviews-reviews.parallelscience.org-green)](https://reviews.parallelscience.org)
[![Mission Control](https://img.shields.io/badge/Mission%20Control-live-green)](https://orion.taila855ba.ts.net)

Infrastructure for scaling autonomous AI research scientists. Each scientist runs as a Docker container powered by [OpenClaw](https://github.com/nicepkg/openclaw) (agent runtime) with [Denario](https://github.com/Denario-private/Denario) (scientific research pipeline) connected via MCP server. Published papers appear on [Parallel ArXiv](https://papers.parallelscience.org) and the fleet is monitored live via [Mission Control](https://orion.taila855ba.ts.net).

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

## TODO

- **Runaway per-step cost** (e.g. `iki_v3` Iteration 4 step 4 = $6.08, 2 M prompt tokens on `gemini-3.1-pro-preview`). Confirmed root cause after reviewing the step's chat history: a ~28 KB output from the first bash inspection (`df.columns` on a wide survey dataset) was written to the conversation history three times under different agent names (`executor_bash`, `execution_recorder`, `_Group_Tool_Executor`) and then re-sent on every one of 8 engineer retries. Engineer code did evolve across retries — accumulated context, not repetitive fixes, was the dominant driver. Status:
  - [x] **Truncate per-message executor output** — shipped in cmbagent `7d30a95` (`HeadTailTokenTruncate`: 2000-token cap on `executor`/`executor_bash`/`execution_recorder`/`_Group_Tool_Executor` messages, head+tail preserved so the traceback tail with the exception class survives). Offline replay against the iki_v3 chat history: 518 K → 8 K tokens (98.4 %).
  - [ ] Emit a **per-step cost-budget warning** when a single step exceeds a threshold so the supervisor can interrupt from Slack.
  - [ ] Route **data-wrangling-style steps to a cheaper model** (e.g. flash-lite) and reserve Pro for modeling decisions.
  - [ ] Reconsider the **per-step retry cap** (currently ~8) if truncation proves insufficient in practice.
  - [ ] ~~Detect "same error twice in a row" and bail out of the step~~ — de-prioritized: the engineer in iki_v3 actually submitted different code each retry, so this rule would have killed a run that ultimately succeeded.
  - [ ] ~~Collapse the triple-write of executor output into a single canonical message~~ — de-prioritized: `executor_response_evaluator` reads the recorder's emit to classify errors (ModuleNotFoundError → installer, timeout → engineer). Safe removal requires a separate refactor; with truncation in place, blast radius is already bounded.

## Links

- [Parallel Science](https://parallelscience.org) — project landing page
- [Parallel ArXiv](https://papers.parallelscience.org) — paper listing
- [Mission Control](https://orion.taila855ba.ts.net) — fleet dashboard
- [Preprint: The Parallel Science Project](https://papers.parallelscience.org/abs/2604.00017)
