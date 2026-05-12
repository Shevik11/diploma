# Docker Deployment Guide: Ollama — From Install to Running Tests from Frontend

This guide describes every step to deploy an Ollama model on Docker and run benchmark tests **from the frontend UI**, collecting metrics and saving results as JSON.

---

## Architecture Overview

```
Frontend (React/Vite :5173)
    ↓ HTTP API calls
Backend (FastAPI :8000)
    ↓ Docker SDK + HTTP
Ollama Container (Docker :11434)
    ↓ loads model
Model weights (ollama_data volume)
    ↓ metrics saved to
results/ (JSON files)
```

---

## Prerequisites

- **Docker Desktop** installed and running (`docker --version`)
- **Python 3.11+** with project dependencies (`uv sync` or `pip install -r requirements.txt`)
- **Node.js 18+** for the frontend (`node --version`)
- Sufficient disk space for model weights (1–15 GB per model)
- Sufficient RAM (minimum 4 GB free for small models, 16 GB+ for 7B+ models)

---

## Step 1: Start the Ollama Docker Container

### Option A: Using docker-compose (recommended)

```bash
cd docker
docker compose up -d ollama
```

This uses `docker/docker-compose.yml` which configures:
- Container name: `ollama`
- Port: `11434:11434`
- Volume: `ollama_data` for persistent model storage
- Memory limit: 8 GB

### Option B: Manual docker run

```bash
docker run -d --name ollama -p 11434:11434 -v ollama_data:/root/.ollama ollama/ollama
```

### Option C: From the Frontend UI

The frontend "Start" button in the Container Deployment Card calls the backend API which automatically:
1. Pulls `ollama/ollama:latest` image if needed
2. Creates and starts the container
3. Waits for the Ollama API to be ready
4. Pulls the selected model

---

## Step 2: Pull a Model

### From CLI

```bash
docker exec ollama ollama pull phi3:mini
docker exec ollama ollama pull gemma2:2b
docker exec ollama ollama pull llama3.2:1b
docker exec ollama ollama pull mistral:7b
docker exec ollama ollama pull qwen2.5:0.5b
```

### From Frontend

When you click **Start** in the Container Deployment Card with a model selected, the backend automatically pulls the model via the Ollama API (`POST /api/pull`).

### Verify models are loaded

```bash
curl http://localhost:11434/api/tags
```

---

## Step 3: Verify the Model is Running

### Health check

```bash
curl http://localhost:11434/api/tags
```

### Test inference

```bash
curl http://localhost:11434/api/generate -d '{"model": "phi3:mini", "prompt": "Hello", "stream": false}'
```

**Expected:** A JSON response with generated text. If you get a response, the model is loaded and ready.

---

## Step 4: Start the Backend

The FastAPI backend connects to the Ollama container and exposes all APIs for the frontend.

```bash
# From project root
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

Key backend endpoints for Ollama:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/container/start` | POST | Start Ollama container + pull model |
| `/api/container/stop` | POST | Stop Ollama container |
| `/api/benchmarks/ollama/status` | GET | Check Ollama connection + list models |
| `/api/benchmarks/categories` | GET | List benchmark prompt categories |
| `/api/benchmarks/run` | POST | Run benchmark suite on a model |
| `/api/benchmarks/status` | GET | Get running benchmark progress |
| `/api/benchmarks/results` | GET | List all saved JSON results |
| `/api/benchmarks/results/{filename}` | GET | Get specific result file |
| `/api/models` | GET | List available models |
| `/api/status` | GET | Get container/VM deployment state |
| `/ws/metrics` | WS | Real-time metrics stream |

---

## Step 5: Start the Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend runs at `http://localhost:5173` and proxies API calls to the backend at `:8000`.

---

## Step 6: Run Tests from the Frontend

### 6.1 Deploy the Model

1. Open `http://localhost:5173` in your browser
2. **Select a model** from the dropdown (e.g., "Phi-3 Mini (3.8B)")
3. In the **Container Deployment Card**, select technology "Ollama (Docker)"
4. Click **Start** — this will:
   - Start the Ollama Docker container (if not running)
   - Pull the selected model
   - Show real-time CPU/Memory/Latency metrics

### 6.2 Run Benchmarks

1. Scroll down to the **Benchmark Runner** section
2. The Ollama connection status indicator shows green when connected
3. Select benchmark categories (short, medium, long, code, reasoning)
4. Configure options:
   - **Warm up**: pre-load model before benchmarking (recommended)
   - **Runs per prompt**: number of iterations per prompt (default: 1)
5. Click **Run Benchmark**
6. Watch real-time progress bar and status updates
7. When complete, results are automatically saved to `results/` as JSON

### 6.3 View Results

- The **Benchmark Runner** section shows a summary table after each run
- Previous results are listed and can be loaded for comparison
- JSON files in `results/` follow this naming: `benchmark_{model}_{platform}_{timestamp}.json`

---

## Step 7: JSON Output Format

All benchmark results are saved as JSON in `results/`:

```
results/
  benchmark_phi3_mini_docker_20260404_153000.json
  benchmark_gemma2_2b_docker_20260404_154500.json
  ...
```

Each JSON file schema:

```json
{
  "model": "phi3:mini",
  "platform": "docker",
  "technology": "ollama",
  "timestamp": "2026-04-04T15:30:00",
  "system_info": {
    "cpu_count": 12,
    "cpu_freq_mhz": 3600,
    "memory_total_gb": 32,
    "platform": "docker"
  },
  "results": [
    {
      "category": "short",
      "run": 1,
      "prompt": "What is 2+2?",
      "response": "2+2 equals 4.",
      "inference": {
        "first_token_latency_ms": 120.5,
        "total_duration_ms": 850.3,
        "tokens_generated": 15,
        "tokens_per_second": 28.5,
        "prompt_tokens": 8,
        "model_load_time_ms": null
      },
      "resources": {
        "cpu_percent": 45.2,
        "memory_percent": 38.1,
        "memory_used_mb": 2048,
        "memory_peak_mb": 2560
      },
      "success": true,
      "error": null
    }
  ],
  "summary": {
    "total_prompts": 14,
    "successful": 14,
    "failed": 0,
    "success_rate": 100.0,
    "avg_tokens_per_second": 28.5,
    "avg_latency_ms": 920.0,
    "avg_first_token_latency_ms": 135.2,
    "total_tokens_generated": 1250,
    "avg_cpu_percent": 42.3,
    "avg_memory_percent": 36.8
  }
}
```

This JSON format is designed for future graph visualization and cross-model comparison.

---

## Step 8: Collect Additional Metrics (Optional)

For deeper container-level metrics, start cAdvisor alongside Ollama:

```bash
cd docker
docker compose --profile monitoring up -d
```

This starts cAdvisor on port `8081` collecting per-container CPU, memory, network, and disk I/O.

| Tool | What It Collects | Access |
|------|------------------|--------|
| `docker stats` | CPU %, memory, network I/O | CLI |
| `cAdvisor` | Per-container detailed metrics | `http://localhost:8081` |
| `psutil` (Python) | Host-level CPU, RAM, disk I/O | Built into benchmarks |
| Backend WebSocket | Real-time CPU/memory stream | Frontend auto-connects |

See [`metrics.md`](./metrics.md) for the full list of metrics to collect.

---

## Supported Models

All models use actual Ollama tags:

| Model | Ollama Tag | Size |
|-------|-----------|------|
| Phi-3 Mini | `phi3:mini` | 3.8B |
| Llama 3.2 | `llama3.2:1b` / `llama3.2:3b` | 1B / 3B |
| Gemma 2 | `gemma2:2b` | 2B |
| Mistral | `mistral:7b` | 7B |
| Qwen 2.5 | `qwen2.5:0.5b` / `qwen2.5:1.5b` / `qwen2.5:3b` | 0.5B–3B |

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Container won't start | Check `docker logs ollama` for errors |
| Model download fails | Verify disk space, check network connectivity |
| Out of memory | Use a smaller model (qwen2.5:0.5b) or increase Docker memory limit |
| Ollama status shows "disconnected" in frontend | Ensure Ollama container is running and backend is started |
| Benchmark fails with "Cannot connect to Ollama" | Start the Ollama container first (Step 1), then verify with `curl http://localhost:11434/api/tags` |
| Frontend can't reach backend | Check backend is running on port 8000, check CORS settings |
| Slow first response | Normal for cold start — model is loading into memory |
| WebSocket metrics not updating | Refresh the page, check backend console for errors |

---

## Quick Reference: Full Command Sequence

```bash
# 1. Start Ollama container
cd docker && docker compose up -d ollama

# 2. Pull a model
docker exec ollama ollama pull phi3:mini

# 3. Verify model is ready
curl http://localhost:11434/api/generate -d '{"model": "phi3:mini", "prompt": "test", "stream": false}'

# 4. Start backend
cd .. && uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

# 5. Start frontend
cd frontend && npm install && npm run dev

# 6. Open browser → http://localhost:5173
# 7. Select model → Start container → Run Benchmark
# 8. Results saved to results/ as JSON
```

---

## Related Files

| File | Purpose |
|------|---------|
| `docker/docker-compose.yml` | Ollama + cAdvisor container orchestration |
| `docker/frameworks/ollama/Dockerfile` | Ollama Docker image with health check |
| `backend/main.py` | FastAPI backend — container management + benchmark API |
| `backend/benchmarks.py` | OllamaBenchmark class — inference + metrics collection |
| `frontend/app/App.tsx` | Main UI — model selection, deployment cards, benchmark runner |
| `frontend/app/components/benchmark-runner.tsx` | Benchmark UI component |
| `frontend/app/services/api.ts` | Frontend API service — all backend calls |
| `results/` | JSON benchmark output directory |
| `agents/metrics.md` | Full metrics reference |
| `agents/testing.md` | Test types reference |
