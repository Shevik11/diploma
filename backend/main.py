from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Literal
import asyncio
import os
import random
import time
import docker
import psutil
from datetime import datetime
from contextlib import asynccontextmanager

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
LLAMA_CPP_URL = os.getenv("LLAMA_CPP_URL", "http://localhost:8080")
VLLM_URL = os.getenv("VLLM_URL", "http://localhost:8100")

# Framework container configurations
FRAMEWORK_CONFIGS = {
    "ollama": {
        "container_name": "ollama",
        "image": "ollama/ollama:latest",
        "ports": {"11434/tcp": 11434},
        "volumes": {"ollama_data": {"bind": "/root/.ollama", "mode": "rw"}},
        "base_url": OLLAMA_URL,
        "health_endpoint": "/api/tags",
        "environment": {},
    },
    "llama-cpp": {
        "container_name": "llama-cpp",
        "image": "ghcr.io/ggerganov/llama.cpp:server",
        "ports": {"8080/tcp": 8080},
        "volumes": {"llama_cpp_models": {"bind": "/models", "mode": "rw"}},
        "base_url": LLAMA_CPP_URL,
        "health_endpoint": "/health",
        "environment": {},
    },
    "vllm": {
        "container_name": "vllm",
        "image": "vllm/vllm-openai:latest",
        "ports": {"8000/tcp": 8100},
        "volumes": {"vllm_models": {"bind": "/root/.cache/huggingface", "mode": "rw"}},
        "base_url": VLLM_URL,
        "health_endpoint": "/health",
        "environment": {},
    },
}

# Model name mapping per framework (Ollama uses short tags, others use HuggingFace IDs)
MODEL_NAMES = {
    "ollama": {
        "phi3:mini": "phi3:mini",
        "llama3.2:1b": "llama3.2:1b",
        "llama3.2:3b": "llama3.2:3b",
        "gemma2:2b": "gemma2:2b",
        "mistral:7b": "mistral:7b",
        "qwen2.5:0.5b": "qwen2.5:0.5b",
        "qwen2.5:1.5b": "qwen2.5:1.5b",
        "qwen2.5:3b": "qwen2.5:3b",
    },
    "llama-cpp": {
        "phi3:mini": "microsoft/Phi-3-mini-4k-instruct-gguf",
        "llama3.2:1b": "meta-llama/Llama-3.2-1B-Instruct-GGUF",
        "llama3.2:3b": "meta-llama/Llama-3.2-3B-Instruct-GGUF",
        "gemma2:2b": "google/gemma-2-2b-it-GGUF",
        "mistral:7b": "mistralai/Mistral-7B-Instruct-v0.3-GGUF",
        "qwen2.5:0.5b": "Qwen/Qwen2.5-0.5B-Instruct-GGUF",
        "qwen2.5:1.5b": "Qwen/Qwen2.5-1.5B-Instruct-GGUF",
        "qwen2.5:3b": "Qwen/Qwen2.5-3B-Instruct-GGUF",
    },
    "vllm": {
        "phi3:mini": "microsoft/Phi-3-mini-4k-instruct",
        "llama3.2:1b": "meta-llama/Llama-3.2-1B-Instruct",
        "llama3.2:3b": "meta-llama/Llama-3.2-3B-Instruct",
        "gemma2:2b": "google/gemma-2-2b-it",
        "mistral:7b": "mistralai/Mistral-7B-Instruct-v0.3",
        "qwen2.5:0.5b": "Qwen/Qwen2.5-0.5B-Instruct",
        "qwen2.5:1.5b": "Qwen/Qwen2.5-1.5B-Instruct",
        "qwen2.5:3b": "Qwen/Qwen2.5-3B-Instruct",
    },
}


def get_framework_model_name(model: str, technology: str) -> str:
    """Get the correct model name for the given framework."""
    return MODEL_NAMES.get(technology, {}).get(model, model)

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


def get_container_stats(container_name: str = "ollama"):
    """Get real-time stats from a Docker container."""
    if not docker_client:
        return 0, 0, 0
    try:
        container = docker_client.containers.get(container_name)
        stats = container.stats(stream=False)

        cpu_delta = stats["cpu_stats"]["cpu_usage"]["total_usage"] - stats["precpu_stats"]["cpu_usage"]["total_usage"]
        system_delta = stats["cpu_stats"]["system_cpu_usage"] - stats["precpu_stats"]["system_cpu_usage"]
        percpu = stats["cpu_stats"]["cpu_usage"].get("percpu_usage") or [0]
        cpu_percent = (cpu_delta / system_delta) * len(percpu) * 100.0 if system_delta else 0

        memory_usage = stats["memory_stats"].get("usage", 0)
        memory_limit = stats["memory_stats"].get("limit", 1)
        memory_percent = (memory_usage / memory_limit) * 100.0

        return round(cpu_percent, 1), round(memory_percent, 1), 0
    except Exception:
        return 0, 0, 0


# Background task for metrics
metrics_task = None


async def broadcast_metrics():
    """Background task to broadcast metrics to all connected clients"""
    while True:
        if manager.active_connections:
            # Refresh real container stats if a container is running
            cn = deployment_state["container"].get("container_name")
            if cn and deployment_state["container"]["status"] == "running":
                cpu, mem, lat = get_container_stats(cn)
                deployment_state["container"]["cpu"] = cpu
                deployment_state["container"]["memory"] = mem
                deployment_state["container"]["latency"] = lat

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
        "container_name": None,
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

# Models — generic IDs, mapped to framework-specific names at runtime
MODELS = [
    {"value": "phi3:mini", "label": "Phi-3 Mini (3.8B)"},
    {"value": "llama3.2:1b", "label": "Llama 3.2 (1B)"},
    {"value": "llama3.2:3b", "label": "Llama 3.2 (3B)"},
    {"value": "gemma2:2b", "label": "Gemma 2 (2B)"},
    {"value": "mistral:7b", "label": "Mistral (7B)"},
    {"value": "qwen2.5:0.5b", "label": "Qwen 2.5 (0.5B)"},
    {"value": "qwen2.5:1.5b", "label": "Qwen 2.5 (1.5B)"},
    {"value": "qwen2.5:3b", "label": "Qwen 2.5 (3B)"},
]

CONTAINER_TECHNOLOGIES = [
    {"value": "ollama", "label": "Ollama (Docker)"},
    {"value": "llama-cpp", "label": "llama.cpp (Docker)"},
    {"value": "vllm", "label": "vLLM (Docker)"},
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


class TestResult(BaseModel):
    id: str
    name: str
    status: Literal["pending", "running", "passed", "failed"]
    duration: Optional[float] = None


# API Endpoints

@app.get("/api/models")
async def get_models():
    """Get available models"""
    return {"models": MODELS}


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
async def start_container(request: DeploymentRequest):
    """Start Docker container for the selected framework and load the requested model"""
    if not docker_client:
        raise HTTPException(status_code=503, detail="Docker is not available")

    technology = request.technology or "ollama"
    config = FRAMEWORK_CONFIGS.get(technology)
    if not config:
        raise HTTPException(status_code=400, detail=f"Unknown technology: {technology}")

    # Use the base container name (not model-suffixed) to reuse existing containers
    container_name = config['container_name']
    framework_model = get_framework_model_name(request.model, technology)

    deployment_state["container"]["status"] = "starting"
    deployment_state["container"]["technology"] = technology
    deployment_state["container"]["model"] = request.model
    deployment_state["container"]["container_name"] = container_name

    try:
        # Check if container already exists
        try:
            container = docker_client.containers.get(container_name)
            if container.status != "running":
                container.start()
        except docker.errors.NotFound:
            # Build run kwargs based on technology
            run_kwargs = {
                "image": config["image"],
                "name": container_name,
                "ports": config["ports"],
                "volumes": config["volumes"],
                "detach": True,
                "restart_policy": {"Name": "unless-stopped"},
            }
            if config["environment"]:
                run_kwargs["environment"] = config["environment"]

            # llama.cpp and vLLM need the model passed at container start
            if technology == "llama-cpp":
                run_kwargs["command"] = ["-m", f"/models/{framework_model}", "--host", "0.0.0.0", "--port", "8080"]
            elif technology == "vllm":
                run_kwargs["command"] = ["--model", framework_model, "--host", "0.0.0.0", "--port", "8000"]
                # vLLM needs GPU; add runtime if available
                try:
                    run_kwargs["runtime"] = "nvidia"
                    run_kwargs["environment"] = {"NVIDIA_VISIBLE_DEVICES": "all"}
                except Exception:
                    pass

            container = docker_client.containers.run(**run_kwargs)

        # Wait for framework to be ready
        import httpx
        base_url = config["base_url"]
        health_endpoint = config["health_endpoint"]
        async with httpx.AsyncClient(timeout=60.0) as client:
            for _ in range(30):
                try:
                    resp = await client.get(f"{base_url}{health_endpoint}")
                    if resp.status_code == 200:
                        break
                except Exception:
                    pass
                await asyncio.sleep(2)
            else:
                raise HTTPException(status_code=504, detail=f"{technology} container did not become ready")

            # Ollama-specific: pull model if not already available
            if technology == "ollama":
                model_already_available = False
                try:
                    tags_resp = await client.get(f"{base_url}/api/tags")
                    if tags_resp.status_code == 200:
                        available_models = [m["name"] for m in tags_resp.json().get("models", [])]
                        requested = framework_model
                        model_already_available = any(
                            m == requested or m == f"{requested}:latest" or requested == m.split(":")[0]
                            for m in available_models
                        )
                except Exception:
                    pass

                if not model_already_available:
                    deployment_state["container"]["status"] = "pulling_model"
                    pull_resp = await client.post(
                        f"{base_url}/api/pull",
                        json={"name": framework_model, "stream": False},
                        timeout=600.0,
                    )
                    if pull_resp.status_code != 200:
                        raise HTTPException(status_code=500, detail=f"Failed to pull model: {pull_resp.text}")
                else:
                    deployment_state["container"]["status"] = "model_ready"

        # Get real container stats
        cpu, mem, lat = get_container_stats(container_name)
        deployment_state["container"]["status"] = "running"
        deployment_state["container"]["cpu"] = cpu
        deployment_state["container"]["memory"] = mem
        deployment_state["container"]["latency"] = lat

        return {"success": True, "state": deployment_state["container"]}

    except HTTPException:
        raise
    except Exception as e:
        deployment_state["container"]["status"] = "error"
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/container/stop")
async def stop_container():
    """Stop the currently running framework container"""
    container_name = deployment_state["container"].get("container_name")
    if not container_name:
        technology = deployment_state["container"].get("technology") or "ollama"
        config = FRAMEWORK_CONFIGS.get(technology, FRAMEWORK_CONFIGS["ollama"])
        container_name = config["container_name"]

    if docker_client:
        try:
            container = docker_client.containers.get(container_name)
            container.stop(timeout=10)
        except docker.errors.NotFound:
            pass
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    deployment_state["container"]["status"] = "stopped"
    deployment_state["container"]["container_name"] = None
    deployment_state["container"]["cpu"] = 0
    deployment_state["container"]["memory"] = 0
    deployment_state["container"]["latency"] = 0

    return {"success": True, "state": deployment_state["container"]}


@app.post("/api/vm/start")
async def start_vm(request: DeploymentRequest):
    """Start VM deployment"""
    deployment_state["vm"]["status"] = "running"
    deployment_state["vm"]["technology"] = request.technology
    deployment_state["vm"]["model"] = request.model

    # Simulate startup metrics (VMs typically use more resources)
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
    # Generate mock metrics data
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


# Test definitions
TESTS = {
    "1": {"name": "Startup Time Comparison", "duration_range": (500, 1500)},
    "2": {"name": "Resource Usage Under Load", "duration_range": (1000, 3000)},
    "3": {"name": "Inference Speed Test", "duration_range": (800, 2000)},
    "4": {"name": "Scalability Test", "duration_range": (1500, 4000)},
}


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
    """Run selected tests (simulated)"""
    results = []

    for test_id in request.test_ids:
        if test_id not in TESTS:
            continue

        test = TESTS[test_id]
        duration = random.uniform(*test["duration_range"])
        passed = random.random() > 0.2  # 80% pass rate

        results.append({
            "id": test_id,
            "name": test["name"],
            "status": "passed" if passed else "failed",
            "duration": round(duration, 0)
        })

    return {"results": results}


# ============== Benchmark Endpoints ==============
from benchmarks import (
    OllamaBenchmark,
    OpenAICompatibleBenchmark,
    create_benchmark,
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
    "message": ""
}


class BenchmarkRequest(BaseModel):
    model: str
    categories: Optional[list[str]] = None
    warm_up: bool = True
    runs_per_prompt: int = 1
    technology: str = "ollama"


class RunAllTestsRequest(BaseModel):
    model: str
    platform: str = "docker"
    technology: str = "ollama"


@app.get("/api/benchmarks/status")
async def get_benchmark_status():
    """Get current benchmark status"""
    return benchmark_state


@app.get("/api/benchmarks/framework/status")
async def get_framework_status(technology: str = "ollama"):
    """Check if the selected framework is running and list available models"""
    benchmark = create_benchmark(technology)
    connected = await benchmark.check_connection()
    models = await benchmark.list_models() if connected else []
    await benchmark.close()

    return {
        "connected": connected,
        "models": models,
        "technology": technology
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
    """Run benchmarks on the selected framework"""
    global benchmark_state

    if benchmark_state["running"]:
        raise HTTPException(status_code=400, detail="Benchmark already running")

    technology = request.technology or deployment_state["container"].get("technology") or "ollama"
    framework_model = get_framework_model_name(request.model, technology)

    benchmark_state["running"] = True
    benchmark_state["progress"] = 0
    benchmark_state["status"] = "starting"
    benchmark_state["message"] = f"Initializing {technology} benchmark..."

    async def progress_callback(status: str, progress: int, message: str):
        benchmark_state["status"] = status
        benchmark_state["progress"] = progress
        benchmark_state["message"] = message

    try:
        summary = await run_benchmark(
            model=framework_model,
            categories=request.categories,
            warm_up=request.warm_up,
            runs_per_prompt=request.runs_per_prompt,
            progress_callback=progress_callback,
            technology=technology
        )

        # Save results to JSON
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


@app.get("/api/benchmarks/results")
async def get_benchmark_results():
    """Get list of all saved benchmark results"""
    results = list_benchmark_results()
    return {"results": results}


@app.get("/api/benchmarks/results/{filename}")
async def get_benchmark_result(filename: str):
    """Get specific benchmark result by filename"""
    from pathlib import Path
    results_dir = Path(__file__).parent / "results"

    # Also check parent results dir
    if not (results_dir / filename).exists():
        results_dir = Path(__file__).parent.parent / "results"

    filepath = results_dir / filename

    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Result not found")

    return load_benchmark_results(str(filepath))


@app.post("/api/benchmarks/run-all")
async def run_all_tests(request: RunAllTestsRequest):
    """Run all benchmark categories on the given model and save results as JSON."""
    global benchmark_state

    if benchmark_state["running"]:
        raise HTTPException(status_code=400, detail="Benchmark already running")

    benchmark_state["running"] = True
    benchmark_state["progress"] = 0
    benchmark_state["status"] = "starting"
    benchmark_state["message"] = "Running all tests..."

    async def progress_callback(status: str, progress: int, message: str):
        benchmark_state["status"] = status
        benchmark_state["progress"] = progress
        benchmark_state["message"] = message

    technology = request.technology or deployment_state["container"].get("technology") or "ollama"
    framework_model = get_framework_model_name(request.model, technology)

    try:
        # Run all categories
        summary = await run_benchmark(
            model=framework_model,
            categories=None,  # None = all categories
            warm_up=True,
            runs_per_prompt=1,
            progress_callback=progress_callback,
            technology=technology
        )

        filepath = save_benchmark_results(summary)

        benchmark_state["status"] = "completed"
        benchmark_state["progress"] = 100
        benchmark_state["message"] = "All tests completed"
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


# WebSocket for real-time metrics
@app.websocket("/ws/metrics")
async def websocket_metrics(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Receive any client messages (heartbeat, etc.)
            data = await websocket.receive_text()

            # Update metrics simulation when running
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
