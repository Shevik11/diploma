"""
Cloud Cost Calculator
=====================
Translates measured inference speed (TPS) into self-hosted $/1M-token cost for
each cloud instance from §6.1 of diploma_plan.md, and compares against the
§6.2 paid-API prices.

Thesis mapping
--------------
§6.1  Cloud instance prices (t3.medium / t3.large / t3.xlarge / g4dn.xlarge)
§6.2  API prices (GPT-4o mini, Claude 3 Haiku, Gemini 1.5 Flash)
§6    Cost analysis: self-hosted vs API

Method
------
1.  Run a short / medium / long probe against the model and measure TPS.
2.  For each cloud tier that fits the measured RAM footprint, compute:
       cost_per_1M_output_tok = ($/h) / (3600 * TPS) * 1_000_000
3.  Pick the cheapest tier the model actually fits into.
4.  Compare self-hosted $/1M vs each API price from §6.2 to compute
    break-even token volume (tokens/month where self-hosting becomes cheaper).

Input
-----
  python cloud_cost_calculator.py <model_name> [port] [--ram-gb N]

`--ram-gb` overrides the measured peak; otherwise the script samples psutil
during inference to approximate the footprint (for self-hosting sizing).
"""

import argparse
import json
import os
import statistics
import sys
import threading
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

# ── §6.1 price table (mid-point of the cited $/h ranges) ─────────────────────
# Values are USD/hour for comparable on-demand pricing circa 2024-2025.
CLOUD_TIERS = [
    {"name": "t3.medium",   "vcpu": 2, "ram_gb": 4,  "gpu_gb": 0, "usd_per_hour": 0.05,  "provider": "AWS"},
    {"name": "e2-medium",   "vcpu": 2, "ram_gb": 4,  "gpu_gb": 0, "usd_per_hour": 0.05,  "provider": "GCP"},
    {"name": "t3.large",    "vcpu": 2, "ram_gb": 8,  "gpu_gb": 0, "usd_per_hour": 0.10,  "provider": "AWS"},
    {"name": "e2-standard-2", "vcpu": 2, "ram_gb": 8, "gpu_gb": 0, "usd_per_hour": 0.10, "provider": "GCP"},
    {"name": "t3.xlarge",   "vcpu": 4, "ram_gb": 16, "gpu_gb": 0, "usd_per_hour": 0.19,  "provider": "AWS"},
    {"name": "e2-standard-4", "vcpu": 4, "ram_gb": 16, "gpu_gb": 0, "usd_per_hour": 0.19, "provider": "GCP"},
    {"name": "g4dn.xlarge", "vcpu": 4, "ram_gb": 16, "gpu_gb": 16, "usd_per_hour": 0.85, "provider": "AWS"},
    {"name": "n1+T4",       "vcpu": 4, "ram_gb": 15, "gpu_gb": 16, "usd_per_hour": 0.60, "provider": "GCP"},
]

# ── §6.2 API prices (USD per 1M output tokens) ───────────────────────────────
API_PRICES = {
    "GPT-4o mini":       0.60,
    "Claude 3 Haiku":    1.25,
    "Gemini 1.5 Flash":  0.30,
}

PROMPTS = {
    "short":  "What is Docker? Answer in one sentence.",
    "medium": "Write a Python function that sorts a list using bubble sort.",
    "long": (
        "Explain in detail the differences between containers and virtual machines. "
        "Cover isolation, resource usage, startup time, portability, and typical use cases. "
        "Give a concrete recommendation for when to use each."
    ),
}


def _sample_ram_mb():
    if not PSUTIL_AVAILABLE:
        return None
    return psutil.virtual_memory().used / 1024 / 1024


class _RamSampler(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self._stop_event = threading.Event()
        self.samples = []

    def run(self):
        while not self._stop_event.is_set():
            v = _sample_ram_mb()
            if v is not None:
                self.samples.append(v)
            self._stop_event.wait(0.5)

    def stop(self):
        self._stop_event.set()
        self.join(timeout=3)


def _infer(url, model, prompt):
    t0 = time.time()
    try:
        r = requests.post(url, json={
            "model": model, "prompt": prompt, "stream": False,
            "keep_alive": "5m",
            "options": {"num_predict": 256, "temperature": 0.1},
        }, timeout=300)
        r.raise_for_status()
        d = r.json()
        eval_s = d.get("eval_duration", 0) / 1e9
        tps = d.get("eval_count", 0) / eval_s if eval_s > 0 else 0
        return {
            "success": True,
            "wall_time_s": round(time.time() - t0, 3),
            "tokens_per_sec": round(tps, 2),
            "eval_tokens": d.get("eval_count", 0),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def _cost_per_1m_tokens(usd_per_hour: float, tps: float) -> float:
    if tps <= 0:
        return float("inf")
    # tokens/hour = TPS * 3600  →  $/1M = usd_per_hour / tokens_per_hour * 1e6
    return usd_per_hour / (tps * 3600) * 1_000_000


def run_cost_calc(model_name: str, port: int = 11434, ram_gb_override: float | None = None) -> int:
    host = os.environ.get("SLM_TEST_HOST", "localhost")
    url = f"http://{host}:{port}/api/generate"

    print(f"\n{'='*62}\n  CLOUD COST CALCULATOR — {model_name}\n{'='*62}")

    sampler = _RamSampler()
    baseline_ram = _sample_ram_mb()
    sampler.start()

    per_prompt = []
    try:
        for key, prompt in PROMPTS.items():
            res = _infer(url, model_name, prompt)
            per_prompt.append({"prompt_key": key, **res})
            status = "OK" if res.get("success") else "FAIL"
            print(f"  [{key:<6}] {status}  tps={res.get('tokens_per_sec')}  tokens={res.get('eval_tokens')}")
    finally:
        sampler.stop()

    speeds = [p["tokens_per_sec"] for p in per_prompt if p.get("success") and p.get("tokens_per_sec", 0) > 0]
    if not speeds:
        print("\n  ERROR: No successful inferences; cannot derive cost.")
        return 1

    avg_tps = statistics.mean(speeds)
    median_tps = statistics.median(speeds)

    if ram_gb_override is not None:
        footprint_gb = ram_gb_override
        ram_source = "override"
    elif sampler.samples and baseline_ram is not None:
        peak_used = max(sampler.samples)
        footprint_gb = round((peak_used - baseline_ram) / 1024, 2) if peak_used > baseline_ram else round(peak_used / 1024, 2)
        ram_source = "measured_delta"
    else:
        footprint_gb = 4.0
        ram_source = "default_assumption"

    print(f"\n  Avg TPS    : {avg_tps:.2f} tok/s")
    print(f"  Median TPS : {median_tps:.2f} tok/s")
    print(f"  RAM need   : ~{footprint_gb} GB ({ram_source})")

    # ── self-hosted costs per tier ───────────────────────────────────────────
    tier_costs = []
    for tier in CLOUD_TIERS:
        fits = tier["ram_gb"] >= max(footprint_gb, 1.0)
        cost_median = _cost_per_1m_tokens(tier["usd_per_hour"], median_tps)
        cost_avg    = _cost_per_1m_tokens(tier["usd_per_hour"], avg_tps)
        tier_costs.append({
            **tier,
            "fits_model":                 fits,
            "usd_per_1m_tok_at_median":   round(cost_median, 4),
            "usd_per_1m_tok_at_avg":      round(cost_avg, 4),
        })

    fitting = [t for t in tier_costs if t["fits_model"] and t["gpu_gb"] == 0]
    cheapest = min(fitting, key=lambda t: t["usd_per_1m_tok_at_median"]) if fitting else None

    # ── API comparison: break-even ───────────────────────────────────────────
    api_comparison = []
    if cheapest:
        hosted = cheapest["usd_per_1m_tok_at_median"]
        monthly_hours = 24 * 30  # always-on
        monthly_cost_hosted = cheapest["usd_per_hour"] * monthly_hours
        for api_name, api_price in API_PRICES.items():
            # break-even tokens/month = monthly_cost_hosted / api_price * 1M
            be_tokens = (monthly_cost_hosted / api_price) * 1_000_000 if api_price > 0 else 0
            api_comparison.append({
                "api":                     api_name,
                "usd_per_1m_tok_api":      api_price,
                "usd_per_1m_tok_hosted":   hosted,
                "self_host_cheaper":       hosted < api_price,
                "break_even_tokens_per_month": int(be_tokens),
                "monthly_hosted_cost":     round(monthly_cost_hosted, 2),
            })

    results = {
        "model":      model_name,
        "port":       port,
        "timestamp":  time.time(),
        "measurement": {
            "avg_tps":       round(avg_tps, 2),
            "median_tps":    round(median_tps, 2),
            "ram_footprint_gb": footprint_gb,
            "ram_source":    ram_source,
            "per_prompt":    per_prompt,
        },
        "cloud_tiers":      tier_costs,
        "cheapest_fitting": cheapest,
        "api_comparison":   api_comparison,
    }

    print(f"\n  ── Self-hosted $/1M output tokens (median TPS) ─────────")
    for t in tier_costs:
        mark = "✓" if t["fits_model"] else "✗"
        gpu = f"+{t['gpu_gb']}GB GPU" if t["gpu_gb"] else "         "
        print(f"   {mark} {t['name']:<16} {t['vcpu']}c/{t['ram_gb']:>2}GB {gpu}  "
              f"${t['usd_per_1m_tok_at_median']:.3f}/1M")

    if cheapest:
        print(f"\n  Cheapest fitting tier: {cheapest['name']} — "
              f"${cheapest['usd_per_1m_tok_at_median']:.3f}/1M vs API:")
        for api in api_comparison:
            verdict = "cheaper to self-host" if api["self_host_cheaper"] else f"cheaper via API (BE: {api['break_even_tokens_per_month']:,} tok/mo)"
            print(f"    {api['api']:<18} ${api['usd_per_1m_tok_api']:.2f}/1M — {verdict}")

    out = RESULTS_DIR / f"cloud_cost_{model_name.replace(':','_')}_{int(time.time())}.json"
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n  Saved → {out}\n")
    return 0


def _parse_args():
    p = argparse.ArgumentParser(description="Cloud cost calculator — §6")
    p.add_argument("model_name")
    p.add_argument("port", nargs="?", type=int, default=11434)
    p.add_argument("--ram-gb", type=float, default=None,
                   help="Override RAM footprint in GB (skip measurement)")
    return p.parse_args()


if __name__ == "__main__":
    a = _parse_args()
    sys.exit(run_cost_calc(a.model_name, a.port, a.ram_gb))
