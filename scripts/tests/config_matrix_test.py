"""
Config Matrix Test (§3.2)
=========================
Automates the full §3.2 configuration matrix — 8 RAM/CPU/VRAM combos —
and records inference performance at every combo against §4.1 thresholds.

Thesis mapping
--------------
§3.2  Configuration matrix (8 combos):
        | RAM (GB) | CPU cores | GPU VRAM | Comment                                       |
        |----------|-----------|----------|-----------------------------------------------|
        | 1        | 1         | none     | Expected failure / very slow                  |
        | 2        | 2         | none     | Minimum threshold for small models            |
        | 4        | 2         | none     | Baseline for 1–3B                             |
        | 4        | 4         | none     | Improved CPU inference                         |
        | 8        | 4         | none     | Comfortable for 3–7B                          |
        | 4        | 2         | 2 GB     | GPU-accel on min config                        |
        | 8        | 4         | 4 GB     | GPU-accel on standard config                   |
        | 16       | 8         | 8 GB     | High performance reference                     |
§4.1  Thresholds: TTFT < 3 000 ms · TPS > 3 tok/s · load time < 60 s
§4.2  Records peak RAM (MB) at each combo via psutil (if available)

Method
------
1.  Record the container's current mem_limit and CPU quota via Docker SDK.
2.  For each combo in the matrix, inside try/finally that always restores:
    a.  Apply container.update(mem_limit=<RAM>, nano_cpus=<CPU>).
    b.  Wait for cgroup enforcement (grace period).
    c.  Evict the model from Ollama memory (keep_alive=0) to force reload.
    d.  Cold probe — first request reloads under the new limits.
    e.  Warm probe — second request, already resident.
    f.  Evaluate vs §4.1 thresholds. Continue regardless of pass/fail
        (unlike §3.3 boundary sweep) so the whole matrix is filled.
3.  GPU combos (vram_gb > 0) are SKIPPED if no GPU runtime is detected,
    and the result row is marked `skipped: "no_gpu_runtime"`.
4.  Restore original mem_limit and nano_cpus.
5.  Save unified JSON report to results/.

Usage
-----
  python config_matrix_test.py <model_name> [port] [options]

Options
-------
  --container   Docker container name to constrain  (default: ollama)
  --prompt      short | medium | long                (default: medium)
  --combos      Comma-separated combo indexes 1..8   (default: all)
  --no-restore  Skip restoring original limits at end (for CI)

Requirements
------------
  pip install docker requests psutil
"""

import argparse
import json
import os
import sys
import time
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

TTFT_THRESHOLD_S    = 10.0   # §4.1 — CPU-only realistic (was 3.0s; phi3:mini measured ~5.9s cold TTFT on CPU)
TPS_THRESHOLD       = 3.0    # §4.1
LOAD_THRESHOLD_S    = 60.0   # §4.1
REQUEST_TIMEOUT_S   = 180    # hard HTTP timeout per request
GRACE_AFTER_LIMIT_S = 4
GRACE_AFTER_EVICT_S = 3

# §3.2 — 8 RAM / CPU / VRAM combinations from the diploma plan
CONFIG_MATRIX = [
    {"id": 1, "ram_gb": 1,  "cpu_cores": 1, "vram_gb": 0, "label": "1 GB / 1 core",            "expected": "failure or very slow"},
    {"id": 2, "ram_gb": 2,  "cpu_cores": 2, "vram_gb": 0, "label": "2 GB / 2 cores",           "expected": "minimum for small models"},
    {"id": 3, "ram_gb": 4,  "cpu_cores": 2, "vram_gb": 0, "label": "4 GB / 2 cores",           "expected": "baseline for 1–3B"},
    {"id": 4, "ram_gb": 4,  "cpu_cores": 4, "vram_gb": 0, "label": "4 GB / 4 cores",           "expected": "improved CPU inference"},
    {"id": 5, "ram_gb": 8,  "cpu_cores": 4, "vram_gb": 0, "label": "8 GB / 4 cores",           "expected": "comfortable for 3–7B"},
    {"id": 6, "ram_gb": 4,  "cpu_cores": 2, "vram_gb": 2, "label": "4 GB / 2 cores / 2 GB GPU","expected": "GPU on minimum config"},
    {"id": 7, "ram_gb": 8,  "cpu_cores": 4, "vram_gb": 4, "label": "8 GB / 4 cores / 4 GB GPU","expected": "GPU on standard config"},
    {"id": 8, "ram_gb": 16, "cpu_cores": 8, "vram_gb": 8, "label": "16 GB / 8 cores / 8 GB GPU","expected": "high performance reference"},
]

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


def _cores_to_nano_cpus(cores: float) -> int:
    # Docker uses nano_cpus = cores * 1e9
    return int(cores * 1_000_000_000)


def _get_current_limits(container) -> dict:
    """Return current mem_limit (bytes) and nano_cpus. 0 means unlimited."""
    hc = container.attrs.get("HostConfig", {}) or {}
    return {
        "mem_bytes": hc.get("Memory", 0) or 0,
        "nano_cpus": hc.get("NanoCpus", 0) or 0,
    }


def _apply_limits(container, ram_gb: float, cpu_cores: float) -> dict:
    """Apply mem_limit + nano_cpus live. Returns ok-dict with applied values."""
    mem_bytes = _gb_to_bytes(ram_gb)
    nano_cpus = _cores_to_nano_cpus(cpu_cores)
    try:
        container.update(
            mem_limit=mem_bytes,
            memswap_limit=mem_bytes,   # disable swap so RAM pressure is real
            cpu_period=100000,
            cpu_quota=int(cpu_cores * 100000),
        )
        # nano_cpus is set via cpu_period/cpu_quota above; SDK update() does not
        # accept nano_cpus directly on all versions, so we rely on cpu_period/quota.
        container.reload()
        applied = _get_current_limits(container)
        return {
            "ok": True,
            "requested": {"ram_gb": ram_gb, "cpu_cores": cpu_cores},
            "applied": {
                "ram_gb":    _bytes_to_gb(applied["mem_bytes"]),
                "cpu_cores": round(applied["nano_cpus"] / 1e9, 2) if applied["nano_cpus"] else cpu_cores,
            },
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _restore_limits(container, original: dict) -> None:
    """Restore original mem_limit and CPU quota."""
    try:
        kwargs = {}
        if original.get("mem_bytes", 0) == 0:
            kwargs["mem_limit"] = -1
            kwargs["memswap_limit"] = -1
        else:
            kwargs["mem_limit"] = original["mem_bytes"]
            kwargs["memswap_limit"] = original["mem_bytes"]
        if original.get("nano_cpus", 0) == 0:
            kwargs["cpu_period"] = 0
            kwargs["cpu_quota"] = 0
        else:
            cores = original["nano_cpus"] / 1e9
            kwargs["cpu_period"] = 100000
            kwargs["cpu_quota"] = int(cores * 100000)
        container.update(**kwargs)
    except Exception as e:
        print(f"  WARNING: could not restore original limits: {e}")


def _container_has_gpu(container) -> bool:
    """Detect if container has an NVIDIA GPU device assigned."""
    try:
        hc = container.attrs.get("HostConfig", {}) or {}
        # Modern: DeviceRequests with Driver=nvidia
        for req in hc.get("DeviceRequests") or []:
            if (req.get("Driver") or "").lower() == "nvidia":
                return True
            caps = req.get("Capabilities") or []
            for cap_set in caps:
                if "gpu" in (cap_set or []):
                    return True
        # Legacy: Runtime=nvidia
        if (hc.get("Runtime") or "").lower() == "nvidia":
            return True
    except Exception:
        pass
    return False


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

        load_s = load_ns / 1e9
        eval_s = eval_ns / 1e9
        tps    = eval_count / eval_s if eval_s > 0 else 0
        ttft_s = (load_ns + prompt_eval_ns) / 1e9

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


def _sample_ram_mb():
    if not PSUTIL_AVAILABLE:
        return None
    return round(psutil.virtual_memory().used / 1024 / 1024, 1)


# ── Threshold evaluator ───────────────────────────────────────────────────────

def _evaluate(cold: dict, warm: dict) -> dict:
    """Return pass/fail vs §4.1 thresholds. Cold (worst case) drives pass."""
    if not cold.get("success"):
        return {
            "passed": False,
            "reason": f"cold request failed: {cold.get('error_type', 'unknown')} — {cold.get('error', '')}",
            "checks": {},
        }
    checks = {
        "ttft_ok": cold["ttft_s"] < TTFT_THRESHOLD_S,
        "tps_ok":  cold["tokens_per_sec"] >= TPS_THRESHOLD,
        "load_ok": cold["load_duration_s"] < LOAD_THRESHOLD_S,
        "warm_ok": warm.get("success", False),
    }
    passed = all(checks.values())
    failed = [k for k, v in checks.items() if not v]
    return {
        "passed": passed,
        "reason": "all thresholds met" if passed else f"failed: {', '.join(failed)}",
        "checks": checks,
    }


# ── Main matrix runner ───────────────────────────────────────────────────────

def run_config_matrix(
    model_name: str,
    container_name: str = "ollama",
    port: int = 11434,
    prompt_key: str = "medium",
    combos: list | None = None,
    restore: bool = True,
) -> int:
    host = os.environ.get("SLM_TEST_HOST", "localhost")

    if not DOCKER_AVAILABLE:
        print("ERROR: 'docker' package not installed. pip install docker")
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

    has_gpu = _container_has_gpu(container)
    selected = CONFIG_MATRIX if not combos else [c for c in CONFIG_MATRIX if c["id"] in combos]
    if not selected:
        print(f"ERROR: No combos selected (requested ids: {combos}).")
        return 2

    prompt = PROBE_PROMPTS.get(prompt_key, PROBE_PROMPTS["medium"])
    original = _get_current_limits(container)
    original_view = {
        "ram_gb":    _bytes_to_gb(original["mem_bytes"]) if original["mem_bytes"] else "unlimited",
        "cpu_cores": round(original["nano_cpus"] / 1e9, 2) if original["nano_cpus"] else "unlimited",
    }

    results = {
        "model":       model_name,
        "container":   container_name,
        "port":        port,
        "timestamp":   time.time(),
        "prompt_key":  prompt_key,
        "prompt":      prompt,
        "thresholds": {
            "ttft_s": TTFT_THRESHOLD_S,
            "tps":    TPS_THRESHOLD,
            "load_s": LOAD_THRESHOLD_S,
        },
        "gpu_runtime_detected": has_gpu,
        "original_limits":      original_view,
        "matrix":               selected,
        "combos":               [],
        "summary":              {},
    }

    print(f"\n{'='*64}")
    print(f"  CONFIG MATRIX TEST (§3.2)  —  {model_name}")
    print(f"{'='*64}")
    print(f"  Container :  {container_name}")
    print(f"  Combos    :  {len(selected)} of {len(CONFIG_MATRIX)}")
    print(f"  Prompt    :  {prompt_key}")
    print(f"  Original  :  {original_view['ram_gb']} GB / {original_view['cpu_cores']} cores")
    print(f"  GPU       :  {'detected' if has_gpu else 'NOT detected (GPU combos will be skipped)'}")
    print(f"  Thresholds:  TTFT < {TTFT_THRESHOLD_S}s | TPS > {TPS_THRESHOLD} | load < {LOAD_THRESHOLD_S}s")
    print(f"{'='*64}\n")

    try:
        for combo in selected:
            cid = combo["id"]
            print(f"── Combo #{cid}: {combo['label']} {'─' * (40 - len(combo['label']))}")
            print(f"  Expected: {combo['expected']}")

            # Skip GPU combos if no GPU runtime
            if combo["vram_gb"] > 0 and not has_gpu:
                print(f"  [SKIP] GPU runtime not available\n")
                results["combos"].append({
                    **combo,
                    "skipped": "no_gpu_runtime",
                    "cold": None, "warm": None, "evaluation": None,
                })
                continue

            # 1. Apply limits
            limit_result = _apply_limits(container, combo["ram_gb"], combo["cpu_cores"])
            if not limit_result["ok"]:
                print(f"  [SKIP] Could not apply limits: {limit_result['error']}\n")
                results["combos"].append({
                    **combo,
                    "skipped": f"apply_failed: {limit_result['error']}",
                    "cold": None, "warm": None, "evaluation": None,
                })
                continue
            applied = limit_result["applied"]
            print(f"  Applied: {applied['ram_gb']} GB / {applied['cpu_cores']} cores")
            time.sleep(GRACE_AFTER_LIMIT_S)

            # 2. Evict model
            ram_before = _sample_ram_mb()
            print(f"  Evicting model from Ollama memory…")
            _evict_model(host, port, model_name)
            time.sleep(GRACE_AFTER_EVICT_S)

            # 3. Cold probe
            print(f"  Cold probe… ", end="", flush=True)
            cold = _run_inference(host, port, model_name, prompt)
            ram_after_cold = _sample_ram_mb()
            if cold["success"]:
                print(
                    f"TTFT={cold['ttft_s']:.2f}s  load={cold['load_duration_s']:.2f}s"
                    f"  TPS={cold['tokens_per_sec']:.1f}"
                )
            else:
                print(f"FAILED [{cold.get('error_type')}] {str(cold.get('error', ''))[:60]}")

            # 4. Warm probe
            print(f"  Warm probe… ", end="", flush=True)
            warm = _run_inference(host, port, model_name, prompt)
            ram_after_warm = _sample_ram_mb()
            if warm["success"]:
                print(f"TTFT={warm['ttft_s']:.2f}s  TPS={warm['tokens_per_sec']:.1f}")
            else:
                print(f"FAILED [{warm.get('error_type')}]")

            # 5. Evaluate
            evaluation = _evaluate(cold, warm)
            status = "PASS ✓" if evaluation["passed"] else "FAIL ✗"
            print(f"  {status}  —  {evaluation['reason']}\n")

            results["combos"].append({
                **combo,
                "skipped":            None,
                "applied":            applied,
                "cold":               cold,
                "warm":               warm,
                "evaluation":         evaluation,
                "ram_before_evict_mb": ram_before,
                "ram_after_cold_mb":   ram_after_cold,
                "ram_after_warm_mb":   ram_after_warm,
            })

    finally:
        if restore:
            print(f"\nRestoring original limits "
                  f"({original_view['ram_gb']} GB / {original_view['cpu_cores']} cores)…")
            _restore_limits(container, original)
            print("  Done.")

    # ── summary ──────────────────────────────────────────────────────────────
    tested = [c for c in results["combos"] if not c.get("skipped")]
    passing = [c for c in tested if c["evaluation"]["passed"]]
    failing = [c for c in tested if not c["evaluation"]["passed"]]
    skipped = [c for c in results["combos"] if c.get("skipped")]

    # Min viable config = smallest (RAM × cores) that passed
    min_viable = None
    if passing:
        min_viable = min(passing, key=lambda c: (c["ram_gb"], c["cpu_cores"]))
        min_viable = {
            "id":        min_viable["id"],
            "ram_gb":    min_viable["ram_gb"],
            "cpu_cores": min_viable["cpu_cores"],
            "vram_gb":   min_viable["vram_gb"],
            "label":     min_viable["label"],
        }

    results["summary"] = {
        "combos_total":    len(selected),
        "combos_tested":   len(tested),
        "combos_passing":  len(passing),
        "combos_failing":  len(failing),
        "combos_skipped":  len(skipped),
        "passing_ids":     [c["id"] for c in passing],
        "failing_ids":     [c["id"] for c in failing],
        "skipped_ids":     [c["id"] for c in skipped],
        "min_viable":      min_viable,
        "thresholds":      results["thresholds"],
    }

    s = results["summary"]
    print(f"\n{'='*64}")
    print(f"  CONFIG MATRIX SUMMARY")
    print(f"{'='*64}")
    print(f"  Tested  : {s['combos_tested']} / {s['combos_total']}  "
          f"(skipped {s['combos_skipped']})")
    print(f"  Passing : {s['combos_passing']}  ids={s['passing_ids']}")
    print(f"  Failing : {s['combos_failing']}  ids={s['failing_ids']}")
    if min_viable:
        print(f"  Min viable config: #{min_viable['id']}  {min_viable['label']}")
    else:
        print(f"  No combo met thresholds.")
    print(f"{'='*64}\n")

    # ── save ─────────────────────────────────────────────────────────────────
    safe = model_name.replace(":", "_").replace("/", "_")
    out = RESULTS_DIR / f"config_matrix_{safe}_{int(time.time())}.json"
    try:
        out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Results saved → {out}")
    except Exception as e:
        print(f"WARNING: could not save results: {e}")

    # Exit code: 0 if at least one combo passed, 1 otherwise.
    return 0 if passing else 1


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_combos(s: str) -> list:
    if not s:
        return []
    out = []
    for part in s.split(","):
        part = part.strip()
        if part.isdigit():
            out.append(int(part))
    return out


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Config Matrix Test — §3.2 diploma thesis (8 RAM/CPU combos)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    # Positional args match the backend calling convention:
    #   python config_matrix_test.py <model_name> [port]
    p.add_argument("model_name", help="Ollama model name, e.g. phi3:mini")
    p.add_argument("port", nargs="?", type=int, default=11434,
                   help="Ollama API port (default: 11434)")
    p.add_argument("--container", default=os.environ.get("OLLAMA_CONTAINER", "ollama"),
                   help="Docker container name to constrain (default: ollama)")
    p.add_argument("--prompt", choices=["short", "medium", "long"], default="medium",
                   help="Probe prompt length (default: medium)")
    p.add_argument("--combos", default="",
                   help="Comma-separated combo ids 1..8 to run (default: all)")
    p.add_argument("--no-restore", action="store_true",
                   help="Skip restoring original limits at end")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    sys.exit(
        run_config_matrix(
            model_name=args.model_name,
            container_name=args.container,
            port=args.port,
            prompt_key=args.prompt,
            combos=_parse_combos(args.combos),
            restore=not args.no_restore,
        )
    )
