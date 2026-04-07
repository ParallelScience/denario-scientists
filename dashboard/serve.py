#!/usr/bin/env python3
"""
Dashboard server — serves static files, stage content API, and runs the
collector in a background thread.
"""

import http.server
import json
import os
import re
import socketserver
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PORT = int(os.environ.get("DASHBOARD_PORT", 3001))
COLLECT_INTERVAL = int(os.environ.get("COLLECT_INTERVAL", 10))
DASHBOARD_DIR = os.path.dirname(os.path.abspath(__file__))
SCIENTISTS_DIR = Path(DASHBOARD_DIR).parent / "scientists"

# Map stage names to file locations relative to a project dir.
# "iteration" means the file lives inside Iteration{N}/input_files/.
STAGE_FILES = {
    "eda": {"path": "EDA/eda.md", "per_iteration": False},
    "idea": {"path": "input_files/idea.md", "per_iteration": True},
    "literature": {"path": "input_files/literature.md", "per_iteration": True},
    "methods": {"path": "input_files/methods.md", "per_iteration": True},
    "results": {"path": "input_files/results.md", "per_iteration": True},
    "paper": {"path": "paper.tex", "per_iteration": False},
}

# Safe name pattern
SAFE_NAME = re.compile(r"^[a-zA-Z0-9_-]+$")


def resolve_stage_file(scientist: str, project: str, stage: str, iteration: int | None) -> Path | None:
    """Resolve the file path for a given stage, with safety checks."""
    if not SAFE_NAME.match(scientist) or not SAFE_NAME.match(project):
        return None
    if stage not in STAGE_FILES:
        return None

    info = STAGE_FILES[stage]
    proj_dir = SCIENTISTS_DIR / scientist / "work" / "projects" / project

    if not proj_dir.is_dir():
        return None

    if not info["per_iteration"]:
        candidate = proj_dir / info["path"]
    else:
        # Find the right iteration
        if iteration is not None:
            iter_dir = proj_dir / f"Iteration{iteration}"
        else:
            # Use the latest iteration
            iters = sorted(
                [d for d in proj_dir.iterdir() if d.is_dir() and re.match(r"Iteration\d+", d.name)],
                key=lambda d: int(re.search(r"\d+", d.name).group()),
            )
            iter_dir = iters[-1] if iters else None
        if not iter_dir or not iter_dir.is_dir():
            return None
        candidate = iter_dir / info["path"]

    # Security: ensure resolved path is inside scientists dir
    try:
        candidate = candidate.resolve()
        if not str(candidate).startswith(str(SCIENTISTS_DIR.resolve())):
            return None
    except (OSError, ValueError):
        return None

    return candidate if candidate.is_file() else None


class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    """Extends SimpleHTTPRequestHandler with a /api/stage endpoint."""

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/stage":
            self.handle_stage_api(parsed)
        else:
            super().do_GET()

    def handle_stage_api(self, parsed):
        params = parse_qs(parsed.query)
        scientist = params.get("scientist", [None])[0]
        project = params.get("project", [None])[0]
        stage = params.get("stage", [None])[0]
        iteration_str = params.get("iteration", [None])[0]
        iteration = int(iteration_str) if iteration_str and iteration_str.isdigit() else None

        if not scientist or not project or not stage:
            self.send_json(400, {"error": "Missing scientist, project, or stage parameter"})
            return

        filepath = resolve_stage_file(scientist, project, stage, iteration)
        if not filepath:
            self.send_json(404, {"error": "Stage content not found"})
            return

        try:
            content = filepath.read_text(errors="ignore")
            self.send_json(200, {
                "scientist": scientist,
                "project": project,
                "stage": stage,
                "iteration": iteration,
                "filename": filepath.name,
                "content": content,
            })
        except OSError:
            self.send_json(500, {"error": "Failed to read file"})

    def send_json(self, code, data):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        # Suppress request logs for cleaner output
        pass


def collect_loop():
    """Run collect.py every COLLECT_INTERVAL seconds."""
    collect_script = os.path.join(DASHBOARD_DIR, "collect.py")
    while True:
        try:
            subprocess.run(
                [sys.executable, collect_script],
                cwd=DASHBOARD_DIR,
                timeout=20,
                capture_output=True,
            )
        except Exception as e:
            print(f"Collector error: {e}", file=sys.stderr)
        time.sleep(COLLECT_INTERVAL)


def main():
    # Run initial collection before starting server
    print(f"Running initial data collection...")
    try:
        subprocess.run(
            [sys.executable, os.path.join(DASHBOARD_DIR, "collect.py")],
            cwd=DASHBOARD_DIR,
            timeout=20,
        )
    except Exception as e:
        print(f"Initial collection failed: {e}", file=sys.stderr)

    # Start collector thread
    collector = threading.Thread(target=collect_loop, daemon=True)
    collector.start()
    print(f"Collector running every {COLLECT_INTERVAL}s")

    # Serve files from dashboard directory
    os.chdir(DASHBOARD_DIR)
    DashboardHandler.extensions_map.update({".json": "application/json"})

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), DashboardHandler) as httpd:
        print(f"Dashboard serving at http://localhost:{PORT}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down.")
            httpd.shutdown()


if __name__ == "__main__":
    main()
