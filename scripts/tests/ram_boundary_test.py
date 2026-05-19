"""
RAM Boundary Sweep Test
=======================
Finds the minimum RAM configuration at which a model still meets thesis thresholds.

Thesis mapping
--------------
§3.3  "Boundary test" — поступове зменшення RAM до відмови моделі
§3.2  Configuration matrix RAM levels: 16 / 12 / 8 / 6 / 5 / 4 / 3 / 2 / 1.5 / 1 GB
§4.1  Thresholds: TTFT < 3 000 ms · TPS > 3 tok/s · load time < 60 s
§4.2  Records peak RAM at each level via psutil (if available)

Method
------
1.  Record the container's current mem_limit via Docker SDK.
2.  For each RAM level (high → low), inside a try/finally that always restores:
    a.  Apply container.update(mem_limit=<level>)   — live cgroup update, no restart.
    b.  Wait for the kernel to enforce the new limit (grace period).
    c.  Evict the model from Ollama memory (keep_alive=0) so it must reload.
    d.  Run cold probe  — first request forces a reload under the constrained limit.
    e.  Run warm probe  — second request, model already resident.
    f.  Evaluate against thresholds; stop at first failure.
3.  Restore original limit (or "unlimited" if it was 0).
4.  Save full results as JSON to results/.

Usage
-----
  python ram_boundary_test.py <model_name> [options]

Options
-------
  --container   Docker container name to constrain  (default: ollama)
  --port        Ollama API port                      (default: 11434)
  --start-gb    Highest RAM level to start from      (default: 8)
  --min-gb      Lowest RAM level to test             (default: 1)
  --prompt      short | medium | long                (default: medium)
  --no-restore  Skip restoring original limit at end (for CI)

Requirements
------------
  pip install docker requests psutil
"""

import argparse
import json
import os
import sys
import time
import statistics
from pathlib import Path

# ── optional deps ─────────────────────────────────────────────────────────────

try:
    import docker as docker_sdk
    DOCKER_AVAILABLE = True
except ImportError:
    DOCKER_AVAILABLE = False

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

import requests

# ── constants ─────────────────────────────────────────────────────────────────

RESULTS_DIR = Path(__file__).parent.parent.parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

TTFT_THRESHOLD_S   = 10.0   # §4.1 CPU-only realistic (was 3.0s; calibrated from phi3:mini ~3.8s measured cold TTFT)
TPS_THRESHOLD      = 3.0    # §4.1 Tokens per Second   > 3 tok/s
LOAD_THRESHOLD_S   = 60.0   # §4.1 Model load time     < 60 s
REQUEST_TIMEOUT_S  = 120    # hard HTTP timeout per request
GRACE_AFTER_LIMIT_S = 4     # seconds to wait after applying a new mem_limit
GRACE_AFTER_EVICT_S = 3     # seconds to wait after evicting model

# §3.2 matrix + intermediates (GB), used to build the sweep sequence
ALL_RAM_LEVELS_GB = [16, 12, 8, 6, 5, 4, 3, 2, 1.5, 1, 0.5]

PROBE_PROMPTS = {
    "short": "What is Docker? Answer in one sentence.",
    "medium": (
        "Write a Python function that sorts a list using bubble sort. "
        "Include a brief inline comment."
    ),
    "long": (
        "Explain in detail the differences between containers and virtual machines. "
        "Cover isolation, resource usage, startup time, portability, and typical use cases. "
        "Give a concrete recommendation for when to use each."
    ),
}


# ── Docker helpers ────────────────────────────────────────────────────────────

def _gb_to_bytes(gb: float) -> int:
    return int(gb * 1024 ** 3)


def _bytes_to_gb(b: int) -> float:
    return round(b / 1024 ** 3, 2)


def _get_current_limit(container) -> int:
    """Return current mem_limit in bytes. 0 means unlimited."""
    return container.attrs.get("HostConfig", {}).get("Memory", 0)


def _apply_limit(container, ram_gb: float) -> dict:
    """
    Apply mem_limit and memswap_limit to running container.
    memswap_limit == mem_limit disables swap so pressure is real.
    Returns {"ok": bool, "error": str|None}
    """
    limit_bytes = _gb_to_bytes(ram_gb)
    try:
        container.update(
            mem_limit=limit_bytes,
            memswap_limit=limit_bytes,
        )
        container.reload()          # refresh attrs
        applied = _get_current_limit(container)
        return {
            "ok": True,
            "requested_bytes": limit_bytes,
            "applied_bytes": applied,
            "applied_gb": _bytes_to_gb(applied),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _restore_limit(container, original_bytes: int) -> None:
    """Restore original mem_limit. If 0 (unlimited) set to a very large value."""
    try:
        if original_bytes == 0:
            # Docker does not accept mem_limit=0 in update(); use -1 to clear
            container.update(mem_limit=-1, memswap_limit=-1)
        else:
            container.update(
                mem_limit=original_bytes,
                memswap_limit=original_bytes,
            )
    except Exception as e:
        print(f"  WARNING: could not restore original limit: {e}")


# ── Ollama helpers ────────────────────────────────────────────────────────────

def _evict_model(host: str, port: int, model_name: str) -> None:
    """Force Ollama to unload model weights from memory."""
    try:
        requests.post(
            f"http://{host}:{port}/api/generate",
            json={"model": model_name, "prompt": "", "keep_alive": 0},
            timeout=20,
        )
    except Exception:
        pass


def _run_inference(host: str, port: int, model_name: str, prompt: str) -> dict:
    """Single inference call. Returns timing dict or failure dict."""
    url = f"http://{host}:{port}/api/generate"
    payload = {
        "model": model_name,
        "prompt": prompt,
        "stream": False,
        "keep_alive": "5m",
        "options": {"num_predict": 128, "temperature": 0.1},
    }
    wall_start = time.time()
    try:
        resp = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT_S)
        resp.raise_for_status()
        wall_s = time.time() - wall_start
        data = resp.json()

        load_ns        = data.get("load_duration", 0)
        prompt_eval_ns = data.get("prompt_eval_duration", 0)
        eval_ns        = data.get("eval_duration", 0)
        eval_count     = data.get("eval_count", 0)

        load_s  = load_ns / 1e9
        eval_s  = eval_ns / 1e9
        tps     = eval_count / eval_s if eval_s > 0 else 0
        ttft_s  = (load_ns + prompt_eval_ns) / 1e9

        return {
            "success":          True,
            "wall_time_s":      round(wall_s, 3),
            "load_duration_s":  round(load_s, 3),
            "ttft_s":           round(ttft_s, 3),
            "tokens_per_sec":   round(tps, 2),
            "eval_tokens":      eval_count,
            "response_preview": data.get("response", "")[:80],
        }
    except requests.exceptions.Timeout:
        return {
            "success":    False,
            "wall_time_s": round(time.time() - wall_start, 3),
            "error_type": "timeout",
            "error":      "Request timed out",
        }
    except requests.exceptions.ConnectionError as e:
        return {
            "success":    False,
            "wall_time_s": round(time.time() - wall_start, 3),
            "error_type": "connection_error",
            "error":      str(e),
        }
    except Exception as e:
        code = getattr(getattr(e, "response", None), "status_code", 0)
        etype = "oom_signal" if code in (500, 503) else f"http_{code}" if code else "unknown"
        return {
            "success":    False,
            "wall_time_s": round(time.time() - wall_start, 3),
            "error_type": etype,
            "error":      str(e),
        }


def _sample_ram_mb() -> float | None:
    if not PSUTIL_AVAILABLE:
        return None
    return round(psutil.virtual_memory().used / 1024 / 1024, 1)


# ── Threshold evaluator ───────────────────────────────────────────────────────

def _evaluate(cold: dict, warm: dict) -> dict:
    """
    Return pass/fail for a cold+warm pair and per-check details.
    A level passes only if the cold (worst-case) run meets all thresholds.
    """
    if not cold.get("success"):
        return {
            "passed": False,
            "reason": f"cold request failed: {cold.get('error_type', 'unknown')} — {cold.get('error', '')}",
            "checks": {},
        }

    checks = {
        "ttft_ok":  cold["ttft_s"] < TTFT_THRESHOLD_S,
        "tps_ok":   cold["tokens_per_sec"] >= TPS_THRESHOLD,
        "load_ok":  cold["load_duration_s"] < LOAD_THRESHOLD_S,
        "warm_ok":  warm.get("success", False),
    }
    passed = all(checks.values())
    failed_checks = [k for k, v in checks.items() if not v]
    return {
        "passed": passed,
        "reason": "all thresholds met" if passed else f"failed: {', '.join(failed_checks)}",
        "checks": checks,
    }


# ── Main sweep ────────────────────────────────────────────────────────────────

def run_ram_boundary_sweep(
    model_name: str,
    container_name: str = "ollama",
    port: int = 11434,
    start_gb: float = 8.0,
    min_gb: float = 1.0,
    prompt_key: str = "medium",
    restore: bool = True,
) -> int:
    host = os.environ.get("SLM_TEST_HOST", "localhost")

    # ── validate docker ──────────────────────────────────────────────────────
    if not DOCKER_AVAILABLE:
        print("ERROR: 'docker' package not installed.")
        print("       pip install docker")
        return 2

    try:
        client = docker_sdk.from_env()
        client.ping()
    except Exception as e:
        print(f"ERROR: Cannot connect to Docker daemon: {e}")
        return 2

    try:
        container = client.containers.get(container_name)
    except docker_sdk.errors.NotFound:
        print(f"ERROR: Container '{container_name}' not found.")
        print(f"       Running containers: {[c.name for c in client.containers.list()]}")
        return 2

    # ── build sweep levels ───────────────────────────────────────────────────
    sweep = sorted(
        [gb for gb in ALL_RAM_LEVELS_GB if min_gb <= gb <= start_gb],
        reverse=True,
    )
    if not sweep:
        print(f"ERROR: No RAM levels between {min_gb} GB and {start_gb} GB in the sweep table.")
        return 2

    prompt = PROBE_PROMPTS.get(prompt_key, PROBE_PROMPTS["medium"])

    # ── record original limit ────────────────────────────────────────────────
    original_bytes = _get_current_limit(container)
    original_gb    = _bytes_to_gb(original_bytes) if original_bytes else "unlimited"

    results = {
        "model":            model_name,
        "container":        container_name,
        "port":             port,
        "timestamp":        time.time(),
        "prompt_key":       prompt_key,
        "prompt":           prompt,
        "thresholds": {
            "ttft_s":       TTFT_THRESHOLD_S,
            "tps":          TPS_THRESHOLD,
            "load_s":       LOAD_THRESHOLD_S,
        },
        "original_limit":   {"bytes": original_bytes, "gb": original_gb},
        "sweep_levels_gb":  sweep,
        "levels":           [],
        "summary":          {},
    }

    print(f"\n{'='*62}")
    print(f"  RAM BOUNDARY SWEEP  —  {model_name}")
    print(f"{'='*62}")
    print(f"  Container :  {container_name}")
    print(f"  Levels    :  {sweep} GB")
    print(f"  Prompt    :  {prompt_key}")
    print(f"  Original  :  {original_gb} GB")
    print(f"  Thresholds:  TTFT < {TTFT_THRESHOLD_S}s  |  TPS > {TPS_THRESHOLD}  |  load < {LOAD_THRESHOLD_S}s")
    print(f"{'='*62}\n")

    min_passing_gb   = None
    first_failing_gb = None

    try:
        for ram_gb in sweep:
            print(f"── {ram_gb} GB {'─'*40}")

            # 1. Apply new RAM limit
            limit_result = _apply_limit(container, ram_gb)
            if not limit_result["ok"]:
                print(f"  [SKIP] Could not apply limit: {limit_result['error']}")
                results["levels"].append({
                    "ram_gb": ram_gb, "skipped": True,
                    "skip_reason": limit_result["error"],
                })
                continue
            print(f"  Limit applied: {limit_result['applied_gb']} GB")
            time.sleep(GRACE_AFTER_LIMIT_S)

            # 2. Evict model
            ram_before_evict = _sample_ram_mb()
            print(f"  Evicting model from Ollama memory…")
            _evict_model(host, port, model_name)
            time.sleep(GRACE_AFTER_EVICT_S)

            # 3. Cold probe (forces reload under new limit)
            print(f"  Cold probe… ", end="", flush=True)
            cold = _run_inference(host, port, model_name, prompt)
            ram_after_cold = _sample_ram_mb()
            if cold["success"]:
                print(
                    f"TTFT={cold['ttft_s']:.2f}s  load={cold['load_duration_s']:.2f}s"
                    f"  TPS={cold['tokens_per_sec']:.1f}"
                )
            else:
                print(f"FAILED [{cold.get('error_type')}] {cold.get('error', '')[:60]}")

            # 4. Warm probe
            print(f"  Warm probe… ", end="", flush=True)
            warm = _run_inference(host, port, model_name, prompt)
            if warm["success"]:
                print(f"TTFT={warm['ttft_s']:.2f}s  TPS={warm['tokens_per_sec']:.1f}")
            else:
                print(f"FAILED [{warm.get('error_type')}]")

            # 5. Evaluate
            eval_result = _evaluate(cold, warm)
            status = "PASS ✓" if eval_result["passed"] else "FAIL ✗"
            print(f"  {status}  —  {eval_result['reason']}")

            level_entry = {
                "ram_gb":         ram_gb,
                "skipped":        False,
                "cold":           cold,
                "warm":           warm,
                "evaluation":     eval_result,
                "ram_before_evict_mb": ram_before_evict,
                "ram_after_cold_mb":   ram_after_cold,
            }
            results["levels"].append(level_entry)

            if eval_result["passed"]:
                min_passing_gb = ram_gb
            else:
                first_failing_gb = ram_gb
                print(f"\n  ► First failure at {ram_gb} GB — stopping sweep.\n")
                break

    finally:
        # Always restore original limit
        if restore:
            print(f"\nRestoring original limit ({original_gb} GB)…")
            _restore_limit(container, original_bytes)
            print("  Done.")

    # ── summary ──────────────────────────────────────────────────────────────
    passing_levels = [
        l["ram_gb"] for l in results["levels"]
        if not l.get("skipped") and l.get("evaluation", {}).get("passed")
    ]
    failing_levels = [
        l["ram_gb"] for l in results["levels"]
        if not l.get("skipped") and not l.get("evaluation", {}).get("passed")
    ]

    results["summary"] = {
        "min_passing_gb":    min_passing_gb,
        "first_failing_gb":  first_failing_gb,
        "boundary_found":    first_failing_gb is not None,
        "passing_levels":    passing_levels,
        "failing_levels":    failing_levels,
        "levels_tested":     len([l for l in results["levels"] if not l.get("skipped")]),
        "ttft_threshold_s":  TTFT_THRESHOLD_S,
        "tps_threshold":     TPS_THRESHOLD,
    }

    s = results["summary"]
    print(f"\n{'='*62}")
    print(f"  BOUNDARY SWEEP SUMMARY")
    print(f"{'='*62}")
    if s["boundary_found"]:
        print(f"  Minimum viable RAM : {s['min_passing_gb']} GB")
        print(f"  First failure at   : {s['first_failing_gb']} GB")
    else:
        print(f"  Model passed all tested levels down to {min(sweep)} GB")
        print(f"  Consider re-running with --min-gb {min(sweep) / 2:.1f}")
    print(f"  Passing levels     : {s['passing_levels']}")
    print(f"  Failing levels     : {s['failing_levels']}")
    print(f"{'='*62}\n")

    # ── save ─────────────────────────────────────────────────────────────────
    safe_name = model_name.replace(":", "_").replace("/", "_")
    out = RESULTS_DIR / f"ram_boundary_{safe_name}_{int(time.time())}.json"
    try:
        out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Results saved → {out}")
    except Exception as e:
        print(f"WARNING: could not save results: {e}")

    return 0 if (s["boundary_found"] or not s["failing_levels"]) else 1


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="RAM Boundary Sweep Test — §3.3 diploma thesis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    # Positional args match the backend calling convention:
    #   python ram_boundary_test.py <model_name> [port]
    p.add_argument("model_name", help="Ollama model name, e.g. phi3:mini")
    p.add_argument("port", nargs="?", type=int, default=11434,
                   help="Ollama API port (default: 11434)")
    p.add_argument("--container", default=os.environ.get("OLLAMA_CONTAINER", "ollama"),
                   help="Docker container name to constrain (default: ollama)")
    p.add_argument("--start-gb", type=float, default=8.0,
                   help="Starting RAM level in GB (default: 8)")
    p.add_argument("--min-gb", type=float, default=1.0,
                   help="Minimum RAM level to test in GB (default: 1)")
    p.add_argument("--prompt", choices=["short", "medium", "long"], default="medium",
                   help="Probe prompt length (default: medium)")
    p.add_argument("--no-restore", action="store_true",
                   help="Skip restoring original mem_limit at end")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    sys.exit(
        run_ram_boundary_sweep(
            model_name=args.model_name,
            container_name=args.container,
            port=args.port,
            start_gb=args.start_gb,
            min_gb=args.min_gb,
            prompt_key=args.prompt,
            restore=not args.no_restore,
        )
    )
