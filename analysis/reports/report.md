# SLM benchmark — analysis report

_Generated 2026-05-09T22:35:22+00:00_


## 1. Overview

- **Total runs:** 25
- **Distinct models:** 2 — qwen2.5-coder:1.5b, qwen2.5-coder:7b
- **Inference technologies:** ollama
- **Deployment platforms:** docker


## 2. Per-model performance summary

| Model | Runs | Median tok/s | Median latency | Median TTFT | Success | Quality | Consistency |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `qwen2.5-coder:1.5b` | 19 | 27.43 tok/s | 7179 ms | 413 ms | 100.0% | 88.1% | 49.6% |
| `qwen2.5-coder:7b` | 6 | — | — | — | — | — | 0.0% |


## 3. Performance by deployment

| Deployment | Runs | Median tok/s | Median latency | Success |
| --- | --- | --- | --- | --- |
| `ollama`/`docker` | 8 | 27.43 tok/s | 7179 ms | 100.0% |


## 4. Cost ranking (cheapest first)

| Model | Resources | Deployment | Throughput | Cheapest fit | USD / 1M tokens | Tokens / USD |
| --- | --- | --- | --- | --- | --- | --- |
| `qwen2.5-coder:1.5b` | 2 GB / 2.0 CPU | `ollama`/`docker` | 24.97 tok/s | `edge-cpu-2c-2g` | $0.1747 | 5724098 |
| `qwen2.5-coder:1.5b` | 2 GB / 1.0 CPU | `ollama`/`docker` | 15.26 tok/s | `edge-cpu-2c-2g` | $0.2858 | 3498950 |
| `qwen2.5-coder:1.5b` | 2 GB / 4.0 CPU | `ollama`/`docker` | 34.54 tok/s | `server-cpu-4c-8g` | $0.6755 | 1480385 |
| `qwen2.5-coder:1.5b` | 4 GB / 4.0 CPU | `ollama`/`docker` | 28.96 tok/s | `server-cpu-4c-8g` | $0.8057 | 1241157 |
| `qwen2.5-coder:1.5b` | 4 GB / 2.0 CPU | `ollama`/`docker` | 25.90 tok/s | `server-cpu-4c-8g` | $0.9009 | 1110001 |
| `qwen2.5-coder:1.5b` | 4 GB / 1.0 CPU | `ollama`/`docker` | 15.48 tok/s | `server-cpu-4c-8g` | $1.5073 | 663438 |
| `qwen2.5-coder:1.5b` | 4 GB / 8.0 CPU | `ollama`/`docker` | 30.48 tok/s | `server-cpu-8c-16g` | $1.5311 | 653125 |
| `qwen2.5-coder:1.5b` | 2 GB / 8.0 CPU | `ollama`/`docker` | 29.02 tok/s | `server-cpu-8c-16g` | $1.6081 | 621852 |


## 5. Cross-deployment speed-ups

_no cross-deployment comparisons available yet._


---

Sources: `analysis/aggregated_metrics.csv`, `analysis/perf_per_model.json`, `analysis/perf_by_deployment.json`, `analysis/perf_speedups.json`, `analysis/cost_per_model.json`.
