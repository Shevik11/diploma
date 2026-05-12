# Diploma Realization Structure Plan

## Objective
Build a reproducible benchmarking pipeline to identify minimal acceptable hardware configurations for SLM inference and produce thesis-ready conclusions.

## Success Criteria
- Every model is tested across a defined RAM/CPU/VRAM matrix.
- Metrics include TTFT, tokens/sec, total response time, load time, peak RAM, CPU usage, and failures.
- Minimal acceptable configuration is identified per model using explicit thresholds.
- Results are aggregated into final tables and charts.
- Cost comparison (self-hosted vs cloud/API) is calculated from measured throughput.

## Phase 1. Protocol Freeze (Day 1)
1. Finalize model list and quantization variants.
2. Freeze test prompts (short, medium, long) and test modes (cold, warm, sequential, stress).
3. Lock pass thresholds:
   - TTFT < 3000 ms
   - Tokens/sec > 3
   - Total response time < 30 s
   - Load time < 60 s
4. Store protocol in config/test-parameters.yml.

## Phase 2. Matrix Runner (Days 2-4)
1. Implement a matrix runner script for model x configuration x test type.
2. Add runtime limits per run (RAM, CPU, optional GPU profile).
3. For each run:
   - Start runtime with limits
   - Execute tests
   - Save raw JSON result
   - Stop runtime and clean state
4. Ensure retries and failure logging are included.

## Phase 3. Unified Result Schema (Day 4)
1. Standardize output fields for all scripts:
   - model, platform, config, test_type, timestamp
   - ttft_ms, tps, total_response_ms, model_load_ms
   - peak_ram_mb, avg_cpu_percent, vram_mb (if available)
   - success, error_type, error_message
2. Validate that all result files conform to the same schema.

## Phase 4. Analysis Pipeline (Days 5-7)
1. Implement analysis/data-processing/metrics-aggregator.py
2. Implement analysis/data-processing/performance-analyzer.py
3. Implement analysis/data-processing/cost-calculator.py
4. Implement analysis/reports/generate-report.py

## Phase 5. Pilot Validation (Days 8-9)
1. Run pilot on 2-3 models and 3 configurations only.
2. Verify metric correctness and reproducibility.
3. Fix schema mismatches and timing issues before full execution.

## Phase 6. Full Experiment (Days 10-14)
1. Execute full matrix for selected models.
2. Re-run failed and outlier configurations.
3. Freeze final dataset in results/.
4. Export plots in analysis/visualization/.

## Phase 7. Thesis Output (Days 15-18)
1. Create final table: Model -> Min RAM/CPU/VRAM -> TPS -> Pass/Fail.
2. Add budget recommendations by scenario.
3. Add break-even estimate for self-hosted vs paid API.
4. Finalize reproducibility appendix.

## Risks and Mitigation
- Inconsistent metrics: enforce one schema and pre-run validation.
- Long experiment time: pilot first, then staggered batches.
- OOM and unstable runs: automatic retry policy and explicit failure labels.
- Cost estimate mismatch: pin pricing date and provider assumptions in report metadata.

## Deliverables Checklist
- Matrix runner script
- Unified result schema
- Aggregated dataset
- Performance and cost analysis outputs
- Charts and final markdown report
- Reproducibility instructions
