# Dev Session — 2026-04-23

## Summary

Development session focused on test coverage and test implementations for the SLM benchmarking diploma thesis.

---

## Test Coverage Audit

Cross-reference of all test scripts in `scripts/tests/` against the diploma plan requirements (`docs/diploma_plan.md`).

### All Existing Tests

| File | Category | What It Measures | Diploma §§ |
|---|---|---|---|
| `cold_start_test.py` | Performance | Cold vs warm TTFT, model load time | §3.3, §4.1 |
| `performance_test.py` | Performance | TTFT, TPS, total response time (latency baseline) | §4.1 |
| `resource_usage_test.py` | Hardware | Peak RAM (MB), avg CPU (%) via psutil during inference | §4.2 |
| `oom_detection_test.py` | Failure Boundary | Escalating context/burst until OOM or timeout | §3.3 (partial — escalates context, not RAM) |
| `ram_boundary_test.py` | Hardware Sweep | Automated sweep 16→1 GB RAM, checks TTFT/TPS thresholds | §3.3 (boundary test) |
| `config_matrix_test.py` | Hardware Matrix | Automated sweep over §3.2 8 RAM/CPU/VRAM combos, checks §4.1 thresholds per combo | §3.2 (config matrix) |
| `vram_monitor_test.py` | Hardware (GPU) | Peak / avg VRAM (MB), GPU utilization (%) via pynvml / nvidia-smi | §4.2 (**created this session**) |
| `cloud_cost_calculator.py` | Economic | $/1M output tokens per cloud tier, break-even vs paid APIs | §6, §6.1, §6.2 (**created this session**) |
| `quantization_compare_test.py` | Model Variant | Q4 vs Q8 (or arbitrary variant list) — TPS / TTFT / RAM / quality diffs | §2.1 (**created this session**) |
| `stress_and_consistency_test.py` | Reliability | Response stability and jitter across repeated identical prompts | §3.3 (sequential series) |
| `context_window_test.py` | Context / RAM | Needle-in-haystack retrieval at varying context lengths | §4.2 (RAM impact on context) |
| `cost_efficiency_test.py` | Economic | TPS vs task complexity trade-off | §6 |
| `quality_test.py` | Quality Smoke | Factual accuracy + instruction following (fast sanity check) | §3.4 |
| `benchmark_mmlu_test.py` | Standard Benchmark | General knowledge accuracy (57 subjects) | §3.4 |
| `benchmark_gsm8k_test.py` | Standard Benchmark | Math word problem reasoning (chain-of-thought) | §3.4 |
| `benchmark_reasoning_test.py` | Standard Benchmark | Commonsense / science reasoning (ARC, HellaSwag style) | §3.4 |
| `benchmark_humaneval_test.py` | Standard Benchmark | Functional Python code generation correctness | §3.4 |
| `benchmark_truthfulqa_test.py` | Standard Benchmark | Resistance to hallucinations and misconceptions | §3.4 |
| `hard_tests.py` | Quality Ceiling | Complex logic/debug tasks — differentiates model capability tiers | §4.1 (quality at config) |
| `advanced_quality_test.py` | Quality Deep | Deep reasoning, logical fallacies, consistency under contradiction | §4.1 (quality at config) |
| `multilingual_test.py` | Language | Translation and cross-lingual understanding | out of scope |
| `safety_robustness_test.py` | Safety | Safety alignment and bias under resource pressure | out of scope |
| `summarization_test.py` | Quality | Long-form summarization accuracy | out of scope |
| `compare_models.py` | Tooling | Side-by-side same-prompt comparison across models/configs | §7.1 |
| `run_all_tests.py` | Orchestration | Runs full suite, aggregates JSON reports | §7.1 |
| `verify_test_coverage.py` | Tooling | Validates that all result files conform to schema | Phase 3 |

---

### Coverage vs Diploma Plan

| Diploma Plan Item | Script(s) | Status |
|---|---|---|
| §3.3 Cold start test | `cold_start_test.py` | ✅ Full |
| §3.3 Warm request test | `cold_start_test.py`, `performance_test.py` | ✅ Full |
| §3.3 Sequential series (10 requests, avg + median) | `stress_and_consistency_test.py` | ✅ Full |
| §2.1 Q4 vs Q8 quantization trade-off | `quantization_compare_test.py` | ✅ Full (created this session) |
| §3.3 Boundary test (reduce RAM until failure) | `ram_boundary_test.py` | ✅ Full |
| §3.2 Config matrix (8 RAM/CPU combos, automated) | `config_matrix_test.py` | ✅ Full |
| §3.4 Short prompt (~50 tokens) | all test scripts | ✅ Full |
| §3.4 Medium prompt (~150 tokens) | all test scripts | ✅ Full |
| §3.4 Long prompt (~300 tokens) | all test scripts | ✅ Full |
| §4.1 TTFT | `cold_start_test.py`, `performance_test.py` | ✅ Full |
| §4.1 Tokens per Second | `performance_test.py`, `ram_boundary_test.py` | ✅ Full |
| §4.1 Total Response Time | `performance_test.py` | ✅ Full |
| §4.1 Model Load Time | `cold_start_test.py` | ✅ Full |
| §4.2 Peak RAM usage | `resource_usage_test.py` | ✅ Full |
| §4.2 Average CPU utilization | `resource_usage_test.py` | ✅ Full |
| §4.2 VRAM usage (GPU memory monitoring) | `vram_monitor_test.py` | ✅ Full (created this session) |
| §4.2 OOM events | `oom_detection_test.py`, `ram_boundary_test.py` | ✅ Full (combined coverage) |
| §6 Cost analysis (self-hosted vs API) | `cost_efficiency_test.py`, `cloud_cost_calculator.py` | ✅ Full (created this session) |
| §6.1 Cloud instance pricing lookup | `cloud_cost_calculator.py` | ✅ Full (created this session) |
| §6.2 Paid API break-even comparison | `cloud_cost_calculator.py` | ✅ Full (created this session) |

---

### What Still Needs to Be Implemented

Nothing from the diploma plan remains uncovered. Out-of-scope future work:

| # | What | Why | Priority |
|---|---|---|---|
| 1 | **Energy / power draw per inference** | Extend `vram_monitor_test.py` with `nvmlDeviceGetPowerUsage` to report J/1k tokens — complements §6 cost analysis. | 🟢 Low |
| 2 | **Prometheus / Grafana export** | §5 lists Prometheus+Grafana but no test pushes metrics there yet. | 🟢 Low |
| 3 | **Streaming-mode TTFT** | All current probes use `stream=False`; true SSE first-byte latency would be more faithful to user-perceived TTFT. | 🟢 Low |

---

## New Tests Added This Session

### VRAM Monitor — §4.2

**File:** `scripts/tests/vram_monitor_test.py`

- Dual backend: `pynvml` (preferred) → `nvidia-smi` CLI fallback
- Graceful no-op on CPU-only hosts (writes `skipped: "no_gpu_detected"` result, exits 0) so Phase-2 `run-all` still passes
- Baseline sample + 0.5 s background sampler during cold + warm (short / medium / long) inferences
- Reports peak / avg / delta VRAM (MB), peak / avg GPU utilization, per-call VRAM peak
- Optional `SLM_GPU_VRAM_GB` env var enables envelope check (fails if peak VRAM exceeds the §3.2 budget)
- Registered in `backend/main.py` as `"vram_monitor"`

### Cloud Cost Calculator — §6 / §6.1 / §6.2

**File:** `scripts/tests/cloud_cost_calculator.py`

- Runs short / medium / long probes, measures avg & median TPS
- Uses §6.1 price table (t3.medium / t3.large / t3.xlarge / g4dn.xlarge + GCP equivalents) to compute self-hosted $/1M output tokens via `usd_per_hour / (TPS * 3600) * 1e6`
- Flags which tiers fit the measured RAM footprint and picks the cheapest one
- Compares vs §6.2 paid APIs (GPT-4o mini, Claude 3 Haiku, Gemini 1.5 Flash) and prints monthly break-even token volume
- Optional `--ram-gb` overrides measured footprint
- Registered in `backend/main.py` as `"cloud_cost"`

### Quantization Compare (Q4 vs Q8) — §2.1

**File:** `scripts/tests/quantization_compare_test.py`

Direct response to §2.1, which enumerates GGUF Q4/Q8 variants. No previous script compared quant levels head-to-head.

- Accepts explicit list via `--variants` or auto-derives a Q4↔Q8 sibling from the input tag
- Runs identical 3-prompt × 2-run evaluation set across every variant (apples-to-apples numbers)
- Captures TTFT, TPS, load time, eval tokens, RAM delta per variant
- Scores answer quality via keyword + length rubric (0..1)
- Emits pair-wise diffs: ΔTPS, ΔTTFT, ΔQuality, ΔRAM, speed-ratio
- Declares winners (fastest / best_quality / lowest_ttft)
- Registered in `backend/main.py` as `"quant_compare"`

---

## Previous Session Recap

### RAM Boundary Sweep Test — §3.3

**File:** `scripts/tests/ram_boundary_test.py`

Implements §3.3 boundary test: *"поступове зменшення RAM до відмови моделі"*.

- Live cgroup update via `container.update(mem_limit=...)` — no container restart
- Iterates `[16, 12, 8, 6, 5, 4, 3, 2, 1.5, 1, 0.5]` GB top-down
- Cold probe + warm probe at each level vs §4.1 thresholds
- Stops at first failure; restores original limit via `try/finally`
- Registered in `backend/main.py` as `"ram_boundary"` test

---

## Files Changed

| File | Change |
|---|---|
| `scripts/tests/ram_boundary_test.py` | Created — §3.3 RAM boundary sweep |
| `scripts/tests/config_matrix_test.py` | Created — §3.2 config matrix runner (8 RAM/CPU/VRAM combos) |
| `scripts/tests/vram_monitor_test.py` | Created — §4.2 VRAM monitor (pynvml + nvidia-smi fallback) |
| `scripts/tests/cloud_cost_calculator.py` | Created — §6 self-hosted vs API break-even calculator |
| `scripts/tests/quantization_compare_test.py` | Created — §2.1 Q4 vs Q8 comparison |
| `scripts/tests/requirements.txt` | Added `docker>=6.0.0` |
| `backend/main.py` | Registered `ram_boundary`, `config_matrix`, `vram_monitor`, `cloud_cost`, `quant_compare` tests |

---

### Config Matrix Runner — §3.2

**File:** `scripts/tests/config_matrix_test.py`

Implements §3.2 configuration matrix: 8 combos from `(1 GB / 1 core)` → `(16 GB / 8 cores / 8 GB GPU)`.

- Live cgroup update via `container.update(mem_limit=..., cpu_period/cpu_quota=...)` — no restart
- Iterates all 8 combos defined in §3.2 (5 CPU-only + 3 GPU)
- GPU combos auto-skipped (`skipped: "no_gpu_runtime"`) when no NVIDIA runtime is detected on the container
- Cold + warm probe per combo, evaluated against §4.1 thresholds (TTFT < 3s · TPS ≥ 3 · load < 60s)
- Continues through the full matrix regardless of pass/fail (unlike §3.3 boundary sweep which stops at first failure)
- Computes `min_viable` config (smallest RAM × cores that passes) in summary
- Restores original `mem_limit` and `cpu_quota` via `try/finally`
- Registered in `backend/main.py` as `"config_matrix"` test
