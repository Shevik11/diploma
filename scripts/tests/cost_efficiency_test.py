"""
Cost and efficiency assessment for SLM models
Tests: tokens per second at various prompt lengths, memory efficiency,
response quality vs speed trade-off, throughput under load
"""
import requests
import json
import sys
import os
import time
import statistics
from pathlib import Path

RESULTS_DIR = Path(__file__).parent.parent.parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def test_cost_efficiency(model_name, port=11434):
    """Run cost and efficiency benchmarks for model comparison"""
    host = os.environ.get("SLM_TEST_HOST", "localhost")
    url = f"http://{host}:{port}/api/generate"

    # Prompts of varying complexity to measure efficiency across workloads
    test_scenarios = [
        {
            "category": "Trivial Task",
            "prompt": "Say hello.",
            "expected_min_tokens": 1,
            "complexity": "trivial"
        },
        {
            "category": "Short Answer",
            "prompt": "What is the capital of France? Answer in one word.",
            "expected_min_tokens": 1,
            "complexity": "simple"
        },
        {
            "category": "Medium Task",
            "prompt": "Explain what an API is in 2-3 sentences.",
            "expected_min_tokens": 20,
            "complexity": "medium"
        },
        {
            "category": "Longer Generation",
            "prompt": "Write a short paragraph (50-100 words) about the benefits of open-source software.",
            "expected_min_tokens": 40,
            "complexity": "medium"
        },
        {
            "category": "Complex Reasoning",
            "prompt": "A store sells apples for $2 each and oranges for $3 each. If I buy 5 apples and 3 oranges, how much do I spend? Show your work step by step.",
            "expected_min_tokens": 30,
            "complexity": "complex"
        },
        {
            "category": "Long Context Input",
            "prompt": (
                "Read this text and answer the question at the end.\n\n"
                "The history of computing spans several decades. In the 1940s, the first electronic "
                "computers were built, including ENIAC and Colossus. The 1950s saw the development of "
                "programming languages like FORTRAN and COBOL. The 1960s brought mainframe computers "
                "to businesses. The 1970s introduced personal computing with machines like the Altair "
                "8800 and Apple II. The 1980s saw the IBM PC and the rise of Microsoft. The 1990s "
                "brought the World Wide Web and the dot-com boom. The 2000s saw the rise of mobile "
                "computing and social media. The 2010s brought cloud computing and AI advances. "
                "The 2020s are seeing the rise of large language models and generative AI.\n\n"
                "Question: In which decade did personal computing begin?"
            ),
            "expected_min_tokens": 5,
            "complexity": "complex"
        },
        {
            "category": "Code Generation",
            "prompt": "Write a Python function that checks if a number is prime. Include a docstring.",
            "expected_min_tokens": 30,
            "complexity": "complex"
        },
        {
            "category": "Multi-step Instruction",
            "prompt": "1) Pick a random number between 1 and 10. 2) Multiply it by 3. 3) Add 7. 4) Tell me the result and show each step.",
            "expected_min_tokens": 20,
            "complexity": "medium"
        },
    ]

    results = {
        "model": model_name,
        "port": port,
        "timestamp": time.time(),
        "scenarios": [],
        "summary": {},
    }

    print(f"\n{'='*60}")
    print(f"COST & EFFICIENCY BENCHMARK: {model_name}")
    print(f"{'='*60}\n")

    all_durations = []
    all_tokens_per_sec = []
    all_eval_counts = []
    complexity_stats = {}

    for i, scenario in enumerate(test_scenarios, 1):
        category = scenario["category"]
        prompt = scenario["prompt"]
        complexity = scenario["complexity"]

        print(f"[{i:2d}/{len(test_scenarios)}] {category} (complexity: {complexity})")

        payload = {
            "model": model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.3
            }
        }

        try:
            start_time = time.time()
            response = requests.post(url, json=payload, timeout=180)
            response.raise_for_status()
            data = response.json()
            wall_time = time.time() - start_time

            response_text = data.get('response', '').strip()
            eval_count = data.get('eval_count', 0)
            eval_duration_ns = data.get('eval_duration', 0)
            prompt_eval_count = data.get('prompt_eval_count', 0)
            prompt_eval_duration_ns = data.get('prompt_eval_duration', 0)
            total_duration_ns = data.get('total_duration', 0)

            eval_duration_s = eval_duration_ns / 1_000_000_000 if eval_duration_ns > 0 else wall_time
            prompt_eval_s = prompt_eval_duration_ns / 1_000_000_000 if prompt_eval_duration_ns > 0 else 0
            total_duration_s = total_duration_ns / 1_000_000_000 if total_duration_ns > 0 else wall_time

            tokens_per_sec = eval_count / eval_duration_s if eval_duration_s > 0 else 0
            prompt_tokens_per_sec = prompt_eval_count / prompt_eval_s if prompt_eval_s > 0 else 0

            # Time to first token (approximate)
            ttft = total_duration_s - eval_duration_s if total_duration_s > eval_duration_s else 0

            scenario_result = {
                "category": category,
                "complexity": complexity,
                "prompt_length": len(prompt),
                "response_length": len(response_text),
                "wall_time_s": round(wall_time, 3),
                "total_duration_s": round(total_duration_s, 3),
                "eval_tokens": eval_count,
                "eval_duration_s": round(eval_duration_s, 3),
                "tokens_per_sec": round(tokens_per_sec, 2),
                "prompt_eval_tokens": prompt_eval_count,
                "prompt_eval_s": round(prompt_eval_s, 3),
                "prompt_tokens_per_sec": round(prompt_tokens_per_sec, 2),
                "time_to_first_token_s": round(ttft, 3),
                "response_preview": response_text[:80]
            }

            results["scenarios"].append(scenario_result)

            all_durations.append(wall_time)
            all_tokens_per_sec.append(tokens_per_sec)
            all_eval_counts.append(eval_count)

            if complexity not in complexity_stats:
                complexity_stats[complexity] = {"times": [], "speeds": [], "tokens": []}
            complexity_stats[complexity]["times"].append(wall_time)
            complexity_stats[complexity]["speeds"].append(tokens_per_sec)
            complexity_stats[complexity]["tokens"].append(eval_count)

            print(f"     Wall time: {wall_time:.2f}s | Tokens: {eval_count} | Speed: {tokens_per_sec:.1f} tok/s | TTFT: {ttft:.3f}s")

        except requests.exceptions.RequestException as e:
            print(f"     вњ— Error: {e}")
            results["scenarios"].append({
                "category": category,
                "complexity": complexity,
                "error": str(e)
            })

        print()

    # Calculate summary statistics
    if all_durations:
        results["summary"] = {
            "total_scenarios": len(test_scenarios),
            "successful_scenarios": len(all_durations),
            "avg_wall_time_s": round(statistics.mean(all_durations), 3),
            "median_wall_time_s": round(statistics.median(all_durations), 3),
            "min_wall_time_s": round(min(all_durations), 3),
            "max_wall_time_s": round(max(all_durations), 3),
            "avg_tokens_per_sec": round(statistics.mean(all_tokens_per_sec), 2),
            "median_tokens_per_sec": round(statistics.median(all_tokens_per_sec), 2),
            "total_tokens_generated": sum(all_eval_counts),
            "total_time_s": round(sum(all_durations), 3),
            "overall_throughput_tok_per_s": round(sum(all_eval_counts) / sum(all_durations), 2) if sum(all_durations) > 0 else 0,
        }

        # Per-complexity breakdown
        complexity_breakdown = {}
        for comp, stats in complexity_stats.items():
            complexity_breakdown[comp] = {
                "avg_time_s": round(statistics.mean(stats["times"]), 3),
                "avg_speed_tok_s": round(statistics.mean(stats["speeds"]), 2),
                "avg_tokens": round(statistics.mean(stats["tokens"]), 1),
                "count": len(stats["times"])
            }
        results["summary"]["by_complexity"] = complexity_breakdown

    # Rating based on speed
    avg_speed = results["summary"].get("avg_tokens_per_sec", 0)
    if avg_speed >= 30:
        rating = "Excellent - Very fast inference"
    elif avg_speed >= 15:
        rating = "Good - Acceptable speed"
    elif avg_speed >= 5:
        rating = "Fair - Slow but usable"
    else:
        rating = "Poor - Too slow for practical use"

    results["rating"] = rating

    print(f"{'='*60}")
    print(f"COST & EFFICIENCY RESULTS")
    print(f"{'='*60}")
    if results["summary"]:
        s = results["summary"]
        print(f"Avg Wall Time:       {s['avg_wall_time_s']:.3f}s")
        print(f"Avg Tokens/sec:      {s['avg_tokens_per_sec']:.2f}")
        print(f"Median Tokens/sec:   {s['median_tokens_per_sec']:.2f}")
        print(f"Total Tokens:        {s['total_tokens_generated']}")
        print(f"Overall Throughput:  {s['overall_throughput_tok_per_s']:.2f} tok/s")
        print()
        print("By Complexity:")
        print(f"  {'Level':<10} {'Avg Time':<12} {'Avg Speed':<15} {'Avg Tokens':<12}")
        print(f"  {'-'*49}")
        for comp in ["trivial", "simple", "medium", "complex"]:
            if comp in results["summary"].get("by_complexity", {}):
                c = results["summary"]["by_complexity"][comp]
                print(f"  {comp:<10} {c['avg_time_s']:<12.3f} {c['avg_speed_tok_s']:<15.2f} {c['avg_tokens']:<12.1f}")
    else:
        print("No successful scenarios.")

    print(f"\nRating: {rating}")
    print(f"{'='*60}\n")

    output_file = RESULTS_DIR / f"cost_efficiency_{model_name.replace(':', '_')}_{int(time.time())}.json"
    try:
        with output_file.open('w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)
        print(f"Results saved to: {output_file}\n")
    except Exception as e:
        print(f"Warning: Could not save results: {e}\n")

    return 0 if len(all_durations) > 0 else 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python cost_efficiency_test.py <model_name> [port]")
        sys.exit(1)

    model = sys.argv[1]
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 11434

    sys.exit(test_cost_efficiency(model, port))
