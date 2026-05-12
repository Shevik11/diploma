"""
comparative-plots.py — cross-model & cross-deployment comparison plots.

Reads the artifacts produced by the analysis pipeline:
    analysis/aggregated_metrics.json
    analysis/perf_by_deployment.json
    analysis/cost_per_model.json
and writes the following PNGs into ``analysis/charts/``:
    cmp_throughput_vs_quality.png    — scatter (cost × quality)
    cmp_throughput_by_deployment.png — grouped bar chart
    cmp_cost_vs_throughput.png       — scatter (price × speed)

Like ``generate-charts.py`` it depends on matplotlib only, exits cleanly
if it is missing, and is safe to re-run.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ANALYSIS_DIR = PROJECT_ROOT / "analysis"
DEFAULT_OUT_DIR = ANALYSIS_DIR / "charts"


def _require_matplotlib():
    try:
        import matplotlib  # noqa: F401
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt  # noqa: F401
        return matplotlib, plt
    except ImportError:
        print(
            "[warn] matplotlib not installed — skipping comparative plots.\n"
            "       install with: pip install matplotlib",
            file=sys.stderr,
        )
        return None, None


def _load(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def _to_float(v):
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def plot_throughput_vs_quality(plt, rows, out_path: Path) -> None:
    """Scatter: x = throughput (tok/s), y = quality (%) — labels per model."""
    by_model: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for r in rows:
        tps = _to_float(r.get("perf_avg_tok_per_s"))
        qual = _to_float(r.get("quality_score_pct"))
        if tps is None or qual is None:
            continue
        by_model[r.get("model") or "?"].append((tps, qual))

    if not by_model:
        return _placeholder(plt, out_path, "throughput vs quality — no data")

    fig = plt.figure(figsize=(9, 6))
    for model, points in by_model.items():
        xs, ys = zip(*points)
        plt.scatter(xs, ys, label=model, s=60, alpha=0.8)
        cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
        plt.text(cx, cy, model, fontsize=8, ha="left", va="bottom")
    plt.xlabel("Throughput, tokens/s")
    plt.ylabel("Quality score, %")
    plt.title("Quality vs throughput across runs")
    plt.grid(True, alpha=0.25)
    plt.legend(fontsize=8, loc="best")
    fig.savefig(out_path, bbox_inches="tight", dpi=120)
    plt.close(fig)


def plot_throughput_by_deployment(plt, by_dep: dict, out_path: Path) -> None:
    if not by_dep:
        return _placeholder(plt, out_path, "throughput by deployment — no data")

    labels, values = [], []
    for key, b in by_dep.items():
        v = b.get("tokens_per_sec", {}).get("median")
        if v is None:
            continue
        labels.append(f"{b['technology']}/{b['platform']}")
        values.append(v)

    if not values:
        return _placeholder(plt, out_path, "throughput by deployment — no data")

    fig = plt.figure(figsize=(8, 0.5 + 0.5 * len(labels)))
    plt.barh(labels[::-1], values[::-1])
    plt.xlabel("median tokens / s")
    plt.title("Median throughput by deployment")
    plt.tight_layout()
    fig.savefig(out_path, bbox_inches="tight", dpi=120)
    plt.close(fig)


def plot_cost_vs_throughput(plt, cost: list[dict], out_path: Path) -> None:
    if not cost:
        return _placeholder(plt, out_path, "cost vs throughput — no data")

    by_model: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for r in cost:
        tps = _to_float(r.get("tok_per_s"))
        usd_m = _to_float(r.get("usd_per_million_tokens_cloud"))
        if tps is None or usd_m is None or usd_m <= 0:
            continue
        by_model[r.get("model") or "?"].append((tps, usd_m))

    if not by_model:
        return _placeholder(plt, out_path, "cost vs throughput — no data")

    fig = plt.figure(figsize=(9, 6))
    for model, points in by_model.items():
        xs, ys = zip(*points)
        plt.scatter(xs, ys, label=model, s=60, alpha=0.8)
    plt.xlabel("Throughput, tokens/s")
    plt.ylabel("USD / 1M tokens (cloud)")
    plt.title("Cost vs throughput")
    plt.grid(True, alpha=0.25)
    plt.legend(fontsize=8, loc="best")
    fig.savefig(out_path, bbox_inches="tight", dpi=120)
    plt.close(fig)


def _placeholder(plt, path: Path, msg: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig = plt.figure(figsize=(8, 2))
    plt.text(0.5, 0.5, msg, ha="center", va="center", fontsize=12)
    plt.axis("off")
    fig.savefig(path, bbox_inches="tight", dpi=120)
    plt.close(fig)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--analysis-dir", default=str(ANALYSIS_DIR))
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    args = p.parse_args()

    matplotlib, plt = _require_matplotlib()
    if matplotlib is None:
        return 0

    a = Path(args.analysis_dir)
    rows = _load(a / "aggregated_metrics.json", [])
    by_dep = _load(a / "perf_by_deployment.json", {})
    cost = _load(a / "cost_per_model.json", [])

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    plot_throughput_vs_quality(plt, rows, out_dir / "cmp_throughput_vs_quality.png")
    plot_throughput_by_deployment(plt, by_dep, out_dir / "cmp_throughput_by_deployment.png")
    plot_cost_vs_throughput(plt, cost, out_dir / "cmp_cost_vs_throughput.png")

    print(f"Comparative plots written to: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
