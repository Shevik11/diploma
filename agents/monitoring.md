# Monitoring & Observability

## Architecture

```
[Docker/VM] → [Metrics Collectors] → [Prometheus] → [Grafana Dashboards]
```

## Docker Monitoring

| Tool | Purpose | Setup |
|------|---------|-------|
| `docker stats` | Real-time CPU, memory, network per container | Built-in |
| Docker SDK (`docker` Python package) | Programmatic access to container stats | `pip install docker` |
| **cAdvisor** | Container-level resource metrics with Prometheus export | Run as sidecar container |
| **Docker Bench Security** | Security audit of Docker configuration | One-time scan |

### cAdvisor Setup

```yaml
# docker-compose.yml
cadvisor:
  image: gcr.io/cadvisor/cadvisor:latest
  ports:
    - "8080:8080"
  volumes:
    - /:/rootfs:ro
    - /var/run:/var/run:ro
    - /sys:/sys:ro
    - /var/lib/docker/:/var/lib/docker:ro
```

## VM Monitoring

| Tool | Purpose |
|------|---------|
| `top` / `htop` | Real-time process monitoring |
| `nvidia-smi` | GPU utilization and VRAM |
| `sar` | Historical system activity |
| `vmstat` | Virtual memory statistics |
| `iostat` | Disk I/O statistics |

## Prometheus

Collects time-series metrics from all sources.

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'cadvisor'
    static_configs:
      - targets: ['localhost:8080']
  - job_name: 'node'
    static_configs:
      - targets: ['localhost:9100']
```

## Grafana Dashboards

Required dashboards:
1. **Model Comparison** — side-by-side Docker vs VM metrics
2. **Resource Usage** — CPU, RAM, GPU over time
3. **Inference Performance** — latency, throughput, QPS
4. **Cost Analysis** — TCO breakdown

## In-App Monitoring

The React frontend communicates with the FastAPI backend (`backend/main.py`) which provides real-time monitoring via:
- `psutil` for system metrics
- Docker SDK for container stats
- WebSocket streaming for live updates

## Energy Monitoring

| Tool | Platform | Metrics |
|------|----------|---------|
| **RAPL** | Intel CPUs | Package/core power (W) |
| **Intel Power Gadget** | Intel CPUs | Power, temperature, frequency |
| **scaphandre** | Linux | Per-process power consumption |

## Data Pipeline

1. **Collect**: Metrics gathered during benchmark runs → JSON files in `results/`
2. **Aggregate**: `analysis/data-processing/metrics-aggregator.py` combines runs
3. **Analyze**: `analysis/data-processing/performance-analyzer.py` computes comparisons
4. **Visualize**: `analysis/visualization/` generates charts
5. **Report**: `analysis/reports/generate-report.py` produces final output
