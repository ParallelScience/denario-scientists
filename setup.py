"""
Generate the full Denario Scientists fleet from config.py.

Usage:
    python setup.py -n 2          # generate configs for 2 scientists
    python setup.py -n 2 --up     # generate and start 2 scientists
    python setup.py --reset -n 3  # wipe and regenerate for 3 scientists
"""

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import time

import config as cfg

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))


def parse_args():
    parser = argparse.ArgumentParser(description="Denario Scientists fleet setup")
    parser.add_argument("-n", "--scientists", type=int, default=cfg.N_SCIENTISTS,
                        help=f"Number of scientists to deploy (default: {cfg.N_SCIENTISTS})")
    parser.add_argument("--up", action="store_true", help="Build and start containers")
    parser.add_argument("--reset", action="store_true", help="Wipe configs and regenerate")
    parser.add_argument("--full-reset", action="store_true", help="Wipe everything including work dirs")
    parser.add_argument("--model", type=str, default=None,
                        help=f"Override default model (default: {cfg.DEFAULT_MODEL})")
    return parser.parse_args()


def generate_compose(fleet):
    """Generate docker-compose.yml from scientist configs."""
    services = {}
    for s in fleet:
        name = s["name"]
        services[name] = {
            "build": {
                "context": "../openclaw",
                "dockerfile": "../denario-scientists/Dockerfile",
                "additional_contexts": {
                    "ag2-src": "../ag2",
                    "cmbagent-src": "../cmbagent",
                    "denario-src": "../Denario",
                },
            },
            "container_name": name,
            "environment": {
                "HOME": "/home/node",
                "TERM": "xterm-256color",
                "OPENCLAW_GATEWAY_TOKEN": f"${{{name.upper().replace('-', '_')}_TOKEN:-{s['token']}}}",
                "OPENCLAW_ALLOW_INSECURE_PRIVATE_WS": "1",
                "ANTHROPIC_API_KEY": "${ANTHROPIC_API_KEY}",
                "OPENAI_API_KEY": "${OPENAI_API_KEY}",
                "GEMINI_API_KEY": "${GEMINI_API_KEY}",
                "GOOGLE_API_KEY": "${GOOGLE_API_KEY}",
                "GOOGLE_GEMINI_API_KEY": "${GOOGLE_GEMINI_API_KEY}",
                "DENARIO_WORK_DIR": "/home/node/.openclaw/workspace/denario",
                "TZ": "${TZ:-UTC}",
                # Slack only on first scientist
                **({
                    "SLACK_BOT_TOKEN": "${SLACK_BOT_TOKEN}",
                    "SLACK_APP_TOKEN": "${SLACK_APP_TOKEN}",
                } if name == "denario-1" else {}),
            },
            "volumes": [
                f"./scientists/{name}/config:/home/node/.openclaw",
                f"./scientists/{name}/workspace:/home/node/.openclaw/workspace",
                f"./scientists/{name}/work:/home/node/.openclaw/workspace/denario",
                "./auto-pair.sh:/app/auto-pair.sh:ro",
                "./entrypoint.sh:/app/entrypoint.sh:ro",
                "${DATA_DIR:-./data}:/home/node/data:ro",
            ],
            "ports": [
                f"{s['gateway_port']}:18789",
                f"{s['bridge_port']}:18790",
            ],
            "deploy": {
                "resources": {
                    "limits": {
                        "cpus": s.get("cpus", "4"),
                        "memory": s.get("memory", "8g"),
                    }
                }
            },
            "init": True,
            "restart": "unless-stopped",
            "command": [
                "sh", "/app/entrypoint.sh",
            ],
            "healthcheck": {
                "test": ["CMD", "node", "-e",
                         "fetch('http://127.0.0.1:18789/healthz').then((r)=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"],
                "interval": "30s",
                "timeout": "5s",
                "retries": 5,
                "start_period": "20s",
            },
        }

    lines = ["services:"]
    for svc_name, svc in services.items():
        lines.append(f"  {svc_name}:")
        lines.append(f"    build:")
        lines.append(f"      context: {svc['build']['context']}")
        lines.append(f"      dockerfile: {svc['build']['dockerfile']}")
        if "additional_contexts" in svc["build"]:
            lines.append(f"      additional_contexts:")
            for k, v in svc["build"]["additional_contexts"].items():
                lines.append(f"        {k}: {v}")
        lines.append(f"    container_name: {svc['container_name']}")
        lines.append(f"    environment:")
        for k, v in svc["environment"].items():
            lines.append(f"      {k}: {v}")
        lines.append(f"    volumes:")
        for v in svc["volumes"]:
            lines.append(f"      - {v}")
        lines.append(f"    ports:")
        for p in svc["ports"]:
            lines.append(f'      - "{p}"')
        lines.append(f"    deploy:")
        lines.append(f"      resources:")
        lines.append(f"        limits:")
        lines.append(f"          cpus: \"{svc['deploy']['resources']['limits']['cpus']}\"")
        lines.append(f"          memory: {svc['deploy']['resources']['limits']['memory']}")
        lines.append(f"    init: true")
        lines.append(f"    restart: unless-stopped")
        cmd = svc["command"]
        lines.append(f"    command:")
        for c in cmd:
            lines.append(f'      - "{c}"')
        hc = svc["healthcheck"]
        lines.append(f"    healthcheck:")
        lines.append(f'      test: ["CMD", "node", "-e", "{hc["test"][3]}"]')
        lines.append(f"      interval: {hc['interval']}")
        lines.append(f"      timeout: {hc['timeout']}")
        lines.append(f"      retries: {hc['retries']}")
        lines.append(f"      start_period: {hc['start_period']}")
        lines.append("")

    path = os.path.join(PROJECT_DIR, "docker-compose.yml")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"  Generated docker-compose.yml ({len(fleet)} scientists)")


def _install_workspace_files(config_dir: str, workspace_dir: str, scientist: dict):
    """Replace OpenClaw default workspace files with Denario research-focused versions."""
    # SOUL.md
    soul_src = os.path.join(PROJECT_DIR, "soul.md")
    if os.path.exists(soul_src):
        shutil.copy2(soul_src, os.path.join(workspace_dir, "SOUL.md"))
        soul_dir = os.path.join(config_dir, "agents", "main", "agent")
        os.makedirs(soul_dir, exist_ok=True)
        shutil.copy2(soul_src, os.path.join(soul_dir, "soul.md"))

    # IDENTITY.md
    with open(os.path.join(workspace_dir, "IDENTITY.md"), "w") as f:
        f.write(f"""# Identity

- **Name:** {scientist['name']}
- **Role:** Denario research scientist
""")

    # Remove files we don't need
    for filename in ["BOOTSTRAP.md", "HEARTBEAT.md", "TOOLS.md", "USER.md"]:
        filepath = os.path.join(workspace_dir, filename)
        if os.path.exists(filepath):
            os.remove(filepath)


def generate_dirs_and_configs(fleet):
    """Create config/workspace dirs and openclaw.json for each scientist."""
    for s in fleet:
        name = s["name"]
        config_dir = os.path.join(PROJECT_DIR, "scientists", name, "config")
        workspace_dir = os.path.join(PROJECT_DIR, "scientists", name, "workspace")
        work_dir = os.path.join(PROJECT_DIR, "scientists", name, "work")
        os.makedirs(config_dir, exist_ok=True)
        os.makedirs(workspace_dir, exist_ok=True)
        os.makedirs(work_dir, exist_ok=True)

        config_path = os.path.join(config_dir, "openclaw.json")
        if not os.path.exists(config_path):
            config = {
                "gateway": {
                    "controlUi": {
                        "allowedOrigins": [
                            f"http://localhost:{s['gateway_port']}",
                            f"http://127.0.0.1:{s['gateway_port']}",
                        ]
                    }
                },
                "agents": {
                    "defaults": {
                        "model": s["model"],
                        "timeoutSeconds": 3600,
                    },
                    "list": [
                        {
                            "id": "main",
                            "identity": {
                                "name": name,
                            },
                        }
                    ],
                },
                "channels": {
                    "slack": {
                        "mode": "socket",
                        "enabled": name == "denario-1",
                        "allowBots": False,
                        "groupPolicy": "open",
                        "dmPolicy": "open",
                        "allowFrom": ["*"],
                        "streaming": "partial",
                        "nativeStreaming": True,
                    }
                },
                "mcp": {
                    "servers": {
                        "denario": {
                            "command": "/opt/denario-venv/bin/python",
                            "args": [cfg.DENARIO_MCP_SERVER_PATH],
                        }
                    }
                },
                "browser": {"enabled": False},
                "cron": {"enabled": False},
                "plugins": {
                    "entries": {
                        "slack": {"enabled": name == "denario-1"},
                        "memory-core": {"enabled": True},
                        "device-pair": {"enabled": False},
                        "phone-control": {"enabled": False},
                        "talk-voice": {"enabled": False},
                    }
                },
                "skills": {"entries": {}},
                "commands": {
                    "native": "auto",
                    "nativeSkills": False,
                    "restart": False,
                },
                "tools": {
                    "profile": "full",
                    "exec": {
                        "security": "full",
                        "ask": "off",
                    },
                },
            }
            with open(config_path, "w") as f:
                json.dump(config, f, indent=2)
            print(f"  Created config for {name}")
        else:
            print(f"  Config exists for {name}")

        _install_workspace_files(config_dir, workspace_dir, s)
        print(f"  Installed workspace for {name}")


def ensure_env_tokens(fleet):
    """Ensure .env has tokens for all scientists."""
    env_path = os.path.join(PROJECT_DIR, ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            content = f.read()
    else:
        content = ""

    added = []
    for s in fleet:
        token_var = s["name"].upper().replace("-", "_") + "_TOKEN"
        if token_var not in content:
            content += f"\n{token_var}={s['token']}"
            added.append(token_var)

    if added:
        with open(env_path, "w") as f:
            f.write(content.strip() + "\n")
        print(f"  Added tokens to .env: {', '.join(added)}")
    else:
        print(f"  All tokens present in .env")


def reset_configs(fleet):
    """Reset openclaw.json for all scientists."""
    for s in fleet:
        config_path = os.path.join(PROJECT_DIR, "scientists", s["name"], "config", "openclaw.json")
        if os.path.exists(config_path):
            os.remove(config_path)
            print(f"  Reset {s['name']} config")
        for f in glob.glob(os.path.join(PROJECT_DIR, "scientists", s["name"], "config", "openclaw.json.bak*")):
            os.remove(f)


def full_reset(fleet):
    """Wipe everything: configs, sessions, work dirs."""
    print("  Stopping containers...")
    subprocess.run(["docker", "compose", "down"], cwd=PROJECT_DIR, capture_output=True)

    for s in fleet:
        name = s["name"]
        base = os.path.join(PROJECT_DIR, "scientists", name)

        for f in glob.glob(os.path.join(base, "config", "openclaw.json*")):
            os.remove(f)

        for subdir in ["config/agents", "config/logs", "config/cron",
                        "config/devices", "config/identity", "config/canvas",
                        "work"]:
            dirpath = os.path.join(base, subdir)
            if os.path.exists(dirpath):
                subprocess.run(["docker", "run", "--rm",
                                "-v", f"{os.path.abspath(dirpath)}:/data",
                                "alpine", "rm", "-rf", "/data"],
                               capture_output=True)
                print(f"  [{name}] Wiped {subdir}")

        workspace_dir = os.path.join(base, "workspace")
        if os.path.exists(workspace_dir):
            for f in os.listdir(workspace_dir):
                if f not in ("SOUL.md", "IDENTITY.md"):
                    fpath = os.path.join(workspace_dir, f)
                    if os.path.isfile(fpath):
                        os.remove(fpath)
                    elif os.path.isdir(fpath):
                        shutil.rmtree(fpath, ignore_errors=True)
            print(f"  [{name}] Cleaned workspace")

        print(f"  [{name}] Reset complete")


def main():
    args = parse_args()

    # Override config with CLI args
    n = args.scientists
    if args.model:
        cfg.DEFAULT_MODEL = args.model
    fleet = cfg.scientists(n)

    print(f"Denario Scientists Setup ({n} scientists)")
    print("=" * 50)

    if args.full_reset:
        print("\nFull reset (wipe everything)...")
        full_reset(fleet)
    elif args.reset:
        print("\nResetting configs...")
        reset_configs(fleet)

    print("\nGenerating configs...")
    generate_dirs_and_configs(fleet)

    print("\nChecking .env tokens...")
    ensure_env_tokens(fleet)

    print("\nGenerating docker-compose.yml...")
    generate_compose(fleet)

    if args.up:
        print("\nBuilding and starting containers...")
        subprocess.run(["docker", "compose", "build"], cwd=PROJECT_DIR)
        subprocess.run(["docker", "compose", "up", "-d"], cwd=PROJECT_DIR)

    print("\nDone.")
    print(f"\nScientist Control UIs:")
    for s in fleet:
        print(f"  {s['name']}: http://localhost:{s['gateway_port']}/#token={s['token']}")


if __name__ == "__main__":
    main()
