"""
Slack cancel watcher — runs independently of OpenClaw.

Watches for "stop" or "cancel" messages in Slack and cancels the running
Denario work. Job-aware (Denario MCP job tools, `denario_job_*`):

1. Preferred path: kill the process group(s) of every running Denario job
   runner (`python -m denario.mcp_servers.jobs run <job_dir>`) plus all of
   their descendants (cmbagent_lg runs generated code in its own session, so
   the runner's group alone is not enough). SIGTERM first, SIGKILL after 10 s.
   The MCP server and the container stay up; the agent sees the job as
   cancelled/lost via `denario_job_status`.
2. Fallback (no job runner found — a legacy synchronous tool call is
   blocking the server): kill the MCP server process and SIGTERM PID 1 so
   docker-compose restarts the container. OpenClaw will respawn the MCP
   server on the next session.

This is the safety net for when the agent is unresponsive. The normal stop
protocol is the agent calling `denario_job_cancel` itself (see SOUL.md).

Started by entrypoint.sh alongside the gateway. Requires SLACK_APP_TOKEN
and SLACK_BOT_TOKEN environment variables. No dependencies beyond
slack_bolt + the standard library (uses `ps`/`pkill` from procps).
"""

import os
import re
import signal
import subprocess
import sys
import time

CANCEL_PATTERNS = re.compile(r"^(stop|cancel|abort|kill)$", re.IGNORECASE)
LOG_PREFIX = "[cancel-watcher]"

# argv fingerprint of a Denario job runner subprocess:
#   <python> [-X ...] -m denario.mcp_servers.jobs run <job_dir>
# The executable must be a python and the `-m denario.mcp_servers.jobs run`
# tokens must follow it: a plain `pgrep -f "denario.mcp_servers.jobs run"`
# would also hit any shell/grep/editor whose command line merely contains that
# text (the agent's own exec calls, for instance) and we must never kill those.
# The job_dir is EVERYTHING after the `run` token (it may contain spaces — the
# `ps` args column is whitespace-joined, so splitting on whitespace would
# truncate it and yield a wrong job id).
JOB_RUNNER_RE = re.compile(r"(?:^|\s)-m\s+denario\.mcp_servers\.jobs\s+run\s+(?P<job_dir>.+?)\s*$")
# Grace period between SIGTERM and SIGKILL of a job's process group.
JOB_KILL_GRACE_S = 10
# Job id regex (mirrors denario/mcp_servers/jobs.py): <stage>-<YYYYmmdd-HHMMSS>-<6 hex>
JOB_ID_RE = re.compile(r"^[a-z_]+-\d{8}-\d{6}-[0-9a-f]{6}$")


def log(msg):
    print(f"{LOG_PREFIX} {msg}", flush=True)


# ---------------------------------------------------------------------------
# Process helpers (procps only, no psutil)
# ---------------------------------------------------------------------------

def _run(cmd):
    """Run a command, return (returncode, stdout). Never raises."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return r.returncode, r.stdout
    except Exception as e:  # noqa: BLE001 — a broken `ps` must not crash the watcher
        log(f"command {cmd[0]} failed: {e!r}")
        return -1, ""


def _proc_table():
    """Return {pid: (ppid, pgid, stat, args)} for every visible process."""
    rc, out = _run(["ps", "-eo", "pid=,ppid=,pgid=,stat=,args="])
    table = {}
    if rc != 0:
        return table
    for line in out.splitlines():
        parts = line.split(None, 4)
        if len(parts) < 4:
            continue
        try:
            pid, ppid, pgid = int(parts[0]), int(parts[1]), int(parts[2])
        except ValueError:
            continue
        stat = parts[3]
        args = parts[4] if len(parts) > 4 else ""
        table[pid] = (ppid, pgid, stat, args)
    return table


def _runner_job_dir(args):
    """Return the job_dir if `args` is a job runner command line, else None.

    The executable (first token) must be a python; the job_dir is the whole
    remainder after `-m denario.mcp_servers.jobs run` (spaces included), with
    a trailing slash stripped.
    """
    tokens = args.split(None, 1)
    if not tokens:
        return None
    exe = os.path.basename(tokens[0])
    if not exe.lower().startswith("python"):
        return None
    m = JOB_RUNNER_RE.search(args)
    if not m:
        return None
    job_dir = m.group("job_dir").rstrip("/")
    return job_dir or None


def _job_id_for(job_dir, pid=None):
    """The job id of a runner: the job_dir's basename when it is a well-formed
    id, else the `job_id` recorded in <job_dir>/spec.json, else a pid label."""
    job_id = os.path.basename(job_dir)
    if JOB_ID_RE.match(job_id):
        return job_id
    try:
        import json
        with open(os.path.join(job_dir, "spec.json"), "r", encoding="utf-8") as f:
            spec = json.load(f)
        jid = spec.get("job_id") if isinstance(spec, dict) else None
        if isinstance(jid, str) and JOB_ID_RE.match(jid):
            return jid
    except (OSError, ValueError):
        pass
    # Unexpected layout: still report something identifiable.
    return job_id or (f"pid{pid}" if pid is not None else "?")


def _find_job_runners(table):
    """Return [(pid, pgid, job_id, job_dir)] for every live job runner."""
    runners = []
    me = os.getpid()
    for pid, (_ppid, pgid, stat, args) in table.items():
        if pid == me or stat.startswith("Z"):
            continue
        job_dir = _runner_job_dir(args)
        if job_dir is None:
            continue
        runners.append((pid, pgid, _job_id_for(job_dir, pid), job_dir))
    return runners


def _selftest():
    """Parsing self-test, no Slack, no processes. Run with
        python cancel-watcher.py --selftest
    or  python -c "import runpy; runpy.run_path('cancel-watcher.py')['_selftest']()"
    """
    import json
    import tempfile

    jid = "results-20260920-101500-0a1b2c"
    cases = [
        (f"/opt/venv/bin/python -P -m denario.mcp_servers.jobs run /home/node/work/.denario_jobs/{jid}",
         f"/home/node/work/.denario_jobs/{jid}"),
        (f"python3.12 -m denario.mcp_servers.jobs run /home/node/work/projects/my project/.denario_jobs/{jid}/",
         f"/home/node/work/projects/my project/.denario_jobs/{jid}"),
        (f"/usr/bin/python3 -X dev -u -m denario.mcp_servers.jobs run /a b c/{jid}", f"/a b c/{jid}"),
        # not runners: wrong executable, or the fingerprint is only quoted text
        (f"bash -c python -m denario.mcp_servers.jobs run /x/{jid}", None),
        (f"grep -r denario.mcp_servers.jobs run /x/{jid}", None),
        ("python -m denario.mcp_servers.jobs", None),
        ("python -m denario.mcp_servers.jobs run", None),
        ("", None),
    ]
    for args, want in cases:
        got = _runner_job_dir(args)
        assert got == want, f"_runner_job_dir({args!r}) = {got!r}, want {want!r}"

    # job id: basename when well-formed, else from spec.json, else a label
    assert _job_id_for(f"/x/y/{jid}") == jid
    with tempfile.TemporaryDirectory() as d:
        odd = os.path.join(d, "odd layout dir")
        os.makedirs(odd)
        with open(os.path.join(odd, "spec.json"), "w", encoding="utf-8") as f:
            json.dump({"job_id": jid, "stage": "results"}, f)
        assert _job_id_for(odd) == jid
        assert _job_id_for(os.path.join(d, "nothing here"), pid=42) == "nothing here"
    assert _job_id_for("", pid=42) == "pid42"

    # the ps-table walk: spaces in job_dir survive, non-runners are skipped
    table = {
        10: (1, 10, "S", f"/opt/venv/bin/python -P -m denario.mcp_servers.jobs run /home/node/work/p q/.denario_jobs/{jid}"),
        11: (10, 10, "S", "sleep 300"),
        12: (1, 12, "S", f"grep denario.mcp_servers.jobs run /home/node/work/p q/.denario_jobs/{jid}"),
        13: (1, 13, "Z", f"/opt/venv/bin/python -m denario.mcp_servers.jobs run /z/{jid}"),
    }
    runners = _find_job_runners(table)
    assert runners == [(10, 10, jid, f"/home/node/work/p q/.denario_jobs/{jid}")], runners
    assert _descendants(table, [10]) == {11}
    print(f"{LOG_PREFIX} selftest ok ({len(cases)} argv cases)")
    return True


def _descendants(table, roots):
    """Transitive children of `roots` (pids) according to the ps snapshot."""
    children = {}
    for pid, (ppid, _pgid, _stat, _args) in table.items():
        children.setdefault(ppid, []).append(pid)
    seen, stack = set(), list(roots)
    while stack:
        pid = stack.pop()
        for child in children.get(pid, []):
            if child not in seen:
                seen.add(child)
                stack.append(child)
    return seen


def _alive(pid):
    """True if pid exists and is not a zombie."""
    rc, out = _run(["ps", "-o", "stat=", "-p", str(pid)])
    if rc != 0:
        return False
    stat = out.strip()
    return bool(stat) and not stat.startswith("Z")


def _signal_targets(pgids, pids, sig):
    """Send `sig` to every process group in pgids, then to every pid in pids."""
    my_pgid = os.getpgid(0)
    protected = {0, 1, my_pgid, os.getpid()}
    for pgid in sorted(pgids):
        if pgid in protected:
            log(f"refusing to signal protected process group {pgid}")
            continue
        try:
            os.killpg(pgid, sig)
        except ProcessLookupError:
            pass
        except PermissionError as e:
            log(f"killpg({pgid}, {sig.name}) denied: {e}")
    for pid in sorted(pids):
        if pid in protected:
            continue
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            pass
        except PermissionError as e:
            log(f"kill({pid}, {sig.name}) denied: {e}")


def cancel_jobs():
    """Kill every running Denario job runner, its process group and descendants.

    Returns a list of job ids that were signalled (empty if none were running).
    """
    table = _proc_table()
    runners = _find_job_runners(table)
    if not runners:
        return []

    root_pids = [pid for pid, _pgid, _jid, _jd in runners]
    all_pids = set(root_pids) | _descendants(table, root_pids)
    pgids = {table[p][1] for p in all_pids if p in table}
    job_ids = [jid for _pid, _pgid, jid, _jd in runners]

    for pid, pgid, jid, job_dir in runners:
        log(f"Cancelling job {jid} (pid {pid}, pgid {pgid}, dir {job_dir or '?'})")
    log(f"SIGTERM -> {len(pgids)} process group(s), {len(all_pids)} process(es)")
    _signal_targets(pgids, all_pids, signal.SIGTERM)

    deadline = time.monotonic() + JOB_KILL_GRACE_S
    survivors = set(all_pids)
    while survivors and time.monotonic() < deadline:
        time.sleep(0.5)
        survivors = {p for p in survivors if _alive(p)}

    if survivors:
        log(f"{len(survivors)} process(es) still alive after {JOB_KILL_GRACE_S}s, SIGKILL: {sorted(survivors)}")
        _signal_targets(pgids, survivors, signal.SIGKILL)
        time.sleep(1)
        survivors = {p for p in survivors if _alive(p)}
        if survivors:
            log(f"WARNING: could not kill pids {sorted(survivors)}")
    else:
        log("All job processes exited after SIGTERM")

    # A runner spawned between the snapshot and the kill (or a descendant that
    # forked meanwhile) gets one strict second sweep, SIGKILL straight away.
    table2 = _proc_table()
    leftovers = _find_job_runners(table2)
    if leftovers:
        late_pids = {p for p, _g, _j, _d in leftovers}
        late_pids |= _descendants(table2, list(late_pids))
        late_pgids = {table2[p][1] for p in late_pids if p in table2}
        log(f"second sweep: SIGKILL {[jid for _p, _g, jid, _d in leftovers]}")
        _signal_targets(late_pgids, late_pids, signal.SIGKILL)
        job_ids += [jid for _p, _g, jid, _d in leftovers if jid not in job_ids]

    log(f"Killed job(s): {', '.join(job_ids)}")
    return job_ids


def cancel_server():
    """Legacy path: kill the MCP server, then SIGTERM the gateway to trigger container restart.

    Used only when no job runner is found, i.e. a legacy synchronous tool call
    is blocking the MCP server. OpenClaw does NOT auto-respawn killed MCP
    processes and mcp unset/set deadlocks during active sessions. The only
    reliable recovery is a container restart. docker-compose
    'restart: unless-stopped' brings everything back cleanly in ~10 seconds.
    """
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


def cancel():
    """Cancel running Denario work.

    Returns ("jobs", [job ids]) when job runners were killed (server and
    container stay up), ("server", None) when the legacy kill-server +
    container-restart path ran, or (None, None) when nothing was running.
    """
    job_ids = cancel_jobs()
    if job_ids:
        return "jobs", job_ids
    log("No job runner found, falling back to MCP server kill + container restart")
    if cancel_server():
        return "server", None
    return None, None


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

        try:
            mode, job_ids = cancel()
        except Exception as e:  # noqa: BLE001 — never let the listener die on a cancel
            log(f"cancel() raised: {e!r}")
            say(f"Cancel failed: {e!r} — check /tmp/cancel-watcher.log")
            return

        if mode == "jobs":
            say(
                f"Cancelled job(s): {', '.join(job_ids)}. "
                "The MCP server is still up; `denario_job_status` will report the job as cancelled/lost. "
                "Nothing resumes on its own — tell the scientist what to do next."
            )
        elif mode == "server":
            say("No job runner found; killed the MCP server. Container restarting — back in ~15 seconds.")
        else:
            say("Nothing to cancel — no Denario job or operation is running.")

    log("Starting socket mode listener")
    handler = SocketModeHandler(app, app_token)
    handler.start()


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        _selftest()
        sys.exit(0)
    main()
