"""
Quantization Comparison Test
============================
Compares two or more quantization variants of the same base model on speed,
memory footprint and quality of output.

Thesis mapping
--------------
§2.1  Model table explicitly lists "GGUF Q4/Q8" variants for Phi-3.5, Llama 3.2
       etc. — the thesis needs to report the Q4-vs-Q8 trade-off.
§4.1  Uses the same TTFT / TPS / load thresholds to judge each variant.
§4.2  Uses psutil to capture the RAM delta between variants (proxy for the
       weight-file size difference between quantizations).

Method
------
1.  Accept two Ollama tags (e.g. `phi3:3.8b-mini-4k-instruct-q4_K_M` vs
    `...-q8_0`), or auto-derive a Q4+Q8 pair from a single base tag if
    common suffixes exist.
2.  For each variant:
    a.  Evict model (keep_alive=0) to force a cold reload.
    b.  Run a fixed prompt set (3 prompts × 2 runs = 6 samples) identical
        across variants so numbers are comparable.
    c.  Capture TTFT, TPS, wall time, eval_count and psutil RAM delta.
3.  Quality evaluation: score each response using the same rubric as
    `quality_test.py` — keyword presence + length sanity — and produce a
    per-variant quality_score in [0..1].
4.  Emit a pair-wise diff: Δ TPS, Δ RAM, Δ quality.
5.  Save JSON report.

Usage
-----
  python quantization_compare_test.py <base_model> [port]
  python quantization_compare_test.py <base_model> [port] --variants tagA,tagB[,tagC]
"""

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

import requests

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

RESULTS_DIR = Path(__file__).parent.parent.parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

REQUEST_TIMEOUT_S = 240

# Identical evaluation set across variants for an apples-to-apples comparison.
EVAL_PROMPTS = [
    {
        "prompt": "What is the capital of France? Answer in one word.",
        "expected_keywords": ["Paris"],
        "min_tokens": 1, "max_tokens": 8,
    },
    {
        "prompt": "Write a Python function `add(a, b)` that returns a + b. Only code.",
        "expected_keywords": ["def", "add", "return"],
        "min_tokens": 8, "max_tokens": 80,
    },
    {
        "prompt": "In 2 sentences, explain what Docker is.",
        "expected_keywords": ["container"],
        "min_tokens": 15, "max_tokens": 120,
    },
]


def _derive_pair(base_tag: str) -> list[str]:
    """
    Given a single Ollama tag, try to pair it with a common quant sibling.
    Strategy: if tag contains 'q4' → add 'q8' sibling and vice-versa.
    Always include the original tag first.
    """
    variants = [base_tag]
    low = base_tag.lower()
    if "q4" in low:
        variants.append(base_tag.replace("q4", "q8").replace("Q4", "Q8"))
    elif "q8" in low:
        variants.append(base_tag.replace("q8", "q4").replace("Q8", "Q4"))
    return variants


def _evict(host: str, port: int, model: str):
    try:
        requests.post(
            f"http://{host}:{port}/api/generate",
            json={"model": model, "prompt": "", "keep_alive": 0},
            timeout=20,
        )
    except Exception:
        pass


def _infer(host, port, model, prompt):
    t0 = time.time()
    try:
        r = requests.post(
            f"http://{host}:{port}/api/generate",
            json={
                "model": model, "prompt": prompt, "stream": False,
                "keep_alive": "5m",
                "options": {"num_predict": 160, "temperature": 0.1},
            },
            timeout=REQUEST_TIMEOUT_S,
        )
        r.raise_for_status()
        d = r.json()
        eval_s = d.get("eval_duration", 0) / 1e9
        tps = d.get("eval_count", 0) / eval_s if eval_s > 0 else 0
        return {
            "success":         True,
            "wall_time_s":     round(time.time() - t0, 3),
            "ttft_s":          round((d.get("load_duration", 0) + d.get("prompt_eval_duration", 0)) / 1e9, 3),
            "load_duration_s": round(d.get("load_duration", 0) / 1e9, 3),
            "tokens_per_sec":  round(tps, 2),
            "eval_tokens":     d.get("eval_count", 0),
            "response":        d.get("response", "").strip(),
        }
    except Exception as e:
        return {
            "success": False,
            "wall_time_s": round(time.time() - t0, 3),
            "error": str(e),
        }


def _score_quality(response: str, expected_keywords: list[str], min_tokens: int, max_tokens: int) -> dict:
    if not response:
        return {"score": 0.0, "reasons": ["empty"]}
    tokens = len(response.split())
    kw_hits = sum(1 for kw in expected_keywords if kw.lower() in response.lower())
    kw_score = kw_hits / max(1, len(expected_keywords))
    len_ok = 1.0 if min_tokens <= tokens <= max_tokens else 0.5 if tokens >= min_tokens else 0.0
    score = round(0.7 * kw_score + 0.3 * len_ok, 3)
    return {
        "score": score,
        "kw_hits": kw_hits,
        "kw_total": len(expected_keywords),
        "tokens": tokens,
        "len_ok": len_ok == 1.0,
    }


def _ram_mb():
    return round(psutil.virtual_memory().used / 1024 / 1024, 1) if PSUTIL_AVAILABLE else None


def _run_variant(host: str, port: int, variant: str) -> dict:
    print(f"\n── {variant} {'─'*(56 - len(variant))}")
    _evict(host, port, variant)
    time.sleep(3)
    ram_before = _ram_mb()

    per_prompt = []
    for p_idx, item in enumerate(EVAL_PROMPTS, 1):
        for run_idx in (1, 2):
            res = _infer(host, port, variant, item["prompt"])
            quality = _score_quality(
                res.get("response", ""),
                item["expected_keywords"], item["min_tokens"], item["max_tokens"],
            ) if res.get("success") else {"score": 0.0}
            per_prompt.append({
                "prompt_idx": p_idx,
                "run":        run_idx,
                "cold":       (run_idx == 1 and p_idx == 1),
                "inference":  {k: v for k, v in res.items() if k != "response"},
                "quality":    quality,
                "response_preview": (res.get("response") or "")[:80],
            })
            mark = "OK" if res.get("success") else "FAIL"
            print(f"  [{p_idx}.{run_idx}] {mark}  "
                  f"tps={res.get('tokens_per_sec')}  "
                  f"ttft={res.get('ttft_s')}s  q={quality['score']}")

    ram_after = _ram_mb()
    successful = [p for p in per_prompt if p["inference"].get("success")]
    tps_vals = [p["inference"]["tokens_per_sec"] for p in successful if p["inference"].get("tokens_per_sec", 0) > 0]
    ttft_vals = [p["inference"]["ttft_s"] for p in successful]
    load_vals = [p["inference"].get("load_duration_s", 0) for p in successful]
    q_vals = [p["quality"]["score"] for p in successful]

    summary = {
        "successful_calls": len(successful),
        "total_calls":      len(per_prompt),
        "avg_tps":          round(statistics.mean(tps_vals), 2) if tps_vals else 0,
        "median_tps":       round(statistics.median(tps_vals), 2) if tps_vals else 0,
        "avg_ttft_s":       round(statistics.mean(ttft_vals), 3) if ttft_vals else 0,
        "max_load_s":       round(max(load_vals), 3) if load_vals else 0,
        "avg_quality":      round(statistics.mean(q_vals), 3) if q_vals else 0,
        "ram_before_mb":    ram_before,
        "ram_after_mb":     ram_after,
        "ram_delta_mb":     round(ram_after - ram_before, 1) if (ram_before and ram_after) else None,
    }
    print(f"  → avg_tps={summary['avg_tps']}  avg_ttft={summary['avg_ttft_s']}s  "
          f"avg_quality={summary['avg_quality']}  ΔRAM={summary['ram_delta_mb']}MB")
    return {"variant": variant, "per_prompt": per_prompt, "summary": summary}


def run_quant_compare(base_model: str, port: int = 11434, variants: list[str] | None = None) -> int:
    host = os.environ.get("SLM_TEST_HOST", "localhost")
    if not variants:
        variants = _derive_pair(base_model)

    # De-dup while preserving order
    seen, uniq = set(), []
    for v in variants:
        if v not in seen:
            seen.add(v); uniq.append(v)
    variants = uniq

    print(f"\n{'='*62}\n  QUANTIZATION COMPARE — {base_model}\n{'='*62}")
    print(f"  Variants: {variants}")

    per_variant_results = []
    for v in variants:
        try:
            per_variant_results.append(_run_variant(host, port, v))
        except Exception as e:
            per_variant_results.append({
                "variant": v,
                "error": str(e),
                "summary": {"successful_calls": 0},
            })

    # ── pair-wise diffs (first vs rest) ──────────────────────────────────────
    pair_diffs = []
    usable = [r for r in per_variant_results if r.get("summary", {}).get("successful_calls", 0) > 0]
    if len(usable) >= 2:
        base = usable[0]["summary"]
        for other in usable[1:]:
            o = other["summary"]
            pair_diffs.append({
                "from":              usable[0]["variant"],
                "to":                other["variant"],
                "delta_tps":         round(o["avg_tps"] - base["avg_tps"], 2),
                "delta_ttft_s":      round(o["avg_ttft_s"] - base["avg_ttft_s"], 3),
                "delta_quality":    round(o["avg_quality"] - base["avg_quality"], 3),
                "delta_ram_mb":     (round(o["ram_delta_mb"] - base["ram_delta_mb"], 1)
                                     if base.get("ram_delta_mb") is not None
                                     and o.get("ram_delta_mb") is not None else None),
                "speed_ratio":      (round(o["avg_tps"] / base["avg_tps"], 3)
                                     if base["avg_tps"] > 0 else None),
            })

    # ── winners ─────────────────────────────────────────────────────────────
    winners = {}
    if usable:
        winners["fastest"] = max(usable, key=lambda r: r["summary"]["avg_tps"])["variant"]
        winners["best_quality"] = max(usable, key=lambda r: r["summary"]["avg_quality"])["variant"]
        winners["lowest_ttft"] = min(usable, key=lambda r: r["summary"]["avg_ttft_s"])["variant"]

    results = {
        "base_model":  base_model,
        "port":        port,
        "timestamp":   time.time(),
        "variants":    variants,
        "per_variant": per_variant_results,
        "pair_diffs":  pair_diffs,
        "winners":     winners,
    }

    print(f"\n{'='*62}\n  SUMMARY\n{'='*62}")
    for r in per_variant_results:
        s = r.get("summary", {})
        print(f"  {r['variant']:<40} tps={s.get('avg_tps')}  q={s.get('avg_quality')}  "
              f"ΔRAM={s.get('ram_delta_mb')}MB")
    for d in pair_diffs:
        print(f"  {d['from']} → {d['to']}: Δtps={d['delta_tps']}  Δq={d['delta_quality']}  "
              f"ΔRAM={d['delta_ram_mb']}MB  speed×={d['speed_ratio']}")
    if winners:
        print(f"  Winners: fastest={winners.get('fastest')} | "
              f"best_quality={winners.get('best_quality')} | "
              f"lowest_ttft={winners.get('lowest_ttft')}")

    safe = base_model.replace(":", "_").replace("/", "_")
    out = RESULTS_DIR / f"quant_compare_{safe}_{int(time.time())}.json"
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n  Saved → {out}\n")
    return 0 if usable else 1


def _parse_args():
    p = argparse.ArgumentParser(description="Quantization compare — §2.1")
    p.add_argument("model_name", help="Base Ollama tag, e.g. phi3:mini")
    p.add_argument("port", nargs="?", type=int, default=11434)
    p.add_argument("--variants", default=None,
                   help="Comma-separated list of explicit variant tags. "
                        "If omitted, auto-derives a Q4/Q8 pair from base tag.")
    return p.parse_args()


if __name__ == "__main__":
    a = _parse_args()
    vs = [v.strip() for v in a.variants.split(",")] if a.variants else None
    sys.exit(run_quant_compare(a.model_name, a.port, vs))
