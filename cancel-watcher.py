"""
Slack cancel watcher — runs independently of OpenClaw.

Watches for "stop" or "cancel" messages in Slack and kills the running
Denario MCP server process. OpenClaw will respawn it on the next tool call.

Started by entrypoint.sh alongside the gateway. Requires SLACK_APP_TOKEN
and SLACK_BOT_TOKEN environment variables.
"""

import os
import re
import subprocess
import sys

CANCEL_PATTERNS = re.compile(r"^(stop|cancel|abort|kill)$", re.IGNORECASE)
LOG_PREFIX = "[cancel-watcher]"


def log(msg):
    print(f"{LOG_PREFIX} {msg}", flush=True)


def cancel():
    """Kill the MCP server, then SIGTERM the gateway to trigger container restart.

    OpenClaw does NOT auto-respawn killed MCP processes and mcp unset/set
    deadlocks during active sessions. The only reliable recovery is a
    container restart. docker-compose 'restart: unless-stopped' brings
    everything back cleanly in ~10 seconds.
    """
    import signal, time

    result = subprocess.run(
        ["pkill", "-f", "denario_server.py"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        log("No MCP server process found")
        return False

    log("Killed MCP server process, restarting container...")
    time.sleep(1)
    os.kill(1, signal.SIGTERM)
    return True


def main():
    app_token = os.environ.get("SLACK_APP_TOKEN")
    bot_token = os.environ.get("SLACK_BOT_TOKEN")

    if not app_token or not bot_token:
        log("SLACK_APP_TOKEN or SLACK_BOT_TOKEN not set, exiting")
        sys.exit(0)

    try:
        from slack_bolt import App
        from slack_bolt.adapter.socket_mode import SocketModeHandler
    except ImportError:
        log("slack_bolt not installed, exiting")
        sys.exit(0)

    app = App(token=bot_token)

    @app.message(CANCEL_PATTERNS)
    def handle_cancel(message, say):
        user = message.get("user", "unknown")
        text = message.get("text", "")
        log(f"Cancel requested by {user}: '{text}'")

        if cancel():
            say("Cancelled. Container restarting — back in ~15 seconds.")
        else:
            say("Nothing to cancel — no Denario operation is running.")

    log("Starting socket mode listener")
    handler = SocketModeHandler(app, app_token)
    handler.start()


if __name__ == "__main__":
    main()
