#!/usr/bin/env python3
"""
Smoke-test all unique models in params.yaml via both backends:
  - AG2 (cmbagent): trivial one_shot engineer call
  - LangGraph (Denario): single LLM invoke through Denario's get_LLM

Exit code 0 = all passed.  Non-zero = at least one failed.

Usage:
    python test_models.py                         # default params
    python test_models.py /path/to/params.yaml
"""

import os
import shutil
import sys
import time

import yaml

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(TEST_DIR, "..", ".."))

PROMPT = "Reply with exactly one word: OK"


# ---------------------------------------------------------------------------
# AG2/cmbagent: trivial engineer call
# ---------------------------------------------------------------------------

def test_cmbagent_engineer(engineer_model: str,
                           evaluator_model: str,
                           ) -> tuple[bool, str, float]:
    """Trivial cmbagent.one_shot engineer call."""
    import cmbagent

    work_dir = os.path.join("/tmp", "output_test_models_engineer")
    if os.path.exists(work_dir):
        shutil.rmtree(work_dir)

    t0 = time.time()
    try:
        results = cmbagent.one_shot(
            "Write a Python script that prints 'Hello from cmbagent!' and exits.",
            agent="engineer",
            engineer_model=engineer_model,
            default_evaluator_model=evaluator_model,
            max_rounds=15,
            max_n_attempts=2,
            work_dir=work_dir,
        )
        elapsed = time.time() - t0

        if results is None:
            return False, "one_shot returned None", elapsed

        ctx = results["final_context"]
        status = ctx.get("step_status", "unknown")
        code_status = ctx.get("code_status", "unknown")

        if status != "completed" or code_status != "success":
            return False, f"step={status}, code={code_status}", elapsed

        return True, f"step={status}, code={code_status}", elapsed

    except Exception as e:
        return False, str(e)[:120], time.time() - t0


# ---------------------------------------------------------------------------
# LangGraph/Denario: single invoke through Denario's get_LLM
# ---------------------------------------------------------------------------

def test_denario_llm(model: str) -> tuple[bool, str, float]:
    """Single LLM call through Denario's get_LLM (same path as LangGraph agents)."""
    from denario.tools.llm import get_LLM
    from denario.key_manager import KeyManager

    keys = KeyManager()
    keys.get_keys_from_env()

    llm_cfg = {"model": model, "temperature": 0}

    t0 = time.time()
    try:
        llm = get_LLM(llm_cfg, keys)
        resp = llm.invoke(PROMPT)
        elapsed = time.time() - t0
        text = resp.content if isinstance(resp.content, str) else str(resp.content)
        return True, text.strip()[:80], elapsed
    except Exception as e:
        return False, str(e)[:120], time.time() - t0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def extract_models(params: dict) -> set[str]:
    """Walk the params dict and return all unique 'model' values."""
    models = set()

    def _walk(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k == "model" and isinstance(v, str):
                    models.add(v)
                else:
                    _walk(v)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)

    _walk(params)
    return models


def main():
    params_path = sys.argv[1] if len(sys.argv) > 1 else "/home/node/work/params.yaml"
    if not os.path.exists(params_path):
        print(f"params file not found: {params_path}")
        sys.exit(1)

    with open(params_path) as f:
        params = yaml.safe_load(f)

    all_models = sorted(extract_models(params))
    eda = params.get("EDA module", {})

    # Pick one model per AG2 engineer test; evaluator is always the orchestration model
    engineer_model = eda.get("engineer", {}).get("model", "gemini-3.1-flash-lite-preview")
    claude_model = eda.get("plan_reviewer", {}).get("model", "claude-sonnet-4-6")
    evaluator_model = eda.get("evaluator", {}).get("model", "gemini-3.1-flash-lite-preview")

    print(f"Params: {params_path}")
    print(f"Models: {', '.join(all_models)}\n")

    tests = []

    # AG2 engineer with each unique cmbagent-path model
    tests.append((f"cmbagent engineer ({engineer_model})",
                  lambda m=engineer_model: test_cmbagent_engineer(m, evaluator_model)))
    tests.append((f"cmbagent engineer ({claude_model})",
                  lambda m=claude_model: test_cmbagent_engineer(m, evaluator_model)))

    # Denario get_LLM for every unique model
    for model in all_models:
        tests.append((f"Denario get_LLM ({model})",
                      lambda m=model: test_denario_llm(m)))

    failures = []

    try:
        for name, test_fn in tests:
            ok, detail, elapsed = test_fn()
            status = "OK" if ok else "FAIL"
            print(f"  [{status}] {name:50s} {elapsed:.1f}s  {detail}")
            if not ok:
                failures.append(name)
    finally:
        for d in ["output_test_models_engineer"]:
            p = os.path.join("/tmp", d)
            if os.path.exists(p):
                shutil.rmtree(p)

    print()
    if failures:
        print(f"FAILED ({len(failures)}):")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("All tests passed.")


if __name__ == "__main__":
    main()
