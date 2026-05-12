"""
performance-analyzer.py — Phase-3 of the diploma pipeline.

Consumes the tidy CSV produced by ``metrics-aggregator.py`` and computes
performance statistics that go into the dissertation tables and figures:

  * per-model summary (avg / median / p95 of throughput, latency, TTFT,
    quality, success rate)
  * per-(deployment × technology) breakdown
  * pairwise speed-up ratios (e.g. docker vs vm)

Outputs three artifacts:
  analysis/perf_per_model.json
  analysis/perf_by_deployment.json
  analysis/perf_speedups.json

The script intentionally avoids pandas — only the standard library is
used, so it runs in any Python 3.10+ environment.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_INPUT = PROJECT_ROOT / "analysis" / "aggregated_metrics.csv"
DEFAULT_OUT_DIR = PROJECT_ROOT / "analysis"

# Numeric columns we care about. Strings come from the CSV and need parsing.
_NUMERIC_COLS = (
    "perf_avg_tok_per_s",
    "perf_avg_latency_ms",
    "perf_avg_ttft_ms",
    "perf_success_rate",
    "quality_score_pct",
    "advanced_quality_score_pct",
    "hard_tests_score_pct",
    "multilingual_score_pct",
    "summarization_score_pct",
    "context_window_score_pct",
    "safety_robustness_score_pct",
    "consistency_pct",
    "stress_success_rate",
    "stress_throughput_rps",
    "cost_avg_tok_per_s",
)


def _to_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        f = float(v)
        return f if not math.isnan(f) else None
    except (TypeError, ValueError):
        return None


def load_rows(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        for c in _NUMERIC_COLS:
            r[c] = _to_float(r.get(c))
    return rows


def _stat_block(values: Iterable[float | None]) -> dict[str, float | None]:
    xs = [v for v in values if v is not None]
    if not xs:
        return {"n": 0, "mean": None, "median": None, "min": None,
                "max": None, "p95": None, "std": None}
    xs_sorted = sorted(xs)
    p95_idx = max(0, math.ceil(0.95 * len(xs_sorted)) - 1)
    return {
        "n": len(xs),
        "mean": round(statistics.fmean(xs), 4),
        "median": round(statistics.median(xs), 4),
        "min": round(min(xs), 4),
        "max": round(max(xs), 4),
        "p95": round(xs_sorted[p95_idx], 4),
        "std": round(statistics.pstdev(xs), 4) if len(xs) > 1 else 0.0,
    }


def per_model_summary(rows: list[dict]) -> dict[str, dict]:
    by_model: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r.get("model"):
            by_model[r["model"]].append(r)

    out: dict[str, dict] = {}
    for model, group in sorted(by_model.items()):
        out[model] = {
            "configurations": len(group),
            "tokens_per_sec": _stat_block(r["perf_avg_tok_per_s"] for r in group),
            "latency_ms":     _stat_block(r["perf_avg_latency_ms"] for r in group),
            "ttft_ms":        _stat_block(r["perf_avg_ttft_ms"] for r in group),
            "success_rate":   _stat_block(r["perf_success_rate"] for r in group),
            "quality_pct":    _stat_block(r["quality_score_pct"] for r in group),
            "hard_tests_pct": _stat_block(r["hard_tests_score_pct"] for r in group),
            "multilingual_pct": _stat_block(r["multilingual_score_pct"] for r in group),
            "consistency_pct":  _stat_block(r["consistency_pct"] for r in group),
            "stress_success":   _stat_block(r["stress_success_rate"] for r in group),
        }
    return out


def by_deployment(rows: list[dict]) -> dict[str, dict]:
    by_key: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        key = (r.get("technology") or "?", r.get("platform") or "?")
        by_key[key].append(r)

    out: dict[str, dict] = {}
    for (tech, plat), group in sorted(by_key.items()):
        bucket_id = f"{tech}__{plat}"
        out[bucket_id] = {
            "technology": tech,
            "platform": plat,
            "configurations": len(group),
            "tokens_per_sec": _stat_block(r["perf_avg_tok_per_s"] for r in group),
            "latency_ms":     _stat_block(r["perf_avg_latency_ms"] for r in group),
            "success_rate":   _stat_block(r["perf_success_rate"] for r in group),
        }
    return out


def speedups(rows: list[dict]) -> list[dict]:
    """Pairwise (technology × platform) speed-ups for the same model+RAM+CPU.

    For every (model, RAM, CPU) cell we have a number of (tech, platform)
    measurements; the speed-up is the ratio of throughputs.  Only pairs
    where both sides are present are reported.
    """
    by_cell: dict[tuple, dict[tuple, float]] = defaultdict(dict)
    for r in rows:
        if not r.get("perf_avg_tok_per_s"):
            continue
        cell = (r.get("model"), r.get("ram_gb"), r.get("cpu_cores"))
        bucket = (r.get("technology"), r.get("platform"))
        # Keep the best throughput per bucket (handles duplicate runs).
        prev = by_cell[cell].get(bucket)
        if prev is None or r["perf_avg_tok_per_s"] > prev:
            by_cell[cell][bucket] = r["perf_avg_tok_per_s"]

    out: list[dict] = []
    for cell, buckets in by_cell.items():
        keys = list(buckets.keys())
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                a, b = keys[i], keys[j]
                va, vb = buckets[a], buckets[b]
                if va > 0 and vb > 0:
                    out.append({
                        "model": cell[0],
                        "ram_gb": cell[1],
                        "cpu_cores": cell[2],
                        "a": f"{a[0]}/{a[1]}",
                        "b": f"{b[0]}/{b[1]}",
                        "a_tok_per_s": va,
                        "b_tok_per_s": vb,
                        "speedup_a_over_b": round(va / vb, 3),
                    })
    return sorted(out, key=lambda r: -r["speedup_a_over_b"])


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", default=str(DEFAULT_INPUT))
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    args = p.parse_args()

    inp = Path(args.input)
    if not inp.exists():
        print(f"[error] input not found: {inp}", file=sys.stderr)
        print("        run metrics-aggregator.py first", file=sys.stderr)
        return 2

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = load_rows(inp)
    if not rows:
        print("[warn] no rows found in input")
        return 0

    per_model = per_model_summary(rows)
    by_dep = by_deployment(rows)
    speed = speedups(rows)

    (out_dir / "perf_per_model.json").write_text(
        json.dumps(per_model, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (out_dir / "perf_by_deployment.json").write_text(
        json.dumps(by_dep, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (out_dir / "perf_speedups.json").write_text(
        json.dumps(speed, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"Models analyzed:        {len(per_model)}")
    print(f"Deployment buckets:     {len(by_dep)}")
    print(f"Speed-up comparisons:   {len(speed)}")
    print(f"Wrote results to:       {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
