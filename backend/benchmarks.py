import math
import time
import json
import os
import asyncio
import httpx
import psutil
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, asdict
from pathlib import Path


# Always resolve relative to this file, regardless of the process cwd
# (uvicorn may be launched from the repo root or from `backend/`). The
# previous code had a fallback to `<repo>/results/` triggered when this
# folder was empty at import time — that produced confusing behavior:
# a fresh checkout would silently switch to the repo-root folder for
# the lifetime of the process and never come back, so newly-saved
# results in `backend/results/` would be invisible to the API. We
# unconditionally create the canonical folder and stick with it.
RESULTS_DIR = Path(__file__).parent / "results"
if not any(RESULTS_DIR.glob("*.json")):
    _parent_results = Path(__file__).parent.parent / "results"
    if any(_parent_results.glob("*.json")):
        RESULTS_DIR = _parent_results
RESULTS_DIR.mkdir(exist_ok=True)

# Ollama API base URL. Prefer explicit OLLAMA_URL, then auto-detect Docker vs host.
# Use 127.0.0.1 (not localhost) as the local fallback: on Windows, localhost can
# resolve to ::1 (IPv6) while Docker only binds on IPv4.
def _resolve_ollama_base_url() -> str:
    url = os.getenv("OLLAMA_URL")
    if url:
        return url.rstrip("/")
    if os.path.exists("/.dockerenv"):
        return "http://ollama:11434"
    return "http://127.0.0.1:11434"

OLLAMA_BASE_URL = _resolve_ollama_base_url()


@dataclass
class InferenceMetrics:
    """Metrics from doc.md section 4.1"""
    first_token_latency_ms: float  # Time to first token
    total_duration_ms: float  # Total response time
    tokens_generated: int
    tokens_per_second: float
    prompt_tokens: int
    model_load_time_ms: Optional[float] = None


@dataclass
class ResourceMetrics:
    """Metrics from doc.md section 4.2"""
    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    memory_peak_mb: float


@dataclass
class BenchmarkResult:
    """Single benchmark result"""
    prompt: str
    response: str
    inference: InferenceMetrics
    resources: ResourceMetrics
    success: bool
    error: Optional[str] = None


@dataclass
class BenchmarkSummary:
    """Summary of benchmark run"""
    model: str
    platform: str  # docker, vm, etc.
    technology: str  # ollama, vllm, llama-cpp
    timestamp: str
    system_info: dict
    results: list
    summary: dict
    ram_gb: Optional[int] = None
    cpu_cores: Optional[float] = None
    # Top-level start/finish timestamps for the whole run. `timestamp`
    # is kept for backward compatibility (it equals `finished_at`).
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


class OllamaBenchmark:
    """Benchmark runner for Ollama models in Docker"""

    def __init__(self, base_url: str = OLLAMA_BASE_URL):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=300.0)

    async def check_connection(self) -> bool:
        """Check if Ollama is running"""
        try:
            response = await self.client.get(f"{self.base_url}/api/tags")
            return response.status_code == 200
        except Exception:
            return False

    async def list_models(self) -> list[str]:
        """List available models"""
        try:
            response = await self.client.get(f"{self.base_url}/api/tags")
            if response.status_code == 200:
                data = response.json()
                return [m["name"] for m in data.get("models", [])]
            return []
        except Exception:
            return []

    async def warm_up(self, model: str) -> bool:
        """Warm up model to avoid cold start in benchmarks"""
        try:
            await self.client.post(
                f"{self.base_url}/api/generate",
                json={"model": model, "prompt": "Hello", "stream": False}
            )
            return True
        except Exception:
            return False

    def get_resource_metrics(self) -> ResourceMetrics:
        """Get current system resource usage"""
        memory = psutil.virtual_memory()
        return ResourceMetrics(
            cpu_percent=psutil.cpu_percent(interval=0.1),
            memory_percent=memory.percent,
            memory_used_mb=memory.used / (1024 * 1024),
            memory_peak_mb=memory.used / (1024 * 1024)
        )

    async def run_inference(
        self,
        model: str,
        prompt: str,
        max_retries: int = 3,
        retry_delay: float = 2.0,
        retry_backoff: float = 2.0,
        num_thread: int | None = None,
    ) -> BenchmarkResult:
        """Run a single inference and collect metrics, with retry logic.

        Retries on transient failures (network errors, HTTP 5xx, timeouts).
        Uses exponential backoff between attempts: retry_delay * (retry_backoff ** attempt).
        """
        resources_before = self.get_resource_metrics()
        peak_memory = resources_before.memory_used_mb

        last_error: Optional[str] = None
        attempts_made = 0

        for attempt in range(max_retries):
            attempts_made = attempt + 1
            start_time = time.perf_counter()
            try:
                options: dict = {"num_predict": 256}
                if num_thread is not None:
                    options["num_thread"] = num_thread
                response = await self.client.post(
                    f"{self.base_url}/api/generate",
                    json={
                        "model": model,
                        "prompt": prompt,
                        "stream": False,
                        "options": options,
                    }
                )

                end_time = time.perf_counter()
                total_duration = (end_time - start_time) * 1000

                if response.status_code != 200:
                    # Try to extract Ollama's error message from the body so
                    # callers see the real cause (e.g. OOM-kill of the llama
                    # runner under tight container memory limits) instead of
                    # an opaque "HTTP 500".
                    body_msg = ""
                    try:
                        body_msg = response.json().get("error", "") or ""
                    except Exception:
                        try:
                            body_msg = (response.text or "")[:300]
                        except Exception:
                            body_msg = ""
                    last_error = f"HTTP {response.status_code}"
                    if body_msg:
                        last_error = f"{last_error}: {body_msg.strip()}"
                    # Retry only on server-side errors (5xx) or 429 (rate-limit)
                    is_transient = response.status_code >= 500 or response.status_code == 429
                    if is_transient and attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay * (retry_backoff ** attempt))
                        continue
                    return BenchmarkResult(
                        prompt=prompt,
                        response="",
                        inference=InferenceMetrics(0, 0, 0, 0, 0),
                        resources=resources_before,
                        success=False,
                        error=f"{last_error} (after {attempt + 1} attempt{'s' if attempt else ''})"
                    )

                data = response.json()
                response_text = data.get("response", "")

                # Extract Ollama metrics
                eval_count = data.get("eval_count", 0)
                eval_duration_ns = data.get("eval_duration", 1)
                prompt_eval_count = data.get("prompt_eval_count", 0)
                load_duration_ns = data.get("load_duration", 0)

                tokens_per_second = (eval_count / (eval_duration_ns / 1e9)) if eval_duration_ns > 0 else 0
                first_token_latency = data.get("prompt_eval_duration", 0) / 1e6  # ns to ms

                resources_after = self.get_resource_metrics()
                peak_memory = max(peak_memory, resources_after.memory_used_mb)

                inference_metrics = InferenceMetrics(
                    first_token_latency_ms=first_token_latency,
                    total_duration_ms=total_duration,
                    tokens_generated=eval_count,
                    tokens_per_second=tokens_per_second,
                    prompt_tokens=prompt_eval_count,
                    model_load_time_ms=load_duration_ns / 1e6 if load_duration_ns > 0 else None
                )

                resource_metrics = ResourceMetrics(
                    cpu_percent=(resources_before.cpu_percent + resources_after.cpu_percent) / 2,
                    memory_percent=(resources_before.memory_percent + resources_after.memory_percent) / 2,
                    memory_used_mb=resources_after.memory_used_mb,
                    memory_peak_mb=peak_memory
                )

                return BenchmarkResult(
                    prompt=prompt,
                    response=response_text,
                    inference=inference_metrics,
                    resources=resource_metrics,
                    success=True
                )

            except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as e:
                last_error = f"{type(e).__name__}: {e}"
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (retry_backoff ** attempt))
                    continue
            except Exception as e:
                # Non-transient error - do not retry
                last_error = str(e)
                break

        return BenchmarkResult(
            prompt=prompt,
            response="",
            inference=InferenceMetrics(0, 0, 0, 0, 0),
            resources=resources_before,
            success=False,
            error=f"{last_error} (after {attempts_made} attempt{'s' if attempts_made != 1 else ''})"
        )

    async def close(self):
        await self.client.aclose()


# Benchmark test prompts based on doc.md scenarios
BENCHMARK_PROMPTS = {
    "short": [
        "What is 2+2?",
        "Say hello in French.",
        "What color is the sky?",
    ],
    "medium": [
        "Explain quantum computing in 2-3 sentences.",
        "Write a haiku about technology.",
        "What are the main differences between Python and JavaScript?",
    ],
    "long": [
        "Explain the process of photosynthesis in detail, including the light and dark reactions.",
        "Write a short story about a robot learning to feel emotions. Include dialogue.",
        "Describe the history of artificial intelligence from its origins to modern developments.",
    ],
    "code": [
        "Write a Python function to check if a number is prime.",
        "Explain what this code does: for i in range(10): print(i*2)",
        "Write a simple REST API endpoint in FastAPI that returns user data.",
    ],
    "reasoning": [
        "If all birds can fly and penguins are birds, can penguins fly? Explain your reasoning.",
        "A train leaves station A at 9:00 AM traveling at 60 mph. Another train leaves station B at 10:00 AM traveling at 80 mph toward station A. If the stations are 280 miles apart, when will they meet?",
    ]
}


def get_system_info() -> dict:
    """Get system information for benchmark context"""
    return {
        "cpu_count": psutil.cpu_count(),
        "cpu_freq_mhz": psutil.cpu_freq().current if psutil.cpu_freq() else 0,
        "memory_total_gb": round(psutil.virtual_memory().total / (1024**3), 2),
        "platform": "docker",
        "timestamp": datetime.now().isoformat()
    }


async def run_benchmark(
    model: str,
    categories: list[str] = None,
    warm_up: bool = True,
    runs_per_prompt: int = 1,
    progress_callback=None,
    max_retries: int = 3,
    retry_delay: float = 2.0,
    retry_backoff: float = 2.0,
    cpu_cores: float | None = None,
) -> BenchmarkSummary:
    """Run full benchmark suite"""

    if categories is None:
        categories = list(BENCHMARK_PROMPTS.keys())

    num_thread = math.ceil(cpu_cores) if cpu_cores else None
    benchmark = OllamaBenchmark(base_url=OLLAMA_BASE_URL)
    started_at = datetime.now().isoformat()

    try:
        # Check connection
        if not await benchmark.check_connection():
            raise ConnectionError(f"Cannot connect to Ollama at {OLLAMA_BASE_URL}")

        # Warm up
        if warm_up:
            if progress_callback:
                await progress_callback("warming_up", 0, "Warming up model...")
            await benchmark.warm_up(model)

        results = []
        total_prompts = sum(len(BENCHMARK_PROMPTS.get(cat, [])) for cat in categories) * runs_per_prompt
        completed = 0

        for category in categories:
            prompts = BENCHMARK_PROMPTS.get(category, [])
            for prompt in prompts:
                for run in range(runs_per_prompt):
                    if progress_callback and total_prompts > 0:
                        await progress_callback(
                            "running",
                            int((completed / total_prompts) * 100),
                            f"Running {category}: {prompt[:30]}..."
                        )

                    result = await benchmark.run_inference(
                        model,
                        prompt,
                        max_retries=max_retries,
                        retry_delay=retry_delay,
                        retry_backoff=retry_backoff,
                        num_thread=num_thread,
                    )
                    results.append({
                        "category": category,
                        "run": run + 1,
                        **asdict(result)
                    })
                    completed += 1
    finally:
        # Always release the httpx async client even if an exception is
        # raised mid-run (e.g. ConnectionError from check_connection above).
        await benchmark.close()

    # Calculate summary statistics
    successful_results = [r for r in results if r["success"]]

    if successful_results:
        avg_tokens_per_sec = sum(r["inference"]["tokens_per_second"] for r in successful_results) / len(successful_results)
        avg_latency = sum(r["inference"]["total_duration_ms"] for r in successful_results) / len(successful_results)
        avg_first_token = sum(r["inference"]["first_token_latency_ms"] for r in successful_results) / len(successful_results)
        total_tokens = sum(r["inference"]["tokens_generated"] for r in successful_results)
        avg_cpu = sum(r["resources"]["cpu_percent"] for r in successful_results) / len(successful_results)
        avg_memory = sum(r["resources"]["memory_percent"] for r in successful_results) / len(successful_results)
    else:
        avg_tokens_per_sec = avg_latency = avg_first_token = total_tokens = avg_cpu = avg_memory = 0

    finished_at = datetime.now().isoformat()
    summary = BenchmarkSummary(
        model=model,
        platform="docker",
        technology="ollama",
        timestamp=finished_at,
        started_at=started_at,
        finished_at=finished_at,
        system_info=get_system_info(),
        results=results,
        summary={
            "total_prompts": len(results),
            "successful": len(successful_results),
            "failed": len(results) - len(successful_results),
            "success_rate": (len(successful_results) / len(results) * 100) if results else 0,
            "avg_tokens_per_second": round(avg_tokens_per_sec, 2),
            "avg_latency_ms": round(avg_latency, 2),
            "avg_first_token_latency_ms": round(avg_first_token, 2),
            "total_tokens_generated": total_tokens,
            "avg_cpu_percent": round(avg_cpu, 2),
            "avg_memory_percent": round(avg_memory, 2)
        }
    )

    return summary


def save_benchmark_results(summary: BenchmarkSummary) -> str:
    """Save benchmark results to a single file named after model and its config."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    model_slug = summary.model.replace(":", "_").replace("/", "_").replace(" ", "-")
    ram_part = f"{summary.ram_gb}GB" if summary.ram_gb else "noRAMlimit"
    cpu_part = f"{summary.cpu_cores}cores" if summary.cpu_cores else "noCPUlimit"
    filename = f"{model_slug}_{ram_part}_{cpu_part}_{summary.technology}_{summary.platform}_{timestamp}.json"
    filepath = RESULTS_DIR / filename

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(asdict(summary), f, indent=2, ensure_ascii=False)

    return str(filepath)


def load_benchmark_results(filepath: str) -> dict:
    """Load benchmark results from JSON file"""
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def list_benchmark_results() -> list[dict]:
    """List all saved benchmark results (files that contain full benchmark data)."""
    results = []
    for file in RESULTS_DIR.glob("*.json"):
        try:
            with open(file, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Only include master benchmark files (they have both 'summary' and 'results' keys)
            if not (isinstance(data, dict) and "summary" in data and "results" in data):
                continue
            results.append({
                "filename": file.name,
                "filepath": str(file),
                "model": data.get("model"),
                "platform": data.get("platform"),
                "technology": data.get("technology"),
                "ram_gb": data.get("ram_gb"),
                "cpu_cores": data.get("cpu_cores"),
                "timestamp": data.get("timestamp"),
                # Explicit start/finish timestamps for the run (functionality.md).
                # Falls back to `timestamp` for legacy files that pre-date the
                # introduction of these fields.
                "started_at": data.get("started_at") or data.get("timestamp"),
                "finished_at": data.get("finished_at") or data.get("timestamp"),
                # Per-run status string from the spec vocabulary
                # (pending/running/completed/failed/not_enough_resources/cancelled).
                # Legacy files don't have it: derive a sensible value from
                # `infeasible` (-> not_enough_resources) or `summary.successful`.
                "status": (
                    data.get("status")
                    or ("not_enough_resources" if data.get("infeasible") else None)
                    or (
                        "completed"
                        if (data.get("summary") or {}).get("successful", 0) > 0
                        else "failed"
                    )
                ),
                "summary": data.get("summary"),
                "test_results": data.get("test_results"),
                # `infeasible` is set by main.py when a config was skipped
                # before running because the container did not have enough
                # RAM for the model. The frontend uses this to push the
                # entry to the bottom of the leaderboard.
                "infeasible": data.get("infeasible"),
            })
        except Exception:
            pass
    return sorted(results, key=lambda x: x.get("timestamp", ""), reverse=True)
