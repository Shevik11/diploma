"""
cost-calculator.py — Phase-3 of the diploma pipeline.

Reads ``analysis/aggregated_metrics.csv`` and ``config/infrastructure.yml``
to compute per-model cost-of-inference metrics:

    * USD per 1M generated tokens (cloud, on-demand pricing)
    * USD per 1M generated tokens (self-hosted, electricity-only)
    * tokens-per-USD (efficiency score, higher is better)

The script does NOT need network access; pricing data lives in version
control under ``config/infrastructure.yml``.

Output:
    analysis/cost_per_model.json
    analysis/cost_per_model.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_INPUT = PROJECT_ROOT / "analysis" / "aggregated_metrics.csv"
DEFAULT_INFRA = PROJECT_ROOT / "config" / "infrastructure.yml"
DEFAULT_OUT_JSON = PROJECT_ROOT / "analysis" / "cost_per_model.json"
DEFAULT_OUT_CSV = PROJECT_ROOT / "analysis" / "cost_per_model.csv"

# Tiny YAML loader — falls back to PyYAML if available, otherwise a
# dependency-free parser that handles the very simple subset we use.
def _load_yaml(path: Path) -> dict:
    try:
        import yaml  # type: ignore
        with path.open("r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except ImportError:
        return _minimal_yaml_load(path)


def _minimal_yaml_load(path: Path) -> dict:
    """Tiny YAML reader: handles indented dicts, lists, simple scalars.

    Sufficient for the project's own config files; not a substitute for
    PyYAML in general.
    """
    import re

    def coerce(s: str):
        s = s.strip()
        if s.startswith('"') and s.endswith('"'):
            return s[1:-1]
        if s.startswith("'") and s.endswith("'"):
            return s[1:-1]
        if re.match(r"^-?\d+$", s):
            return int(s)
        if re.match(r"^-?\d+\.\d+$", s):
            return float(s)
        if s in ("true", "True", "yes"):
            return True
        if s in ("false", "False", "no"):
            return False
        if s in ("null", "~", ""):
            return None
        if s.startswith("[") and s.endswith("]"):
            inner = s[1:-1].strip()
            if not inner:
                return []
            return [coerce(p) for p in inner.split(",")]
        return s

    root: dict = {}
    stack: list[tuple[int, Any]] = [(-1, root)]

    with path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            indent = len(line) - len(line.lstrip(" "))
            content = line.strip()
            # pop deeper frames
            while stack and stack[-1][0] >= indent:
                stack.pop()
            parent = stack[-1][1] if stack else root

            if content.startswith("- "):
                # list item
                item_body = content[2:].strip()
                if isinstance(parent, list):
                    target = parent
                else:
                    # parent is a dict with the most recent key holding a list
                    last_key = list(parent.keys())[-1]
                    if not isinstance(parent[last_key], list):
                        parent[last_key] = []
                    target = parent[last_key]

                if ":" in item_body:
                    item: dict = {}
                    target.append(item)
                    stack.append((indent, item))
                    key, _, val = item_body.partition(":")
                    item[key.strip()] = coerce(val) if val.strip() else {}
                    if not val.strip():
                        stack.append((indent + 2, item[key.strip()]))
                else:
                    target.append(coerce(item_body))
            else:
                key, _, val = content.partition(":")
                key = key.strip()
                if val.strip() == "":
                    new_obj: dict = {}
                    parent[key] = new_obj
                    stack.append((indent, new_obj))
                else:
                    parent[key] = coerce(val)

    return root


def _to_float(v: Any) -> float | None:
    if v in (None, ""):
        return None
    try:
        f = float(v)
        return f if not math.isnan(f) else None
    except (TypeError, ValueError):
        return None


def load_metrics_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def select_hw_profile(infra: dict, ram_gb, cpu_cores) -> dict | None:
    """Pick the cheapest hardware profile that satisfies the row's RAM/CPU."""
    profiles = infra.get("hardware_profiles") or []
    candidates = []
    ram_v = _to_float(ram_gb)
    cpu_v = _to_float(cpu_cores)
    for p in profiles:
        p_ram = _to_float(p.get("ram_gb"))
        p_cpu = _to_float(p.get("cpu_cores"))
        if p_ram is None or p_cpu is None:
            continue
        if ram_v is not None and p_ram < ram_v:
            continue
        if cpu_v is not None and p_cpu < cpu_v:
            continue
        candidates.append(p)
    if not candidates:
        return None
    return min(candidates, key=lambda x: _to_float(x.get("usd_per_hour")) or 1e9)


def cost_per_million_tokens(usd_per_hour: float, tok_per_s: float) -> float | None:
    """USD spent generating 1,000,000 tokens at the given throughput."""
    if not tok_per_s or tok_per_s <= 0 or usd_per_hour is None:
        return None
    tokens_per_hour = tok_per_s * 3600
    if tokens_per_hour <= 0:
        return None
    hours_per_million = 1_000_000 / tokens_per_hour
    return round(usd_per_hour * hours_per_million, 4)


def compute(rows: list[dict], infra: dict) -> list[dict]:
    elec_table = infra.get("electricity_usd_per_kwh") or {}
    # Pick a reasonable default: average of values, or 0.10 USD/kWh.
    if isinstance(elec_table, dict) and elec_table:
        elec_default = sum(_to_float(v) or 0 for v in elec_table.values()) / len(elec_table)
    else:
        elec_default = 0.10

    out: list[dict] = []
    for r in rows:
        tok_per_s = _to_float(r.get("perf_avg_tok_per_s")) or _to_float(r.get("cost_avg_tok_per_s"))
        if not tok_per_s:
            continue

        hw = select_hw_profile(infra, r.get("ram_gb"), r.get("cpu_cores"))
        if not hw:
            continue

        usd_h = _to_float(hw.get("usd_per_hour"))
        kwh_h = _to_float(hw.get("electricity_kwh")) or 0.0
        cost_cloud_per_m = cost_per_million_tokens(usd_h or 0.0, tok_per_s)
        cost_self_per_m = cost_per_million_tokens(elec_default * kwh_h, tok_per_s)

        out.append({
            "model": r.get("model"),
            "ram_gb": r.get("ram_gb"),
            "cpu_cores": r.get("cpu_cores"),
            "technology": r.get("technology"),
            "platform": r.get("platform"),
            "tok_per_s": tok_per_s,
            "hw_profile": hw.get("id"),
            "usd_per_hour_cloud": usd_h,
            "kwh_per_hour": kwh_h,
            "usd_per_million_tokens_cloud": cost_cloud_per_m,
            "usd_per_million_tokens_self_hosted": cost_self_per_m,
            "tokens_per_usd_cloud": (
                round(1_000_000 / cost_cloud_per_m, 0)
                if cost_cloud_per_m and cost_cloud_per_m > 0 else None
            ),
        })
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", default=str(DEFAULT_INPUT))
    p.add_argument("--infra", default=str(DEFAULT_INFRA))
    p.add_argument("--out-json", default=str(DEFAULT_OUT_JSON))
    p.add_argument("--out-csv", default=str(DEFAULT_OUT_CSV))
    args = p.parse_args()

    if not Path(args.input).exists():
        print(f"[error] missing input CSV: {args.input}", file=sys.stderr)
        print("        run metrics-aggregator.py first", file=sys.stderr)
        return 2
    if not Path(args.infra).exists():
        print(f"[error] missing infra config: {args.infra}", file=sys.stderr)
        return 2

    rows = load_metrics_csv(Path(args.input))
    infra = _load_yaml(Path(args.infra))
    res = compute(rows, infra)

    # Sort cheapest-first
    res.sort(key=lambda r: r["usd_per_million_tokens_cloud"] or float("inf"))

    Path(args.out_json).write_text(
        json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    if res:
        cols = list(res[0].keys())
        with open(args.out_csv, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            for row in res:
                w.writerow(row)
    print(f"Computed cost for {len(res)} configuration(s)")
    print(f"  JSON: {args.out_json}")
    print(f"  CSV : {args.out_csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
