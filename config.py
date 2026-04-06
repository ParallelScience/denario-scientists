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

# GPU assignment (optional). Key = scientist name, value = list of GPU device IDs.
# Only listed scientists get GPU access; others get none.
GPU_ASSIGNMENT = {
    "denario-3": ["0"],  # GPU 0 — NVIDIA RTX PRO 6000 Blackwell (96 GB VRAM)
    # "denario-2": ["1"],  # GPU 1
}

# Per-scientist resource overrides (optional). Key = scientist name.
# Scientists not listed here get DEFAULT_MEMORY / DEFAULT_CPUS.
RESOURCE_OVERRIDES = {
    "denario-3": {"memory": "64g", "cpus": "32"},  # GPU scientist gets more resources
}

# Per-scientist params.yaml overrides (optional).
# Deep-merged on top of data/params.yaml. Use dotted module paths.
# Unset scientists get the base params.yaml as-is.
PARAMS_OVERRIDES = {
    "denario-3": {
        "hardware_constraints": (
            "- Linux x86_64 Docker container\n"
            "- 32 CPUs (AMD Ryzen Threadripper PRO 9995WX), 64 GB RAM\n"
            "- NVIDIA RTX PRO 6000 Blackwell Edition (96 GB VRAM), CUDA 13.0\n"
            "- For PyTorch GPU: use device='cuda'\n"
            "- Multiprocessing: limit to ~8-16 workers to avoid oversubscription\n"
            "- NumPy/SciPy use OpenBLAS — set OMP_NUM_THREADS to avoid thread oversubscription with multiprocessing"
        ),
        "EDA module": {
            "code_execution_timeout": 1800,
            "enable_vlm_review": True,
        },
        "Analysis module": {
            "code_execution_timeout": 1800,
            "enable_vlm_review": True,
        },
    },
}

# Default hardware_constraints for non-GPU scientists (added to base params)
DEFAULT_HARDWARE_CONSTRAINTS = (
    "- Linux x86_64 Docker container\n"
    "- 4 CPUs (AMD Ryzen Threadripper PRO 9995WX), 8 GB RAM\n"
    "- No GPU — do not use CUDA or GPU-dependent libraries\n"
    "- Multiprocessing: limit to 4 workers max\n"
    "- NumPy/SciPy use OpenBLAS — set OMP_NUM_THREADS=2 to avoid thread oversubscription with multiprocessing\n"
    "- Memory is limited — avoid loading large datasets entirely into RAM; use chunked/streaming approaches for data > 2 GB"
)

# Per-scientist ElevenLabs voice IDs
DEFAULT_VOICE_ID = "sJKq4p1ljb8oxmfBK2hp"
VOICE_OVERRIDES = {
    "denario-2": "4nLKNoWGCgxnhFTvHPNL",
    "denario-3": "GPQBwvkAgD34c9QL6VOy",
    "denario-4": "wHmPF60BN2ikHIqbdAP6",
    "denario-5": "W2ZOpTX05dpEry2h5LQb",
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
            "voice_id": VOICE_OVERRIDES.get(f"denario-{i}", DEFAULT_VOICE_ID),
            "memory": RESOURCE_OVERRIDES.get(f"denario-{i}", {}).get("memory", DEFAULT_MEMORY),
            "cpus": RESOURCE_OVERRIDES.get(f"denario-{i}", {}).get("cpus", DEFAULT_CPUS),
            "gpus": GPU_ASSIGNMENT.get(f"denario-{i}"),
        }
        for i in range(1, count + 1)
    ]
