"""
Single source of truth for the Denario Scientists fleet.
"""

# How many scientists to run
N_SCIENTISTS = 1  # default, overridden by setup.py --scientists N

# Default model for all scientists (can be overridden per-scientist below)
DEFAULT_MODEL = "anthropic/claude-sonnet-4-6"
DEFAULT_MEMORY = "8g"
DEFAULT_CPUS = "4"

# Base port: scientist-i gets port BASE_PORT + i for gateway, BASE_PORT + 10 + i for bridge
BASE_GATEWAY_PORT = 18796
BASE_BRIDGE_PORT = 18806

# Per-scientist overrides (optional). Key = scientist name, value = model.
MODEL_OVERRIDES = {
    # "denario-1": "google/gemini-3.1-flash-lite-preview",
}

# Denario MCP server path inside container
DENARIO_MCP_SERVER_PATH = "/opt/denario-venv/lib/python3.12/site-packages/denario/mcp_servers/denario_server.py"
DENARIO_PARAMS_FILE = "/home/node/work/params.yaml"


def scientists(n=None):
    """Return list of scientist configs."""
    count = n if n is not None else N_SCIENTISTS
    return [
        {
            "name": f"denario-{i}",
            "container": f"denario-{i}",
            "agent": "main",
            "gateway_port": BASE_GATEWAY_PORT + i - 1,
            "bridge_port": BASE_BRIDGE_PORT + i - 1,
            "token": f"denario-{i}-token",
            "model": MODEL_OVERRIDES.get(f"denario-{i}", DEFAULT_MODEL),
            "memory": DEFAULT_MEMORY,
            "cpus": DEFAULT_CPUS,
        }
        for i in range(1, count + 1)
    ]
