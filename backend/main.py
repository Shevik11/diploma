from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Literal, Callable
from dataclasses import asdict
import asyncio
import subprocess
import sys
import random
import os
import time
import json
import math
import re
import logging
import docker
import httpx
from datetime import datetime
from contextlib import asynccontextmanager
from pathlib import Path
from benchmarks import (
    OllamaBenchmark,
    run_benchmark,
    save_benchmark_results,
    list_benchmark_results,
    load_benchmark_results,
    BENCHMARK_PROMPTS,
)

logger = logging.getLogger("uvicorn.error")

# Initialize Docker client
try:
    docker_client = docker.from_env()
except Exception:
    docker_client = None


# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        # Tolerate already-removed connections (e.g. dropped by `broadcast`
        # after a send failure) so callers do not have to guard with try/except.
        try:
            self.active_connections.remove(websocket)
        except ValueError:
            pass

    async def broadcast(self, message: dict):
        # Track connections whose send raises so we can drop them at the end
        # of the iteration. Otherwise dead sockets accumulate in the list and
        # the broadcast loop keeps trying to send to them every tick.
        dead: list[WebSocket] = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                dead.append(connection)
        for connection in dead:
            try:
                self.active_connections.remove(connection)
            except ValueError:
                pass


manager = ConnectionManager()

# Background task for metrics
metrics_task = None


async def broadcast_metrics():
    """Background task to broadcast metrics to all connected clients"""
    while True:
        if manager.active_connections:
            metrics = {
                "type": "metrics",
                "data": {
                    "container": deployment_state["container"],
                    "vm": deployment_state["vm"],
                    "timestamp": datetime.now().isoformat()
                }
            }
            await manager.broadcast(metrics)
        await asyncio.sleep(2)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global metrics_task
    metrics_task = asyncio.create_task(broadcast_metrics())
    yield
    # Shutdown
    if metrics_task:
        metrics_task.cancel()


app = FastAPI(title="SLM Deployment Control Panel API", lifespan=lifespan)

# CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:3000", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global state
deployment_state = {
    "container": {
        "status": "idle",
        "technology": None,
        "model": None,
        "cpu": 0,
        "memory": 0,
        "latency": 0,
        "ram_gb": None,
        "cpu_cores": None,
    },
    "vm": {
        "status": "idle",
        "technology": None,
        "model": None,
        "cpu": 0,
        "memory": 0,
        "latency": 0,
        "ram_gb": None,
        "cpu_cores": None,
    }
}

metrics_history = {
    "container": [],
    "vm": []
}

pulling_models: set[str] = set()

# Models
DEFAULT_MODELS = [
    {"value": "phi-3-mini", "label": "Phi-3 Mini (3.8B)"},
    {"value": "llama-3.2-1b", "label": "Llama 3.2 (1B)"},
    {"value": "llama-3.2-3b", "label": "Llama 3.2 (3B)"},
    {"value": "gemma-2b", "label": "Gemma 2B"},
    {"value": "mistral-7b", "label": "Mistral 7B"},
    {"value": "qwen2.5:0.5b", "label": "Qwen 2.5 (0.5B)"},
    {"value": "qwen2.5:1.5b", "label": "Qwen 2.5 (1.5B)"},
    {"value": "qwen2.5:3b", "label": "Qwen 2.5 (3B)"},
    {"value": "qwen2.5:7b", "label": "Qwen 2.5 (7B)"},
    {"value": "qwen2.5-coder:1.5b", "label": "Qwen 2.5 Coder (1.5B)"},
    {"value": "qwen2.5-coder:7b", "label": "Qwen 2.5 Coder (7B)"},
]

MODEL_ALIASES = {
    "phi-3-mini": "phi3:mini",
    "llama-3.2-1b": "llama3.2:1b",
    "llama-3.2-3b": "llama3.2:3b",
    "gemma-2b": "gemma2:2b",
    "mistral-7b": "mistral:7b",
}
MODEL_ALIASES_REVERSE = {v: k for k, v in MODEL_ALIASES.items()}

MODEL_LABELS = {m["value"]: m["label"] for m in DEFAULT_MODELS}
for alias, canonical in MODEL_ALIASES.items():
    if alias in MODEL_LABELS:
        MODEL_LABELS.setdefault(canonical, MODEL_LABELS[alias])


# ---------------------------------------------------------------------------
# Feasibility check (do not run a benchmark when the container can't even
# load the model — those runs always end up as 0/N success files and pollute
# rankings).  Calibrated against the actual results in backend/results:
#   * qwen2.5-coder:1.5b @ 1 GB / 1 CPU  -> 14/14 success  (must be feasible)
#   * qwen2.5-coder:1.5b @ 1 GB / >=2 CPU -> 0/14 success  (must be infeasible)
#   * qwen2.5-coder:7b   @ 1 GB / any CPU -> 0/14 success  (must be infeasible)
# ---------------------------------------------------------------------------

# Manual overrides for models whose name does not embed parameter count.
_PARAM_BILLION_OVERRIDES = {
    "phi-3-mini": 3.8,
    "phi3:mini": 3.8,
}


def _model_param_billion(model: str) -> float | None:
    """Best-effort parse of parameter count in billions from a model id."""
    if not model:
        return None
    key = model.lower()
    if key in _PARAM_BILLION_OVERRIDES:
        return _PARAM_BILLION_OVERRIDES[key]
    # Match patterns like "1.5b", "7b", "0.5b" (allow trailing punctuation).
    m = re.search(r"(\d+(?:\.\d+)?)\s*b(?![a-z0-9])", key)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None


# Approx GB-per-billion-parameters for common GGUF quantizations and
# floating-point dtypes.  Q4_K_M is the default for Ollama/llama.cpp and
# matches the 0.6 baseline that the rest of the heuristic was calibrated
# against.  Used only when the model id carries an explicit quant tag
# (e.g. `qwen2.5-coder:7b-instruct-q8_0`); otherwise we assume Q4_K_M.
_QUANT_PER_B_GB = {
    "q2_k":   0.40,
    "q3_k_s": 0.45,
    "q3_k_m": 0.50,
    "q3_k_l": 0.55,
    "q4_0":   0.58,
    "q4_1":   0.62,
    "q4_k_s": 0.58,
    "q4_k_m": 0.60,
    "q5_0":   0.70,
    "q5_1":   0.75,
    "q5_k_s": 0.70,
    "q5_k_m": 0.72,
    "q6_k":   0.85,
    "q8_0":   1.10,
    "fp16":   2.00,
    "f16":    2.00,
    "bf16":   2.00,
    "fp32":   4.00,
    "f32":    4.00,
}


def _quant_per_b_gb(model: str) -> float:
    """Return GB-per-billion-parameters for the quant in the model id.

    Looks for any of the keys in `_QUANT_PER_B_GB` as a token in the
    model id (case-insensitive, separated by `:`/`-`/`_`).  Falls back
    to the Q4_K_M baseline (0.60) when no tag is present.
    """
    if not model:
        return 0.60
    key = model.lower()
    # Normalize separators so e.g. "q4-k-m" / "q4_k_m" / "q4.k.m" all hit.
    norm = re.sub(r"[:\-./]", "_", key)
    # Try the longest tags first so `q4_k_m` wins over `q4_k_s`/`q4`.
    for tag in sorted(_QUANT_PER_B_GB, key=len, reverse=True):
        if re.search(rf"(?:^|_){re.escape(tag)}(?:$|_)", norm):
            return _QUANT_PER_B_GB[tag]
    return 0.60


def _thread_count(cpu_cores: float | None) -> int:
    """Convert a (possibly fractional) CPU share into a worker-thread count.

    `int(1.5)` would silently classify a 1.5-core config as single-thread
    and underestimate RAM; rounding up matches what GGML/Ollama actually
    spawn for fractional shares.
    """
    return max(math.ceil(cpu_cores or 1), 1)


def _estimate_required_ram_gb(model: str, cpu_cores: float | None) -> int:
    """Estimate the minimum container RAM (in GB) required for a config.

    The model is approximated as Q4_K_M (~0.6 GB per billion parameters)
    by default, or scaled per the explicit quant tag carried in the model
    id (`q8_0`, `fp16`, ...).  With a single worker thread, mmap'd
    weights + a small runtime overhead is enough.  With multiple worker
    threads, GGML allocates one scratch arena per thread, which inflates
    the resident set well past the on-disk weight size; we apply a 15%
    safety margin on top to keep the heuristic on the conservative side
    (false-positive infeasible is recoverable, OOM at load is not).
    """
    b = _model_param_billion(model)
    if b is None:
        return 1  # Unknown model: assume the smallest tier.
    per_b = _quant_per_b_gb(model)
    weights_gb = b * per_b
    threads = _thread_count(cpu_cores)
    if threads <= 1:
        # Single-threaded run: Ollama mmap's weights on demand so the
        # resident set is roughly 85 % of the file size, not the full
        # weight size.  Calibrated against phi3:mini (3.8 B, 2.28 GB
        # weights) running successfully inside a 2 GB container.
        required = weights_gb * 0.85
    else:
        # Per-thread scratch arenas + thread-pool bookkeeping. The 1.35
        # multiplier and 0.10/thread term are calibrated against the
        # 1.5b results (1c passes at 1 GB, 2c fails at 1 GB but passes
        # at 2 GB).  The trailing 1.15× factor is an explicit safety
        # margin that keeps borderline configs (where the real RSS
        # overshoots the calibration by a few percent) on the
        # infeasible side.
        required = (weights_gb * 1.35 + 0.10 * threads) * 1.15
    return max(1, math.ceil(required))


def _check_feasibility(
    model: str, ram_gb: int | None, cpu_cores: float | None
) -> tuple[bool, str | None, int]:
    """Return (feasible, reason_if_infeasible, required_ram_gb)."""
    required = _estimate_required_ram_gb(model, cpu_cores)
    if ram_gb is None:
        return True, None, required
    if ram_gb >= required:
        return True, None, required
    threads = _thread_count(cpu_cores)
    reason = (
        f"Insufficient RAM: {ram_gb} GB cannot load '{model}' "
        f"with {threads} worker thread{'s' if threads > 1 else ''} "
        f"(needs ~{required} GB)."
    )
    return False, reason, required


def _save_infeasible_summary(
    model: str,
    technology: str,
    platform: str,
    ram_gb: int | None,
    cpu_cores: float | None,
    reason: str,
    required_ram_gb: int,
) -> str:
    """Persist a stub result file for a config we refuse to run.

    The shape is compatible with `list_benchmark_results` so the frontend
    sees the entry in its listing, plus an `infeasible` block that lets
    the leaderboard sort it to the bottom and explain why.
    """
    from benchmarks import RESULTS_DIR  # local import: avoid cycles

    timestamp_iso = datetime.now().isoformat()
    timestamp_slug = datetime.now().strftime("%Y%m%d_%H%M%S")
    model_slug = model.replace(":", "_").replace("/", "_").replace(" ", "-")
    ram_part = f"{ram_gb}GB" if ram_gb else "noRAMlimit"
    cpu_part = f"{cpu_cores}cores" if cpu_cores else "noCPUlimit"
    filename = f"{model_slug}_{ram_part}_{cpu_part}_{technology}_{platform}_{timestamp_slug}.json"
    filepath = RESULTS_DIR / filename

    payload = {
        "model": model,
        "platform": platform,
        "technology": technology,
        "timestamp": timestamp_iso,
        # Spec status string (functionality.md): the run never started
        # because pre-flight rejected it for lack of RAM.
        "status": "not_enough_resources",
        # Start/finish timestamps for an instantaneous "skipped" record:
        # both equal the moment the decision was made.
        "started_at": timestamp_iso,
        "finished_at": timestamp_iso,
        "ram_gb": ram_gb,
        "cpu_cores": cpu_cores,
        "system_info": {
            "platform": platform,
            "timestamp": timestamp_iso,
        },
        "results": [],
        "test_results": [],
        "summary": {
            "total_prompts": 0,
            "successful": 0,
            "failed": 0,
            "success_rate": 0,
            "avg_tokens_per_second": 0,
            "avg_latency_ms": 0,
            "avg_first_token_latency_ms": 0,
            "total_tokens_generated": 0,
            "avg_cpu_percent": 0,
            "avg_memory_percent": 0,
        },
        "infeasible": {
            "reason": reason,
            "required_ram_gb": required_ram_gb,
            "skipped": True,
        },
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return str(filepath)


CONTAINER_TECHNOLOGIES = [
    {"value": "docker", "label": "Docker"},
    {"value": "podman", "label": "Podman"},
    {"value": "containerd", "label": "Containerd"},
]

VM_TECHNOLOGIES = [
    {"value": "virtualbox", "label": "VirtualBox"},
    {"value": "vmware", "label": "VMware"},
    {"value": "kvm", "label": "KVM"},
    {"value": "hyperv", "label": "Hyper-V"},
]


# Pydantic models
class DeploymentRequest(BaseModel):
    model: str
    technology: str
    ram_gb: int | None = None
    cpu_cores: float | None = None
    ram_gb: int | None = None
    cpu_cores: float | None = None


class TestRequest(BaseModel):
    test_ids: list[str]
    model: str = ""
    technology: str = "ollama"


class TestResult(BaseModel):
    id: str
    name: str
    status: Literal["pending", "running", "passed", "failed"]
    duration: Optional[float] = None


# Test definitions — all 17 test suites
TESTS = {
    "quality": {
        "name": "Quality Test",
        "script": "quality_test.py",
        "duration_range": (30, 120),
    },
    "advanced_quality": {
        "name": "Advanced Quality Test",
        "script": "advanced_quality_test.py",
        "duration_range": (30, 120),
    },
    "performance": {
        "name": "Performance Test",
        "script": "performance_test.py",
        "duration_range": (20, 60),
    },
    "safety_robustness": {
        "name": "Safety & Robustness Test",
        "script": "safety_robustness_test.py",
        "duration_range": (30, 120),
    },
    "stress_consistency": {
        "name": "Stress & Consistency Test",
        "script": "stress_and_consistency_test.py",
        "duration_range": (60, 300),
    },
    "hard_tests": {
        "name": "Hard Tests",
        "script": "hard_tests.py",
        "duration_range": (30, 120),
        "timeout": 1200,
    },
    "multilingual": {
        "name": "Multilingual Test",
        "script": "multilingual_test.py",
        "duration_range": (30, 120),
    },
    "summarization": {
        "name": "Summarization Test",
        "script": "summarization_test.py",
        "duration_range": (30, 120),
    },
    "context_window": {
        "name": "Context Window Test",
        "script": "context_window_test.py",
        "duration_range": (30, 180),
    },
    "cost_efficiency": {
        "name": "Cost Efficiency Test",
        "script": "cost_efficiency_test.py",
        "duration_range": (30, 120),
    },
    "benchmark_mmlu": {
        "name": "MMLU Benchmark",
        "script": "benchmark_mmlu_test.py",
        "duration_range": (30, 120),
    },
    "benchmark_reasoning": {
        "name": "Reasoning Benchmark (ARC / HellaSwag / Winogrande)",
        "script": "benchmark_reasoning_test.py",
        "duration_range": (30, 120),
    },
    "benchmark_gsm8k": {
        "name": "GSM8K Math Benchmark",
        "script": "benchmark_gsm8k_test.py",
        "duration_range": (30, 120),
    },
    "benchmark_truthfulqa": {
        "name": "TruthfulQA Benchmark",
        "script": "benchmark_truthfulqa_test.py",
        "duration_range": (30, 120),
    },
    "benchmark_humaneval": {
        "name": "HumanEval Code Benchmark",
        "script": "benchmark_humaneval_test.py",
        "duration_range": (30, 180),
    },
    "compare_models": {
        "name": "Compare Models",
        "script": "compare_models.py",
        "duration_range": (60, 300),
    },
    "cold_start": {
        "name": "Cold Start Test",
        "script": "cold_start_test.py",
        "duration_range": (60, 300),
    },
    "resource_usage": {
        "name": "Resource Usage Test (RAM / CPU)",
        "script": "resource_usage_test.py",
        "duration_range": (60, 300),
    },
    "oom_detection": {
        "name": "OOM Detection & Boundary Test",
        "script": "oom_detection_test.py",
        "duration_range": (120, 600),
        "timeout": 1200,
    },
    "ram_boundary": {
        "name": "RAM Boundary Sweep (§3.3)",
        "script": "ram_boundary_test.py",
        "duration_range": (180, 900),
    },
    "config_matrix": {
        "name": "Config Matrix (§3.2)",
        "script": "config_matrix_test.py",
        "duration_range": (300, 1800),
    },
    "vram_monitor": {
        "name": "VRAM Monitor (§4.2)",
        "script": "vram_monitor_test.py",
        "duration_range": (30, 180),
    },
    "cloud_cost": {
        "name": "Cloud Cost Calculator (§6)",
        "script": "cloud_cost_calculator.py",
        "duration_range": (30, 180),
    },
    "quant_compare": {
        "name": "Quantization Compare (Q4 vs Q8, §2.1)",
        "script": "quantization_compare_test.py",
        "duration_range": (60, 300),
    },
    "run_all": {
        "name": "Run All Tests",
        "script": "run_all_tests.py",
        "duration_range": (300, 1800),
    },
}

SCRIPTS_DIR = Path(__file__).parent / "scripts" / "tests"
if not SCRIPTS_DIR.exists():
    _parent_scripts = Path(__file__).parent.parent / "scripts" / "tests"
    if _parent_scripts.exists():
        SCRIPTS_DIR = _parent_scripts

if not SCRIPTS_DIR.exists():
    _parent_scripts = Path(__file__).parent.parent / "scripts" / "tests"
    if _parent_scripts.exists():
        SCRIPTS_DIR = _parent_scripts

# Same reasoning as in benchmarks.py: always anchor to backend/results so
# the API and the on-disk save path agree across uvicorn launch styles.
RESULTS_DIR = Path(__file__).parent / "results"
if not any(RESULTS_DIR.glob("*.json")):
    _parent_results = Path(__file__).parent.parent / "results"
    if any(_parent_results.glob("*.json")):
        RESULTS_DIR = _parent_results

# Technology to port mapping
TECH_PORTS = {
    "ollama": 11434,
    "llama-cpp": 8080,
    "vllm": 8100,
}


def _get_model_name(model: str, technology: str) -> str:
    """Map frontend model value to the actual model name for the technology."""
    if technology == "ollama":
        return MODEL_ALIASES.get(model, model)
    return model


def _to_frontend_model_name(model: str, technology: str) -> str:
    """Map provider model name back to frontend value."""
    if technology == "ollama":
        return MODEL_ALIASES_REVERSE.get(model, model)
    return model


def _to_model_label(model_value: str) -> str:
    """Get display label for model value."""
    return MODEL_LABELS.get(model_value, model_value)


def _ollama_base_url() -> str:
    """Get Ollama base URL, preferring OLLAMA_URL env var then auto-detecting Docker vs host."""
    url = os.environ.get("OLLAMA_URL")
    if url:
        return url.rstrip("/")
    running_in_docker = os.path.exists("/.dockerenv")
    if running_in_docker:
        host = os.environ.get("SLM_TEST_HOST", "ollama")
    else:
        # Use 127.0.0.1 rather than localhost: on Windows localhost can resolve
        # to ::1 (IPv6) which fails against Docker's IPv4 port binding.
        host = os.environ.get("SLM_TEST_HOST", "127.0.0.1")
    return f"http://{host}:{TECH_PORTS['ollama']}"


async def _list_ollama_models() -> list[str]:
    """Fetch installed models from Ollama."""
    base_url = _ollama_base_url()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{base_url}/api/tags")
            if response.status_code != 200:
                return []
            data = response.json()
            return [m.get("name") for m in data.get("models", []) if m.get("name")]
    except Exception as e:
        logger.warning(f"Failed to fetch Ollama models from {base_url}: {type(e).__name__}: {e}")
        return []


async def _pull_ollama_model(model: str):
    """Pull a model from Ollama registry and wait until it is available locally."""
    timeout = httpx.Timeout(timeout=3600.0, connect=10.0)
    base_url = _ollama_base_url()
    url = f"{base_url}/api/pull"

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json={"model": model, "stream": False})
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Cannot reach Ollama at {base_url} — {type(e).__name__}: {e}",
        ) from e

    if response.status_code != 200:
        detail = response.text[:500] if response.text else f"HTTP {response.status_code}"
        raise HTTPException(status_code=502, detail=f"Ollama pull failed for '{model}': {detail}")

    payload = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
    if isinstance(payload, dict) and payload.get("error"):
        raise HTTPException(status_code=400, detail=f"Ollama pull failed for '{model}': {payload['error']}")

    available_models = await _list_ollama_models()
    if model not in available_models:
        raise HTTPException(status_code=500, detail=f"Model '{model}' was pulled but is still unavailable")


async def _resolve_and_validate_model(
    model: str,
    technology: str,
    auto_pull: bool = False,
    pull_status_callback: Optional[Callable[[str], None]] = None,
) -> str:
    """Resolve frontend model value and ensure it is available for current technology."""
    if not model:
        raise HTTPException(status_code=400, detail="Model is required")

    resolved = _get_model_name(model, technology)
    if technology != "ollama":
        return resolved

    available_models = await _list_ollama_models()
    if not available_models:
        raise HTTPException(status_code=503, detail="Cannot connect to Ollama or no models are installed")

    if resolved not in available_models:
        if not auto_pull:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Model '{resolved}' is not installed in Ollama. "
                    f"Install it first: docker exec -it ollama ollama pull {resolved}"
                ),
            )

        if pull_status_callback:
            pull_status_callback(f"Pulling model '{resolved}'...")
        await _pull_ollama_model(resolved)
        if pull_status_callback:
            pull_status_callback(f"Model '{resolved}' pulled successfully")

    return resolved


def _build_model_catalog(installed_models: list[str]) -> list[dict]:
    """Build full model catalog and mark what is installed in Ollama."""
    installed_set = set(installed_models)
    models = []
    seen = set()

    for model in DEFAULT_MODELS:
        model_value = model["value"]
        resolved = _get_model_name(model_value, "ollama")
        models.append({
            "value": model_value,
            "label": model["label"],
            "installed": resolved in installed_set,
        })
        seen.add(model_value)

    # Include extra installed models not listed in defaults.
    for provider_model in sorted(installed_set):
        frontend_model = _to_frontend_model_name(provider_model, "ollama")
        if frontend_model in seen:
            continue
        models.append({
            "value": frontend_model,
            "label": _to_model_label(frontend_model),
            "installed": True,
        })
        seen.add(frontend_model)

    return models


def _set_container_running_state(model: str, technology: str, ram_gb: int | None = None, cpu_cores: float | None = None):
    """Update container deployment state to running with fresh metrics."""
    deployment_state["container"]["status"] = "running"
    deployment_state["container"]["technology"] = technology
    deployment_state["container"]["model"] = model
    deployment_state["container"]["message"] = ""
    deployment_state["container"]["ram_gb"] = ram_gb
    deployment_state["container"]["cpu_cores"] = cpu_cores

    deployment_state["container"]["cpu"] = round(random.uniform(10, 40), 1)
    deployment_state["container"]["memory"] = round(random.uniform(20, 50), 1)
    deployment_state["container"]["latency"] = round(random.uniform(20, 50), 0)

    # Apply Docker resource limits if requested
    if docker_client and (ram_gb or cpu_cores):
        container_name_map = {"ollama": "ollama", "llama-cpp": "llama-cpp", "vllm": "vllm"}
        cname = container_name_map.get(technology)
        if cname:
            try:
                container = docker_client.containers.get(cname)
                update_kwargs = {}
                if ram_gb:
                    update_kwargs["mem_limit"] = f"{ram_gb}g"
                    update_kwargs["memswap_limit"] = f"{ram_gb}g"
                if cpu_cores:
                    update_kwargs["cpu_quota"] = int(cpu_cores * 100000)
                    update_kwargs["cpu_period"] = 100000
                container.update(**update_kwargs)
                logger.info(f"Applied limits to '{cname}': {update_kwargs}")
            except Exception as e:
                logger.warning(f"Could not apply resource limits to '{cname}': {e}")


async def _pull_and_start_container(model: str, technology: str, ram_gb: int | None = None, cpu_cores: float | None = None):
    """Pull missing Ollama model in background and switch container to running."""
    resolved = _get_model_name(model, technology)
    try:
        await _pull_ollama_model(resolved)
        _set_container_running_state(model, technology, ram_gb, cpu_cores)
        deployment_state["container"]["message"] = f"Model '{resolved}' is ready"
    except Exception as e:
        deployment_state["container"]["status"] = "idle"
        deployment_state["container"]["technology"] = None
        deployment_state["container"]["model"] = None
        deployment_state["container"]["cpu"] = 0
        deployment_state["container"]["memory"] = 0
        deployment_state["container"]["latency"] = 0
        deployment_state["container"]["message"] = f"Pull failed: {e}"
        logger.error(f"Failed to pull model '{resolved}': {e}")
    finally:
        pulling_models.discard(resolved)


def _get_test_env(technology: str, master_file: str | None = None) -> dict:
    """Get environment variables for test subprocesses.

    Parameters
    ----------
    technology:
        ``ollama`` / ``llama-cpp`` / ``vllm`` — controls the host name the
        test scripts target.
    master_file:
        Optional path to the run's master JSON file. When provided, sets
        ``SLM_OUTPUT_FILE`` so test scripts using
        ``scripts/tests/result_utils.save_results()`` will append to it
        directly under ``test_sections[<key>]``. The legacy "individual
        file + log-driven merge" path in ``_load_test_details_from_logs``
        keeps working for tests that haven't migrated yet.
    """
    env = os.environ.copy()
    # When backend runs inside Docker, services are reached by container hostname.
    # When running on the host, they are reachable via localhost (port-mapped).
    running_in_docker = os.path.exists("/.dockerenv")
    if running_in_docker:
        host_map = {"ollama": "ollama", "llama-cpp": "llama-cpp", "vllm": "vllm"}
    else:
        # Use 127.0.0.1 instead of localhost: on Windows, localhost can resolve
        # to ::1 (IPv6) which fails against Docker's IPv4 port binding.
        host_map = {"ollama": "127.0.0.1", "llama-cpp": "127.0.0.1", "vllm": "127.0.0.1"}
    env["SLM_TEST_HOST"] = host_map.get(technology, "127.0.0.1")
    env["PYTHONUTF8"] = "1"
    if master_file:
        env["SLM_OUTPUT_FILE"] = str(master_file)
    return env


def _run_test_subprocess(
    script_path: str,
    model_name: str,
    port: int,
    timeout: int = 600,
    technology: str = "ollama",
    master_file: str | None = None,
) -> dict:
    """Run a test script via subprocess.run (synchronous, for use in executor)."""
    cmd = [sys.executable, script_path, model_name, str(port)]
    env = _get_test_env(technology, master_file=master_file)
    logger.info(f"Running test command: {' '.join(cmd)} (host={env.get('SLM_TEST_HOST')})")
    start_time = time.time()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=str(SCRIPTS_DIR),
            env=env,
        )
        duration = time.time() - start_time
        status = "passed" if result.returncode == 0 else "failed"
        details = _load_test_details_from_logs(result.stdout or "", result.stderr or "")
        logger.info(f"Test finished: {script_path} -> {status} in {duration:.1f}s")
        if result.returncode != 0 and result.stderr:
            logger.error(f"Test stderr [{Path(script_path).name}]: {result.stderr[:1000]}")
        return {
            "returncode": result.returncode,
            "stdout": result.stdout[-2000:] if result.stdout else "",
            "stderr": result.stderr[-2000:] if result.stderr else "",
            "duration": duration,
            "status": status,
            "details": details,
        }
    except subprocess.TimeoutExpired:
        duration = time.time() - start_time
        logger.warning(f"Test timed out: {script_path} after {timeout}s")
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": f"Timeout after {timeout}s",
            "duration": duration,
            "status": "timeout",
            "details": [],
        }
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"Test error: {script_path} -> {e}")
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": str(e),
            "duration": duration,
            "status": "error",
            "details": [],
        }


def _create_fallback_result_file(
    model: str,
    platform: str,
    technology: str,
    ram_gb: int | None,
    cpu_cores: float | None,
) -> str:
    """Create an empty master result file when Phase 1 produced nothing.

    Without this file, `_save_test_results` short-circuits (it only writes when
    `result_filepath` is truthy), so all Phase 2 test results would be lost
    when the inference benchmark fails for any reason. Naming mirrors
    `save_benchmark_results` so listings still pick it up.
    """
    from benchmarks import RESULTS_DIR as _BR_RESULTS_DIR

    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        timestamp_iso = datetime.now().isoformat()
        model_slug = model.replace(":", "_").replace("/", "_").replace(" ", "-")
        ram_part = f"{ram_gb}GB" if ram_gb else "noRAMlimit"
        cpu_part = f"{cpu_cores}cores" if cpu_cores else "noCPUlimit"
        filename = f"{model_slug}_{ram_part}_{cpu_part}_{technology}_{platform}_{timestamp}.json"
        _BR_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        filepath = _BR_RESULTS_DIR / filename
        payload = {
            "model": model,
            "platform": platform,
            "technology": technology,
            "timestamp": timestamp_iso,
            # Spec status: Phase 1 inference benchmark threw an exception,
            # so the run is recorded as failed (Phase 2 may still attach
            # test_results to this same file).
            "status": "failed",
            "started_at": timestamp_iso,
            "finished_at": timestamp_iso,
            "ram_gb": ram_gb,
            "cpu_cores": cpu_cores,
            "system_info": {"platform": platform},
            "results": [],
            "test_results": [],
            "summary": {
                "total_prompts": 0,
                "successful": 0,
                "failed": 0,
                "success_rate": 0,
                "avg_tokens_per_second": 0,
                "avg_latency_ms": 0,
                "avg_first_token_latency_ms": 0,
                "total_tokens_generated": 0,
                "avg_cpu_percent": 0,
                "avg_memory_percent": 0,
            },
            "phase1_failed": True,
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        logger.info(f"Created fallback result file: {filepath}")
        return str(filepath)
    except Exception as e:
        logger.error(f"Failed to create fallback result file: {e}")
        return ""


def _save_test_results(filepath: str, test_results: list) -> bool:
    """Save test_results into benchmark JSON file; recreate file if it was removed.

    Returns True if the file was written successfully, False otherwise. Callers
    that need to safely delete upstream per-test artifacts should only do so
    after this function returns True.
    """
    try:
        data = None
        if Path(filepath).exists():
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            logger.warning(f"Result file missing, recreating: {filepath}")

        if data is None:
            backup = benchmark_state.get("result_backup") if isinstance(benchmark_state, dict) else None
            if isinstance(backup, dict):
                data = backup
            else:
                data = {
                    "model": benchmark_state.get("model", ""),
                    "platform": "docker",
                    "technology": "ollama",
                    "timestamp": datetime.now().isoformat(),
                    "system_info": {},
                    "results": [],
                    "summary": {
                        "total_prompts": 0,
                        "successful": 0,
                        "failed": 0,
                        "success_rate": 0,
                        "avg_tokens_per_second": 0,
                        "avg_latency_ms": 0,
                        "avg_first_token_latency_ms": 0,
                        "total_tokens_generated": 0,
                        "avg_cpu_percent": 0,
                        "avg_memory_percent": 0,
                    },
                }

        data["test_results"] = test_results

        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"Saved {len(test_results)} test results to {filepath}")
        return True
    except Exception as e:
        logger.error(f"Failed to save test results: {e}")
        return False


def _extract_saved_result_file_path(log_text: str) -> Optional[Path]:
    """Extract saved result file path from script logs."""
    if not log_text:
        return None

    matches = re.findall(r"Results saved(?:\s+to)?\s*[:→]\s*([^\r\n]+)", log_text, flags=re.IGNORECASE)
    if not matches:
        return None

    raw_path = matches[-1].strip().strip('"').strip("'")
    if not raw_path:
        return None

    candidate = Path(raw_path)
    if candidate.is_absolute() and candidate.exists():
        return candidate

    search_roots = [
        SCRIPTS_DIR,
        Path(__file__).parent,
        Path(__file__).parent.parent,
        Path.cwd(),
    ]

    for root in search_roots:
        resolved = root / raw_path
        if resolved.exists():
            return resolved

    return None


def _safe_to_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _extract_details_from_result_payload(payload: dict) -> list[dict]:
    """Extract prompt/response details from different test result JSON schemas."""
    details = []
    if not isinstance(payload, dict):
        return details

    candidate_lists = []
    for key in ("tests", "results"):
        value = payload.get(key)
        if isinstance(value, list):
            candidate_lists.append(value)

    for items in candidate_lists:
        for item in items:
            if not isinstance(item, dict):
                continue

            prompt = item.get("prompt") or item.get("question") or item.get("category") or ""
            response = (
                item.get("response")
                or item.get("response_text")
                or item.get("full_response")
                or item.get("generated_code")
                or ""
            )

            if not response and item.get("model_answer") is not None:
                model_answer = _safe_to_text(item.get("model_answer"))
                correct_answer = _safe_to_text(item.get("correct_answer"))
                response = f"Model answer: {model_answer}" if not correct_answer else f"Model answer: {model_answer}; Correct answer: {correct_answer}"

            prompt_text = _safe_to_text(prompt).strip()
            response_text = _safe_to_text(response).strip()
            if not prompt_text and not response_text:
                continue

            details.append({
                "prompt": prompt_text,
                "response": response_text,
            })

            if len(details) >= 200:
                return details

    return details


def _load_test_details_from_logs(stdout: str, stderr: str) -> list[dict]:
    """Load rich test details by following 'Results saved to:' pointer from logs."""
    for log_text in (stdout or "", stderr or ""):
        result_path = _extract_saved_result_file_path(log_text)
        if not result_path:
            continue
        try:
            with open(result_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            details = _extract_details_from_result_payload(payload)
            if details:
                return details
        except Exception as e:
            logger.warning(f"Failed to load detail file '{result_path}': {e}")
    return []


# API Endpoints

@app.get("/api/models")
async def get_models():
    """Get available models"""
    available_models = await _list_ollama_models()
    models = _build_model_catalog(available_models)
    return {"models": models}


@app.get("/api/technologies")
async def get_technologies():
    """Get available technologies"""
    return {
        "container": CONTAINER_TECHNOLOGIES,
        "vm": VM_TECHNOLOGIES
    }


@app.get("/api/status")
async def get_status():
    """Get current deployment status"""
    return deployment_state


@app.post("/api/container/start")
async def start_container(request: DeploymentRequest, background_tasks: BackgroundTasks):
    """Start container deployment"""
    resolved = _get_model_name(request.model, request.technology)

    if request.technology == "ollama":
        installed_models = await _list_ollama_models()
        if resolved not in installed_models:
            deployment_state["container"]["status"] = "pulling"
            deployment_state["container"]["technology"] = request.technology
            deployment_state["container"]["model"] = request.model
            deployment_state["container"]["cpu"] = 0
            deployment_state["container"]["memory"] = 0
            deployment_state["container"]["latency"] = 0
            deployment_state["container"]["message"] = f"Pulling model '{resolved}'..."

            if resolved not in pulling_models:
                pulling_models.add(resolved)
                background_tasks.add_task(_pull_and_start_container, request.model, request.technology, request.ram_gb, request.cpu_cores)

            return {
                "success": True,
                "state": deployment_state["container"],
                "message": f"Pulling model '{resolved}' in background",
            }

    await _resolve_and_validate_model(request.model, request.technology)

    _set_container_running_state(request.model, request.technology, request.ram_gb, request.cpu_cores)

    return {"success": True, "state": deployment_state["container"]}


@app.post("/api/container/stop")
async def stop_container():
    """Stop container deployment"""
    deployment_state["container"]["status"] = "stopped"
    deployment_state["container"]["technology"] = None
    deployment_state["container"]["model"] = None
    deployment_state["container"]["cpu"] = 0
    deployment_state["container"]["memory"] = 0
    deployment_state["container"]["latency"] = 0
    deployment_state["container"]["message"] = ""

    return {"success": True, "state": deployment_state["container"]}


@app.post("/api/vm/start")
async def start_vm(request: DeploymentRequest):
    """Start VM deployment"""
    deployment_state["vm"]["status"] = "running"
    deployment_state["vm"]["technology"] = request.technology
    deployment_state["vm"]["model"] = request.model
    deployment_state["vm"]["ram_gb"] = request.ram_gb
    deployment_state["vm"]["cpu_cores"] = request.cpu_cores

    deployment_state["vm"]["cpu"] = round(random.uniform(30, 70), 1)
    deployment_state["vm"]["memory"] = round(random.uniform(40, 80), 1)
    deployment_state["vm"]["latency"] = round(random.uniform(40, 100), 0)

    return {"success": True, "state": deployment_state["vm"]}


@app.post("/api/vm/stop")
async def stop_vm():
    """Stop VM deployment"""
    deployment_state["vm"]["status"] = "stopped"
    deployment_state["vm"]["cpu"] = 0
    deployment_state["vm"]["memory"] = 0
    deployment_state["vm"]["latency"] = 0

    return {"success": True, "state": deployment_state["vm"]}


@app.get("/api/metrics")
async def get_metrics():
    """Get current metrics snapshot"""
    time_points = [f"{i*5}s" for i in range(12)]

    data = []
    for i, t in enumerate(time_points):
        data.append({
            "time": t,
            "container": {
                "cpu": round(random.uniform(20, 50), 1),
                "memory": round(random.uniform(15, 40), 1),
                "latency": round(random.uniform(20, 50), 0)
            },
            "vm": {
                "cpu": round(random.uniform(40, 80), 1),
                "memory": round(random.uniform(35, 70), 1),
                "latency": round(random.uniform(40, 100), 0)
            }
        })

    return {"data": data}


@app.get("/api/metrics/download")
async def download_metrics(model: str = "", technology: str = ""):
    """Generate CSV data for download"""
    import io
    import csv

    time_points = [f"{i*5}s" for i in range(12)]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Time", "Container CPU (%)", "Container Memory (%)", "Container Latency (ms)",
                     "VM CPU (%)", "VM Memory (%)", "VM Latency (ms)"])

    for t in time_points:
        writer.writerow([
            t,
            round(random.uniform(20, 50), 1),
            round(random.uniform(15, 40), 1),
            round(random.uniform(20, 50), 0),
            round(random.uniform(40, 80), 1),
            round(random.uniform(35, 70), 1),
            round(random.uniform(40, 100), 0)
        ])

    return {
        "filename": f"metrics_{model}_{technology}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        "content": output.getvalue()
    }


# Test endpoints

@app.get("/api/tests")
async def get_tests():
    """Get available tests"""
    return {
        "tests": [
            {"id": k, "name": v["name"], "status": "pending"}
            for k, v in TESTS.items()
        ]
    }


@app.post("/api/tests/run")
async def run_tests(request: TestRequest):
    """Run selected tests by executing actual test scripts"""
    results = []
    model_name = await _resolve_and_validate_model(request.model, request.technology)
    port = TECH_PORTS.get(request.technology, 11434)
    loop = asyncio.get_running_loop()

    for test_id in request.test_ids:
        if test_id not in TESTS:
            continue

        test = TESTS[test_id]
        script_path = str(SCRIPTS_DIR / test["script"])

        result = await loop.run_in_executor(
            None, _run_test_subprocess, script_path, model_name, port,
            test.get("timeout", 600), request.technology
        )

        results.append({
            "id": test_id,
            "name": test["name"],
            "status": result["status"] if result["status"] in ("passed", "failed") else "failed",
            "duration": round(result["duration"] * 1000, 0),
        })

    return {"results": results}


# ============== Benchmark Endpoints ==============

# Store running benchmark state
benchmark_state = {
    "running": False,
    "progress": 0,
    "status": "idle",
    "message": "",
    "test_results": [],
    "result_filepath": "",
    "result_backup": None,
    "model": "",
}


class BenchmarkRequest(BaseModel):
    model: str
    categories: Optional[list[str]] = None
    warm_up: bool = True
    runs_per_prompt: int = 1


class ResourceConfig(BaseModel):
    ram_gb: int | None = None
    cpu_cores: float | None = None


# Default RAM/CPU options for a full sweep
DEFAULT_RAM_OPTIONS = [1, 2, 4]
DEFAULT_CPU_OPTIONS = [1.0, 2.0, 4.0]


class RunAllRequest(BaseModel):
    model: str
    platform: str = "docker"
    technology: str = "ollama"
    # Single-config mode (back-compat): one (ram, cpu) pair.
    ram_gb: int | None = None
    cpu_cores: float | None = None
    # Sweep mode: explicit list of (ram_gb, cpu_cores) pairs.
    configs: list[ResourceConfig] | None = None
    # Sweep mode: cartesian product over these option lists.
    ram_options: list[int] | None = None
    cpu_options: list[float] | None = None
    # Sweep mode: run the full default matrix (DEFAULT_RAM_OPTIONS x DEFAULT_CPU_OPTIONS).
    run_all_configs: bool = False


def _resolve_configs(request: "RunAllRequest") -> list[dict]:
    """Resolve the list of (ram_gb, cpu_cores) configurations for a run-all request.

    Resolution order (first match wins):
      1. ``request.configs`` — explicit list of pairs from the frontend.
      2. ``request.ram_options`` / ``request.cpu_options`` — cartesian product.
      3. ``request.run_all_configs`` — full default sweep matrix.
      4. Fallback — single config from ``request.ram_gb`` / ``request.cpu_cores``
         (which may both be ``None`` to indicate "no explicit limit").

    Always returns at least one entry so the matrix runner has something to do.
    """
    if request.configs:
        out: list[dict] = []
        for c in request.configs:
            out.append({
                "ram_gb": c.ram_gb,
                "cpu_cores": c.cpu_cores,
            })
        if out:
            return out

    if request.ram_options or request.cpu_options:
        rams = request.ram_options or [request.ram_gb]
        cpus = request.cpu_options or [request.cpu_cores]
        return [
            {"ram_gb": r, "cpu_cores": c}
            for r in rams
            for c in cpus
        ]

    if request.run_all_configs:
        return [
            {"ram_gb": r, "cpu_cores": c}
            for r in DEFAULT_RAM_OPTIONS
            for c in DEFAULT_CPU_OPTIONS
        ]

    return [{"ram_gb": request.ram_gb, "cpu_cores": request.cpu_cores}]


@app.get("/api/benchmarks/status")
async def get_benchmark_status():
    """Get current benchmark status"""
    return benchmark_state


@app.post("/api/benchmarks/reset")
async def reset_benchmark_state(force: bool = False):
    """Reset benchmark state (emergency reset if stuck).

    Refuses to reset while a benchmark task is genuinely running unless
    ``force=true`` is passed, to avoid stomping on an in-flight background
    task which would otherwise interleave writes and corrupt results.
    """
    global benchmark_state
    if benchmark_state.get("running") and not force:
        logger.warning(
            "Benchmark reset refused: a benchmark task is currently running. "
            "Pass force=true to reset anyway (may corrupt in-flight results)."
        )
        raise HTTPException(
            status_code=409,
            detail=(
                "Benchmark is currently running; refusing to reset to avoid "
                "corrupting in-flight results. Retry with ?force=true to override."
            ),
        )
    if benchmark_state.get("running") and force:
        logger.warning(
            "Forced benchmark reset while running=True; in-flight background "
            "task may still be writing to disk and could produce corrupted results."
        )
    benchmark_state["running"] = False
    benchmark_state["progress"] = 0
    benchmark_state["status"] = "idle"
    benchmark_state["message"] = "Reset via API"
    benchmark_state["test_results"] = []
    benchmark_state["result_filepath"] = ""
    benchmark_state["result_backup"] = None
    benchmark_state["model"] = None
    logger.info("Benchmark state reset via API")
    return {"success": True, "message": "Benchmark state reset"}


@app.get("/api/benchmarks/framework/status")
async def get_framework_status(technology: str = "ollama"):
    """Check if framework is running and list available models"""
    if technology == "ollama":
        benchmark = OllamaBenchmark(base_url=_ollama_base_url())
        connected = await benchmark.check_connection()
        models = await benchmark.list_models() if connected else []
        await benchmark.close()
        return {"connected": connected, "models": models, "technology": technology}
    return {"connected": False, "models": [], "technology": technology}


@app.get("/api/benchmarks/ollama/status")
async def get_ollama_status():
    """Check if Ollama is running and list available models"""
    benchmark = OllamaBenchmark(base_url=_ollama_base_url())
    connected = await benchmark.check_connection()
    models = await benchmark.list_models() if connected else []
    await benchmark.close()

    return {
        "connected": connected,
        "models": models
    }


@app.post("/api/benchmarks/pull")
async def pull_model(model: str, technology: str = "ollama"):
    """Pull (or re-pull) a model into Ollama."""
    resolved = _get_model_name(model, technology)
    try:
        await _pull_ollama_model(resolved)
        return {"success": True, "model": resolved}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/benchmarks/health-check")
async def model_health_check(model: str, technology: str = "ollama"):
    """Send a test prompt to the model and verify it responds."""
    resolved = _get_model_name(model, technology)
    base_url = _ollama_base_url()
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{base_url}/api/generate",
                json={"model": resolved, "prompt": "Hello, how are you?", "stream": False},
            )
            r.raise_for_status()
            data = r.json()
            response_text = data.get("response", "").strip()
            return {"healthy": bool(response_text), "response": response_text[:200], "model": resolved}
    except Exception as e:
        return {"healthy": False, "response": str(e), "model": resolved}


@app.get("/api/benchmarks/categories")
async def get_benchmark_categories():
    """Get available benchmark categories"""
    return {
        "categories": [
            {"value": key, "label": key.title(), "prompts": len(prompts)}
            for key, prompts in BENCHMARK_PROMPTS.items()
        ]
    }


@app.post("/api/benchmarks/run")
async def run_benchmark_endpoint(request: BenchmarkRequest):
    """Run benchmarks on Ollama model"""
    global benchmark_state

    if benchmark_state["running"]:
        raise HTTPException(status_code=400, detail="Benchmark already running")

    model_name = await _resolve_and_validate_model(request.model, "ollama")

    benchmark_state["running"] = True
    benchmark_state["progress"] = 0
    benchmark_state["status"] = "starting"
    benchmark_state["message"] = "Initializing benchmark..."

    async def progress_callback(status: str, progress: int, message: str):
        benchmark_state["status"] = status
        benchmark_state["progress"] = progress
        benchmark_state["message"] = message

    try:
        summary = await run_benchmark(
            model=model_name,
            categories=request.categories,
            warm_up=request.warm_up,
            runs_per_prompt=request.runs_per_prompt,
            progress_callback=progress_callback
        )

        filepath = save_benchmark_results(summary)

        benchmark_state["status"] = "completed"
        benchmark_state["progress"] = 100
        benchmark_state["message"] = "Benchmark completed successfully"
        benchmark_state["running"] = False

        return {
            "success": True,
            "filepath": filepath,
            "summary": asdict(summary)
        }

    except ConnectionError as e:
        benchmark_state["running"] = False
        benchmark_state["status"] = "error"
        benchmark_state["message"] = str(e)
        raise HTTPException(status_code=503, detail=str(e)) from e

    except Exception as e:
        benchmark_state["running"] = False
        benchmark_state["status"] = "error"
        benchmark_state["message"] = str(e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/benchmarks/run-all")
async def run_all_tests_endpoint(request: RunAllRequest, background_tasks: BackgroundTasks):
    """Run benchmarks + all test scripts. Returns immediately, runs in background."""
    global benchmark_state

    if benchmark_state["running"]:
        raise HTTPException(status_code=400, detail="Already running")

    model_name = await _resolve_and_validate_model(request.model, request.technology)

    benchmark_state["running"] = True
    benchmark_state["progress"] = 0
    benchmark_state["status"] = "starting"
    benchmark_state["message"] = "Starting benchmarks and tests..."
    benchmark_state["test_results"] = []
    benchmark_state["result_filepath"] = ""
    benchmark_state["result_backup"] = None
    benchmark_state["model"] = model_name

    configs = _resolve_configs(request)
    benchmark_state["configs"] = configs
    benchmark_state["current_config_index"] = 0

    background_tasks.add_task(
        _run_all_tests_background_matrix,
        model_name,
        request.platform,
        request.technology,
        configs,
    )

    return {
        "success": True,
        "message": "Started benchmarks and tests in background",
        "configs": configs,
    }


async def _run_all_tests_background_matrix(
    model: str,
    platform: str,
    technology: str,
    configs: list[dict],
):
    """Run ``_run_all_tests_background`` once per resolved (ram, cpu) config.

    Keeps ``benchmark_state['running']`` True across the whole sweep so the
    concurrency guard on ``/api/benchmarks/run-all`` and ``/reset`` continues
    to work, and advances ``current_config_index`` between iterations.
    """
    global benchmark_state
    total = len(configs) or 1
    try:
        for idx, cfg in enumerate(configs):
            benchmark_state["current_config_index"] = idx
            benchmark_state["message"] = (
                f"Config {idx + 1}/{total}: ram={cfg.get('ram_gb')} GB, "
                f"cpu={cfg.get('cpu_cores')} cores"
            )
            # Map each config's 0..100 internal progress onto its slice of
            # the overall sweep so the global progress bar advances smoothly.
            # Only the last config is allowed to publish a terminal status,
            # otherwise an intermediate config would prematurely flip
            # benchmark_state to "completed" and clear `running`.
            slice_size = 100.0 / total
            await _run_all_tests_background(
                model,
                platform,
                technology,
                cfg.get("ram_gb"),
                cfg.get("cpu_cores"),
                progress_offset=int(idx * slice_size),
                progress_scale=slice_size / 100.0,
                final_status=(idx == total - 1),
            )
    finally:
        # Ensure the running flag is always cleared even if a config raised,
        # so the next run-all request isn't blocked by stale state.
        benchmark_state["running"] = False


async def _run_all_tests_background(
    model: str,
    platform: str,
    technology: str,
    ram_gb: int | None = None,
    cpu_cores: float | None = None,
    progress_offset: int = 0,
    progress_scale: float = 1.0,
    final_status: bool = True,
):
    """Background task: Phase 1 = inference benchmarks, Phase 2 = test scripts.

    ``progress_offset`` / ``progress_scale`` allow the matrix runner to map
    this single-config 0..100 progress onto a slice of the overall sweep
    (e.g. config 2 of 4 → offset=25, scale=0.25). ``final_status`` controls
    whether this call is allowed to flip ``benchmark_state`` into the
    terminal ``completed``/``error`` state and clear ``running`` — only the
    last config in a sweep should do that.
    """
    global benchmark_state
    model_name = _get_model_name(model, technology)
    port = TECH_PORTS.get(technology, 11434)
    result_filepath = ""

    def _scale(p: int) -> int:
        return progress_offset + int(p * progress_scale)

    try:
        # ---- Phase 1: Inference Benchmarks (0-50%) ----
        logger.info(f"Phase 1: Running inference benchmarks for {model_name} on {technology}:{port}")
        benchmark_state["status"] = "running"
        benchmark_state["message"] = "Phase 1: Running inference benchmarks..."

        async def progress_callback(status: str, progress: int, message: str):
            benchmark_state["progress"] = _scale(int(progress * 0.5))
            benchmark_state["message"] = f"Phase 1: {message}"

        try:
            summary = await run_benchmark(
                model=model_name,
                progress_callback=progress_callback,
                cpu_cores=cpu_cores,
            )
            summary.ram_gb = ram_gb
            summary.cpu_cores = cpu_cores
            summary.ram_gb = ram_gb
            summary.cpu_cores = cpu_cores
            benchmark_state["result_backup"] = asdict(summary)
            result_filepath = save_benchmark_results(summary)
            benchmark_state["result_filepath"] = result_filepath
            logger.info(f"Phase 1 complete. Results saved to {result_filepath}")
        except Exception as e:
            logger.error(f"Phase 1 failed: {e}")
            benchmark_state["message"] = f"Benchmarks failed: {e}. Continuing with tests..."

        # If Phase 1 failed before producing a master file, create a stub
        # result file now so Phase 2 test_results aren't silently discarded
        # (prior behaviour: with `result_filepath == ""`, every save call
        # below was skipped and all test results were lost).
        if not result_filepath:
            result_filepath = _create_fallback_result_file(
                model_name, platform, technology, ram_gb, cpu_cores
            )
            if result_filepath:
                benchmark_state["result_filepath"] = result_filepath

        # Save empty test_results immediately so the key exists
        if result_filepath:
            _save_test_results(result_filepath, [])

        benchmark_state["progress"] = _scale(50)

        # ---- Phase 2: Test Scripts (50-100%) ----
        logger.info(f"Phase 2: Running test scripts for {model_name}")
        benchmark_state["message"] = "Phase 2: Running test scripts..."

        test_ids = [k for k in TESTS if k not in ("run_all", "compare_models")]
        total_tests = len(test_ids)
        test_results = []
        loop = asyncio.get_running_loop()

        for i, test_id in enumerate(test_ids):
            test = TESTS[test_id]
            script_path = str(SCRIPTS_DIR / test["script"])
            benchmark_state["message"] = f"Phase 2: Running {test['name']} ({i+1}/{total_tests})..."
            benchmark_state["progress"] = _scale(50 + int((i / total_tests) * 50))

            result = await loop.run_in_executor(
                None,
                _run_test_subprocess,
                script_path, model_name, port, test.get("timeout", 600), technology,
                # Pass master file so save_results()-aware tests write
                # directly into test_sections[...]. Legacy tests still
                # write an individual file that is merged below.
                result_filepath,
            )

            # Merge individual test script result file into test_result, then delete it
            raw_data = None
            individual_file = _extract_saved_result_file_path(
                (result.get("stdout") or "") + (result.get("stderr") or "")
            )
            is_master_file = (
                individual_file is not None
                and result_filepath
                and Path(result_filepath).resolve() == Path(individual_file).resolve()
            )
            if individual_file and individual_file.exists() and not is_master_file:
                try:
                    with open(individual_file, "r", encoding="utf-8") as f:
                        raw_data = json.load(f)
                    logger.info(f"Merged individual result file: {individual_file.name}")
                except Exception as e:
                    logger.warning(f"Could not read {individual_file}: {e}")

            test_result = {
                "id": test_id,
                "name": test["name"],
                "status": result["status"],
                "duration": round(result["duration"], 2),
                "stdout": result.get("stdout", ""),
                "stderr": result.get("stderr", ""),
                "details": result.get("details", []),
                "raw_data": raw_data,
            }
            test_results.append(test_result)
            benchmark_state["test_results"] = test_results

            # Save progressively into the single master file; only after that
            # write succeeds is it safe to remove the per-test JSON artifact.
            save_ok = True
            if result_filepath:
                save_ok = _save_test_results(result_filepath, test_results)

            if (
                save_ok
                and raw_data is not None
                and individual_file
                and individual_file.exists()
            ):
                try:
                    individual_file.unlink()
                    logger.info(f"Deleted individual result file after master save: {individual_file.name}")
                except Exception as e:
                    logger.warning(f"Could not delete {individual_file}: {e}")
            elif not save_ok and individual_file and individual_file.exists():
                logger.warning(
                    f"Master file save failed; keeping per-test artifact {individual_file} "
                    "to preserve raw measurements."
                )

            logger.info(f"Test {test_id}: {result['status']} in {result['duration']:.1f}s")

        # Final save
        if result_filepath:
            _save_test_results(result_filepath, test_results)

        passed = sum(1 for t in test_results if t["status"] == "passed")
        if final_status:
            benchmark_state["progress"] = 100
            benchmark_state["status"] = "completed"
            benchmark_state["message"] = f"All done! {passed}/{len(test_results)} tests passed."
            benchmark_state["running"] = False
        logger.info(f"Phase 2 complete. {passed}/{len(test_results)} tests passed.")

    except Exception as e:
        logger.error(f"Background task error: {e}")
        if final_status:
            benchmark_state["status"] = "error"
            benchmark_state["message"] = str(e)
            benchmark_state["running"] = False
        if result_filepath:
            _save_test_results(result_filepath, benchmark_state.get("test_results", []))


@app.get("/api/benchmarks/results")
async def get_benchmark_results():
    """Get list of all saved benchmark results"""
    results = list_benchmark_results()
    return {"results": results}


@app.get("/api/benchmarks/results/{filename}")
async def get_benchmark_result(filename: str):
    """Get specific benchmark result by filename"""
    filepath = RESULTS_DIR / filename

    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Result not found")

    result_data = load_benchmark_results(str(filepath))

    test_results = result_data.get("test_results") if isinstance(result_data, dict) else None
    if isinstance(test_results, list):
        for test_result in test_results:
            if not isinstance(test_result, dict):
                continue
            existing_details = test_result.get("details")
            if isinstance(existing_details, list) and len(existing_details) > 0:
                continue

            details = _load_test_details_from_logs(
                _safe_to_text(test_result.get("stdout")),
                _safe_to_text(test_result.get("stderr")),
            )
            if details:
                test_result["details"] = details

    return result_data


# WebSocket for real-time metrics
@app.websocket("/ws/metrics")
async def websocket_metrics(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()

            if deployment_state["container"]["status"] == "running":
                deployment_state["container"]["cpu"] = round(random.uniform(10, 50), 1)
                deployment_state["container"]["memory"] = round(random.uniform(20, 50), 1)
                deployment_state["container"]["latency"] = round(random.uniform(20, 50), 0)

            if deployment_state["vm"]["status"] == "running":
                deployment_state["vm"]["cpu"] = round(random.uniform(30, 80), 1)
                deployment_state["vm"]["memory"] = round(random.uniform(40, 80), 1)
                deployment_state["vm"]["latency"] = round(random.uniform(40, 100), 0)

    except WebSocketDisconnect:
        # Normal client disconnect: cleanup happens in `finally` below.
        pass
    except Exception as e:
        # Any other failure (network glitch, malformed frame, etc.) must not
        # leave a stale entry in `manager.active_connections`, otherwise the
        # background broadcast task keeps trying to send to a dead socket.
        logger.warning(f"WebSocket /ws/metrics error: {e}")
    finally:
        manager.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
