from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Literal, Callable
import asyncio
import subprocess
import random
import os
import time
import json
import re
import logging
import docker
import httpx
from datetime import datetime
from contextlib import asynccontextmanager
from pathlib import Path

logger = logging.getLogger("uvicorn.error")

# Initialize Docker client
try:
    docker_client = docker.from_env()
except:
    docker_client = None


# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
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
        "latency": 0
    },
    "vm": {
        "status": "idle",
        "technology": None,
        "model": None,
        "cpu": 0,
        "memory": 0,
        "latency": 0
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
    "run_all": {
        "name": "Run All Tests",
        "script": "run_all_tests.py",
        "duration_range": (300, 1800),
    },
}

SCRIPTS_DIR = Path(__file__).parent / "scripts" / "tests"
RESULTS_DIR = Path(__file__).parent / "results"

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


async def _list_ollama_models() -> list[str]:
    """Fetch installed models from Ollama."""
    host = os.environ.get("SLM_TEST_HOST", "localhost")
    port = TECH_PORTS["ollama"]
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"http://{host}:{port}/api/tags")
            if response.status_code != 200:
                return []
            data = response.json()
            return [m.get("name") for m in data.get("models", []) if m.get("name")]
    except Exception as e:
        logger.warning(f"Failed to fetch Ollama models: {e}")
        return []


def _ollama_base_url() -> str:
    """Get Ollama base URL based on current host mapping."""
    host = os.environ.get("SLM_TEST_HOST", "localhost")
    port = TECH_PORTS["ollama"]
    return f"http://{host}:{port}"


async def _pull_ollama_model(model: str):
    """Pull a model from Ollama registry and wait until it is available locally."""
    timeout = httpx.Timeout(timeout=3600.0, connect=10.0)
    url = f"{_ollama_base_url()}/api/pull"

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json={"model": model, "stream": False})
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Failed to connect to Ollama for pull: {e}")

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


def _set_container_running_state(model: str, technology: str):
    """Update container deployment state to running with fresh metrics."""
    deployment_state["container"]["status"] = "running"
    deployment_state["container"]["technology"] = technology
    deployment_state["container"]["model"] = model
    deployment_state["container"]["message"] = ""

    deployment_state["container"]["cpu"] = round(random.uniform(10, 40), 1)
    deployment_state["container"]["memory"] = round(random.uniform(20, 50), 1)
    deployment_state["container"]["latency"] = round(random.uniform(20, 50), 0)


async def _pull_and_start_container(model: str, technology: str):
    """Pull missing Ollama model in background and switch container to running."""
    resolved = _get_model_name(model, technology)
    try:
        await _pull_ollama_model(resolved)
        _set_container_running_state(model, technology)
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


def _get_test_env(technology: str) -> dict:
    """Get environment variables for test subprocesses."""
    env = os.environ.copy()
    # Inside Docker, services are accessed by container hostname, not localhost
    host_map = {"ollama": "ollama", "llama-cpp": "llama-cpp", "vllm": "vllm"}
    env["SLM_TEST_HOST"] = host_map.get(technology, "localhost")
    return env


def _run_test_subprocess(script_path: str, model_name: str, port: int, timeout: int = 600, technology: str = "ollama") -> dict:
    """Run a test script via subprocess.run (synchronous, for use in executor)."""
    cmd = ["python", script_path, model_name, str(port)]
    env = _get_test_env(technology)
    logger.info(f"Running test command: {' '.join(cmd)} (host={env.get('SLM_TEST_HOST')})")
    start_time = time.time()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(SCRIPTS_DIR),
            env=env,
        )
        duration = time.time() - start_time
        status = "passed" if result.returncode == 0 else "failed"
        details = _load_test_details_from_logs(result.stdout or "", result.stderr or "")
        logger.info(f"Test finished: {script_path} -> {status} in {duration:.1f}s")
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


def _save_test_results(filepath: str, test_results: list):
    """Save test_results into benchmark JSON file; recreate file if it was removed."""
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
    except Exception as e:
        logger.error(f"Failed to save test results: {e}")


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
                background_tasks.add_task(_pull_and_start_container, request.model, request.technology)

            return {
                "success": True,
                "state": deployment_state["container"],
                "message": f"Pulling model '{resolved}' in background",
            }

    await _resolve_and_validate_model(request.model, request.technology)

    _set_container_running_state(request.model, request.technology)

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
            None, _run_test_subprocess, script_path, model_name, port, 600, request.technology
        )

        results.append({
            "id": test_id,
            "name": test["name"],
            "status": result["status"] if result["status"] in ("passed", "failed") else "failed",
            "duration": round(result["duration"] * 1000, 0),
        })

    return {"results": results}


# ============== Benchmark Endpoints ==============
from benchmarks import (
    OllamaBenchmark,
    run_benchmark,
    save_benchmark_results,
    list_benchmark_results,
    load_benchmark_results,
    BENCHMARK_PROMPTS
)
from dataclasses import asdict

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


class RunAllRequest(BaseModel):
    model: str
    platform: str = "docker"
    technology: str = "ollama"


@app.get("/api/benchmarks/status")
async def get_benchmark_status():
    """Get current benchmark status"""
    return benchmark_state


@app.get("/api/benchmarks/framework/status")
async def get_framework_status(technology: str = "ollama"):
    """Check if framework is running and list available models"""
    port = TECH_PORTS.get(technology, 11434)
    if technology == "ollama":
        host = os.environ.get("SLM_TEST_HOST", "localhost")
        benchmark = OllamaBenchmark(base_url=f"http://{host}:{port}")
        connected = await benchmark.check_connection()
        models = await benchmark.list_models() if connected else []
        await benchmark.close()
        return {"connected": connected, "models": models, "technology": technology}
    return {"connected": False, "models": [], "technology": technology}


@app.get("/api/benchmarks/ollama/status")
async def get_ollama_status():
    """Check if Ollama is running and list available models"""
    benchmark = OllamaBenchmark()
    connected = await benchmark.check_connection()
    models = await benchmark.list_models() if connected else []
    await benchmark.close()

    return {
        "connected": connected,
        "models": models
    }


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
        raise HTTPException(status_code=503, detail=str(e))

    except Exception as e:
        benchmark_state["running"] = False
        benchmark_state["status"] = "error"
        benchmark_state["message"] = str(e)
        raise HTTPException(status_code=500, detail=str(e))


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

    background_tasks.add_task(
        _run_all_tests_background,
        model_name,
        request.platform,
        request.technology,
    )

    return {"success": True, "message": "Started benchmarks and tests in background"}


async def _run_all_tests_background(model: str, platform: str, technology: str):
    """Background task: Phase 1 = inference benchmarks, Phase 2 = test scripts."""
    global benchmark_state
    model_name = _get_model_name(model, technology)
    port = TECH_PORTS.get(technology, 11434)
    result_filepath = ""

    try:
        # ---- Phase 1: Inference Benchmarks (0-50%) ----
        logger.info(f"Phase 1: Running inference benchmarks for {model_name} on {technology}:{port}")
        benchmark_state["status"] = "running"
        benchmark_state["message"] = "Phase 1: Running inference benchmarks..."

        async def progress_callback(status: str, progress: int, message: str):
            benchmark_state["progress"] = int(progress * 0.5)
            benchmark_state["message"] = f"Phase 1: {message}"

        try:
            summary = await run_benchmark(
                model=model_name,
                progress_callback=progress_callback,
            )
            benchmark_state["result_backup"] = asdict(summary)
            result_filepath = save_benchmark_results(summary)
            benchmark_state["result_filepath"] = result_filepath
            logger.info(f"Phase 1 complete. Results saved to {result_filepath}")
        except Exception as e:
            logger.error(f"Phase 1 failed: {e}")
            benchmark_state["message"] = f"Benchmarks failed: {e}. Continuing with tests..."

        # Save empty test_results immediately so the key exists
        if result_filepath:
            _save_test_results(result_filepath, [])

        benchmark_state["progress"] = 50

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
            benchmark_state["progress"] = 50 + int((i / total_tests) * 50)

            result = await loop.run_in_executor(
                None, _run_test_subprocess, script_path, model_name, port, 600, technology
            )

            test_result = {
                "id": test_id,
                "name": test["name"],
                "status": result["status"],
                "duration": round(result["duration"], 2),
                "stdout": result.get("stdout", ""),
                "stderr": result.get("stderr", ""),
                "details": result.get("details", []),
            }
            test_results.append(test_result)
            benchmark_state["test_results"] = test_results

            # Save progressively
            if result_filepath:
                _save_test_results(result_filepath, test_results)

            logger.info(f"Test {test_id}: {result['status']} in {result['duration']:.1f}s")

        # Final save
        if result_filepath:
            _save_test_results(result_filepath, test_results)

        passed = sum(1 for t in test_results if t["status"] == "passed")
        benchmark_state["progress"] = 100
        benchmark_state["status"] = "completed"
        benchmark_state["message"] = f"All done! {passed}/{len(test_results)} tests passed."
        benchmark_state["running"] = False
        logger.info(f"Phase 2 complete. {passed}/{len(test_results)} tests passed.")

    except Exception as e:
        logger.error(f"Background task error: {e}")
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
    results_dir = Path(__file__).parent / "results"

    # Also check parent results dir
    if not (results_dir / filename).exists():
        results_dir = Path(__file__).parent.parent / "results"

    filepath = results_dir / filename

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
        manager.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
