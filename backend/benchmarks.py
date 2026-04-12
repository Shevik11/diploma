import asyncio
import time
import json
import os
import httpx
import psutil
import docker
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, asdict
from pathlib import Path


RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

# Ollama API base URL (Docker container)
OLLAMA_BASE_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")


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

    async def run_inference(self, model: str, prompt: str) -> BenchmarkResult:
        """Run a single inference and collect metrics"""
        resources_before = self.get_resource_metrics()
        peak_memory = resources_before.memory_used_mb

        start_time = time.perf_counter()
        first_token_time = None

        try:
            response = await self.client.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"num_predict": 256}
                }
            )

            end_time = time.perf_counter()
            total_duration = (end_time - start_time) * 1000

            if response.status_code != 200:
                return BenchmarkResult(
                    prompt=prompt,
                    response="",
                    inference=InferenceMetrics(0, 0, 0, 0, 0),
                    resources=resources_before,
                    success=False,
                    error=f"HTTP {response.status_code}"
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

        except Exception as e:
            return BenchmarkResult(
                prompt=prompt,
                response="",
                inference=InferenceMetrics(0, 0, 0, 0, 0),
                resources=resources_before,
                success=False,
                error=str(e)
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
    progress_callback=None
) -> BenchmarkSummary:
    """Run full benchmark suite"""

    if categories is None:
        categories = list(BENCHMARK_PROMPTS.keys())

    benchmark = OllamaBenchmark()

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
                if progress_callback:
                    await progress_callback(
                        "running",
                        int((completed / total_prompts) * 100),
                        f"Running {category}: {prompt[:30]}..."
                    )

                result = await benchmark.run_inference(model, prompt)
                results.append({
                    "category": category,
                    "run": run + 1,
                    **asdict(result)
                })
                completed += 1

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

    summary = BenchmarkSummary(
        model=model,
        platform="docker",
        technology="ollama",
        timestamp=datetime.now().isoformat(),
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
    """Save benchmark results to JSON file"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"benchmark_{summary.model.replace(':', '_')}_{summary.platform}_{timestamp}.json"
    filepath = RESULTS_DIR / filename

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(asdict(summary), f, indent=2, ensure_ascii=False)

    return str(filepath)


def load_benchmark_results(filepath: str) -> dict:
    """Load benchmark results from JSON file"""
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def list_benchmark_results() -> list[dict]:
    """List all saved benchmark results"""
    results = []
    for file in RESULTS_DIR.glob("benchmark_*.json"):
        try:
            with open(file, "r", encoding="utf-8") as f:
                data = json.load(f)
                results.append({
                    "filename": file.name,
                    "filepath": str(file),
                    "model": data.get("model"),
                    "platform": data.get("platform"),
                    "timestamp": data.get("timestamp"),
                    "summary": data.get("summary"),
                    "test_results": data.get("test_results"),
                })
        except Exception:
            pass
    return sorted(results, key=lambda x: x.get("timestamp", ""), reverse=True)
