"""
VRAM Monitor Test
=================
Samples GPU video memory and utilization while the model runs inference.

Thesis mapping
--------------
§4.2  "VRAM usage" — obsyag videopam'yati (yaksho vykorystovuyetsya GPU)
§3.2  GPU combos (2 GB / 4 GB / 8 GB VRAM)

Method
------
1.  Probe for a GPU via `pynvml` (preferred) or `nvidia-smi` CLI fallback.
2.  If no GPU is available, record a `skipped` result and exit 0 so the test
    is a no-op on CPU-only hosts (Phase-2 of /api/benchmarks/run-all must not
    fail just because the host has no GPU).
3.  Baseline sample, then start a background sampler @ 0.5 s.
4.  Run cold + warm + 3 warm-series inference calls (short / medium / long).
5.  Stop sampler and compute: peak / avg / delta VRAM (MB), peak / avg GPU
    utilization (%), per-call VRAM peak.
6.  Evaluate against §3.2 VRAM envelopes: if VRAM is reported through the
    SLM_GPU_VRAM_GB env var (set by config_matrix_test.py), flag overflow.
7.  Save a JSON report to results/.

Requirements
------------
  pip install pynvml requests         # pynvml is optional; nvidia-smi works too
"""

import json
import os
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

import requests

RESULTS_DIR = Path(__file__).parent.parent.parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

SAMPLE_INTERVAL_S = 0.5
REQUEST_TIMEOUT_S = 180

PROBE_PROMPTS = {
    "short":  "What is Docker? Answer in one sentence.",
    "medium": "Write a Python function that sorts a list using bubble sort.",
    "long": (
        "Explain in detail the differences between containers and virtual machines. "
        "Cover isolation, resource usage, startup time, portability, and typical use cases."
    ),
}


# ── GPU backends ─────────────────────────────────────────────────────────────

class _NvmlBackend:
    name = "pynvml"

    def __init__(self):
        import pynvml
        pynvml.nvmlInit()
        self._pynvml = pynvml
        self._h = pynvml.nvmlDeviceGetHandleByIndex(0)
        self.device_name = pynvml.nvmlDeviceGetName(self._h)
        if isinstance(self.device_name, bytes):
            self.device_name = self.device_name.decode("utf-8", "replace")
        mem = pynvml.nvmlDeviceGetMemoryInfo(self._h)
        self.total_mb = round(mem.total / 1024 / 1024, 1)

    def sample(self):
        mem = self._pynvml.nvmlDeviceGetMemoryInfo(self._h)
        util = self._pynvml.nvmlDeviceGetUtilizationRates(self._h)
        return {
            "used_mb": mem.used / 1024 / 1024,
            "free_mb": mem.free / 1024 / 1024,
            "gpu_util": util.gpu,
            "mem_util": util.memory,
        }

    def close(self):
        try:
            self._pynvml.nvmlShutdown()
        except Exception:
            pass


class _SmiBackend:
    """Fallback: parse `nvidia-smi --query-gpu=...` CSV."""
    name = "nvidia-smi"

    _QUERY = "memory.used,memory.total,memory.free,utilization.gpu,utilization.memory,name"

    def __init__(self):
        out = self._run()
        fields = [x.strip() for x in out.splitlines()[0].split(",")]
        self.device_name = fields[5]
        self.total_mb = float(fields[1])

    def _run(self):
        proc = subprocess.run(
            ["nvidia-smi", f"--query-gpu={self._QUERY}", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or "nvidia-smi failed")
        return proc.stdout

    def sample(self):
        out = self._run()
        fields = [x.strip() for x in out.splitlines()[0].split(",")]
        return {
            "used_mb": float(fields[0]),
            "free_mb": float(fields[2]),
            "gpu_util": float(fields[3]),
            "mem_util": float(fields[4]),
        }

    def close(self):
        pass


def _detect_gpu():
    try:
        return _NvmlBackend()
    except Exception:
        pass
    try:
        return _SmiBackend()
    except Exception:
        return None


# ── sampler ──────────────────────────────────────────────────────────────────

class _GpuSampler(threading.Thread):
    def __init__(self, backend):
        super().__init__(daemon=True)
        self.backend = backend
        self._stop = threading.Event()
        self.samples = []

    def run(self):
        while not self._stop.is_set():
            try:
                self.samples.append(self.backend.sample())
            except Exception:
                pass
            self._stop.wait(SAMPLE_INTERVAL_S)

    def stop(self):
        self._stop.set()
        self.join(timeout=3)

    def snapshot(self):
        return list(self.samples)


def _summarize(samples):
    if not samples:
        return {}
    used = [s["used_mb"] for s in samples]
    gu   = [s["gpu_util"] for s in samples]
    return {
        "peak_vram_mb":  round(max(used), 1),
        "avg_vram_mb":   round(statistics.mean(used), 1),
        "min_vram_mb":   round(min(used), 1),
        "peak_gpu_util": round(max(gu), 1),
        "avg_gpu_util":  round(statistics.mean(gu), 1),
        "samples":       len(samples),
    }


# ── inference ────────────────────────────────────────────────────────────────

def _infer(url, model, prompt):
    t0 = time.time()
    try:
        r = requests.post(url, json={
            "model": model, "prompt": prompt, "stream": False,
            "keep_alive": "5m",
            "options": {"num_predict": 128, "temperature": 0.1},
        }, timeout=REQUEST_TIMEOUT_S)
        r.raise_for_status()
        d = r.json()
        eval_s = d.get("eval_duration", 0) / 1e9
        return {
            "success":        True,
            "wall_time_s":    round(time.time() - t0, 3),
            "ttft_s":         round((d.get("load_duration", 0) + d.get("prompt_eval_duration", 0)) / 1e9, 3),
            "tokens_per_sec": round(d.get("eval_count", 0) / eval_s, 2) if eval_s > 0 else 0,
            "eval_tokens":    d.get("eval_count", 0),
        }
    except Exception as e:
        return {"success": False, "error": str(e), "wall_time_s": round(time.time() - t0, 3)}


# ── main ─────────────────────────────────────────────────────────────────────

def run_vram_monitor(model_name: str, port: int = 11434) -> int:
    host = os.environ.get("SLM_TEST_HOST", "localhost")
    url = f"http://{host}:{port}/api/generate"

    print(f"\n{'='*60}\n  VRAM MONITOR — {model_name}\n{'='*60}")

    backend = _detect_gpu()
    if backend is None:
        print("  No GPU detected (pynvml + nvidia-smi both unavailable).")
        print("  Recording skipped result and exiting 0.")
        out = RESULTS_DIR / f"vram_monitor_{model_name.replace(':','_')}_{int(time.time())}.json"
        out.write_text(json.dumps({
            "model": model_name, "port": port, "timestamp": time.time(),
            "skipped": True, "skip_reason": "no_gpu_detected",
        }, indent=2), encoding="utf-8")
        return 0

    print(f"  GPU       : {backend.device_name}")
    print(f"  Total VRAM: {backend.total_mb:.0f} MB")
    print(f"  Backend   : {backend.name}")

    baseline = backend.sample()
    print(f"  Baseline  : {baseline['used_mb']:.0f} MB used / {backend.total_mb:.0f} MB total")

    per_call = []
    sampler = _GpuSampler(backend)
    sampler.start()

    try:
        # cold: force reload by evicting
        try:
            requests.post(url, json={"model": model_name, "prompt": "", "keep_alive": 0}, timeout=20)
        except Exception:
            pass
        time.sleep(2)

        phases = [
            ("cold_short",  PROBE_PROMPTS["short"]),
            ("warm_short",  PROBE_PROMPTS["short"]),
            ("warm_medium", PROBE_PROMPTS["medium"]),
            ("warm_long",   PROBE_PROMPTS["long"]),
        ]
        for label, prompt in phases:
            t0 = time.time()
            before_len = len(sampler.samples)
            res = _infer(url, model_name, prompt)
            after = sampler.samples[before_len:] or [backend.sample()]
            used = [s["used_mb"] for s in after]
            per_call.append({
                "phase": label,
                "duration_s": round(time.time() - t0, 3),
                "inference": res,
                "peak_vram_mb": round(max(used), 1) if used else None,
                "avg_vram_mb":  round(statistics.mean(used), 1) if used else None,
            })
            mark = "OK" if res.get("success") else "FAIL"
            print(f"  [{label:<12}] {mark}  peak_vram={per_call[-1]['peak_vram_mb']} MB  "
                  f"tps={res.get('tokens_per_sec')}")

    finally:
        sampler.stop()
        backend.close()

    summary = _summarize(sampler.snapshot())
    summary["baseline_vram_mb"] = round(baseline["used_mb"], 1)
    summary["delta_vram_mb"] = (
        round(summary.get("peak_vram_mb", 0) - baseline["used_mb"], 1)
        if summary else 0
    )

    # §3.2 envelope check (if config_matrix provided VRAM budget)
    envelope_gb = os.environ.get("SLM_GPU_VRAM_GB")
    envelope_check = None
    if envelope_gb:
        try:
            cap_mb = float(envelope_gb) * 1024
            envelope_check = {
                "envelope_mb": cap_mb,
                "peak_mb": summary.get("peak_vram_mb"),
                "within": summary.get("peak_vram_mb", 0) <= cap_mb,
            }
        except Exception:
            pass

    results = {
        "model":       model_name,
        "port":        port,
        "timestamp":   time.time(),
        "gpu":         {"name": backend.device_name, "total_mb": backend.total_mb, "backend": backend.name},
        "baseline":    baseline,
        "per_call":    per_call,
        "summary":     summary,
        "envelope_check": envelope_check,
        "skipped":     False,
    }

    print(f"\n  Peak VRAM : {summary.get('peak_vram_mb')} MB")
    print(f"  Delta     : {summary.get('delta_vram_mb')} MB over baseline")
    print(f"  Avg util  : {summary.get('avg_gpu_util')}%")

    out = RESULTS_DIR / f"vram_monitor_{model_name.replace(':','_')}_{int(time.time())}.json"
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  Saved     : {out}\n")

    all_ok = all(c["inference"].get("success") for c in per_call)
    if envelope_check is not None and not envelope_check["within"]:
        all_ok = False
    return 0 if all_ok else 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python vram_monitor_test.py <model_name> [port]")
        sys.exit(2)
    model = sys.argv[1]
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 11434
    sys.exit(run_vram_monitor(model, port))
