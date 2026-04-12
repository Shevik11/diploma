# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a diploma thesis project benchmarking **Small Language Models (SLMs)** across Docker containers vs Virtual Machines. It consists of a FastAPI backend, React frontend, and integrates with Ollama/llama.cpp/vLLM inference frameworks to collect performance, resource usage, and quality metrics.

## Development Commands

### Backend (FastAPI)
```bash
cd backend
pip install -r requirements.txt
python main.py
# or in dev mode:
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend (React + Vite)
```bash
cd frontend
npm install
npm run dev       # Dev server at http://localhost:3000
npm run build     # Production build to frontend/dist/
npm run lint      # ESLint check
```

### Docker (all services)
```bash
cd docker
docker-compose up                          # Core services (frontend, backend, ollama)
docker-compose --profile monitoring up    # Add cAdvisor
docker-compose --profile llama-cpp up    # Add llama.cpp
docker-compose --profile vllm up         # Add vLLM (requires NVIDIA GPU)
```

### Model Testing Scripts
```bash
# Windows PowerShell (per-model scripts)
.\scripts\make-llama.ps1 test
.\scripts\make-mistral.ps1 test
.\scripts\make-gemma.ps1 test
.\scripts\make-phi.ps1 test

# Linux/WSL equivalents
make -f scripts/Makefile-llama test
```

### Running Test Suites Directly
```bash
cd scripts/tests
python run_all_tests.py                   # All 17 test suites
python quality_test.py                   # Individual test
```

## Architecture

```
Frontend (React/Vite :3000)
    │  HTTP REST + WebSocket
    ▼
Backend (FastAPI :8000)
    │  Docker SDK / HTTP
    ├──► Ollama (:11434)     - Primary model server
    ├──► llama.cpp (:8080)   - CPU-optimized (GGUF, profile: llama-cpp)
    └──► vLLM (:8100)        - GPU-optimized (HuggingFace, profile: vllm)
```

**Data flow:** User selects model + technology → backend starts/pulls container → tests run as subprocesses against the inference API → metrics collected via psutil + httpx → results saved as JSON in `/results/` → WebSocket streams live metrics to frontend every 2s.

## Key Backend Endpoints (`backend/main.py`)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/models` | List available SLM models |
| GET | `/api/technologies` | Docker/Podman/etc options |
| GET | `/api/status` | Current deployment state |
| POST | `/api/container/start` | Deploy a container with model |
| POST | `/api/container/stop` | Stop running container |
| POST | `/api/vm/start` | Deploy VM instance |
| POST | `/api/vm/stop` | Stop VM |
| GET | `/api/tests` | List 17 available test suites |
| POST | `/api/tests/run` | Execute tests against deployment |
| GET | `/api/metrics` | Collected metrics data |
| WS | `/ws/metrics` | Real-time metrics stream |

## Test Suites (`scripts/tests/`)

17 test files covering: quality, performance, safety/robustness, stress, multilingual, summarization, context window, cost efficiency, and standard benchmarks (MMLU, GSM8K, TruthfulQA, HumanEval, reasoning).

## Supported Models

- **Phi**: 3.5 Mini, 4.8B, 3 Vision
- **Llama**: 3.2, 3.1
- **Mistral**: 7B, v0.3, 3B, 8B
- **Gemma**: 2B, 9B
- **Qwen**: 2.5 (0.5B–7B, including Coder variants)
- **StableLM**: 1.6B, 12B
- **Falcon**: 1B, 7B

## Project Documentation

The `agents/` directory contains canonical documentation for this project:
- `agents/source_of_truth.md` — Dissertation outline (Ukrainian)
- `agents/project_structure.md` — Directory layout and conventions
- `agents/technology_stack.md` — Full tech stack reference
- `agents/metrics.md` — Metrics collection guide
- `agents/testing.md` — Test requirements
- `agents/deployment_docker.md` / `deployment_vm.md` — Deployment guides

## Post-Change Validation

After making any code changes, verify the stack still works by running Docker and checking all services are healthy:

```bash
cd docker
docker-compose up --build -d
# Wait for services to start, then check health
docker-compose ps
# All services should show status "Up" or "running"

# Verify backend is responding
curl http://localhost:8000/api/status

# Verify frontend is serving
curl -o /dev/null -s -w "%{http_code}" http://localhost:3000
# Should return 200

# Check logs for errors
docker-compose logs backend
docker-compose logs frontend
```

If any service fails to start or returns errors, fix the issue before considering the change complete.

## Key Conventions

- Results are stored in `/results/` as JSON; never commit raw benchmark data
- The backend mounts `/var/run/docker.sock` to manage containers directly
- Frontend dev server proxies `/api` and `/ws` to the backend (configured in `vite.config.ts`)
- Python dependencies: `backend/requirements.txt` for runtime; `pyproject.toml` for analysis/processing tools
- The `.junie/` directory contains AI assistant memory/feedback — check it for project-specific corrections
