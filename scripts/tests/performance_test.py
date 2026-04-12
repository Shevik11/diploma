"""
Performance benchmarking for Ollama models
Measures: response time, tokens/sec, latency
"""
import requests
import time
import json
import sys
import os
import statistics
from pathlib import Path

RESULTS_DIR = Path(__file__).parent.parent.parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

def test_performance(model_name, port=11434, num_tests=5):
    """Run performance benchmark"""
    host = os.environ.get("SLM_TEST_HOST", "localhost")
    url = f"http://{host}:{port}/api/generate"
    
    test_prompts = [
        "What is 2+2?",
        "Explain quantum computing in one sentence.",
        "Write a haiku about technology.",
        "What is the capital of France?",
        "Define artificial intelligence briefly."
    ]
    
    results = {
        "model": model_name,
        "port": port,
        "tests": [],
        "avg_time": 0,
        "avg_tokens_per_sec": 0,
        "total_tokens": 0
    }
    
    print(f"\n=== Performance Test: {model_name} ===\n")
    
    for i, prompt in enumerate(test_prompts[:num_tests], 1):
        print(f"[{i}/{num_tests}] Testing: {prompt[:50]}...")
        
        payload = {
            "model": model_name,
            "prompt": prompt,
            "stream": False
        }
        
        start_time = time.time()
        
        try:
            response = requests.post(url, json=payload, timeout=120)
            response.raise_for_status()
            data = response.json()
            
            end_time = time.time()
            duration = end_time - start_time
            
            # Extract metrics
            total_duration = data.get('total_duration', 0) / 1_000_000_000  # Convert to seconds
            eval_count = data.get('eval_count', 0)
            eval_duration = data.get('eval_duration', 0) / 1_000_000_000
            
            tokens_per_sec = eval_count / eval_duration if eval_duration > 0 else 0
            
            test_result = {
                "prompt": prompt,
                "duration": duration,
                "total_duration": total_duration,
                "tokens": eval_count,
                "tokens_per_sec": tokens_per_sec,
                "response_length": len(data.get('response', ''))
            }
            
            results["tests"].append(test_result)
            
            print(f"  [SUCCESS] Time: {duration:.2f}s | Tokens: {eval_count} | Speed: {tokens_per_sec:.2f} tok/s")
            
        except requests.exceptions.RequestException as e:
            print(f"  [ERROR] Error: {e}")
            test_result = {
                "prompt": prompt,
                "error": str(e)
            }
            results["tests"].append(test_result)
    
    # Calculate averages
    successful_tests = [t for t in results["tests"] if "error" not in t]
    
    if successful_tests:
        results["avg_time"] = statistics.mean([t["duration"] for t in successful_tests])
        results["avg_tokens_per_sec"] = statistics.mean([t["tokens_per_sec"] for t in successful_tests])
        results["total_tokens"] = sum([t["tokens"] for t in successful_tests])
        results["success_rate"] = len(successful_tests) / len(results["tests"]) * 100
        
        print(f"\n=== Summary ===")
        print(f"Success Rate: {results['success_rate']:.0f}%")
        print(f"Average Time: {results['avg_time']:.2f}s")
        print(f"Average Speed: {results['avg_tokens_per_sec']:.2f} tokens/sec")
        print(f"Total Tokens: {results['total_tokens']}")
    else:
        print("\n[ERROR] All tests failed!")
        return 1
    
    # Save results
    output_file = RESULTS_DIR / f"performance_{model_name.replace(':', '_')}_{int(time.time())}.json"
    try:
        with output_file.open('w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to: {output_file}")
    except Exception as e:
        print(f"Warning: Could not save results: {e}")
    
    return 0

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python performance_test.py <model_name> [port] [num_tests]")
        sys.exit(1)
    
    model = sys.argv[1]
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 11434
    num_tests = int(sys.argv[3]) if len(sys.argv) > 3 else 5
    
    sys.exit(test_performance(model, port, num_tests))
