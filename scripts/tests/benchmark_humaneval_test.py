"""
HumanEval-Style Benchmark вЂ” Code Generation & Understanding
Based on the real HumanEval benchmark: the model must generate correct Python
functions given a docstring specification, then we verify with test cases.

Reference: Chen et al., "Evaluating Large Language Models Trained on Code" (2021)
"""
import requests
import json
import sys
import os
import time
import re
import textwrap
from pathlib import Path

RESULTS_DIR = Path(__file__).parent.parent.parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

def extract_code(response_text):
    """Extract Python code from a model response (handles markdown code blocks)."""
    # Try to find code in ```python ... ``` blocks
    match = re.search(r'```(?:python)?\s*\n(.*?)```', response_text, re.DOTALL)
    if match:
        return match.group(1).strip()
    # Try to find code starting with def
    match = re.search(r'(def\s+\w+.*?)(?:\n\n|\Z)', response_text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return response_text.strip()


def safe_exec_test(code, test_code, timeout_sec=5):
    """Execute code + test in a restricted way. Returns (passed, error_msg)."""
    full_code = code + "\n\n" + test_code
    try:
        exec_globals = {}
        exec(full_code, exec_globals)
        return True, None
    except AssertionError as e:
        return False, f"AssertionError: {e}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def test_humaneval(model_name, port=11434):
    """Run HumanEval-style code generation benchmark"""
    host = os.environ.get("SLM_TEST_HOST", "localhost")
    url = f"http://{host}:{port}/api/generate"

    test_cases = [
        {
            "category": "HumanEval вЂ” Two Sum",
            "prompt": (
                "Write a Python function `two_sum(nums, target)` that returns the indices "
                "of two numbers in the list `nums` that add up to `target`. "
                "Return a list of two indices. Assume exactly one solution exists.\n"
                "Only output the function, no explanation."
            ),
            "test_code": textwrap.dedent("""\
                assert sorted(two_sum([2, 7, 11, 15], 9)) == [0, 1]
                assert sorted(two_sum([3, 2, 4], 6)) == [1, 2]
                assert sorted(two_sum([3, 3], 6)) == [0, 1]
            """),
            "points": 15,
        },
        {
            "category": "HumanEval вЂ” Palindrome Check",
            "prompt": (
                "Write a Python function `is_palindrome(s)` that returns True if the string "
                "`s` is a palindrome (ignoring case and non-alphanumeric characters), False otherwise.\n"
                "Only output the function, no explanation."
            ),
            "test_code": textwrap.dedent("""\
                assert is_palindrome("racecar") == True
                assert is_palindrome("A man, a plan, a canal: Panama") == True
                assert is_palindrome("hello") == False
                assert is_palindrome("") == True
            """),
            "points": 10,
        },
        {
            "category": "HumanEval вЂ” FizzBuzz",
            "prompt": (
                "Write a Python function `fizzbuzz(n)` that returns a list of strings from 1 to n. "
                "For multiples of 3, use 'Fizz'. For multiples of 5, use 'Buzz'. "
                "For multiples of both, use 'FizzBuzz'. Otherwise, use the number as a string.\n"
                "Only output the function, no explanation."
            ),
            "test_code": textwrap.dedent("""\
                result = fizzbuzz(15)
                assert result[0] == '1'
                assert result[2] == 'Fizz'
                assert result[4] == 'Buzz'
                assert result[14] == 'FizzBuzz'
                assert len(result) == 15
            """),
            "points": 10,
        },
        {
            "category": "HumanEval вЂ” Fibonacci",
            "prompt": (
                "Write a Python function `fibonacci(n)` that returns the nth Fibonacci number. "
                "fibonacci(0) = 0, fibonacci(1) = 1, fibonacci(2) = 1, etc.\n"
                "Only output the function, no explanation."
            ),
            "test_code": textwrap.dedent("""\
                assert fibonacci(0) == 0
                assert fibonacci(1) == 1
                assert fibonacci(2) == 1
                assert fibonacci(10) == 55
                assert fibonacci(20) == 6765
            """),
            "points": 10,
        },
        {
            "category": "HumanEval вЂ” Max Subarray",
            "prompt": (
                "Write a Python function `max_subarray_sum(nums)` that returns the maximum "
                "sum of a contiguous subarray in the list `nums` (Kadane's algorithm).\n"
                "Only output the function, no explanation."
            ),
            "test_code": textwrap.dedent("""\
                assert max_subarray_sum([-2, 1, -3, 4, -1, 2, 1, -5, 4]) == 6
                assert max_subarray_sum([1]) == 1
                assert max_subarray_sum([-1, -2, -3]) == -1
                assert max_subarray_sum([5, 4, -1, 7, 8]) == 23
            """),
            "points": 15,
        },
        {
            "category": "HumanEval вЂ” Flatten List",
            "prompt": (
                "Write a Python function `flatten(lst)` that takes a nested list and returns "
                "a flat list. For example, flatten([1, [2, [3, 4], 5]]) returns [1, 2, 3, 4, 5].\n"
                "Only output the function, no explanation."
            ),
            "test_code": textwrap.dedent("""\
                assert flatten([1, [2, [3, 4], 5]]) == [1, 2, 3, 4, 5]
                assert flatten([]) == []
                assert flatten([1, 2, 3]) == [1, 2, 3]
                assert flatten([[1, 2], [3, [4, [5]]]]) == [1, 2, 3, 4, 5]
            """),
            "points": 15,
        },
        {
            "category": "HumanEval вЂ” Remove Duplicates",
            "prompt": (
                "Write a Python function `remove_duplicates(lst)` that returns a new list "
                "with duplicates removed, preserving the original order of first occurrences.\n"
                "Only output the function, no explanation."
            ),
            "test_code": textwrap.dedent("""\
                assert remove_duplicates([1, 2, 3, 2, 1, 4]) == [1, 2, 3, 4]
                assert remove_duplicates([]) == []
                assert remove_duplicates([1, 1, 1]) == [1]
                assert remove_duplicates(['a', 'b', 'a', 'c']) == ['a', 'b', 'c']
            """),
            "points": 10,
        },
        {
            "category": "HumanEval вЂ” Roman to Integer",
            "prompt": (
                "Write a Python function `roman_to_int(s)` that converts a Roman numeral "
                "string to an integer. Handle I, V, X, L, C, D, M and subtractive notation.\n"
                "Only output the function, no explanation."
            ),
            "test_code": textwrap.dedent("""\
                assert roman_to_int('III') == 3
                assert roman_to_int('IV') == 4
                assert roman_to_int('IX') == 9
                assert roman_to_int('XLII') == 42
                assert roman_to_int('MCMXCIV') == 1994
            """),
            "points": 15,
        },
        {
            "category": "HumanEval вЂ” Valid Parentheses",
            "prompt": (
                "Write a Python function `is_valid_parens(s)` that returns True if the string "
                "of parentheses '(', ')', '{', '}', '[', ']' is valid (properly opened and closed).\n"
                "Only output the function, no explanation."
            ),
            "test_code": textwrap.dedent("""\
                assert is_valid_parens('()') == True
                assert is_valid_parens('()[]{}') == True
                assert is_valid_parens('(]') == False
                assert is_valid_parens('([)]') == False
                assert is_valid_parens('{[]}') == True
                assert is_valid_parens('') == True
            """),
            "points": 15,
        },
        {
            "category": "HumanEval вЂ” Count Vowels",
            "prompt": (
                "Write a Python function `count_vowels(s)` that returns the number of vowels "
                "(a, e, i, o, u вЂ” both upper and lower case) in the string `s`.\n"
                "Only output the function, no explanation."
            ),
            "test_code": textwrap.dedent("""\
                assert count_vowels('hello') == 2
                assert count_vowels('AEIOU') == 5
                assert count_vowels('bcdfg') == 0
                assert count_vowels('') == 0
                assert count_vowels('Python Programming') == 4
            """),
            "points": 10,
        },
    ]

    results = {
        "model": model_name,
        "port": port,
        "benchmark": "HumanEval-style",
        "timestamp": time.time(),
        "tests": [],
        "total_score": 0,
        "max_score": sum(tc["points"] for tc in test_cases),
        "pass_count": 0,
    }

    print(f"\n{'='*70}")
    print(f"HUMANEVAL-STYLE CODE BENCHMARK вЂ” {model_name}")
    print(f"Tests: {len(test_cases)}  Max score: {results['max_score']}")
    print(f"{'='*70}\n")

    for i, tc in enumerate(test_cases, 1):
        category = tc["category"]
        points = tc["points"]

        print(f"[{i:2d}/{len(test_cases)}] {category}")

        payload = {
            "model": model_name,
            "prompt": tc["prompt"],
            "stream": False,
            "options": {"temperature": 0.1},
        }

        try:
            t0 = time.time()
            response = requests.post(url, json=payload, timeout=120)
            response.raise_for_status()
            elapsed = time.time() - t0
            data = response.json()
            response_text = data.get("response", "").strip()

            # Extract and test code
            code = extract_code(response_text)
            passed, error = safe_exec_test(code, tc["test_code"])

            score = points if passed else 0
            status = "[SUCCESS]" if passed else "[ERROR]"

            if passed:
                results["pass_count"] += 1

            results["tests"].append({
                "category": category,
                "generated_code": code[:500],
                "passed": passed,
                "error": error,
                "score": score,
                "max_score": points,
                "time": round(elapsed, 2),
            })
            results["total_score"] += score

            if passed:
                print(f"  [{status}] All test cases passed  ({elapsed:.1f}s)")
            else:
                print(f"  [{status}] {error}  ({elapsed:.1f}s)")

        except requests.exceptions.RequestException as e:
            print(f"  [ERROR] Error: {e}")
            results["tests"].append({
                "category": category,
                "error": str(e),
                "score": 0,
                "max_score": points,
            })

    # Summary
    pct = (results["total_score"] / results["max_score"] * 100) if results["max_score"] > 0 else 0
    pass_rate = (results["pass_count"] / len(test_cases) * 100) if test_cases else 0
    results["percentage"] = round(pct, 1)
    results["pass_rate"] = round(pass_rate, 1)

    print(f"\n{'='*70}")
    print(f"HUMANEVAL RESULTS вЂ” {model_name}")
    print(f"{'='*70}")
    print(f"Score: {results['total_score']}/{results['max_score']} ({pct:.1f}%)")
    print(f"Pass@1: {results['pass_count']}/{len(test_cases)} ({pass_rate:.1f}%)")

    if pct >= 80:
        rating = "Excellent"
    elif pct >= 60:
        rating = "Good"
    elif pct >= 40:
        rating = "Fair"
    else:
        rating = "Poor"
    results["rating"] = rating
    print(f"Rating: {rating}")
    print(f"{'='*70}\n")

    output_file = RESULTS_DIR / f"humaneval_{model_name.replace(':', '_')}_{int(time.time())}.json"
    try:
        with output_file.open('w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)
        print(f"Results saved to: {output_file}\n")
    except Exception as e:
        print(f"Warning: Could not save results: {e}\n")

    return 0 if pct >= 50 else 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python benchmark_humaneval_test.py <model_name> [port]")
        sys.exit(1)

    model = sys.argv[1]
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 11434
    sys.exit(test_humaneval(model, port))
