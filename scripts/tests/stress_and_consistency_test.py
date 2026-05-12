"""
Stress and Consistency Tests for LLM Models
Tests: response consistency across multiple calls, handling of edge cases,
context length management, and repeated pattern recognition
"""
import requests
import json
import sys
import os
import time
import hashlib
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

try:
    from result_utils import save_results
except Exception:  # pragma: no cover
    save_results = None

RESULTS_DIR = Path(__file__).parent.parent.parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def test_consistency(model_name, port=11434, num_repeats=3):
    """Test if model gives consistent responses to the same prompt"""
    host = os.environ.get("SLM_TEST_HOST", "localhost")
    url = f"http://{host}:{port}/api/generate"
    
    consistency_prompts = [
        "What is 2+2?",
        "What is the capital of France?",
        "Name a primary color.",
        "Is water wet?",
        "What day comes after Monday?",
    ]
    
    results = {
        "model": model_name,
        "port": port,
        "timestamp": time.time(),
        "num_repeats": num_repeats,
        "tests": [],
        "total_consistency_score": 0,
        "max_consistency_score": 0,
        "consistency_percentage": 0
    }
    
    print(f"\n{'='*60}")
    print(f"CONSISTENCY TEST: {model_name}")
    print(f"Testing {num_repeats} repetitions per prompt")
    print(f"{'='*60}\n")
    
    for prompt_idx, prompt in enumerate(consistency_prompts, 1):
        print(f"[{prompt_idx}/{len(consistency_prompts)}] Testing: {prompt}")
        
        responses = []
        timings = []
        
        for attempt in range(num_repeats):
            # Determinism for the consistency test:
            #   * temperature 0  -> always pick the most-likely token
            #   * fixed seed     -> identical sampling state across calls
            #   * top_k 1        -> argmax decoding regardless of sampler
            # With these set, any remaining variance is due to the runtime
            # (e.g. KV-cache state) and is what we actually want to measure.
            payload = {
                "model": model_name,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.0,
                    "top_k": 1,
                    "seed": 42,  # constant seed across attempts
                },
            }
            
            try:
                start = time.time()
                response = requests.post(url, json=payload, timeout=60)
                response.raise_for_status()
                data = response.json()
                duration = time.time() - start
                
                response_text = data.get('response', '').strip()
                responses.append(response_text)
                timings.append(duration)
                
                print(f"  Attempt {attempt+1}: {response_text[:50]}... ({duration:.2f}s)")
                
            except requests.exceptions.RequestException as e:
                print(f"  Attempt {attempt+1}: Error - {e}")
                responses.append(None)
                timings.append(0)
        
        # Calculate consistency
        valid_responses = [r for r in responses if r is not None]
        
        if not valid_responses:
            consistency_score = 0
            consistency_pct = 0
            similarity_report = "All requests failed"
        else:
            # Calculate similarity between responses
            # Use keyword matching as a simple similarity metric
            all_words = set()
            word_sets = []
            
            for resp in valid_responses:
                words = set(resp.lower().split())
                word_sets.append(words)
                all_words.update(words)
            
            # Calculate Jaccard similarity between all pairs
            similarities = []
            for i in range(len(word_sets)):
                for j in range(i+1, len(word_sets)):
                    intersection = len(word_sets[i] & word_sets[j])
                    union = len(word_sets[i] | word_sets[j])
                    if union > 0:
                        similarity = intersection / union
                        similarities.append(similarity)
            
            if similarities:
                avg_similarity = sum(similarities) / len(similarities)
                consistency_score = int(avg_similarity * 100)
                consistency_pct = consistency_score
            else:
                consistency_score = 100
                consistency_pct = 100
            
            # Check for exact duplicates
            unique_responses = len(set(valid_responses))
            if unique_responses == 1:
                similarity_report = "All identical (perfect consistency)"
            else:
                similarity_report = f"Avg similarity: {consistency_pct:.0f}%, {unique_responses} unique variants"
        
        test_result = {
            "prompt": prompt,
            "num_responses": len(valid_responses),
            "consistency_score": consistency_score,
            "consistency_percentage": consistency_pct,
            "unique_responses": len(set(valid_responses)) if valid_responses else 0,
            "responses_sample": valid_responses[:2] if valid_responses else [],
            "timing_stats": {
                "min": min(timings) if timings else 0,
                "max": max(timings) if timings else 0,
                "avg": sum(timings) / len(timings) if timings else 0
            },
            "similarity_report": similarity_report
        }
        
        results["tests"].append(test_result)
        results["total_consistency_score"] += consistency_score
        results["max_consistency_score"] += 100
        
        print(f"  {similarity_report}\n")
    
    # Calculate overall consistency
    results["consistency_percentage"] = (
        results["total_consistency_score"] / results["max_consistency_score"] * 100
        if results["max_consistency_score"] > 0 else 0
    )
    
    # Determine rating
    if results["consistency_percentage"] >= 90:
        rating = "Excellent - Highly consistent responses"
    elif results["consistency_percentage"] >= 75:
        rating = "Good - Generally consistent"
    elif results["consistency_percentage"] >= 60:
        rating = "Fair - Some variability"
    else:
        rating = "Poor - Inconsistent responses"
    
    results["rating"] = rating
    
    print(f"{'='*60}")
    print(f"CONSISTENCY RESULTS")
    print(f"{'='*60}")
    print(f"Overall Consistency: {results['consistency_percentage']:.1f}%")
    print(f"Rating: {rating}")
    print(f"{'='*60}\n")
    
    if save_results is not None:
        save_results(results, "consistency", model_name, "stress_consistency", subkey="consistency")
    else:  # pragma: no cover
        output_file = RESULTS_DIR / f"consistency_{model_name.replace(':', '_')}_{int(time.time())}.json"
        try:
            with output_file.open('w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            print(f"Results saved to: {output_file}\n")
        except Exception as e:
            print(f"Warning: Could not save results: {e}\n")

    return 0 if results["consistency_percentage"] >= 50 else 1


def _do_one_request(url: str, model_name: str, prompt: str, timeout: int = 120) -> dict:
    """Single Ollama call used by the stress (load) test."""
    payload = {
        "model": model_name,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.3},
    }
    start = time.time()
    try:
        response = requests.post(url, json=payload, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        duration = time.time() - start
        return {
            "prompt": prompt[:50],
            "duration": duration,
            "tokens": data.get("eval_count", 0),
            "response_length": len(data.get("response", "")),
            "success": True,
        }
    except requests.exceptions.RequestException as e:
        return {
            "prompt": prompt[:50],
            "duration": time.time() - start,
            "error": str(e),
            "success": False,
        }


def test_stress(model_name, port=11434, num_concurrent=5):
    """Stress / load test the model with concurrent requests.

    The test fires ``num_concurrent`` requests in parallel using a thread
    pool. Throughput is measured as wall-clock requests-per-second across
    the full burst, so it is NOT just an average of individual latencies.
    Set ``SLM_STRESS_CONCURRENCY`` to override the parallelism (default 5).
    """
    host = os.environ.get("SLM_TEST_HOST", "localhost")
    url = f"http://{host}:{port}/api/generate"

    # Guard against a malformed env value (e.g. ``SLM_STRESS_CONCURRENCY=abc``
    # or an empty string) — previously this raised ``ValueError`` and aborted
    # the whole stress test before any request was made. Fall back to the
    # function default and warn instead so a typo in the environment never
    # prevents the benchmark from running.
    raw_concurrency = os.environ.get("SLM_STRESS_CONCURRENCY")
    if raw_concurrency is None or str(raw_concurrency).strip() == "":
        concurrency = num_concurrent
    else:
        try:
            concurrency = int(str(raw_concurrency).strip())
        except (TypeError, ValueError):
            print(
                f"[WARN] Ignoring invalid SLM_STRESS_CONCURRENCY={raw_concurrency!r}; "
                f"falling back to default {num_concurrent}.",
                file=sys.stderr,
            )
            concurrency = num_concurrent
    concurrency = max(1, concurrency)

    base_prompts = [
        "What is AI?",
        "Explain machine learning",
        "What is deep learning?",
        "Tell me about neural networks",
        "How does training work?",
    ]
    # Repeat the prompts so total count >= 2x concurrency to actually exercise
    # the worker pool.
    repeats = max(2, (concurrency * 2 + len(base_prompts) - 1) // len(base_prompts))
    stress_prompts = base_prompts * repeats

    results = {
        "model": model_name,
        "port": port,
        "timestamp": time.time(),
        "concurrency": concurrency,
        "num_requests": len(stress_prompts),
        "requests": [],
        "success_count": 0,
        "failure_count": 0,
        "total_time": 0,
        "avg_response_time": 0,
        "throughput": 0,
    }

    print(f"\n{'='*60}")
    print(f"STRESS / LOAD TEST: {model_name}")
    print(
        f"Running {len(stress_prompts)} requests at concurrency={concurrency}"
    )
    print(f"{'='*60}\n")

    test_start = time.time()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [
            pool.submit(_do_one_request, url, model_name, p)
            for p in stress_prompts
        ]
        for idx, future in enumerate(as_completed(futures), 1):
            res = future.result()
            results["requests"].append(res)
            if res.get("success"):
                results["success_count"] += 1
                print(f"[{idx}/{len(stress_prompts)}] [SUCCESS] {res['duration']:.2f}s")
            else:
                results["failure_count"] += 1
                print(
                    f"[{idx}/{len(stress_prompts)}] [ERROR] "
                    f"{str(res.get('error', ''))[:40]}"
                )
    test_end = time.time()
    results["total_time"] = test_end - test_start
    
    # Calculate metrics
    successful_requests = [r for r in results["requests"] if r.get("success")]
    
    if successful_requests:
        results["avg_response_time"] = sum(r["duration"] for r in successful_requests) / len(successful_requests)
        results["throughput"] = len(successful_requests) / results["total_time"]  # requests per second
    
    success_rate = (results["success_count"] / len(stress_prompts) * 100) if stress_prompts else 0
    results["success_rate"] = success_rate
    
    # Determine rating
    if success_rate == 100 and results["avg_response_time"] < 30:
        rating = "Excellent - Stable under stress"
    elif success_rate >= 95 and results["avg_response_time"] < 45:
        rating = "Good - Handles stress well"
    elif success_rate >= 80:
        rating = "Fair - Some failures under stress"
    else:
        rating = "Poor - Cannot handle stress"
    
    results["rating"] = rating
    
    print(f"\n{'='*60}")
    print(f"STRESS TEST RESULTS")
    print(f"{'='*60}")
    print(f"Success Rate: {success_rate:.1f}% ({results['success_count']}/{len(stress_prompts)})")
    print(f"Avg Response Time: {results['avg_response_time']:.2f}s")
    print(f"Throughput: {results['throughput']:.2f} req/s")
    print(f"Total Time: {results['total_time']:.2f}s")
    print(f"Rating: {rating}")
    print(f"{'='*60}\n")
    
    if save_results is not None:
        save_results(results, "stress", model_name, "stress_consistency", subkey="stress")
    else:  # pragma: no cover
        output_file = RESULTS_DIR / f"stress_{model_name.replace(':', '_')}_{int(time.time())}.json"
        try:
            with output_file.open('w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            print(f"Results saved to: {output_file}\n")
        except Exception as e:
            print(f"Warning: Could not save results: {e}\n")

    return 0 if success_rate >= 80 else 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python stress_and_consistency_test.py <model_name> [port]")
        print("   or: python stress_and_consistency_test.py <test_type> <model_name> [port]")
        print("Test types: consistency, stress, both")
        sys.exit(1)

    supported_types = {"consistency", "stress", "both"}

    # Backend invokes scripts as: <script> <model_name> <port>
    # Keep backward compatibility with explicit mode: <script> <test_type> <model_name> <port>
    if sys.argv[1] in supported_types:
        test_type = sys.argv[1]
        if len(sys.argv) < 3:
            print("Usage: python stress_and_consistency_test.py <test_type> <model_name> [port]")
            sys.exit(1)
        model = sys.argv[2]
        port = int(sys.argv[3]) if len(sys.argv) > 3 else 11434
    else:
        test_type = "both"
        model = sys.argv[1]
        port = int(sys.argv[2]) if len(sys.argv) > 2 else 11434

    if test_type == "consistency":
        sys.exit(test_consistency(model, port))
    if test_type == "stress":
        sys.exit(test_stress(model, port))

    result1 = test_consistency(model, port)
    result2 = test_stress(model, port)
    sys.exit(max(result1, result2))
