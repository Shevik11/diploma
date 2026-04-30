# Technology Stack

## Language

- **Python 3.11+** — primary language for all scripts, backend, benchmarks, and analysis

## Core Dependencies

| Package | Purpose |
|---------|---------|
| `fastapi` | REST API backend |
| `uvicorn` | ASGI server |
| `docker` | Docker SDK for container management |
| `psutil` | System resource monitoring |
| `pandas` | Data processing and aggregation |
| `numpy` | Numerical computations |
| `plotly` | Interactive charts and visualizations |
| `matplotlib` | Static plots and report generation |
| `requests` | HTTP client for model inference calls |
| `pydantic` | Data validation and settings |
| `pytest` | Testing framework |
| `websockets` | Real-time metrics streaming |

## ML Inference Frameworks

| Framework | Use Case |
|-----------|----------|
| **Ollama** | Primary local model runner (Docker-based) |
| **llama.cpp** | CPU-optimized inference, GGUF format |
| **vLLM** | High-throughput GPU inference |
| **Transformers** | HuggingFace model loading and inference |
| **ONNX Runtime** | Edge deployment, optimized inference |

## Model Formats

| Format | Description |
|--------|-------------|
| **GGUF** | llama.cpp native format, quantized |
| **AWQ** | Activation-aware weight quantization |
| **EXL2** | ExLlamaV2 format |
| **Quantization** | Q4, Q8, FP16, INT8 variants |

## Containerization

- **Docker** — primary container runtime
- **Podman** — rootless alternative
- **containerd** — lightweight runtime

## Virtualization

- **KVM / QEMU** — primary VM hypervisor
- **VirtualBox** — cross-platform VM
- **VMware** — enterprise VM
- **Hyper-V** — Windows native
- **Xen** — type-1 hypervisor
- **Firecracker** — microVM for serverless
- **LXC/LXD** — system containers

## Cloud Platforms

- AWS Lambda, AWS Fargate
- Google Cloud Run
- Vercel AI

## Infrastructure as Code

- **Terraform** — infrastructure provisioning
- **Ansible** — configuration management

## Monitoring & Observability

- **Prometheus** — metrics collection
- **Grafana** — dashboards and visualization
- **cAdvisor** — container metrics
- **docker stats** — built-in container monitoring
- **nvidia-smi** — GPU monitoring

## Security Tools

- **Trivy** — container vulnerability scanning
- **OpenSCAP** — VM security compliance
- **Docker Bench Security** — Docker hardening

## Package Management

- **uv** — fast Python package manager (see `uv.lock`)
- **pip** — fallback package manager
