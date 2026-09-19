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

# Agent runtime fronting each scientist:
#   "openclaw" (default) — OpenClaw gateway + Slack/voice, local control UI
#   "claude"             — a Claude Code session running the denario plugin,
#                          driven over MCP and controlled REMOTELY via
#                          `claude --remote-control` (attach from claude.ai/code
#                          or the mobile app by session name). No OpenClaw, no
#                          Slack, no inbound port — outbound HTTPS only.
DEFAULT_BACKEND = "openclaw"
BACKEND_OVERRIDES = {
    # denario-3 moved back to openclaw on 2026-09-19: its brain is the local
    # qwen3.8 llama-server (see MODEL_OVERRIDES / VLLM_PROVIDER_CATALOGS), and
    # only the OpenClaw gateway can be pointed at a self-hosted model.
    "denario-6": "claude",
}

# Per-scientist overrides (optional). Key = scientist name, value = model.
MODEL_OVERRIDES = {
    "denario-2": "anthropic/claude-sonnet-4-6",
    # denario-3: gateway brain on the host-side llama.cpp Qwen3.8-Flash-Next
    # (GPU 1, reached at host.docker.internal:30000). The "vllm/" prefix is just
    # the provider key setup.py injects the catalog under (parseModelRef splits
    # on the first slash); the server is llama-server, not vLLM.
    "denario-3": "vllm/qwen3.8-flash-next",
    "denario-4": "zai/glm-5.1",
    "denario-5": "anthropic/claude-sonnet-4-6",
    "denario-6": "anthropic/claude-sonnet-4-6",
    # denario-6: gateway brain on the host-side vLLM Gemma 4 31B.
    # openclaw.json also gets a models.providers.vllm block (see VLLM_PROVIDER_CATALOGS)
    # so the provider catalog knows the base URL + model metadata.
    # Temporarily disabled — falling back to DEFAULT_MODEL (MiniMax-M2.7).
    # "denario-6": "vllm//rds/models/gemma-4-31B-it",
}

# Extra models.providers.<id> blocks injected into a scientist's openclaw.json
# when its gateway model lives behind a self-hosted OpenAI-compatible backend.
# setup.py injects the value as models.providers.vllm into a FRESH openclaw.json
# for ANY scientist listed here -- there is no model-prefix check -- so only list
# scientists whose model really starts with "vllm/". Keys are scientist names.
VLLM_PROVIDER_CATALOGS = {
    "denario-3": {
        "baseUrl": "http://host.docker.internal:30000/v1",
        "apiKey": "EMPTY",               # sent as "Authorization: Bearer EMPTY"; llama-server ignores it
        "api": "openai-completions",     # REQUIRED: without it OpenClaw falls back to openai-responses + 200k defaults
        "models": [
            {
                # OpenClaw matches this against the model string suffix exactly.
                "id": "qwen3.8-flash-next",
                "name": "Qwen3.8 Flash Next (local llama.cpp, GPU 1)",
                "reasoning": True,
                "input": ["text", "image"],
                "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
                # MUST be the per-slot context (server -c / --parallel), NOT the
                # 262144 training window: it is what drives OpenClaw's compaction.
                # The class deployment ran 196608/32 = 6144, far too small for a
                # ~22k-token bootstrap; it is relaunched with PARALLEL=4 -> 49152.
                "contextWindow": 49152,
                "maxTokens": 8192,
                # llama.cpp is not vLLM: no developer role / store / strict tool
                # schemas, and it ignores reasoning_effort. Thinking is driven
                # through the Qwen chat template instead.
                "compat": {
                    "supportsDeveloperRole": False,
                    "supportsStore": False,
                    "supportsStrictMode": False,
                    "supportsReasoningEffort": False,
                    "thinkingFormat": "qwen-chat-template",
                },
            }
        ],
    },
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
                "contextWindow": 262144,
                "maxTokens": 8192,
            }
        ],
    },
}

# Per-scientist agents.defaults overrides, merged into a FRESH openclaw.json by
# setup.py (same rule as VLLM_PROVIDER_CATALOGS). OpenClaw's default compaction
# reserve floor is 20000 tokens; on denario-3's 49152-token slot with a ~22k
# bootstrap that would fire compaction at ~29k. 8192 moves the trigger to ~41k.
AGENT_DEFAULTS_OVERRIDES = {
    "denario-3": {
        "compaction": {"reserveTokensFloor": 8192, "reserveTokens": 8192},
    },
}

# GPU assignment (optional). Key = scientist name, value = list of GPU device IDs.
# Only listed scientists get GPU access; others get none.
GPU_ASSIGNMENT = {
    # GPU 1 holds the host-side llama.cpp Qwen3.8 server (~91 GB of 96), so
    # scientists that run experiments on a GPU take GPU 0. GPU 0 is shared with
    # the denario_fleet workers (~3-4 GB each); ~80 GB stays free.
    "denario-3": ["0"],  # GPU 0 — NVIDIA RTX PRO 6000 Blackwell (96 GB VRAM, shared)
    "denario-6": ["1"],  # (claude backend, currently down) still on GPU 1
}

# Per-scientist resource overrides (optional). Key = scientist name.
# Scientists not listed here get DEFAULT_MEMORY / DEFAULT_CPUS.
RESOURCE_OVERRIDES = {
    "denario-3": {"memory": "64g", "cpus": "32"},  # GPU scientist gets more resources
    "denario-5": {"memory": "16g", "cpus": "8"},
    "denario-6": {"memory": "128g", "cpus": "64"},
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
        # The Gemma 4 routing ("/rds/models/gemma-4-31B-it" via GEMMA4_URL on
        # port 8010) was removed 2026-09-19: that vLLM server is gone, and the
        # id has no provider rule in cmbagent_lg, so read_params() raised at
        # Denario() init and EVERY denario MCP tool call failed before spending.
        # denario-1 now uses the base data/params.yaml models, like denario-2/4.
        "EDA module":      {"code_execution_timeout": 1800},
        "Analysis module": {"code_execution_timeout": 1800},
    },
    "denario-2": {
        "EDA module":      {"code_execution_timeout": 1800},
        "Analysis module": {"code_execution_timeout": 1800},
    },
    "denario-4": {
        "EDA module":      {"code_execution_timeout": 1800},
        "Analysis module": {"code_execution_timeout": 1800},
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
            "- 64 vCPUs (AMD Ryzen Threadripper PRO 9995WX), 128 GB RAM\n"
            "- NVIDIA RTX PRO 6000 Blackwell Edition (96 GB VRAM), CUDA 13.0\n"
            "- For PyTorch GPU: use device='cuda'\n"
            "- Multiprocessing: limit to ~8-16 workers to avoid oversubscription\n"
            "- NumPy/SciPy use OpenBLAS — set OMP_NUM_THREADS to avoid thread oversubscription with multiprocessing"
        ),
        "EDA module":      {"code_execution_timeout": 3600},
        "Analysis module": {
            "code_execution_timeout": 7200,
            "enable_vlm_review": True,
            },
    },
    "denario-3": {
        "hardware_constraints": (
            "- Linux x86_64 Docker container\n"
            "- 32 CPUs (AMD Ryzen Threadripper PRO 9995WX), 64 GB RAM\n"
            "- NVIDIA RTX PRO 6000 Blackwell Edition, CUDA 13.0 — SHARED with other jobs: budget ~60 GB VRAM and check torch.cuda.mem_get_info() first\n"
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
    "denario-6": "GPQBwvkAgD34c9QL6VOy",
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
            "backend": BACKEND_OVERRIDES.get(f"denario-{i}", DEFAULT_BACKEND),
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
