"""
Single source of truth for the Denario Scientists fleet.
"""

# How many scientists to run
N_SCIENTISTS = 12  # default, overridden by setup.py --scientists N

# Default model for all scientists (can be overridden per-scientist below)
DEFAULT_MODEL = "minimax/MiniMax-M2.7"
DEFAULT_MEMORY = "8g"
DEFAULT_CPUS = "4"

# Minimal containers for scientists 6-12
MINIMAL_MEMORY = "2g"
MINIMAL_CPUS = "2"

# Base port: scientist-i gets port BASE_PORT + i for gateway, BASE_PORT + 10 + i for bridge
BASE_GATEWAY_PORT = 18796
BASE_BRIDGE_PORT = 18820

# Per-scientist overrides (optional). Key = scientist name, value = model.
MODEL_OVERRIDES = {
    "denario-2": "nvidia/nvidia/nemotron-3-super-120b-a12b",
    "denario-3": "anthropic/claude-sonnet-4-6",
    "denario-4": "zai/glm-5.1",
    # denario-6: gateway brain on the host-side vLLM Gemma 4 31B.
    # openclaw.json also gets a models.providers.vllm block (see VLLM_PROVIDER_CATALOGS)
    # so the provider catalog knows the base URL + model metadata.
    "denario-6": "vllm//rds/models/gemma-4-31B-it",
}

# Extra models.providers.<id> blocks injected into a scientist's openclaw.json
# when its gateway model lives behind a self-hosted OpenAI-compatible backend.
# setup.py merges the value into the config only when the scientist's model
# prefix matches (e.g. "vllm/..."). Keys are scientist names.
VLLM_PROVIDER_CATALOGS = {
    "denario-6": {
        "baseUrl": "http://host.docker.internal:8010/v1",
        "apiKey": "EMPTY",
        "api": "openai-completions",
        "models": [
            {
                "id": "/rds/models/gemma-4-31B-it",
                "name": "Gemma 4 31B (local vLLM)",
                "reasoning": True,
                "input": ["text"],
                "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
                "contextWindow": 16384,
                "maxTokens": 8192,
            }
        ],
    },
}

# GPU assignment (optional). Key = scientist name, value = list of GPU device IDs.
# Only listed scientists get GPU access; others get none.
GPU_ASSIGNMENT = {
    # GPU 0 is reserved for the host-side vLLM Gemma 4 31B deployment
    # (serves the parallel fan-out pool). Scientists use GPU 1.
    "denario-3": ["1"],  # GPU 1 — NVIDIA RTX PRO 6000 Blackwell (96 GB VRAM)
}

# Per-scientist resource overrides (optional). Key = scientist name.
# Scientists not listed here get DEFAULT_MEMORY / DEFAULT_CPUS.
RESOURCE_OVERRIDES = {
    "denario-3": {"memory": "64g", "cpus": "32"},  # GPU scientist gets more resources
    "denario-5": {"memory": "16g", "cpus": "8"},
    "denario-6": {"memory": "16g", "cpus": "8"},
    **{f"denario-{i}": {"memory": MINIMAL_MEMORY, "cpus": MINIMAL_CPUS} for i in range(7, 13)},
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

# Hardware constraints for minimal scientists (6-12)
MINIMAL_HARDWARE_CONSTRAINTS = (
    "- Linux x86_64 Docker container\n"
    "- 2 CPUs (AMD Ryzen Threadripper PRO 9995WX), 2 GB RAM\n"
    "- No GPU — do not use CUDA or GPU-dependent libraries\n"
    "- Multiprocessing: limit to 2 workers max\n"
    "- Memory is very limited — keep datasets under 500 MB, use streaming/chunked approaches\n"
    "- NumPy/SciPy use OpenBLAS — set OMP_NUM_THREADS=1"
)

# Per-scientist params.yaml overrides (optional).
# Deep-merged on top of data/params.yaml. Use dotted module paths.
# Unset scientists get the base params.yaml as-is.
PARAMS_OVERRIDES = {
    **{f"denario-{i}": {"hardware_constraints": MINIMAL_HARDWARE_CONSTRAINTS} for i in range(7, 13)},
    "denario-1": {
        # Route the cmbagent engineer + researcher through the host-side
        # vLLM Gemma 4 31B (reached via GEMMA4_URL / host.docker.internal).
        # cmbagent's local_llm_urls registry maps this id to the base URL and
        # local_llm_extra_body turns on chat_template_kwargs.enable_thinking.
        "EDA module": {
            "engineer":   {"model": "/rds/models/gemma-4-31B-it", "temperature": 0.2},
            "researcher": {"model": "/rds/models/gemma-4-31B-it", "temperature": 0.2},
        },
        "Analysis module": {
            "engineer":   {"model": "/rds/models/gemma-4-31B-it", "temperature": 0.2},
            "researcher": {"model": "/rds/models/gemma-4-31B-it", "temperature": 0.2},
        },
    },
    "denario-5": {
        "hardware_constraints": (
            "- Linux x86_64 Docker container\n"
            "- 8 CPUs (AMD Ryzen Threadripper PRO 9995WX), 16 GB RAM\n"
            "- No GPU — do not use CUDA or GPU-dependent libraries\n"
            "- Multiprocessing: limit to 8 workers max\n"
            "- NumPy/SciPy use OpenBLAS — set OMP_NUM_THREADS=2 to avoid thread oversubscription with multiprocessing\n"
            "- Memory is limited — avoid loading large datasets entirely into RAM; use chunked/streaming approaches for data > 4 GB"
        ),
        "EDA module": {
            "code_execution_timeout": 1800,
        },
        "Analysis module": {
            "code_execution_timeout": 1800,
        },
    },
    "denario-6": {
        "hardware_constraints": (
            "- Linux x86_64 Docker container\n"
            "- 8 CPUs (AMD Ryzen Threadripper PRO 9995WX), 16 GB RAM\n"
            "- No GPU — do not use CUDA or GPU-dependent libraries\n"
            "- Multiprocessing: limit to 8 workers max\n"
            "- NumPy/SciPy use OpenBLAS — set OMP_NUM_THREADS=2 to avoid thread oversubscription with multiprocessing\n"
            "- Memory is limited — avoid loading large datasets entirely into RAM; use chunked/streaming approaches for data > 4 GB"
        ),
    },
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

# Per-scientist ElevenLabs voice IDs
# Scientists 6-12 share denario-1's voice (DEFAULT_VOICE_ID)
DEFAULT_VOICE_ID = "sJKq4p1ljb8oxmfBK2hp"
VOICE_OVERRIDES = {
    "denario-2": "4nLKNoWGCgxnhFTvHPNL",
    "denario-3": "GPQBwvkAgD34c9QL6VOy",
    "denario-4": "wHmPF60BN2ikHIqbdAP6",
    "denario-5": "W2ZOpTX05dpEry2h5LQb",
    # denario-6 through denario-12: use DEFAULT_VOICE_ID (same as denario-1)
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
