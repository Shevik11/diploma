# Metrics Collection Guide

All metrics below must be collected for every model on every platform during every benchmark run.

## 1. Inference Metrics

| Metric | Unit | Description |
|--------|------|-------------|
| First Token Latency | ms | Time from request to first token generated |
| Throughput | tokens/sec | Number of tokens generated per second |
| Response Time | ms | Time for complete response |
| QPS | req/sec | Queries per second the system can handle |
| Model Load Time | sec | Time to load model into memory |

## 2. Resource Usage — CPU

| Metric | Unit | Description |
|--------|------|-------------|
| CPU Utilization (total) | % | Overall CPU usage during inference |
| CPU Utilization (per-core) | % | Per-core breakdown |
| Context Switching Overhead | count/sec | OS context switches during inference |

## 3. Resource Usage — Memory

| Metric | Unit | Description |
|--------|------|-------------|
| RAM Usage | MB | Memory consumed during inference |
| Peak Memory | MB | Maximum memory usage observed |

## 4. Resource Usage — Disk

| Metric | Unit | Description |
|--------|------|-------------|
| Disk I/O Speed | MB/s | Read/write throughput |
| Disk Space Used | GB | Model + runtime storage footprint |

## 5. Resource Usage — GPU (if available)

| Metric | Unit | Description |
|--------|------|-------------|
| GPU Utilization | % | GPU compute usage |
| VRAM Usage | MB | GPU memory consumed |

## 6. Resource Usage — Network

| Metric | Unit | Description |
|--------|------|-------------|
| Network Throughput | MB/s | Data transfer rate |
| Network Latency | ms | Round-trip time |

## 7. Operational Metrics

| Metric | Unit | Description |
|--------|------|-------------|
| Deployment Time | sec | Time to deploy model from scratch |
| Image/Container Size | MB | Size of Docker image or VM disk |
| Configuration Complexity | score (1-5) | Subjective complexity rating |
| Recovery Time | sec | Time to recover after crash |
| Scale-out Time | sec | Time to create additional instances |

## 8. Stability & Reliability

| Metric | Unit | Description |
|--------|------|-------------|
| Jitter | ms (stddev) | Standard deviation of response times |
| Noisy Neighbour Effect | % degradation | Performance impact from co-located workloads |
| Error Rate | % | Percentage of failed requests under load |

## 9. Energy Efficiency

| Metric | Unit | Description |
|--------|------|-------------|
| Power Consumption | W | Measured via RAPL, Intel Power Gadget, or scaphandre |
| CO2 Equivalent | g CO2 | Carbon footprint per inference |

## 10. Quality Metrics

| Metric | Unit | Description |
|--------|------|-------------|
| BLEU Score | 0-1 | Translation/generation quality |
| ROUGE Score | 0-1 | Summarization quality |
| Platform Accuracy Delta | % | Quality difference between Docker vs VM |
| Multilingual Score | 0-1 | Performance across languages |

## 11. Cost Metrics

| Metric | Unit | Description |
|--------|------|-------------|
| Hardware Cost | $/hr | Amortized hardware cost |
| Energy Cost | $/hr | Electricity cost |
| Management Cost | $/hr | Operational overhead |
| TCO | $ | `(Hardware + Energy + Management) / Throughput` |
| ROI | ratio | Return on investment per scenario |

## Collection Tools

| Tool | Metrics Collected |
|------|-------------------|
| `psutil` | CPU, RAM, disk I/O |
| `docker stats` / Docker SDK | Container CPU, memory, network |
| `nvidia-smi` | GPU utilization, VRAM |
| `cAdvisor` | Container-level resource metrics |
| `Prometheus` | Time-series aggregation |
| `RAPL` / `scaphandre` | Energy consumption |
| `sar`, `vmstat`, `iostat` | System-level metrics |

## Output Format

Store all metrics as JSON per run:

```json
{
  "model": "phi-3-mini",
  "platform": "docker",
  "test_type": "cold_start",
  "timestamp": "2026-04-04T15:00:00Z",
  "inference": {
    "first_token_latency_ms": 245,
    "throughput_tokens_sec": 32.5,
    "response_time_ms": 1200,
    "model_load_time_sec": 4.2
  },
  "resources": {
    "cpu_percent": 78.3,
    "ram_mb": 2048,
    "peak_ram_mb": 2560,
    "disk_io_mbps": 120
  },
  "quality": {
    "bleu": 0.42,
    "rouge": 0.55
  }
}
```
