#!/usr/bin/env python3
"""
Dashboard server — serves static files and runs the collector in a background thread.
"""

import http.server
import os
import socketserver
import subprocess
import sys
import threading
import time

PORT = int(os.environ.get("DASHBOARD_PORT", 3001))
COLLECT_INTERVAL = int(os.environ.get("COLLECT_INTERVAL", 10))
DASHBOARD_DIR = os.path.dirname(os.path.abspath(__file__))


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
    handler = http.server.SimpleHTTPRequestHandler
    handler.extensions_map.update({".json": "application/json"})

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), handler) as httpd:
        print(f"Dashboard serving at http://localhost:{PORT}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down.")
            httpd.shutdown()


if __name__ == "__main__":
    main()
