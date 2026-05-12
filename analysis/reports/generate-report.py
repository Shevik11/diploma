"""
generate-report.py — final stage of the diploma analysis pipeline.

Reads the artifacts produced by the earlier scripts:
  analysis/aggregated_metrics.json
  analysis/perf_per_model.json
  analysis/perf_by_deployment.json
  analysis/perf_speedups.json
  analysis/cost_per_model.json
and produces a human-readable Markdown report at
  analysis/reports/report.md
plus a machine-readable summary at
  analysis/reports/report.json.

The report is intentionally short and dissertation-friendly: tables of
medians/p95s, a per-model "best deployment" recommendation, and a cost
ranking. Generation is purely deterministic — running the script twice
on the same inputs gives identical output.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ANALYSIS_DIR = PROJECT_ROOT / "analysis"
DEFAULT_OUT_MD = ANALYSIS_DIR / "reports" / "report.md"
DEFAULT_OUT_JSON = ANALYSIS_DIR / "reports" / "report.json"


def _load(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def _fmt(v, suffix: str = "", n: int = 2) -> str:
    if v is None or v == "":
        return "—"
    if isinstance(v, (int, float)):
        return f"{v:.{n}f}{suffix}"
    return str(v)


def _md_table(rows: list[list[str]], header: list[str]) -> str:
    if not rows:
        return "_no data_\n"
    sep = ["---"] * len(header)
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join(sep) + " |"]
    for r in rows:
        lines.append("| " + " | ".join(r) + " |")
    return "\n".join(lines) + "\n"


def render_overview(rows: list[dict]) -> str:
    n_total = len(rows)
    models = sorted({r.get("model") for r in rows if r.get("model")})
    techs = sorted({r.get("technology") for r in rows if r.get("technology")})
    plats = sorted({r.get("platform") for r in rows if r.get("platform")})

    return (
        f"- **Total runs:** {n_total}\n"
        f"- **Distinct models:** {len(models)} — {', '.join(models) or '—'}\n"
        f"- **Inference technologies:** {', '.join(techs) or '—'}\n"
        f"- **Deployment platforms:** {', '.join(plats) or '—'}\n"
    )


def _success_pct(v):
    """Some sources record success_rate as 0..1, others as 0..100. Normalise."""
    if not isinstance(v, (int, float)):
        return None
    return v if v > 1.5 else v * 100


def render_per_model(per_model: dict) -> str:
    rows = []
    for model, m in per_model.items():
        rows.append([
            f"`{model}`",
            str(m["configurations"]),
            _fmt(m["tokens_per_sec"]["median"], " tok/s"),
            _fmt(m["latency_ms"]["median"], " ms", 0),
            _fmt(m["ttft_ms"]["median"], " ms", 0),
            _fmt(_success_pct(m["success_rate"]["mean"]), "%", 1),
            _fmt(m["quality_pct"]["mean"], "%", 1),
            _fmt(m["consistency_pct"]["mean"], "%", 1),
        ])
    return _md_table(
        rows,
        ["Model", "Runs", "Median tok/s", "Median latency",
         "Median TTFT", "Success", "Quality", "Consistency"],
    )


def render_by_deployment(by_dep: dict) -> str:
    rows = []
    for key, b in by_dep.items():
        # Skip rows produced from older single-test files that don't carry
        # a (technology, platform) tag — they show up as "?/?" and have no
        # throughput/latency to report.
        if (b.get("technology") in (None, "?")
                and b.get("platform") in (None, "?")):
            continue
        rows.append([
            f"`{b['technology']}`/`{b['platform']}`",
            str(b["configurations"]),
            _fmt(b["tokens_per_sec"]["median"], " tok/s"),
            _fmt(b["latency_ms"]["median"], " ms", 0),
            _fmt(_success_pct(b["success_rate"]["mean"]), "%", 1),
        ])
    return _md_table(
        rows,
        ["Deployment", "Runs", "Median tok/s", "Median latency", "Success"],
    )


def render_cost(cost: list[dict], top_n: int = 10) -> str:
    if not cost:
        return "_no cost data — re-run after running benchmarks._\n"
    rows = []
    for r in cost[:top_n]:
        rows.append([
            f"`{r['model']}`",
            f"{r.get('ram_gb', '?')} GB / {r.get('cpu_cores', '?')} CPU",
            f"`{r.get('technology')}`/`{r.get('platform')}`",
            _fmt(r["tok_per_s"], " tok/s"),
            f"`{r.get('hw_profile') or '—'}`",
            f"${_fmt(r.get('usd_per_million_tokens_cloud'), '', 4)}",
            _fmt(r.get("tokens_per_usd_cloud"), "", 0),
        ])
    return _md_table(
        rows,
        ["Model", "Resources", "Deployment", "Throughput",
         "Cheapest fit", "USD / 1M tokens", "Tokens / USD"],
    )


def render_speedups(speed: list[dict], top_n: int = 10) -> str:
    if not speed:
        return "_no cross-deployment comparisons available yet._\n"
    rows = []
    for s in speed[:top_n]:
        rows.append([
            f"`{s['model']}`",
            f"{s.get('ram_gb', '?')} GB / {s.get('cpu_cores', '?')} CPU",
            f"`{s['a']}`",
            f"`{s['b']}`",
            _fmt(s["a_tok_per_s"], " tok/s"),
            _fmt(s["b_tok_per_s"], " tok/s"),
            f"×{s['speedup_a_over_b']}",
        ])
    return _md_table(
        rows,
        ["Model", "Resources", "A", "B", "A tok/s", "B tok/s", "Speed-up A/B"],
    )


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--analysis-dir", default=str(ANALYSIS_DIR))
    p.add_argument("--out-md", default=str(DEFAULT_OUT_MD))
    p.add_argument("--out-json", default=str(DEFAULT_OUT_JSON))
    args = p.parse_args()

    a = Path(args.analysis_dir)
    rows = _load(a / "aggregated_metrics.json", [])
    per_model = _load(a / "perf_per_model.json", {})
    by_dep = _load(a / "perf_by_deployment.json", {})
    speed = _load(a / "perf_speedups.json", [])
    cost = _load(a / "cost_per_model.json", [])

    md = []
    md.append("# SLM benchmark — analysis report\n")
    md.append(f"_Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')}_\n")

    md.append("\n## 1. Overview\n")
    md.append(render_overview(rows))

    md.append("\n## 2. Per-model performance summary\n")
    md.append(render_per_model(per_model))

    md.append("\n## 3. Performance by deployment\n")
    md.append(render_by_deployment(by_dep))

    md.append("\n## 4. Cost ranking (cheapest first)\n")
    md.append(render_cost(cost))

    md.append("\n## 5. Cross-deployment speed-ups\n")
    md.append(render_speedups(speed))

    md.append("\n---\n")
    md.append(
        "Sources: `analysis/aggregated_metrics.csv`, "
        "`analysis/perf_per_model.json`, "
        "`analysis/perf_by_deployment.json`, "
        "`analysis/perf_speedups.json`, "
        "`analysis/cost_per_model.json`.\n"
    )

    out_md = Path(args.out_md)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(md), encoding="utf-8")

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "totals": {
            "runs": len(rows),
            "models": len(per_model),
            "deployments": len(by_dep),
            "cost_rows": len(cost),
            "speedup_rows": len(speed),
        },
    }
    Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_json).write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"Report written to: {out_md}")
    print(f"Summary written to: {args.out_json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
