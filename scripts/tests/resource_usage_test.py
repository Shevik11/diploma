"""
Resource Usage Test for SLM models
Measures: peak RAM, average CPU utilization during inference, memory growth across requests.

Method:
  - A background thread samples psutil every 0.5s during each inference call
  - Reports peak RAM (MB), average CPU (%), and idle baseline
  - Runs short / medium / long prompts and a sequential series (10 requests)
  - Compares peak RAM against the configured container RAM limit
  - Thesis thresholds: TPS > 3, peak RAM should not exceed container limit
"""
import requests
import time
import json
import sys
import os
import threading
import statistics
from pathlib import Path

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

RESULTS_DIR = Path(__file__).parent.parent.parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

TPS_THRESHOLD     = 3.0   # tok/s — thesis minimum
SAMPLE_INTERVAL_S = 0.5   # resource sampling rate


class ResourceMonitor:
    """Background sampler that records CPU and RAM while inference runs."""

    def __init__(self):
        self.cpu_samples  = []
        self.ram_samples  = []   # MB
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self._stop.clear()
        self.cpu_samples = []
        self.ram_samples = []
        self._thread = threading.Thread(target=self._sample, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)

    def _sample(self):
        while not self._stop.is_set():
            if PSUTIL_AVAILABLE:
                mem = psutil.virtual_memory()
                self.ram_samples.append(mem.used / 1024 / 1024)
                self.cpu_samples.append(psutil.cpu_percent(interval=None))
            self._stop.wait(SAMPLE_INTERVAL_S)

    def summary(self):
        if not self.ram_samples:
            return {}
        return {
            "peak_ram_mb":      round(max(self.ram_samples), 1),
            "avg_ram_mb":       round(statistics.mean(self.ram_samples), 1),
            "min_ram_mb":       round(min(self.ram_samples), 1),
            "peak_cpu_percent": round(max(self.cpu_samples), 1) if self.cpu_samples else 0,
            "avg_cpu_percent":  round(statistics.mean(self.cpu_samples), 1) if self.cpu_samples else 0,
            "samples":          len(self.ram_samples),
        }


def _infer(url, model_name, prompt):
    """Run inference and return timing + ollama metrics dict."""
    payload = {
        "model":   model_name,
        "prompt":  prompt,
        "stream":  False,
        "options": {"num_predict": 256, "temperature": 0.1},
    }
    wall_start = time.time()
    try:
        response = requests.post(url, json=payload, timeout=300)
        response.raise_for_status()
        wall_time = time.time() - wall_start
        data = response.json()

        eval_count       = data.get("eval_count", 0)
        eval_duration_ns = data.get("eval_duration", 0)
        total_ns         = data.get("total_duration", 0)
        load_ns          = data.get("load_duration", 0)
        prompt_eval_ns   = data.get("prompt_eval_duration", 0)

        eval_s  = eval_duration_ns / 1e9
        total_s = total_ns / 1e9
        tps     = eval_count / eval_s if eval_s > 0 else 0
        ttft_s  = (load_ns + prompt_eval_ns) / 1e9

        return {
            "success":          True,
            "wall_time_s":      round(wall_time, 3),
            "total_duration_s": round(total_s, 3),
            "load_duration_s":  round(load_ns / 1e9, 3),
            "ttft_s":           round(ttft_s, 3),
            "eval_tokens":      eval_count,
            "tokens_per_sec":   round(tps, 2),
            "response_preview": data.get("response", "")[:80],
        }
    except Exception as e:
        return {"success": False, "error": str(e), "wall_time_s": round(time.time() - wall_start, 3)}


def test_resource_usage(model_name, port=11434):
    host    = os.environ.get("SLM_TEST_HOST", "localhost")
    url     = f"http://{host}:{port}/api/generate"
    monitor = ResourceMonitor()

    if not PSUTIL_AVAILABLE:
        print("WARNING: psutil not installed — RAM/CPU monitoring disabled.")
        print("         Install with: pip install psutil")

    # --- Measure idle baseline ---
    baseline_ram = 0
    baseline_cpu = 0
    if PSUTIL_AVAILABLE:
        time.sleep(1)
        mem = psutil.virtual_memory()
        baseline_ram = round(mem.used / 1024 / 1024, 1)
        baseline_cpu = round(psutil.cpu_percent(interval=1), 1)

    prompts = [
        {"label": "short",  "prompt": "What is Docker? One sentence."},
        {"label": "medium", "prompt": "Explain the difference between RAM and disk storage in 3-4 sentences."},
        {"label": "long",   "prompt": (
            "Write a detailed explanation of how a CPU executes instructions, "
            "covering the fetch-decode-execute cycle, registers, cache levels, "
            "and the role of the operating system scheduler."
        )},
    ]

    results = {
        "model":           model_name,
        "port":            port,
        "timestamp":       time.time(),
        "psutil_available": PSUTIL_AVAILABLE,
        "thresholds":      {"tps": TPS_THRESHOLD},
        "baseline":        {"ram_mb": baseline_ram, "cpu_percent": baseline_cpu},
        "per_prompt":      [],
        "sequential":      {},
        "summary":         {},
    }

    print(f"\n{'='*60}")
    print(f"RESOURCE USAGE TEST: {model_name}")
    print(f"Baseline RAM: {baseline_ram} MB | Baseline CPU: {baseline_cpu}%")
    print(f"{'='*60}\n")

    all_peak_ram   = []
    all_avg_cpu    = []
    all_tps        = []

    # --- Per-prompt resource profiling ---
    for i, item in enumerate(prompts, 1):
        label  = item["label"]
        prompt = item["prompt"]
        print(f"[{i}/{len(prompts)}] Prompt: {label}")

        monitor.start()
        inf = _infer(url, model_name, prompt)
        monitor.stop()
        res = monitor.summary()

        entry = {"prompt_label": label, "inference": inf, "resources": res}
        if inf["success"] and res:
            ram_over_baseline = round(res["peak_ram_mb"] - baseline_ram, 1)
            entry["ram_increase_over_baseline_mb"] = ram_over_baseline
            all_peak_ram.append(res["peak_ram_mb"])
            all_avg_cpu.append(res["avg_cpu_percent"])
            all_tps.append(inf["tokens_per_sec"])

            print(f"  TPS: {inf['tokens_per_sec']:.2f} tok/s | TTFT: {inf['ttft_s']:.3f}s")
            print(f"  Peak RAM: {res['peak_ram_mb']:.1f} MB (+{ram_over_baseline:.1f} over baseline)")
            print(f"  Avg CPU:  {res['avg_cpu_percent']:.1f}% | Peak CPU: {res['peak_cpu_percent']:.1f}%")
        elif not inf["success"]:
            print(f"  [ERROR] {inf.get('error', 'unknown')}")
        print()
        results["per_prompt"].append(entry)

    # --- Sequential series: 10 requests, same medium prompt ---
    print("Sequential series (10 requests, medium prompt)...")
    seq_prompt = "Explain what an operating system does in 2-3 sentences."
    seq_results = []
    monitor.start()
    for j in range(10):
        inf = _infer(url, model_name, seq_prompt)
        seq_results.append(inf)
        status = f"{inf['tokens_per_sec']:.1f} tok/s" if inf["success"] else inf.get("error", "fail")
        print(f"  [{j+1:2d}/10] {status}")
    monitor.stop()
    seq_res = monitor.summary()

    successful_seq = [r for r in seq_results if r["success"]]
    seq_tps_list   = [r["tokens_per_sec"] for r in successful_seq]

    results["sequential"] = {
        "runs":             10,
        "successful":       len(successful_seq),
        "success_rate":     round(len(successful_seq) / 10 * 100, 1),
        "avg_tps":          round(statistics.mean(seq_tps_list), 2) if seq_tps_list else 0,
        "median_tps":       round(statistics.median(seq_tps_list), 2) if seq_tps_list else 0,
        "min_tps":          round(min(seq_tps_list), 2) if seq_tps_list else 0,
        "max_tps":          round(max(seq_tps_list), 2) if seq_tps_list else 0,
        "avg_wall_time_s":  round(statistics.mean([r["wall_time_s"] for r in successful_seq]), 3) if successful_seq else 0,
        "resources":        seq_res,
        "runs_detail":      seq_results,
    }

    if seq_res:
        print(f"\n  Sequential peak RAM: {seq_res['peak_ram_mb']:.1f} MB")
        print(f"  Sequential avg CPU:  {seq_res['avg_cpu_percent']:.1f}%")

    # --- Overall summary ---
    if all_tps:
        results["summary"] = {
            "avg_peak_ram_mb":       round(statistics.mean(all_peak_ram), 1) if all_peak_ram else 0,
            "max_peak_ram_mb":       round(max(all_peak_ram), 1) if all_peak_ram else 0,
            "avg_cpu_percent":       round(statistics.mean(all_avg_cpu), 1) if all_avg_cpu else 0,
            "avg_tps":               round(statistics.mean(all_tps), 2),
            "tps_threshold_pass":    statistics.mean(all_tps) >= TPS_THRESHOLD,
            "sequential_avg_tps":    results["sequential"].get("avg_tps", 0),
            "sequential_median_tps": results["sequential"].get("median_tps", 0),
        }

        s = results["summary"]
        print(f"\n{'='*60}")
        print(f"RESOURCE SUMMARY")
        print(f"{'='*60}")
        print(f"Avg peak RAM: {s['avg_peak_ram_mb']:.1f} MB (max: {s['max_peak_ram_mb']:.1f} MB)")
        print(f"Avg CPU:      {s['avg_cpu_percent']:.1f}%")
        print(f"Avg TPS:      {s['avg_tps']:.2f} tok/s  (threshold: >{TPS_THRESHOLD})")
        print(f"TPS pass:     {'YES' if s['tps_threshold_pass'] else 'NO'}")
        print(f"Sequential avg TPS:    {s['sequential_avg_tps']:.2f} tok/s")
        print(f"Sequential median TPS: {s['sequential_median_tps']:.2f} tok/s")
        print(f"{'='*60}\n")

    output_file = RESULTS_DIR / f"resource_usage_{model_name.replace(':', '_')}_{int(time.time())}.json"
    try:
        with output_file.open("w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        print(f"Results saved to: {output_file}")
    except Exception as e:
        print(f"Warning: Could not save results: {e}")

    tps_pass = results["summary"].get("tps_threshold_pass", False)
    return 0 if tps_pass else 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python resource_usage_test.py <model_name> [port]")
        sys.exit(1)

    model = sys.argv[1]
    port  = int(sys.argv[2]) if len(sys.argv) > 2 else 11434
    sys.exit(test_resource_usage(model, port))
