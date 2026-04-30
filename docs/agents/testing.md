# Testing Requirements

Every model must be tested across all test types below on both Docker and VM platforms.

## Test Types

### 1. Cold Start Test

**File**: `benchmarks/load-generator/cold-start-test.py`

- Start model from scratch (no cache, no warm-up)
- Measure: time to first response, model load time, container/VM boot time
- Run **3+ times** and average results
- Record resource usage during startup

### 2. Warm Test

- Run inference after model is already loaded and warmed up
- Measure: steady-state latency, throughput (tokens/sec)
- Warm-up: send 5 throwaway requests before measuring
- Run **10+ iterations** for statistical significance

### 3. Sequential Request Test

**File**: `benchmarks/load-generator/sequential-test.py`

- Send requests one after another
- Measure: per-request latency, total throughput
- Use standardized prompts from datasets (Alpaca, Lotus)
- Minimum **50 requests** per run

### 4. Concurrent Request Test

**File**: `benchmarks/load-generator/concurrent-test.py`

- Send parallel requests (2, 4, 8, 16 concurrent)
- Measure: throughput under load, latency percentiles (p50, p95, p99)
- Record resource saturation points
- Test with increasing concurrency until failure

### 5. Stress Test

**File**: `benchmarks/load-generator/stress-test.py`

- Push model to maximum capacity
- Measure: breaking point, degradation curve, recovery time
- Record: OOM events, crashes, error rates
- Gradually increase load until failure

### 6. Failure Scenario Tests

**File**: `benchmarks/scenarios/failure-scenarios.py`

- **Out of Memory**: Trigger OOM and measure recovery
- **Model Crash**: Kill process and measure restart time
- **Host Overload**: Saturate host resources and observe behavior
- **Container restart vs VM reboot**: Compare recovery times

### 7. Quality Tests

**File**: `scripts/tests/quality_test.py`

- Measure model output quality (not just speed)
- Metrics: BLEU score, ROUGE score
- Compare: same model on Docker vs VM (should be identical)
- Test multilingual capabilities
- Use standardized evaluation prompts

### 8. Chatbot Simulation

**File**: `benchmarks/scenarios/chatbot-simulation.py`

- Simulate real-world chatbot usage with random prompts
- Use Alpaca and Lotus datasets
- Measure end-to-end response time and quality

### 9. Real-World Use Cases

**File**: `benchmarks/scenarios/real-world-use-cases.py`

- Code generation, summarization, translation, Q&A
- Measure task-specific performance

## Test Data

- **Alpaca dataset** — instruction-following prompts
- **Lotus dataset** — diverse evaluation prompts
- **Custom prompts** — project-specific test cases

## Test Execution Rules

1. All tests must run on **both Docker and VM** with identical prompts
2. Record **all metrics** from [`metrics.md`](./metrics.md) during every test
3. Use fixed hardware configuration (document in results)
4. Set random seeds where applicable for reproducibility
5. Store raw results in `results/` directory as JSON/CSV
6. Generate comparison reports in `analysis/`

## Test Matrix

Every model × every platform × every test type = one result set.

```
Models:      Phi, Gemma, Llama, Mistral, Qwen, StableLM, Falcon, ...
Platforms:   Docker, VM (KVM), [optional: Podman, Firecracker, ...]
Tests:       cold_start, warm, sequential, concurrent, stress, failure, quality
```
