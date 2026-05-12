"""
OOM Detection and Boundary Test for SLM models
Measures: failure modes when resources are constrained.

Method:
  1. Escalating context size test — sends prompts with growing input length until
     the model times out, errors, or returns empty. Records the boundary token count.
  2. Rapid sequential burst — fires 20 back-to-back requests as fast as possible
     and records failures, slowdowns, and OOM-like errors.
  3. Max output test — requests very long outputs (num_predict=2048) and checks
     whether the model degrades or crashes under memory pressure.

No Docker API access is needed: failures manifest as HTTP errors, empty responses,
or extreme latency — all detectable from the Ollama API alone.

Thesis relevance:
  - Captures the "failure boundary" (minimum config point where model breaks)
  - Records error_type: timeout | empty_response | http_error | oom_signal
  - All results feed into the pass/fail matrix per RAM/CPU config
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

RESPONSE_TIMEOUT_S   = 120    # treat as failure if no response within this time
EMPTY_RESPONSE_LIMIT = 5      # chars — shorter than this = empty response failure
TPS_FLOOR            = 1.0    # tok/s — below this we mark as degraded


def _classify_error(exc: Exception, status_code: int = 0, response_text: str = "") -> str:
    msg = str(exc).lower()
    if "timeout" in msg or "timed out" in msg:
        return "timeout"
    if "out of memory" in msg or "oom" in msg or "cuda" in msg:
        return "oom_signal"
    if status_code in (500, 503):
        return "server_error"
    if status_code != 0:
        return f"http_{status_code}"
    return "connection_error"


def _infer(url, model_name, prompt, num_predict=256, timeout=RESPONSE_TIMEOUT_S):
    payload = {
        "model":   model_name,
        "prompt":  prompt,
        "stream":  False,
        "options": {"num_predict": num_predict, "temperature": 0.1},
    }
    wall_start = time.time()
    status_code = 0
    try:
        resp = requests.post(url, json=payload, timeout=timeout)
        status_code = resp.status_code
        resp.raise_for_status()
        wall_time = time.time() - wall_start
        data = resp.json()

        response_text    = data.get("response", "")
        eval_count       = data.get("eval_count", 0)
        eval_duration_ns = data.get("eval_duration", 0)
        eval_s           = eval_duration_ns / 1e9
        tps              = eval_count / eval_s if eval_s > 0 else 0

        is_empty = len(response_text.strip()) < EMPTY_RESPONSE_LIMIT
        degraded = tps < TPS_FLOOR and eval_count > 0

        return {
            "success":          True,
            "wall_time_s":      round(wall_time, 3),
            "tokens_per_sec":   round(tps, 2),
            "eval_tokens":      eval_count,
            "response_length":  len(response_text),
            "empty_response":   is_empty,
            "degraded":         degraded,
            "error_type":       "empty_response" if is_empty else None,
        }
    except requests.exceptions.Timeout:
        return {
            "success":    False,
            "wall_time_s": round(time.time() - wall_start, 3),
            "error_type": "timeout",
            "error":      "Request timed out",
        }
    except Exception as e:
        return {
            "success":    False,
            "wall_time_s": round(time.time() - wall_start, 3),
            "error_type": _classify_error(e, status_code),
            "error":      str(e),
        }


# ---------------------------------------------------------------------------
# Test 1 — Escalating context size
# ---------------------------------------------------------------------------

def _build_long_prompt(target_words: int) -> str:
    """Build a prompt of approximately target_words input words."""
    base = (
        "The quick brown fox jumps over the lazy dog. "
        "Containers are lightweight virtualization units. "
        "Virtual machines emulate full hardware environments. "
    )
    reps = max(1, target_words // len(base.split()))
    return (base * reps).strip() + "\n\nSummarize the above in one sentence."


def run_escalating_context(url, model_name):
    """Increase prompt size until model fails. Returns list of results."""
    word_counts = [50, 100, 250, 500, 1000, 2000, 4000]
    results = []
    failure_boundary = None

    print("\n--- Test 1: Escalating Context Size ---")
    for wc in word_counts:
        prompt = _build_long_prompt(wc)
        prompt_chars = len(prompt)
        print(f"  Input ~{wc} words ({prompt_chars} chars)... ", end="", flush=True)

        r = _infer(url, model_name, prompt, num_predict=64, timeout=RESPONSE_TIMEOUT_S)
        r["input_words_approx"] = wc
        r["input_chars"]        = prompt_chars
        results.append(r)

        if r["success"] and not r["empty_response"]:
            print(f"OK ({r['tokens_per_sec']:.1f} tok/s)")
        else:
            err = r.get("error_type", "unknown")
            print(f"FAIL [{err}]")
            if failure_boundary is None:
                failure_boundary = wc
            # Don't stop — continue to see if it recovers
    return results, failure_boundary


# ---------------------------------------------------------------------------
# Test 2 — Rapid sequential burst
# ---------------------------------------------------------------------------

def run_burst(url, model_name, n=20):
    """Fire n requests back-to-back, no delay. Record failures and latency."""
    prompt = "What is 2+2? Answer in one word."
    results = []

    print(f"\n--- Test 2: Rapid Sequential Burst ({n} requests) ---")
    for i in range(n):
        r = _infer(url, model_name, prompt, num_predict=16, timeout=60)
        results.append(r)
        status = f"{r['tokens_per_sec']:.1f} tok/s" if r["success"] else f"FAIL [{r.get('error_type')}]"
        print(f"  [{i+1:2d}/{n}] {status}")

    successful = [r for r in results if r["success"] and not r.get("empty_response")]
    failed     = [r for r in results if not r["success"] or r.get("empty_response")]
    tps_list   = [r["tokens_per_sec"] for r in successful]

    return {
        "total":        n,
        "successful":   len(successful),
        "failed":       len(failed),
        "success_rate": round(len(successful) / n * 100, 1),
        "error_types":  [r.get("error_type") for r in failed],
        "avg_tps":      round(statistics.mean(tps_list), 2) if tps_list else 0,
        "min_tps":      round(min(tps_list), 2) if tps_list else 0,
        "max_tps":      round(max(tps_list), 2) if tps_list else 0,
        "runs":         results,
    }


# ---------------------------------------------------------------------------
# Test 3 — Max output generation
# ---------------------------------------------------------------------------

def run_max_output(url, model_name):
    """Request a very long output and check for degradation or failure."""
    prompt = (
        "Write a comprehensive essay about containerization technology, "
        "covering Docker, Kubernetes, microservices, and deployment best practices. "
        "Be thorough and detailed."
    )
    num_predict_values = [256, 512, 1024, 2048]
    results = []

    print("\n--- Test 3: Max Output Generation ---")
    for np in num_predict_values:
        print(f"  num_predict={np}... ", end="", flush=True)
        r = _infer(url, model_name, prompt, num_predict=np, timeout=RESPONSE_TIMEOUT_S)
        r["num_predict"] = np
        results.append(r)

        if r["success"]:
            print(f"OK — {r['eval_tokens']} tokens at {r['tokens_per_sec']:.1f} tok/s")
        else:
            print(f"FAIL [{r.get('error_type')}]")

    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def test_oom_detection(model_name, port=11434):
    host = os.environ.get("SLM_TEST_HOST", "localhost")
    url  = f"http://{host}:{port}/api/generate"

    results = {
        "model":     model_name,
        "port":      port,
        "timestamp": time.time(),
        "thresholds": {
            "response_timeout_s":   RESPONSE_TIMEOUT_S,
            "empty_response_chars": EMPTY_RESPONSE_LIMIT,
            "tps_floor":            TPS_FLOOR,
        },
        "escalating_context": {},
        "burst":              {},
        "max_output":         {},
        "summary":            {},
    }

    print(f"\n{'='*60}")
    print(f"OOM DETECTION & BOUNDARY TEST: {model_name}")
    print(f"{'='*60}")

    # Test 1
    ctx_results, failure_boundary = run_escalating_context(url, model_name)
    results["escalating_context"] = {
        "failure_boundary_words": failure_boundary,
        "runs": ctx_results,
    }

    # Test 2
    results["burst"] = run_burst(url, model_name)

    # Test 3
    results["max_output"] = {"runs": run_max_output(url, model_name)}

    # --- Summary ---
    burst       = results["burst"]
    ctx_runs    = ctx_results
    max_runs    = results["max_output"]["runs"]

    successful_ctx = [r for r in ctx_runs if r["success"] and not r.get("empty_response")]
    failed_ctx     = [r for r in ctx_runs if not r["success"] or r.get("empty_response")]
    all_error_types = (
        [r.get("error_type") for r in failed_ctx if r.get("error_type")] +
        burst.get("error_types", []) +
        [r.get("error_type") for r in max_runs if not r.get("success") and r.get("error_type")]
    )

    results["summary"] = {
        "context_boundary_words":      failure_boundary,
        "context_max_success_words":   max((r["input_words_approx"] for r in successful_ctx), default=0),
        "burst_success_rate":          burst["success_rate"],
        "burst_avg_tps":               burst["avg_tps"],
        "max_output_failures":         sum(1 for r in max_runs if not r.get("success")),
        "observed_error_types":        list(set(t for t in all_error_types if t)),
        "overall_stable":              failure_boundary is None and burst["success_rate"] >= 90,
    }

    s = results["summary"]
    print(f"\n{'='*60}")
    print(f"OOM / BOUNDARY SUMMARY")
    print(f"{'='*60}")
    print(f"Context boundary:       {'no failure' if not failure_boundary else f'~{failure_boundary} words'}")
    print(f"Max stable context:     ~{s['context_max_success_words']} words")
    print(f"Burst success rate:     {s['burst_success_rate']}%")
    print(f"Burst avg TPS:          {s['burst_avg_tps']:.2f} tok/s")
    print(f"Max output failures:    {s['max_output_failures']} / {len(max_runs)}")
    print(f"Error types seen:       {s['observed_error_types'] or ['none']}")
    print(f"Overall stable:         {'YES' if s['overall_stable'] else 'NO'}")
    print(f"{'='*60}\n")

    output_file = RESULTS_DIR / f"oom_detection_{model_name.replace(':', '_')}_{int(time.time())}.json"
    try:
        with output_file.open("w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        print(f"Results saved to: {output_file}")
    except Exception as e:
        print(f"Warning: Could not save results: {e}")

    return 0 if results["summary"]["overall_stable"] else 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python oom_detection_test.py <model_name> [port]")
        sys.exit(1)

    model = sys.argv[1]
    port  = int(sys.argv[2]) if len(sys.argv) > 2 else 11434
    sys.exit(test_oom_detection(model, port))
