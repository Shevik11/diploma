"""
Comprehensive Test Suite Runner
Runs all tests against a model and generates a comprehensive report
"""
import subprocess
import sys
import time
import json
import os
from pathlib import Path


def get_container_name(port):
    """Find the docker container running on the given port"""
    try:
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}\t{{.Ports}}"],
            capture_output=True, text=True, check=True
        )
        for line in result.stdout.splitlines():
            if f":{port}->" in line or f"{port}/tcp" in line:
                return line.split("\t")[0]
    except Exception:
        pass
    return "ollama"

def run_test(test_script, model_name, port, *args, master_file=None):
    """Run a single test script.

    When ``master_file`` is provided, the path is exported to the child via
    ``SLM_OUTPUT_FILE`` so that scripts using ``result_utils.save_results``
    consolidate their output into one shared JSON file.
    """
    env = os.environ.copy()
    env["OLLAMA_CONTAINER"] = get_container_name(port)
    if master_file is not None:
        env["SLM_OUTPUT_FILE"] = str(master_file)
    # Force UTF-8 on Windows children so non-ASCII test prompts/print()s do
    # not crash with UnicodeEncodeError when the parent runs under cp1251 etc.
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")

    cmd = [sys.executable, test_script, model_name, str(port)] + list(args)
    print(f"\n{'='*70}")
    print(f"Running: {' '.join(cmd)}")
    print(f"{'='*70}\n")
    
    try:
        result = subprocess.run(cmd, env=env, capture_output=False, text=True)
        return result.returncode == 0
    except Exception as e:
        print(f"Error running test: {e}")
        return False


def main():
    if len(sys.argv) < 2:
        print("Usage: python run_all_tests.py <model_name> [port]")
        print("Example: python run_all_tests.py llama2 11434")
        sys.exit(1)
    
    model_name = sys.argv[1]
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 11434
    
    print(f"\n{'='*70}")
    print(f"COMPREHENSIVE TEST SUITE FOR {model_name}")
    print(f"Port: {port}")
    print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}\n")
    
    # Get the scripts directory
    scripts_dir = Path(__file__).parent
    
    # Create results directory if it doesn't exist
    results_dir = scripts_dir.parent.parent / "results"
    results_dir.mkdir(exist_ok=True)

    # ---- Consolidated master file -------------------------------------------
    # All child scripts that go through ``result_utils.save_results`` will
    # append their section into this single JSON.  We pre-create it with the
    # top-level metadata so even no-op runs leave a valid artefact, and we
    # print its absolute path on a dedicated line so the e2e test (and any
    # downstream tool) can locate it deterministically.
    safe_model = model_name.replace(":", "_").replace("/", "_")
    master_file = results_dir / f"run_{safe_model}_{int(time.time())}.json"
    initial_payload = {
        "model": model_name,
        "port": port,
        "timestamp": time.time(),
        "test_sections": {},
    }
    try:
        with open(master_file, "w", encoding="utf-8") as fh:
            json.dump(initial_payload, fh, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Warning: could not initialise master file: {e}")
    print(f"Master results file: {master_file}")
    
    tests = [
        ("Original Quality Test", "quality_test.py", []),
        ("Performance Test", "performance_test.py", ["5"]),
        ("Advanced Quality Test", "advanced_quality_test.py", []),
        ("Hard Tests (Logic / Math / Code)", "hard_tests.py", []),
        ("MMLU Benchmark (Knowledge)", "benchmark_mmlu_test.py", []),
        ("Reasoning Benchmark (ARC + HellaSwag + Winogrande)", "benchmark_reasoning_test.py", []),
        ("GSM8K Benchmark (Math)", "benchmark_gsm8k_test.py", []),
        ("TruthfulQA Benchmark (Hallucination)", "benchmark_truthfulqa_test.py", []),
        ("HumanEval Benchmark (Code)", "benchmark_humaneval_test.py", []),
        ("Multilingual Test", "multilingual_test.py", []),
        ("Summarization & Comprehension Test", "summarization_test.py", []),
        ("Context Window & Memory Test", "context_window_test.py", []),
        ("Cost & Efficiency Test", "cost_efficiency_test.py", []),
        ("Consistency Test", "stress_and_consistency_test.py", ["consistency"]),
        ("Stress Test", "stress_and_consistency_test.py", ["stress"]),
        ("Safety & Robustness Test", "safety_robustness_test.py", []),
        ("Cold Start Test", "cold_start_test.py", []),
        ("OOM Detection Test", "oom_detection_test.py", []),
        ("Resource Usage Test", "resource_usage_test.py", []),
        ("VRAM Monitor Test", "vram_monitor_test.py", []),
        ("Config Matrix Test", "config_matrix_test.py", []),
        ("RAM Boundary Test", "ram_boundary_test.py", []),
    ]
    
    results_summary = {
        "model": model_name,
        "port": port,
        "timestamp": time.time(),
        "tests_run": [],
        "total_passed": 0,
        "total_failed": 0
    }
    
    for test_name, test_script, extra_args in tests:
        test_path = scripts_dir / test_script
        if not test_path.exists():
            print(f"Warning: {test_script} not found, skipping {test_name}")
            results_summary["tests_run"].append({
                "name": test_name,
                "passed": False,
                "reason": "Test script not found"
            })
            results_summary["total_failed"] += 1
            continue
        
        print(f"\n{'#'*70}")
        print(f"# {test_name}")
        print(f"{'#'*70}")
        
        success = run_test(
            str(test_path), model_name, port, *extra_args, master_file=master_file
        )
        
        results_summary["tests_run"].append({
            "name": test_name,
            "passed": success,
            "timestamp": time.time()
        })
        
        if success:
            results_summary["total_passed"] += 1
            print(f"\n✓ {test_name} PASSED")
        else:
            results_summary["total_failed"] += 1
            print(f"\n✗ {test_name} FAILED or returned non-zero")
    
    # Print summary
    print(f"\n\n{'='*70}")
    print(f"TEST SUITE SUMMARY")
    print(f"{'='*70}")
    print(f"Model: {model_name}")
    print(f"Port: {port}")
    print(f"Total Tests Run: {len(results_summary['tests_run'])}")
    print(f"Passed: {results_summary['total_passed']}")
    print(f"Failed: {results_summary['total_failed']}")
    print(f"Success Rate: {results_summary['total_passed'] / len(results_summary['tests_run']) * 100:.1f}%")
    
    print(f"\nTest Results:")
    for test in results_summary["tests_run"]:
        status = "✓" if test["passed"] else "✗"
        print(f"  {status} {test['name']}")
    
    print(f"{'='*70}\n")
    
    # Save summary --- both as a standalone file (backwards compat) and as a
    # ``run_summary`` key inside the consolidated master file.
    summary_file = results_dir / f"test_suite_summary_{safe_model}_{int(time.time())}.json"
    try:
        with open(summary_file, 'w', encoding="utf-8") as f:
            json.dump(results_summary, f, indent=2, ensure_ascii=False)
        print(f"Summary saved to: {summary_file}\n")
    except Exception as e:
        print(f"Warning: Could not save summary: {e}\n")

    try:
        master_data = {}
        if master_file.exists():
            with open(master_file, "r", encoding="utf-8") as fh:
                master_data = json.load(fh)
        # Re-assert top-level metadata in case no child script populated it.
        master_data.setdefault("model", model_name)
        master_data.setdefault("port", port)
        master_data.setdefault("timestamp", time.time())
        master_data.setdefault("test_sections", {})
        master_data["run_summary"] = results_summary
        with open(master_file, "w", encoding="utf-8") as fh:
            json.dump(master_data, fh, indent=2, ensure_ascii=False)
        print(f"Master results file: {master_file}\n")
    except Exception as e:
        print(f"Warning: could not finalise master file: {e}\n")
    
    # Exit with success only if all tests passed
    return 0 if results_summary["total_failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
