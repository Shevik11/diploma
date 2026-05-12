"""
metrics-aggregator.py — Phase-3 of the diploma pipeline.

Walks ``results/`` (and any subdirectory containing master JSON files
produced by ``backend/benchmarks.save_benchmark_results`` or by the test
scripts via ``scripts/tests/result_utils.save_results``) and produces a
single tidy table of metrics that downstream scripts (performance
analyzer, cost calculator, report generator, plotters) consume.

This is intentionally **pure** (no LLM calls) and **stdlib-only** apart
from PyYAML — so it runs in any Python 3.10+ env.

Output schema (CSV-ready, one row per (model × ram × cpu × technology ×
platform) configuration):

    model, ram_gb, cpu_cores, technology, platform, timestamp,
    perf_avg_tok_per_s, perf_avg_latency_ms, perf_avg_ttft_ms,
    perf_success_rate,
    quality_score_pct, safety_score_pct, multilingual_score_pct,
    context_score_pct, consistency_pct, stress_success_rate,
    stress_throughput_rps, hard_total_pct, source_file
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_RESULTS_DIRS = [
    PROJECT_ROOT / "results",
    PROJECT_ROOT / "backend" / "results",
]


# ---------------------------------------------------------------------------
# Filename parser
# ---------------------------------------------------------------------------
# Examples handled:
#   phi3_mini_2GB_1cores_ollama_docker_20240910_140212.json
#   llama3.2_1b_4GB_2cores_llama-cpp_vm_20250101_010101.json
#   quality_phi3_mini_8GB_1c_1717777777.json   (older single-test file)
_RE_BENCH = re.compile(
    r"^(?P<model>.+?)_"
    r"(?P<ram>\d+(?:GB|gb)|noRAMlimit)_"
    r"(?P<cpu>\d+(?:\.\d+)?(?:cores|c))_"
    r"(?P<technology>[a-z0-9-]+)_"
    r"(?P<platform>[a-z0-9-]+)_"
    r"(?P<ts>\d{8}_\d{6})\.json$",
    re.IGNORECASE,
)


def parse_filename(path: Path) -> dict[str, Any] | None:
    """Try to extract structured fields from a result filename.

    Returns None if the filename doesn't match the conventional layout —
    in that case the aggregator still tries to read fields from the JSON
    body (``model``, ``ram_gb``, ``cpu_cores``, ``technology``,
    ``platform``).
    """
    m = _RE_BENCH.match(path.name)
    if not m:
        return None
    g = m.groupdict()
    ram_raw = g["ram"].lower()
    cpu_raw = g["cpu"].lower()
    return {
        "model": g["model"].replace("_", ":", 1),
        "ram_gb": None if ram_raw == "noramlimit" else int(re.sub(r"\D", "", ram_raw)),
        "cpu_cores": float(re.sub(r"[^\d.]", "", cpu_raw)),
        "technology": g["technology"],
        "platform": g["platform"],
        "timestamp": g["ts"],
    }


# ---------------------------------------------------------------------------
# Per-section extractors (defensive: every key is optional)
# ---------------------------------------------------------------------------
def _safe_pct(score: float | None, max_score: float | None) -> float | None:
    if score is None or not max_score:
        return None
    try:
        return round(float(score) / float(max_score) * 100, 2)
    except (TypeError, ZeroDivisionError):
        return None


def extract_summary(payload: dict) -> dict[str, Any]:
    """Pull the Phase-1 inference benchmark summary."""
    summary = payload.get("summary") or {}
    return {
        "perf_avg_tok_per_s": summary.get("avg_tokens_per_second"),
        "perf_avg_latency_ms": summary.get("avg_latency_ms"),
        "perf_avg_ttft_ms": summary.get("avg_first_token_latency_ms"),
        "perf_success_rate": (
            summary.get("success_rate")
            if summary.get("success_rate") is not None
            else (
                summary.get("successful", 0) / summary.get("total_prompts", 1)
                if summary.get("total_prompts")
                else None
            )
        ),
    }


def extract_test_sections(payload: dict) -> dict[str, Any]:
    """Pull Phase-2 test-section scores from a master JSON."""
    sections = payload.get("test_sections") or {}
    out: dict[str, Any] = {}

    for key in ("quality", "advanced_quality", "hard_tests"):
        sec = sections.get(key)
        if isinstance(sec, dict):
            out[f"{key}_score_pct"] = _safe_pct(
                sec.get("total_score") or sec.get("score"),
                sec.get("max_score") or sec.get("max"),
            )

    for key in ("multilingual", "summarization", "context_window",
                "safety_robustness"):
        sec = sections.get(key)
        if isinstance(sec, dict):
            out[f"{key}_score_pct"] = sec.get(
                "percentage",
                _safe_pct(sec.get("total_score"), sec.get("max_score")),
            )

    sc = sections.get("stress_consistency")
    if isinstance(sc, dict):
        cons = sc.get("consistency") or {}
        stress = sc.get("stress") or {}
        out["consistency_pct"] = cons.get("consistency_percentage")
        out["stress_success_rate"] = stress.get("success_rate")
        out["stress_throughput_rps"] = stress.get("throughput")
        out["stress_concurrency"] = stress.get("concurrency")

    cost = sections.get("cost_efficiency")
    if isinstance(cost, dict):
        s = cost.get("summary") or {}
        out["cost_avg_tok_per_s"] = s.get("avg_tokens_per_sec")
        out["cost_total_tokens"] = s.get("total_tokens_generated")
        out["cost_total_time_s"] = s.get("total_time_s")

    return out


# ---------------------------------------------------------------------------
# Standalone-file extractors (fallback when not using master files)
# ---------------------------------------------------------------------------
_SINGLE_FILE_PREFIXES = {
    "quality": "quality_score_pct",
    "advanced_quality": "advanced_quality_score_pct",
    "multilingual": "multilingual_score_pct",
    "summarization": "summarization_score_pct",
    "context_window": "context_window_score_pct",
    "safety_robustness": "safety_robustness_score_pct",
    "consistency": "consistency_pct",
    "stress": "stress_success_rate",
    "hard_tests": "hard_tests_score_pct",
    "performance": None,            # has its own fields
    "cost_efficiency": None,
}


def extract_single_file(prefix: str, payload: dict) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if prefix == "performance":
        out.update(extract_summary({"summary": payload.get("summary", payload)}))
    elif prefix == "cost_efficiency":
        s = payload.get("summary") or {}
        out["cost_avg_tok_per_s"] = s.get("avg_tokens_per_sec")
        out["cost_total_tokens"] = s.get("total_tokens_generated")
        out["cost_total_time_s"] = s.get("total_time_s")
    elif prefix == "stress":
        out["stress_success_rate"] = payload.get("success_rate")
        out["stress_throughput_rps"] = payload.get("throughput")
        out["stress_concurrency"] = payload.get("concurrency")
    elif prefix == "consistency":
        out["consistency_pct"] = payload.get("consistency_percentage")
    elif prefix in _SINGLE_FILE_PREFIXES and _SINGLE_FILE_PREFIXES[prefix]:
        out[_SINGLE_FILE_PREFIXES[prefix]] = payload.get(
            "percentage",
            _safe_pct(payload.get("total_score"), payload.get("max_score")),
        )
    return out


# ---------------------------------------------------------------------------
# Main aggregation
# ---------------------------------------------------------------------------
def load_payload(path: Path) -> dict | None:
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError) as e:
        print(f"[skip] {path}: {e}", file=sys.stderr)
        return None


def aggregate(results_dirs: list[Path]) -> list[dict[str, Any]]:
    """Return a list of merged-row dicts (one per master file)."""
    rows: dict[tuple, dict[str, Any]] = {}

    for root in results_dirs:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.json")):
            if path.name.startswith("_"):
                continue
            payload = load_payload(path)
            if payload is None:
                continue

            meta = parse_filename(path) or {}
            # Body fields override filename when present
            row: dict[str, Any] = {
                "model": payload.get("model") or meta.get("model"),
                "ram_gb": payload.get("ram_gb", meta.get("ram_gb")),
                "cpu_cores": payload.get("cpu_cores", meta.get("cpu_cores")),
                "technology": payload.get("technology") or meta.get("technology"),
                "platform": payload.get("platform") or meta.get("platform"),
                "timestamp": payload.get("timestamp") or meta.get("timestamp"),
                "source_file": str(path.relative_to(PROJECT_ROOT)
                                   if path.is_relative_to(PROJECT_ROOT)
                                   else path),
            }

            if not row["model"]:
                continue

            # Master file (has both a Phase-1 summary and Phase-2 sections)
            if "test_sections" in payload or "summary" in payload:
                row.update(extract_summary(payload))
                row.update(extract_test_sections(payload))

            # Standalone single-test file: deduce prefix from filename head.
            head = path.stem.split("_", 1)[0]
            for prefix in _SINGLE_FILE_PREFIXES:
                if path.stem.startswith(prefix):
                    row.update(extract_single_file(prefix, payload))
                    break

            key = (
                row["model"],
                row["ram_gb"],
                row["cpu_cores"],
                row["technology"],
                row["platform"],
                # Different result files for the same configuration get
                # merged when they were produced for the same run; we use
                # the timestamp as a tie-breaker only at a coarse level
                # (date) so test scripts saving slightly later than the
                # benchmark still aggregate together.
                str(row.get("timestamp") or "")[:8],
            )
            existing = rows.setdefault(key, {})
            for k, v in row.items():
                if v is None:
                    continue
                # Don't clobber with empty / earlier values.
                if existing.get(k) in (None, "", 0):
                    existing[k] = v

    return list(rows.values())


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------
COLUMNS = [
    "model", "ram_gb", "cpu_cores", "technology", "platform", "timestamp",
    "perf_avg_tok_per_s", "perf_avg_latency_ms", "perf_avg_ttft_ms",
    "perf_success_rate",
    "quality_score_pct", "advanced_quality_score_pct",
    "hard_tests_score_pct",
    "multilingual_score_pct", "summarization_score_pct",
    "context_window_score_pct", "safety_robustness_score_pct",
    "consistency_pct",
    "stress_success_rate", "stress_throughput_rps", "stress_concurrency",
    "cost_avg_tok_per_s", "cost_total_tokens", "cost_total_time_s",
    "source_file",
]


def write_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


def write_json(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--results-dir",
        action="append",
        default=None,
        help="Override the default results directories (can be repeated).",
    )
    p.add_argument(
        "--out-csv",
        default=str(PROJECT_ROOT / "analysis" / "aggregated_metrics.csv"),
    )
    p.add_argument(
        "--out-json",
        default=str(PROJECT_ROOT / "analysis" / "aggregated_metrics.json"),
    )
    args = p.parse_args()

    dirs = [Path(d) for d in args.results_dir] if args.results_dir else DEFAULT_RESULTS_DIRS
    rows = aggregate(dirs)

    write_csv(rows, Path(args.out_csv))
    write_json(rows, Path(args.out_json))

    print(f"Aggregated {len(rows)} configuration row(s)")
    print(f"  CSV : {args.out_csv}")
    print(f"  JSON: {args.out_json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
