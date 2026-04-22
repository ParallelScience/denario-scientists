#!/usr/bin/env python3
"""
Collect fleet status from Docker containers and scientist work directories.
Writes status.json for the dashboard frontend.
"""

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add parent dir so we can import config
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import (
    GPU_ASSIGNMENT,
    RESOURCE_OVERRIDES,
    PARAMS_OVERRIDES,
    DEFAULT_MEMORY,
    DEFAULT_CPUS,
    scientists,
)
import yaml

SCIENTISTS_DIR = Path(__file__).resolve().parent.parent / "scientists"
OUTPUT_FILE = Path(__file__).resolve().parent / "status.json"

# Pipeline stages in order
PIPELINE_STAGES = ["eda", "idea", "literature", "methods", "results", "paper"]


def parse_memory_mb(mem_str: str) -> int:
    """Convert '8g' or '64g' to MB."""
    mem_str = mem_str.lower().strip()
    if mem_str.endswith("g"):
        return int(mem_str[:-1]) * 1024
    if mem_str.endswith("m"):
        return int(mem_str[:-1])
    return int(mem_str)


def run_cmd(cmd: list[str], timeout: int = 10) -> str | None:
    """Run a command and return stdout, or None on failure."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip() if r.returncode == 0 else None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def get_container_info(container_name: str) -> dict:
    """Get container status, health, and uptime via docker inspect."""
    raw = run_cmd(["docker", "inspect", container_name])
    if not raw:
        return {"running": False, "healthy": False, "uptime": None,
                "cpu_percent": 0, "memory_used_mb": 0}

    try:
        info = json.loads(raw)[0]
    except (json.JSONDecodeError, IndexError):
        return {"running": False, "healthy": False, "uptime": None,
                "cpu_percent": 0, "memory_used_mb": 0}

    state = info.get("State", {})
    running = state.get("Running", False)
    health_status = state.get("Health", {}).get("Status", "")
    healthy = health_status == "healthy" if health_status else running
    restarting = state.get("Restarting", False)

    # Start time
    started_at = None
    uptime = None
    if running and state.get("StartedAt"):
        try:
            started = datetime.fromisoformat(state["StartedAt"].replace("Z", "+00:00"))
            started_at = started.isoformat()
            delta = datetime.now(timezone.utc) - started
            days = delta.days
            hours = delta.seconds // 3600
            if days > 0:
                uptime = f"{days}d {hours}h"
            elif hours > 0:
                uptime = f"{hours}h {(delta.seconds % 3600) // 60}m"
            else:
                uptime = f"{delta.seconds // 60}m"
        except (ValueError, TypeError):
            pass

    return {
        "running": running,
        "healthy": healthy and not restarting,
        "restarting": restarting,
        "started_at": started_at,
        "uptime": uptime,
        "cpu_percent": 0,
        "memory_used_mb": 0,
    }


def get_container_stats(container_name: str) -> dict:
    """Get live CPU/memory usage via docker stats."""
    raw = run_cmd(
        ["docker", "stats", "--no-stream", "--format",
         "{{.CPUPerc}}|{{.MemUsage}}", container_name],
        timeout=15,
    )
    if not raw:
        return {"cpu_percent": 0, "memory_used_mb": 0}

    try:
        parts = raw.split("|")
        cpu = float(parts[0].strip().rstrip("%"))
        mem_str = parts[1].split("/")[0].strip()
        # Parse memory like "684MiB" or "1.2GiB"
        mem_mb = 0
        if "GiB" in mem_str:
            mem_mb = int(float(mem_str.replace("GiB", "").strip()) * 1024)
        elif "MiB" in mem_str:
            mem_mb = int(float(mem_str.replace("MiB", "").strip()))
        elif "KiB" in mem_str:
            mem_mb = max(1, int(float(mem_str.replace("KiB", "").strip()) / 1024))
        return {"cpu_percent": round(cpu, 1), "memory_used_mb": mem_mb}
    except (ValueError, IndexError):
        return {"cpu_percent": 0, "memory_used_mb": 0}


def detect_iteration_stages(iter_dir: Path) -> list[str]:
    """Detect which pipeline stages are complete for a single iteration."""
    completed = []
    input_files = iter_dir / "input_files"
    if (input_files / "idea.md").exists():
        completed.append("idea")
    lit_out = iter_dir / "literature_output"
    if lit_out.exists() or (input_files / "literature.md").exists():
        completed.append("literature")
    if (input_files / "methods.md").exists():
        completed.append("methods")
    if (input_files / "results.md").exists():
        completed.append("results")
    return completed


def detect_pipeline_stages_all(project_dir: Path) -> dict:
    """Detect pipeline stages per iteration and overall.

    Returns dict with:
      - stages_completed: list of all completed stages (union across iterations + EDA/paper)
      - stages_by_iteration: list of per-iteration stage lists, indexed by iteration number
    """
    has_eda = (project_dir / "EDA" / "eda.md").exists()
    has_paper = (project_dir / "paper.tex").exists()

    iterations = sorted(
        [d for d in project_dir.iterdir() if d.is_dir() and re.match(r"Iteration\d+", d.name)],
        key=lambda d: int(re.search(r"\d+", d.name).group()),
    )

    stages_by_iteration = []
    all_stages = set()
    if has_eda:
        all_stages.add("eda")

    for iter_dir in iterations:
        iter_stages = []
        if has_eda:
            iter_stages.append("eda")
        iter_stages.extend(detect_iteration_stages(iter_dir))
        if has_paper:
            iter_stages.append("paper")
        stages_by_iteration.append(iter_stages)
        all_stages.update(iter_stages)

    if has_paper:
        all_stages.add("paper")

    # If no iterations but EDA exists
    if not iterations and has_eda:
        stages_by_iteration = [["eda"]]

    # Maintain canonical order
    stage_order = ["eda", "idea", "literature", "methods", "results", "paper"]
    stages_completed = [s for s in stage_order if s in all_stages]

    return {
        "stages_completed": stages_completed,
        "stages_by_iteration": stages_by_iteration,
    }


def get_plan_steps(project_dir: Path, iteration_dir: Path | None = None) -> list[dict] | None:
    """Extract plan steps and their execution status from experiment_output.

    If iteration_dir is given, reads from that iteration. Otherwise falls back
    to the latest iteration in the project.
    """
    if iteration_dir is not None:
        exp_out = iteration_dir / "experiment_output"
    else:
        iterations = sorted(
            [d for d in project_dir.iterdir() if d.is_dir() and re.match(r"Iteration\d+", d.name)],
            key=lambda d: int(re.search(r"\d+", d.name).group()),
        )
        if not iterations:
            return None
        exp_out = iterations[-1] / "experiment_output"
    if not exp_out.exists():
        return None

    # Load plan
    plan_file = exp_out / "planning" / "final_plan.json"
    if not plan_file.exists():
        return None

    try:
        with open(plan_file) as f:
            plan_data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    sub_tasks = plan_data.get("sub_tasks", [])
    if not sub_tasks:
        return None

    steps = []
    for i, task in enumerate(sub_tasks, 1):
        step = {
            "number": i,
            "total": len(sub_tasks),
            "name": task.get("sub_task", f"Step {i}"),
            "agent": task.get("sub_task_agent", "unknown"),
            "status": "pending",
            "attempt": None,
            "max_attempts": None,
            "time_seconds": None,
            "cost_dollars": None,
        }

        # Check execution status from chat history
        chat_file = exp_out / "control" / "chats" / f"chat_history_step_{i}.json"
        if chat_file.exists():
            step["status"] = "completed"
            try:
                with open(chat_file) as f:
                    chat = json.load(f)
                # Look for the last record_status call
                for msg in reversed(chat):
                    tool_calls = msg.get("tool_calls", [])
                    for tc in tool_calls:
                        fn = tc.get("function", {})
                        if fn.get("name") == "record_status":
                            try:
                                args = json.loads(fn.get("arguments", "{}"))
                                status = args.get("step_status", "")
                                if status == "in progress":
                                    step["status"] = "in_progress"
                                elif status == "completed":
                                    step["status"] = "completed"
                                # Extract attempt info from step_iteration
                                step_iter = args.get("step_iteration", "")
                                if "/" in str(step_iter):
                                    parts = str(step_iter).split("/")
                                    step["attempt"] = int(parts[0])
                                    step["max_attempts"] = int(parts[1])
                            except (json.JSONDecodeError, ValueError):
                                pass
                            break
                    if step["status"] != "pending":
                        break
            except (json.JSONDecodeError, OSError):
                pass

        # Load timing
        time_dir = exp_out / "control" / "time"
        if time_dir.exists():
            for tf in time_dir.glob(f"timing_report_step_{i}_*.json"):
                try:
                    with open(tf) as f:
                        t = json.load(f)
                    step["time_seconds"] = round(t.get("total_time", 0), 1)
                except (json.JSONDecodeError, OSError):
                    pass
                break

        # Load cost
        cost_dir = exp_out / "control" / "cost"
        if cost_dir.exists():
            for cf in cost_dir.glob(f"cost_report_step_{i}_*.json"):
                try:
                    with open(cf) as f:
                        costs = json.load(f)
                    for entry in costs:
                        if entry.get("Agent") == "Total":
                            step["cost_dollars"] = round(entry.get("Cost ($)", 0), 4)
                            break
                except (json.JSONDecodeError, OSError):
                    pass
                break

        steps.append(step)

    # Planning cost and time
    planning_info = {"time_seconds": None, "cost_dollars": None}
    plan_time_dir = exp_out / "planning" / "time"
    if plan_time_dir.exists():
        for tf in plan_time_dir.glob("timing_report_planning_*.json"):
            try:
                with open(tf) as f:
                    t = json.load(f)
                planning_info["time_seconds"] = round(t.get("total_time", 0), 1)
            except (json.JSONDecodeError, OSError):
                pass
            break
    plan_cost_dir = exp_out / "planning" / "cost"
    if plan_cost_dir.exists():
        for cf in plan_cost_dir.glob("cost_report_*.json"):
            try:
                with open(cf) as f:
                    costs = json.load(f)
                for entry in costs:
                    if entry.get("Agent") == "Total":
                        planning_info["cost_dollars"] = round(entry.get("Cost ($)", 0), 4)
                        break
            except (json.JSONDecodeError, OSError):
                pass
            break

    return {"steps": steps, "planning": planning_info}


def get_project_costs(project_dir: Path) -> dict:
    """Aggregate all costs for a project across iterations and pipeline stages.

    Returns dict with total_dollars, by_source breakdown, and by_iteration.
    Sources: results (CMBAgent JSON reports), idea, methods, paper, evaluate,
    classifier (log files), eda (JSON reports), compare_plans (JSON reports).
    """
    total = 0.0
    by_source = {}  # e.g. {"results": 5.23, "idea": 0.10, ...}
    by_iteration = {}  # e.g. {0: 1.23, 1: 0.98, ...}

    # --- 1. Log file costs (idea, methods, paper, evaluate, classifier) ---
    logs_dir = project_dir / "logs"
    if logs_dir.exists():
        cost_re = re.compile(r"Cost:\s*\$([0-9.]+)")
        iter_re = re.compile(r"_iter(\d+)\.log$")
        for log_file in logs_dir.glob("*.log"):
            m_iter = iter_re.search(log_file.name)
            if not m_iter:
                continue
            iter_num = int(m_iter.group(1))
            # Determine stage from filename prefix
            stage = log_file.name.split("_iter")[0]

            try:
                # Read last 500 bytes for the cost line
                size = log_file.stat().st_size
                with open(log_file, "r", errors="ignore") as f:
                    if size > 500:
                        f.seek(size - 500)
                    tail = f.read()
                m_cost = cost_re.search(tail)
                if m_cost:
                    cost = float(m_cost.group(1))
                    # Skip results logs — we use JSON reports for those (more accurate)
                    if stage == "results":
                        continue
                    total += cost
                    by_source[stage] = by_source.get(stage, 0) + cost
                    by_iteration[iter_num] = by_iteration.get(iter_num, 0) + cost
            except OSError:
                pass

    # --- 2. JSON cost reports (CMBAgent planning + control steps) ---
    def sum_json_costs(cost_dir: Path) -> float:
        """Sum 'Total' costs from all cost_report JSON files in a directory."""
        subtotal = 0.0
        if not cost_dir.exists():
            return subtotal
        for cf in cost_dir.glob("cost_report_*.json"):
            try:
                with open(cf) as f:
                    entries = json.load(f)
                for entry in entries:
                    if entry.get("Agent") == "Total":
                        subtotal += entry.get("Cost ($)", 0)
                        break
            except (json.JSONDecodeError, OSError):
                pass
        return subtotal

    # Per-iteration experiment costs
    for iter_dir in project_dir.iterdir():
        if not iter_dir.is_dir() or not re.match(r"Iteration\d+", iter_dir.name):
            continue
        iter_num = int(re.search(r"\d+", iter_dir.name).group())
        exp_out = iter_dir / "experiment_output"
        if not exp_out.exists():
            continue
        planning_cost = sum_json_costs(exp_out / "planning" / "cost")
        control_cost = sum_json_costs(exp_out / "control" / "cost")
        iter_results_cost = planning_cost + control_cost
        total += iter_results_cost
        by_source["results"] = by_source.get("results", 0) + iter_results_cost
        by_iteration[iter_num] = by_iteration.get(iter_num, 0) + iter_results_cost

    # --- 3. EDA costs (JSON reports) ---
    eda_out = project_dir / "EDA" / "EDA_output"
    if eda_out.exists():
        eda_cost = sum_json_costs(eda_out / "planning" / "cost") + sum_json_costs(eda_out / "control" / "cost")
        if eda_cost > 0:
            total += eda_cost
            by_source["eda"] = by_source.get("eda", 0) + eda_cost

    # --- 4. compare_plans costs ---
    compare_cost_dir = project_dir / "compare_plans" / "cost"
    compare_cost = sum_json_costs(compare_cost_dir)
    if compare_cost > 0:
        total += compare_cost
        by_source["compare_plans"] = by_source.get("compare_plans", 0) + compare_cost

    return {
        "total_dollars": round(total, 4),
        "by_source": {k: round(v, 4) for k, v in sorted(by_source.items())},
        "by_iteration": {str(k): round(v, 4) for k, v in sorted(by_iteration.items())},
    }


def scan_projects(scientist_name: str) -> list[dict]:
    """Scan a scientist's work directory for projects."""
    work_dir = SCIENTISTS_DIR / scientist_name / "work" / "projects"
    if not work_dir.exists():
        return []

    projects = []
    for proj_dir in sorted(work_dir.iterdir()):
        if not proj_dir.is_dir() or proj_dir.name.startswith("."):
            continue

        # Skip non-project directories (no params.yaml or Iteration*)
        has_iterations = any(
            d.is_dir() and re.match(r"Iteration\d+", d.name)
            for d in proj_dir.iterdir()
        )
        has_eda = (proj_dir / "EDA").exists()
        if not has_iterations and not has_eda:
            continue

        # Count iterations
        iterations = sorted(
            [d for d in proj_dir.iterdir()
             if d.is_dir() and re.match(r"Iteration\d+", d.name)],
            key=lambda d: int(re.search(r"\d+", d.name).group()),
        )
        iteration_count = len(iterations)

        # Last modified
        try:
            mtime = proj_dir.stat().st_mtime
            # Check children for more recent mtime
            for child in proj_dir.rglob("*"):
                try:
                    child_mtime = child.stat().st_mtime
                    if child_mtime > mtime:
                        mtime = child_mtime
                except OSError:
                    pass
            last_modified = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
        except OSError:
            last_modified = None

        # Parse title: prefer paper.tex, fall back to idea.md from latest iteration
        title = None
        paper_tex = proj_dir / "paper.tex"
        if paper_tex.exists():
            try:
                content = paper_tex.read_text(errors="ignore")[:5000]
                m = re.search(r"\\title\{(.+?)\}", content, re.DOTALL)
                if m:
                    title = re.sub(r"\s+", " ", m.group(1)).strip()
            except OSError:
                pass

        if not title and iterations:
            # Check latest iteration's idea.md for title
            for it in reversed(iterations):
                idea_file = it / "input_files" / "idea.md"
                if idea_file.exists():
                    try:
                        first_lines = idea_file.read_text(errors="ignore")[:500]
                        m = re.search(r"\*\*Title\*?\*?:?\s*(.+)", first_lines)
                        if m:
                            title = m.group(1).strip().rstrip("*")
                            break
                    except OSError:
                        pass

        # GitHub URLs
        github_url = None
        pages_url = None
        git_dir = proj_dir / ".git"
        if git_dir.exists():
            remote = run_cmd(["git", "-C", str(proj_dir), "remote", "get-url", "origin"])
            if remote:
                github_url = remote.replace(".git", "")
                # Derive pages URL from github URL
                m = re.match(r"https://github\.com/([^/]+)/([^/]+)", github_url)
                if m:
                    pages_url = f"https://{m.group(1).lower()}.github.io/{m.group(2)}"

        # Best iteration (from latest iteration's best_iteration.md)
        best_iteration = None
        if iterations:
            for it in reversed(iterations):
                bi_file = it / "input_files" / "best_iteration.md"
                if bi_file.exists():
                    try:
                        m = re.search(r"Best iteration:\s*(\d+)", bi_file.read_text(errors="ignore"))
                        if m:
                            best_iteration = int(m.group(1))
                    except OSError:
                        pass
                    break

        # Pipeline stages (per-iteration)
        pipeline = detect_pipeline_stages_all(proj_dir)

        # Plan execution detail (per-iteration)
        plan_by_iteration = {}
        data_desc_by_iteration = {}
        for it in iterations:
            idx = int(re.search(r"\d+", it.name).group())
            plan = get_plan_steps(proj_dir, iteration_dir=it)
            if plan:
                plan_by_iteration[idx] = plan
            dd_file = it / "input_files" / "data_description.md"
            if dd_file.exists():
                try:
                    text = dd_file.read_text(errors="ignore")
                    if len(text) > 20000:
                        text = text[:20000] + "\n\n…(truncated)"
                    data_desc_by_iteration[idx] = text
                except OSError:
                    pass
        plan_execution = plan_by_iteration.get(iteration_count - 1) if iterations else None

        # Cost aggregation
        cost = get_project_costs(proj_dir)

        projects.append({
            "name": proj_dir.name,
            "title": title,
            "iteration_count": iteration_count,
            "best_iteration": best_iteration,
            "stages_completed": pipeline["stages_completed"],
            "stages_by_iteration": pipeline["stages_by_iteration"],
            "plan_execution": plan_execution,
            "plan_by_iteration": plan_by_iteration,
            "data_desc_by_iteration": {str(k): v for k, v in data_desc_by_iteration.items()},
            "cost": cost,
            "last_modified": last_modified,
            "github_url": github_url,
            "pages_url": pages_url,
        })

    return projects


def get_mcp_log_age(container_name: str) -> float | None:
    """Return seconds since the MCP log was last written to, or None if unavailable."""
    raw = run_cmd(
        ["docker", "exec", container_name, "stat", "-c", "%Y", "/tmp/denario-mcp.log"],
        timeout=5,
    )
    if not raw:
        return None
    try:
        mtime = float(raw.strip())
        return time.time() - mtime
    except (ValueError, TypeError):
        return None


def get_scientist_status(container_info: dict, container_name: str) -> str:
    """Determine scientist status: offline, error, busy, idle."""
    if not container_info["running"]:
        return "offline"
    if container_info.get("restarting") or not container_info["healthy"]:
        return "error"

    # Check MCP log recency — if written to in the last 60s, scientist is busy
    mcp_age = get_mcp_log_age(container_name)
    if mcp_age is not None and mcp_age < 60:
        return "busy"

    # Secondary: high CPU usage suggests active work
    if container_info.get("cpu_percent", 0) > 50:
        return "busy"

    return "idle"


def get_current_project(projects: list[dict]) -> str | None:
    """Return the most recently modified project name."""
    if not projects:
        return None
    most_recent = max(projects, key=lambda p: p.get("last_modified") or "")
    return most_recent["name"] if most_recent.get("last_modified") else None


def get_github_repos() -> list[dict]:
    """Fetch ParallelScience org repos."""
    raw = run_cmd(
        ["gh", "repo", "list", "ParallelScience", "--json", "name,url,homepageUrl", "--limit", "100"],
        timeout=15,
    )
    if not raw:
        return []
    try:
        repos = json.loads(raw)
        return [{"name": r["name"], "url": r["url"], "homepage": r.get("homepageUrl")}
                for r in repos]
    except (json.JSONDecodeError, KeyError):
        return []


def build_activity_feed(all_scientists: list[dict]) -> list[dict]:
    """Build a chronological activity feed from project data."""
    events = []

    for sci in all_scientists:
        name = sci["name"]
        for proj in sci.get("projects", []):
            # Project existence = started
            if proj.get("last_modified"):
                events.append({
                    "timestamp": proj["last_modified"],
                    "scientist": name,
                    "event": f"Working on {proj['name']}",
                    "type": "activity",
                })

            # Completed stages
            for stage in proj.get("stages_completed", []):
                # Use last_modified as approximate time (we don't have per-stage timestamps easily)
                events.append({
                    "timestamp": proj.get("last_modified"),
                    "scientist": name,
                    "event": f"Completed {stage} for {proj['name']}",
                    "type": "stage_complete",
                })

            # Published paper
            if proj.get("title") and "paper" in proj.get("stages_completed", []):
                events.append({
                    "timestamp": proj.get("last_modified"),
                    "scientist": name,
                    "event": f"Published paper: {proj['title']}",
                    "type": "paper",
                })

    # Sort by timestamp descending
    events.sort(key=lambda e: e.get("timestamp") or "", reverse=True)
    return events[:50]  # Keep last 50


def get_scientist_config(sci_name: str) -> dict:
    """Extract safe (no secrets) config info for a scientist.

    Reads openclaw.json for agent/channel settings and merges
    params.yaml with per-scientist overrides from config.py.
    """
    config = {}

    # --- OpenClaw config (safe fields only) ---
    oc_path = SCIENTISTS_DIR / sci_name / "config" / "openclaw.json"
    if oc_path.exists():
        try:
            with open(oc_path) as f:
                oc = json.load(f)
            defaults = oc.get("agents", {}).get("defaults", {})
            config["gateway_model"] = defaults.get("model")
            config["timeout_seconds"] = defaults.get("timeoutSeconds")

            # Enabled channels
            channels = oc.get("channels", {})
            config["channels"] = [ch for ch, v in channels.items() if v.get("enabled")]

            # Enabled plugins
            plugins = oc.get("plugins", {}).get("entries", {})
            config["plugins"] = [p for p, v in plugins.items() if v.get("enabled")]

            # MCP servers (names only)
            mcp = oc.get("mcp", {}).get("servers", {})
            config["mcp_servers"] = list(mcp.keys())
        except (json.JSONDecodeError, OSError):
            pass

    # --- Denario params (base + per-scientist overrides) ---
    params_path = Path(__file__).resolve().parent.parent / "data" / "params.yaml"
    if params_path.exists():
        try:
            with open(params_path) as f:
                params = yaml.safe_load(f) or {}

            # Apply per-scientist overrides
            overrides = PARAMS_OVERRIDES.get(sci_name, {})
            for key, val in overrides.items():
                if isinstance(val, dict) and key in params and isinstance(params[key], dict):
                    params[key].update(val)
                else:
                    params[key] = val

            config["max_iterations"] = params.get("max_iterations")

            # EDA module config
            eda = params.get("EDA module", {})
            config["eda_timeout"] = eda.get("code_execution_timeout")
            config["eda_vlm_review"] = eda.get("enable_vlm_review")
            config["eda_max_steps"] = eda.get("max_n_steps")

            # Analysis module config
            analysis = params.get("Analysis module", {})
            config["analysis_timeout"] = analysis.get("code_execution_timeout")
            config["analysis_vlm_review"] = analysis.get("enable_vlm_review")
            config["analysis_max_steps"] = analysis.get("max_n_steps")

            # Key models (engineer = primary research model)
            engineer = analysis.get("engineer", eda.get("engineer", {}))
            config["research_model"] = engineer.get("model")
            config["research_temperature"] = engineer.get("temperature")

            # Paper model
            paper = params.get("Paper module", {})
            section_writer = paper.get("section_writer", {})
            config["paper_model"] = section_writer.get("model")

            # Plan reviewer model
            plan_reviewer = analysis.get("plan_reviewer", eda.get("plan_reviewer", {}))
            config["plan_review_model"] = plan_reviewer.get("model")

            # Full merged params for the config modal (all modules with agents)
            config["params"] = params
        except (yaml.YAMLError, OSError):
            pass

    return config


def collect():
    """Main collection routine."""
    # Detect how many scientists exist from the scientists/ directory
    scientist_dirs = sorted(
        [d.name for d in SCIENTISTS_DIR.iterdir() if d.is_dir() and d.name.startswith("denario-")],
        key=lambda n: int(re.search(r"\d+", n).group()),
    ) if SCIENTISTS_DIR.exists() else []

    if not scientist_dirs:
        # Fall back to config
        scientist_dirs = [s["name"] for s in scientists(5)]

    configs = {s["name"]: s for s in scientists(len(scientist_dirs))}
    all_scientists = []

    # Collect container stats in one batch call
    stats_raw = run_cmd(
        ["docker", "stats", "--no-stream", "--format", "{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}"]
        + scientist_dirs,
        timeout=15,
    )
    stats_map = {}
    if stats_raw:
        for line in stats_raw.strip().split("\n"):
            parts = line.split("|")
            if len(parts) >= 3:
                cname = parts[0].strip()
                try:
                    cpu = float(parts[1].strip().rstrip("%"))
                except ValueError:
                    cpu = 0
                mem_str = parts[2].split("/")[0].strip()
                mem_mb = 0
                if "GiB" in mem_str:
                    mem_mb = int(float(mem_str.replace("GiB", "").strip()) * 1024)
                elif "MiB" in mem_str:
                    mem_mb = int(float(mem_str.replace("MiB", "").strip()))
                stats_map[cname] = {"cpu_percent": round(cpu, 1), "memory_used_mb": mem_mb}

    for sci_name in scientist_dirs:
        cfg = configs.get(sci_name, {})
        container_info = get_container_info(sci_name)

        # Merge stats
        if sci_name in stats_map:
            container_info.update(stats_map[sci_name])

        projects = scan_projects(sci_name)
        status = get_scientist_status(container_info, sci_name)
        current_project = get_current_project(projects) if status == "busy" else None

        gpu_ids = GPU_ASSIGNMENT.get(sci_name)
        gpu_label = None
        if gpu_ids:
            gpu_label = f"GPU {', '.join(gpu_ids)}"

        all_scientists.append({
            "name": sci_name,
            "status": status,
            "container": {
                "running": container_info["running"],
                "healthy": container_info["healthy"],
                "started_at": container_info.get("started_at"),
                "uptime": container_info["uptime"],
                "cpu_percent": container_info["cpu_percent"],
                "memory_used_mb": container_info["memory_used_mb"],
                "memory_limit_mb": parse_memory_mb(
                    RESOURCE_OVERRIDES.get(sci_name, {}).get("memory", DEFAULT_MEMORY)
                ),
                "cpus": int(RESOURCE_OVERRIDES.get(sci_name, {}).get("cpus", DEFAULT_CPUS)),
                "gpu": gpu_label,
            },
            "model": cfg.get("model", "unknown"),
            "config": get_scientist_config(sci_name),
            "current_project": current_project,
            "projects": projects,
        })

    activity_feed = build_activity_feed(all_scientists)
    repos = get_github_repos()

    status_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "scientists": all_scientists,
        "activity_feed": activity_feed,
        "repos": repos,
    }

    # Atomic write
    tmp = OUTPUT_FILE.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(status_data, f, indent=2)
    tmp.rename(OUTPUT_FILE)

    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] Collected status for {len(all_scientists)} scientists, {sum(len(s['projects']) for s in all_scientists)} projects")


if __name__ == "__main__":
    collect()
