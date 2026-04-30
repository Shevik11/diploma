"""
Cold Start Test for SLM models
Measures: model load time (TTFT on cold model), warm TTFT, and load time variance.

Method:
  1. Unload the model from memory using keep_alive=0
  2. Send first request — this is a cold start (forces model reload)
  3. Measure load_duration (time spent loading model weights)
  4. Send second request immediately — this is a warm start
  5. Repeat across short / medium / long prompts
  6. Report cold vs warm delta and pass/fail against 60s threshold
"""
import requests
import time
import json
import sys
import os
import statistics
from pathlib import Path

RESULTS_DIR = Path(__file__).parent.parent.parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

LOAD_TIME_THRESHOLD_S = 60.0   # thesis threshold: model load < 60s
TTFT_THRESHOLD_S = 3.0         # thesis threshold: TTFT < 3s


def _unload_model(host, port, model_name):
    """Evict model from Ollama memory by setting keep_alive=0."""
    try:
        requests.post(
            f"http://{host}:{port}/api/generate",
            json={"model": model_name, "prompt": "", "keep_alive": 0},
            timeout=30,
        )
    except Exception:
        pass
    time.sleep(1)


def _run_inference(url, model_name, prompt, keep_alive="5m"):
    """Run single inference and return full timing data dict, or None on error."""
    payload = {
        "model": model_name,
        "prompt": prompt,
        "stream": False,
        "keep_alive": keep_alive,
        "options": {"num_predict": 128, "temperature": 0.1},
    }
    wall_start = time.time()
    try:
        response = requests.post(url, json=payload, timeout=180)
        response.raise_for_status()
        wall_time = time.time() - wall_start
        data = response.json()

        load_duration_ns   = data.get("load_duration", 0)
        eval_duration_ns   = data.get("eval_duration", 0)
        total_duration_ns  = data.get("total_duration", 0)
        prompt_eval_ns     = data.get("prompt_eval_duration", 0)
        eval_count         = data.get("eval_count", 0)

        load_duration_s   = load_duration_ns  / 1e9
        eval_duration_s   = eval_duration_ns  / 1e9
        total_duration_s  = total_duration_ns / 1e9
        prompt_eval_s     = prompt_eval_ns    / 1e9

        tps = eval_count / eval_duration_s if eval_duration_s > 0 else 0
        # TTFT = load + prompt eval (everything before first output token)
        ttft_s = load_duration_s + prompt_eval_s

        return {
            "wall_time_s":      round(wall_time, 3),
            "load_duration_s":  round(load_duration_s, 3),
            "prompt_eval_s":    round(prompt_eval_s, 3),
            "eval_duration_s":  round(eval_duration_s, 3),
            "total_duration_s": round(total_duration_s, 3),
            "ttft_s":           round(ttft_s, 3),
            "eval_tokens":      eval_count,
            "tokens_per_sec":   round(tps, 2),
            "response_preview": data.get("response", "")[:80],
            "success":          True,
        }
    except Exception as e:
        return {"success": False, "error": str(e), "wall_time_s": round(time.time() - wall_start, 3)}


def test_cold_start(model_name, port=11434):
    host = os.environ.get("SLM_TEST_HOST", "localhost")
    url  = f"http://{host}:{port}/api/generate"

    prompts = [
        {
            "label": "short",
            "prompt": "What is Docker? Answer in one sentence.",
        },
        {
            "label": "medium",
            "prompt": "Write a Python function that sorts a list using bubble sort. Include a brief comment.",
        },
        {
            "label": "long",
            "prompt": (
                "Explain in detail the differences between containers and virtual machines. "
                "Cover isolation, resource usage, startup time, portability, and typical use cases. "
                "Give a concrete recommendation for when to use each."
            ),
        },
    ]

    results = {
        "model":     model_name,
        "port":      port,
        "timestamp": time.time(),
        "thresholds": {
            "load_time_s": LOAD_TIME_THRESHOLD_S,
            "ttft_s":      TTFT_THRESHOLD_S,
        },
        "tests":   [],
        "summary": {},
    }

    print(f"\n{'='*60}")
    print(f"COLD START TEST: {model_name}")
    print(f"Thresholds: load < {LOAD_TIME_THRESHOLD_S}s | TTFT < {TTFT_THRESHOLD_S}s")
    print(f"{'='*60}\n")

    cold_load_times = []
    warm_load_times = []
    cold_ttfts      = []
    warm_ttfts      = []

    for i, item in enumerate(prompts, 1):
        label  = item["label"]
        prompt = item["prompt"]
        print(f"[{i}/{len(prompts)}] Prompt: {label}")

        # --- Cold run ---
        print("  Unloading model from memory...")
        _unload_model(host, port, model_name)
        print("  Cold run...")
        cold = _run_inference(url, model_name, prompt)

        # --- Warm run (model already in memory) ---
        print("  Warm run...")
        warm = _run_inference(url, model_name, prompt)

        test_entry = {
            "prompt_label":  label,
            "prompt":        prompt,
            "cold":          cold,
            "warm":          warm,
        }

        if cold["success"] and warm["success"]:
            delta_load = round(cold["load_duration_s"] - warm["load_duration_s"], 3)
            delta_ttft = round(cold["ttft_s"] - warm["ttft_s"], 3)
            test_entry["cold_vs_warm_load_delta_s"] = delta_load
            test_entry["cold_vs_warm_ttft_delta_s"] = delta_ttft
            test_entry["load_time_pass"] = cold["load_duration_s"] <= LOAD_TIME_THRESHOLD_S
            test_entry["ttft_pass"]      = cold["ttft_s"] <= TTFT_THRESHOLD_S

            cold_load_times.append(cold["load_duration_s"])
            warm_load_times.append(warm["load_duration_s"])
            cold_ttfts.append(cold["ttft_s"])
            warm_ttfts.append(warm["ttft_s"])

            print(f"  Cold: load={cold['load_duration_s']:.2f}s | TTFT={cold['ttft_s']:.2f}s | {cold['tokens_per_sec']:.1f} tok/s")
            print(f"  Warm: load={warm['load_duration_s']:.2f}s | TTFT={warm['ttft_s']:.2f}s | {warm['tokens_per_sec']:.1f} tok/s")
            print(f"  Delta load: {delta_load:+.2f}s | Delta TTFT: {delta_ttft:+.2f}s")
            status = "[PASS]" if test_entry["load_time_pass"] and test_entry["ttft_pass"] else "[FAIL]"
            print(f"  {status}\n")
        else:
            err = cold.get("error") or warm.get("error", "unknown")
            print(f"  [ERROR] {err}\n")

        results["tests"].append(test_entry)

    # Summary
    if cold_load_times:
        results["summary"] = {
            "runs":                     len(cold_load_times),
            "avg_cold_load_s":          round(statistics.mean(cold_load_times), 3),
            "max_cold_load_s":          round(max(cold_load_times), 3),
            "avg_warm_load_s":          round(statistics.mean(warm_load_times), 3),
            "avg_cold_ttft_s":          round(statistics.mean(cold_ttfts), 3),
            "avg_warm_ttft_s":          round(statistics.mean(warm_ttfts), 3),
            "avg_cold_warm_load_delta_s": round(statistics.mean(cold_load_times) - statistics.mean(warm_load_times), 3),
            "load_time_threshold_pass": max(cold_load_times) <= LOAD_TIME_THRESHOLD_S,
            "ttft_threshold_pass":      max(cold_ttfts) <= TTFT_THRESHOLD_S,
        }

        s = results["summary"]
        print(f"{'='*60}")
        print(f"SUMMARY")
        print(f"{'='*60}")
        print(f"Avg cold load time: {s['avg_cold_load_s']:.3f}s  (max: {s['max_cold_load_s']:.3f}s)")
        print(f"Avg warm load time: {s['avg_warm_load_s']:.3f}s")
        print(f"Avg cold TTFT:      {s['avg_cold_ttft_s']:.3f}s")
        print(f"Avg warm TTFT:      {s['avg_warm_ttft_s']:.3f}s")
        print(f"Load time pass (<{LOAD_TIME_THRESHOLD_S}s): {'YES' if s['load_time_threshold_pass'] else 'NO'}")
        print(f"TTFT pass (<{TTFT_THRESHOLD_S}s):           {'YES' if s['ttft_threshold_pass'] else 'NO'}")
        print(f"{'='*60}\n")

    output_file = RESULTS_DIR / f"cold_start_{model_name.replace(':', '_')}_{int(time.time())}.json"
    try:
        with output_file.open("w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        print(f"Results saved to: {output_file}")
    except Exception as e:
        print(f"Warning: Could not save results: {e}")

    all_pass = results["summary"].get("load_time_threshold_pass", False) and \
               results["summary"].get("ttft_threshold_pass", False)
    return 0 if all_pass else 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python cold_start_test.py <model_name> [port]")
        sys.exit(1)

    model = sys.argv[1]
    port  = int(sys.argv[2]) if len(sys.argv) > 2 else 11434
    sys.exit(test_cold_start(model, port))
