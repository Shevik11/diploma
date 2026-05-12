# SLM Deployment Control Panel

A web application to compare container vs VM deployment performance for Small Language Models (SLMs).

## Project Structure

```
diploma/
├── docker-compose.yml              # All services: frontend, backend, ollama, llama.cpp, vLLM, cAdvisor
│
├── backend/                        # FastAPI backend
│   ├── main.py                     # All API endpoints + WebSocket
│   ├── benchmarks.py               # Inference benchmark runner (Ollama)
│   ├── requirements.txt
│   ├── Dockerfile
│   └── run.ps1 / run.sh            # Local start scripts
│
├── frontend/                       # React + Vite dashboard
│   ├── app/
│   │   ├── App.tsx                 # Main app: model/RAM/CPU selectors, test runner
│   │   ├── components/
│   │   │   ├── deployment-card.tsx
│   │   │   ├── metrics-section.tsx
│   │   │   ├── metrics-chart.tsx
│   │   │   ├── results-viewer.tsx
│   │   │   ├── model-compare.tsx
│   │   │   ├── benchmark-runner.tsx
│   │   │   ├── test-runner.tsx
│   │   │   └── ui/                 # shadcn/ui component library
│   │   ├── services/
│   │   │   └── api.ts              # REST + WebSocket client
│   │   └── main.tsx
│   ├── styles/                     # Global CSS / Tailwind
│   ├── Dockerfile
│   ├── nginx.conf
│   └── run.ps1 / run.sh
│
├── scripts/
│   ├── tests/                      # 17 test suites (run as subprocesses by backend)
│   │   ├── quality_test.py
│   │   ├── advanced_quality_test.py
│   │   ├── performance_test.py
│   │   ├── safety_robustness_test.py
│   │   ├── stress_and_consistency_test.py
│   │   ├── hard_tests.py
│   │   ├── multilingual_test.py
│   │   ├── summarization_test.py
│   │   ├── context_window_test.py
│   │   ├── cost_efficiency_test.py
│   │   ├── benchmark_mmlu_test.py
│   │   ├── benchmark_reasoning_test.py
│   │   ├── benchmark_gsm8k_test.py
│   │   ├── benchmark_truthfulqa_test.py
│   │   ├── benchmark_humaneval_test.py
│   │   ├── compare_models.py
│   │   ├── run_all_tests.py
│   │   └── requirements.txt
│   ├── Makefile-{llama,mistral,gemma,phi}   # Linux/WSL per-model test runners
│   └── make-{llama,mistral,gemma,phi}.ps1   # Windows PowerShell equivalents
│
├── results/                        # Benchmark output (one JSON per run)
│   └── {model}_{ram}GB_{cpu}cores_{tech}_{platform}_{datetime}.json
│
├── analysis/                       # Post-run data processing scripts
│   ├── data-processing/
│   │   ├── metrics-aggregator.py
│   │   ├── performance-analyzer.py
│   │   └── cost-calculator.py
│   ├── reports/
│   │   └── generate-report.py
│   └── visualization/
│       ├── generate-charts.py
│       └── comparative-plots.py
│
├── config/                         # Experiment configuration
│   ├── test-parameters.yml         # RAM/CPU matrix, thresholds, prompts
│   ├── models.yml                  # Model list and quantization variants
│   └── infrastructure.yml
│
├── monitoring/                     # Prometheus + Grafana configs
│   ├── prometheus/
│   │   └── prometheus.yml
│   └── grafana/
│       └── dashboards/
│
└── docs/
    ├── agents/                     # Project documentation
    │   ├── source_of_truth.md      # Dissertation outline (Ukrainian)
    │   ├── technology_stack.md
    │   ├── metrics.md
    │   ├── testing.md
    │   ├── deployment_docker.md
    │   └── deployment_vm.md
    └── models/                     # Per-model notes
        ├── phi.md
        ├── llama.md
        ├── mistral.md
        └── gemma.md
```

## Prerequisites

- **Python 3.11+** for the backend
- **Node.js 18+** for the frontend
- **Docker** (optional, for container deployment features)

## Quick Start

### 1. Start the Backend

```bash
cd backend

# Create virtual environment
python -m venv venv

# Activate (Windows PowerShell)
.\venv\Scripts\Activate.ps1

# Activate (Linux/Mac)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the server
python main.py
```

The API will be available at `http://localhost:8000`

### 2. Start the Frontend

```bash
cd frontend

# Install dependencies
npm install

# Run development server
npm run dev
```

The frontend will be available at `http://localhost:3000`

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/models` | GET | Get available models |
| `/api/technologies` | GET | Get container/VM technologies |
| `/api/status` | GET | Get current deployment status |
| `/api/container/start` | POST | Start container deployment |
| `/api/container/stop` | POST | Stop container deployment |
| `/api/vm/start` | POST | Start VM deployment |
| `/api/vm/stop` | POST | Stop VM deployment |
| `/api/metrics` | GET | Get metrics data |
| `/api/tests` | GET | Get available tests |
| `/api/tests/run` | POST | Run selected tests |
| `/ws/metrics` | WebSocket | Real-time metrics stream |

## Features

- **Deployment Cards**: Start/stop container or VM deployments with different technologies
- **Real-time Metrics**: Live CPU, Memory, and Latency monitoring via WebSocket
- **Metrics Visualization**: Comparative charts using Recharts
- **Test Suite**: Run performance comparison tests
- **Download Data**: Export raw metrics as CSV

## Technologies

### Backend
- FastAPI
- Uvicorn
- WebSocket support
- Docker SDK (optional)

### Frontend
- React 18
- TypeScript
- Vite
- Tailwind CSS
- Radix UI (shadcn/ui components)
- Recharts

## Development

### Backend Development

```bash
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend Development

```bash
cd frontend
npm run dev
```

The frontend dev server proxies `/api` and `/ws` requests to the backend automatically.

## Building for Production

### Frontend

```bash
cd frontend
npm run build
```

Build output will be in `frontend/dist/`.
