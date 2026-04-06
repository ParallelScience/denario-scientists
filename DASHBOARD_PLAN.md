# Dashboard Plan — Parallel Science Mission Control

Public read-only dashboard at `dashboard.parallelscience.org` showing fleet status, research progress, and published papers.

## Architecture

```
orion
├── collect.py          # Cron (every 30s): polls state, writes status.json
├── index.html          # Single-page dashboard (reads status.json, auto-refreshes)
├── serve.py            # Simple HTTP server (port 3001)
└── status.json         # Generated fleet state

Tailscale Funnel → dashboard.parallelscience.org → 127.0.0.1:3001
```

No build step, no framework, no database. Single HTML + vanilla JS + Tailwind CDN. Dark theme matching parallelscience.org.

## Sections

### 1. Fleet Cards (top)

One card per scientist showing:
- Name, status (idle / busy / error / offline)
- Resource allocation (CPU, RAM, GPU if any)
- Current resource usage (CPU %, memory %)
- Current project name (if any)
- Pipeline progress bar: EDA → Idea → Literature → Methods → Results → Paper
- Current iteration number
- Link to scientist's Control UI (internal only, or omit for public)

Status logic:
- **offline**: container not running or unhealthy
- **busy**: a project dir was modified in the last 10 minutes
- **error**: container restarting or unhealthy
- **idle**: running but no recent activity

### 2. Recent Papers (middle)

Latest completed papers from scientists' work dirs. Each entry shows:
- Paper title (parsed from paper.tex `\title{}`)
- Scientist name
- Time completed
- Link to GitHub Pages site (if published)
- Link to papers.parallelscience.org listing

"View all papers" link → papers.parallelscience.org

### 3. Activity Feed (middle-bottom)

Chronological stream, latest first. Derived from:
- Project directory timestamps (creation = project started, step files = step completed)
- Docker container events (restart, OOM, etc.)

Each entry: `timestamp · scientist · event description`

### 4. Published Repos (footer)

Horizontal list of ParallelScience GitHub repos with links. From `gh repo list ParallelScience --json name,url`.

Footer links: papers.parallelscience.org | github.com/ParallelScience | Denario

## Data Collection (collect.py)

Runs every 30s via a loop (or systemd timer). Writes `status.json`.

```python
status = {
    "timestamp": "2026-04-06T10:00:00Z",
    "scientists": [
        {
            "name": "denario-1",
            "status": "idle",              # idle/busy/error/offline
            "container": {
                "running": true,
                "healthy": true,
                "uptime": "2d 3h",
                "cpu_percent": 2.1,
                "memory_used_mb": 684,
                "memory_limit_mb": 8192,
                "cpus": 4,
                "gpu": null
            },
            "current_project": null,
            "projects": [
                {
                    "name": "damped_oscillators_v3",
                    "iteration": 2,
                    "steps_completed": ["eda", "idea", "literature", "methods", "results", "paper"],
                    "last_modified": "2026-04-06T08:30:00Z",
                    "github_url": "https://github.com/ParallelScience/denario-1-damped-oscillators-v3",
                    "pages_url": "https://parallelscience.github.io/denario-1-damped-oscillators-v3"
                }
            ]
        },
        ...
    ],
    "repos": [
        {"name": "denario-3-dark-matter", "url": "https://github.com/ParallelScience/..."}
    ]
}
```

### Data sources

| Data | Source | Method |
|------|--------|--------|
| Container health + uptime | `docker inspect` | JSON output |
| CPU/memory usage | `docker stats --no-stream` | Parse output |
| Resource limits | `docker inspect` (NanoCpus, Memory) | Already known from config |
| GPU assignment | config.py GPU_ASSIGNMENT | Static |
| Project list | `scientists/*/work/projects/` | Scan dirs |
| Pipeline progress | Check for `EDA/eda.md`, `Iteration*/input_files/idea.md`, `methods.md`, `results.md`, `paper.tex` | File existence |
| Current project | Most recently modified project dir | mtime |
| Paper titles | Parse `\title{}` from `paper.tex` | Regex |
| GitHub repos | `gh repo list ParallelScience --json name,url,homepageUrl` | CLI |
| Activity feed | File mtimes across project dirs | Sort by time |

## Serving

```python
# serve.py — minimal
import http.server, socketserver, threading, time, subprocess

PORT = 3001

# Start collector in background
def collect_loop():
    while True:
        subprocess.run(["python", "collect.py"])
        time.sleep(30)

threading.Thread(target=collect_loop, daemon=True).start()

handler = http.server.SimpleHTTPRequestHandler
with socketserver.TCPServer(("", PORT), handler) as httpd:
    httpd.serve_forever()
```

## Tailscale Funnel Setup

```bash
# On orion
tailscale funnel --bg --https 10000 http://127.0.0.1:3001

# DNS: CNAME dashboard.parallelscience.org → orion.taila855ba.ts.net
```

Update the parent CLAUDE.md Tailscale table:
| 10000 | Funnel (public) | 127.0.0.1:3001 | Dashboard (Mission Control) |

## Design

- Dark background (#0a0a0a), light text — match parallelscience.org
- EB Garamond headings (same font as landing page)
- Monospace for data/stats
- Cards with subtle borders, status dot (green/yellow/red/gray)
- Progress bar as segmented steps, filled = complete
- Responsive: cards wrap on mobile
- No emojis, minimal color — green for healthy, amber for busy, red for error

## File Location

`/scratch/scratch-aiscientist/parallelscience/denario-scientists/dashboard/`

Lives inside denario-scientists since it reads from `scientists/*/work/` directly. Could also be a sibling repo if preferred.

## Implementation Order

1. `collect.py` — get the data pipeline working, output status.json
2. `index.html` — build the frontend reading status.json
3. `serve.py` — wire up the server + collector loop
4. Tailscale funnel + DNS
5. Add link to parallelscience.org landing page ("Dashboard" button alongside Papers and Denario)
