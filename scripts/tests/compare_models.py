"""
Compare multiple models side-by-side
Tests same prompts across different models/ports
"""
import requests
import json
import sys
import os
import time
from pathlib import Path
from tabulate import tabulate

RESULTS_DIR = Path(__file__).parent.parent.parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

def compare_models(models_config):
    """
    Compare multiple models
    models_config: list of dicts with 'name', 'port'
    """
    
    test_prompts = [
        "What is 2+2?",
        "Explain AI in one sentence.",
        "Write a haiku about coding."
    ]
    
    print(f"\n=== Comparing {len(models_config)} Models ===\n")
    
    comparison_results = []
    
    for prompt_idx, prompt in enumerate(test_prompts, 1):
        print(f"\n[Prompt {prompt_idx}/{len(test_prompts)}] {prompt}\n")
        
        for model_config in models_config:
            model_name = model_config['name']
            port = model_config['port']
            
            host = os.environ.get("SLM_TEST_HOST", "localhost")
            url = f"http://{host}:{port}/api/generate"
            payload = {
                "model": model_name,
                "prompt": prompt,
                "stream": False
            }
            
            print(f"  Testing {model_name}...", end=" ")
            
            try:
                start_time = time.time()
                response = requests.post(url, json=payload, timeout=60)
                response.raise_for_status()
                data = response.json()
                duration = time.time() - start_time
                
                response_text = data.get('response', '').strip()
                eval_count = data.get('eval_count', 0)
                eval_duration = data.get('eval_duration', 1) / 1_000_000_000
                tokens_per_sec = eval_count / eval_duration if eval_duration > 0 else 0
                
                comparison_results.append({
                    "prompt": prompt,
                    "model": model_name,
                    "port": port,
                    "response": response_text[:200],  # First 200 chars
                    "full_response": response_text,
                    "duration": duration,
                    "tokens": eval_count,
                    "tokens_per_sec": tokens_per_sec,
                    "response_length": len(response_text)
                })
                
                print(f"вњ“ {duration:.2f}s, {tokens_per_sec:.1f} tok/s")
                print(f"    Response: {response_text[:80]}...")
                
            except requests.exceptions.RequestException as e:
                print(f"вњ— Error: {e}")
                comparison_results.append({
                    "prompt": prompt,
                    "model": model_name,
                    "port": port,
                    "error": str(e)
                })
    
    # Generate comparison table
    print("\n\n=== Performance Summary ===\n")
    
    # Group by model
    model_stats = {}
    for result in comparison_results:
        if "error" in result:
            continue
        
        model = result["model"]
        if model not in model_stats:
            model_stats[model] = {
                "times": [],
                "speeds": [],
                "tokens": []
            }
        
        model_stats[model]["times"].append(result["duration"])
        model_stats[model]["speeds"].append(result["tokens_per_sec"])
        model_stats[model]["tokens"].append(result["tokens"])
    
    # Create table
    table_data = []
    for model, stats in model_stats.items():
        avg_time = sum(stats["times"]) / len(stats["times"])
        avg_speed = sum(stats["speeds"]) / len(stats["speeds"])
        total_tokens = sum(stats["tokens"])
        
        table_data.append([
            model,
            f"{avg_time:.2f}s",
            f"{avg_speed:.1f}",
            total_tokens
        ])
    
    headers = ["Model", "Avg Time", "Avg Speed (tok/s)", "Total Tokens"]
    print(tabulate(table_data, headers=headers, tablefmt="grid"))
    
    # Save detailed results
    output_file = RESULTS_DIR / f"comparison_{int(time.time())}.json"
    try:
        with output_file.open('w', encoding='utf-8') as f:
            json.dump({
                "timestamp": time.time(),
                "models": [m["name"] for m in models_config],
                "results": comparison_results,
                "summary": model_stats
            }, f, indent=2)
        print(f"\nDetailed results saved to: {output_file}")
    except Exception as e:
        print(f"Warning: Could not save results: {e}")
    
    return 0

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python compare_models.py <model1:port1> <model2:port2> ...")
        print("Example: python compare_models.py llama2:11434 mistral:11435")
        sys.exit(1)
    
    # Parse arguments
    models = []
    for arg in sys.argv[1:]:
        if ':' in arg:
            name, port = arg.rsplit(':', 1)
            models.append({"name": name, "port": int(port)})
        else:
            print(f"Error: Invalid format '{arg}'. Use model:port format.")
            sys.exit(1)
    
    if len(models) < 2:
        print("Error: Need at least 2 models to compare")
        sys.exit(1)
    
    sys.exit(compare_models(models))
