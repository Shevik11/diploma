"""
generate-charts.py — produce per-model summary charts (PNG).

Generates the following PNG figures into ``analysis/charts/``:
    chart_throughput_by_model.png
    chart_latency_by_model.png
    chart_quality_by_model.png

Each figure is a horizontal bar chart of the median value across all
configurations for that model.  Uses matplotlib only.

Designed to be safe to call repeatedly:
    * if matplotlib is missing, the script prints an instructive error
      and exits with status 0 (so CI pipelines do not fail).
    * if there is no input data, an empty placeholder image is still
      created so downstream consumers do not have missing files.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_INPUT = PROJECT_ROOT / "analysis" / "perf_per_model.json"
DEFAULT_OUT_DIR = PROJECT_ROOT / "analysis" / "charts"


def _require_matplotlib():
    try:
        import matplotlib  # noqa: F401
        matplotlib.use("Agg")  # headless backend
        import matplotlib.pyplot as plt  # noqa: F401
        return matplotlib, plt
    except ImportError:
        print(
            "[warn] matplotlib not installed — skipping chart generation.\n"
            "       install with: pip install matplotlib",
            file=sys.stderr,
        )
        return None, None


def _bar_chart(plt, models, values, title, x_label, out_path: Path,
               value_format=None):
    """Horizontal bar chart, models sorted by value descending."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pairs = [(m, v) for m, v in zip(models, values) if v is not None]
    if not pairs:
        # Empty placeholder
        fig = plt.figure(figsize=(8, 1.5))
        plt.text(0.5, 0.5, "no data", ha="center", va="center", fontsize=14)
        plt.axis("off")
        fig.savefig(out_path, bbox_inches="tight", dpi=120)
        plt.close(fig)
        return

    pairs.sort(key=lambda p: p[1], reverse=True)
    labels, vals = zip(*pairs)
    fig = plt.figure(figsize=(9, 0.5 + 0.4 * len(labels)))
    bars = plt.barh(labels[::-1], list(vals)[::-1])
    plt.title(title)
    plt.xlabel(x_label)
    for bar, v in zip(bars, list(vals)[::-1]):
        plt.text(
            bar.get_width(),
            bar.get_y() + bar.get_height() / 2,
            (value_format(v) if value_format else f"{v:.2f}"),
            va="center",
            ha="left",
            fontsize=8,
        )
    plt.tight_layout()
    fig.savefig(out_path, bbox_inches="tight", dpi=120)
    plt.close(fig)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", default=str(DEFAULT_INPUT))
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    args = p.parse_args()

    matplotlib, plt = _require_matplotlib()
    if matplotlib is None:
        return 0

    src = Path(args.input)
    if not src.exists():
        print(f"[error] input not found: {src}", file=sys.stderr)
        print("        run performance-analyzer.py first", file=sys.stderr)
        return 2

    data = json.loads(src.read_text(encoding="utf-8"))
    out_dir = Path(args.out_dir)

    models = list(data.keys())
    median_tps = [data[m]["tokens_per_sec"]["median"] for m in models]
    median_lat = [data[m]["latency_ms"]["median"] for m in models]
    quality = [data[m]["quality_pct"]["mean"] for m in models]

    _bar_chart(
        plt, models, median_tps,
        "Median throughput per model",
        "tokens / second",
        out_dir / "chart_throughput_by_model.png",
        value_format=lambda v: f"{v:.1f}",
    )
    _bar_chart(
        plt, models, median_lat,
        "Median per-prompt latency per model",
        "milliseconds",
        out_dir / "chart_latency_by_model.png",
        value_format=lambda v: f"{v:.0f} ms",
    )
    _bar_chart(
        plt, models, quality,
        "Average quality score per model",
        "score (%)",
        out_dir / "chart_quality_by_model.png",
        value_format=lambda v: f"{v:.1f}%",
    )

    print(f"Charts written to: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
