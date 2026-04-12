"""
GSM8K-Style Benchmark — Grade School Math
Based on the real GSM8K benchmark: multi-step math word problems requiring
chain-of-thought reasoning. The model must show work and arrive at a numeric answer.

Reference: Cobbe et al., "Training Verifiers to Solve Math Word Problems" (2021)
"""
import requests
import json
import sys
import os
import time
import re


def extract_final_number(text):
    """Extract the final numeric answer from a response (looks for #### pattern or last number)."""
    # GSM8K format: #### <number>
    match = re.search(r'####\s*(\d+)', text)
    if match:
        return int(match.group(1))
    # Fallback: find all numbers and take the last one mentioned
    numbers = re.findall(r'\b(\d+)\b', text)
    if numbers:
        return int(numbers[-1])
    return None


def test_gsm8k(model_name, port=11434):
    """Run GSM8K-style math word problem benchmark"""
    host = os.environ.get("SLM_TEST_HOST", "localhost")
    url = f"http://{host}:{port}/api/generate"

    test_cases = [
        {
            "category": "GSM8K — Basic Arithmetic",
            "prompt": (
                "Solve step by step, then give the final answer after ####.\n\n"
                "Janet's ducks lay 16 eggs per day. She eats three for breakfast every morning "
                "and bakes muffins for her friends every day with four. She sells the remainder "
                "at the farmers' market for $2 per egg. How much does she make every day?"
            ),
            "answer": 18,  # 16 - 3 - 4 = 9 eggs; 9 * 2 = $18
            "points": 15,
        },
        {
            "category": "GSM8K — Multi-step",
            "prompt": (
                "Solve step by step, then give the final answer after ####.\n\n"
                "A store sells notebooks for $4 each and pens for $1 each. "
                "Tom buys 5 notebooks and 8 pens. He pays with a $50 bill. "
                "How much change does he receive?"
            ),
            "answer": 22,  # 5*4 + 8*1 = 28; 50 - 28 = 22
            "points": 10,
        },
        {
            "category": "GSM8K — Fractions & Division",
            "prompt": (
                "Solve step by step, then give the final answer after ####.\n\n"
                "Natalia sold clips to 48 of her friends in April, and then she sold "
                "half as many clips in May. How many clips did Natalia sell altogether "
                "in April and May?"
            ),
            "answer": 72,  # 48 + 24 = 72
            "points": 10,
        },
        {
            "category": "GSM8K — Rate Problem",
            "prompt": (
                "Solve step by step, then give the final answer after ####.\n\n"
                "A car travels at 60 km/h for 2 hours, then at 80 km/h for 1.5 hours. "
                "What is the total distance traveled in kilometers?"
            ),
            "answer": 240,  # 60*2 + 80*1.5 = 120 + 120 = 240
            "points": 10,
        },
        {
            "category": "GSM8K — Percentage",
            "prompt": (
                "Solve step by step, then give the final answer after ####.\n\n"
                "A shirt originally costs $80. It is on sale for 25% off. "
                "Then there is an additional 10% discount on the sale price. "
                "What is the final price of the shirt in dollars?"
            ),
            "answer": 54,  # 80 * 0.75 = 60; 60 * 0.90 = 54
            "points": 15,
        },
        {
            "category": "GSM8K — Age Problem",
            "prompt": (
                "Solve step by step, then give the final answer after ####.\n\n"
                "Maria is twice as old as her son. In 10 years, the sum of their ages "
                "will be 70. How old is Maria now?"
            ),
            "answer": 100 // 3,  # Actually: let son = x, Maria = 2x. (2x+10)+(x+10) = 70 → 3x = 50 → x ≈ 16.67
            # Corrected: let's use a clean problem
            "points": 15,
        },
        {
            "category": "GSM8K — Work Problem",
            "prompt": (
                "Solve step by step, then give the final answer after ####.\n\n"
                "Weng earns $12 an hour for babysitting. Yesterday, she just did "
                "50 minutes of babysitting. How much did she earn?"
            ),
            "answer": 10,  # 12 * (50/60) = 10
            "points": 10,
        },
        {
            "category": "GSM8K — Profit Calculation",
            "prompt": (
                "Solve step by step, then give the final answer after ####.\n\n"
                "A baker buys flour for $5, sugar for $3, and eggs for $4. "
                "She makes 20 cupcakes and sells each for $2. "
                "What is her profit in dollars?"
            ),
            "answer": 28,  # Revenue: 20*2=40; Cost: 5+3+4=12; Profit: 40-12=28
            "points": 10,
        },
        {
            "category": "GSM8K — Ratio Problem",
            "prompt": (
                "Solve step by step, then give the final answer after ####.\n\n"
                "In a class, the ratio of boys to girls is 3:5. If there are 40 students "
                "in total, how many girls are there?"
            ),
            "answer": 25,  # 5/8 * 40 = 25
            "points": 10,
        },
        {
            "category": "GSM8K — Multi-step with Remainder",
            "prompt": (
                "Solve step by step, then give the final answer after ####.\n\n"
                "A library has 156 books to distribute equally among 7 shelves. "
                "How many books will be left over after distributing them equally?"
            ),
            "answer": 2,  # 156 / 7 = 22 remainder 2
            "points": 10,
        },
        {
            "category": "GSM8K — Combined Operations",
            "prompt": (
                "Solve step by step, then give the final answer after ####.\n\n"
                "Beth bakes 4 batches of 2 dozen cookies in a week. If these cookies "
                "are shared equally among 16 people, how many cookies does each person get?"
            ),
            "answer": 6,  # 4 * 24 = 96; 96 / 16 = 6
            "points": 10,
        },
        {
            "category": "GSM8K — Distance Problem",
            "prompt": (
                "Solve step by step, then give the final answer after ####.\n\n"
                "Two trains start from the same station at the same time, traveling in "
                "opposite directions. One travels at 50 km/h and the other at 70 km/h. "
                "After 3 hours, how far apart are they in kilometers?"
            ),
            "answer": 360,  # (50 + 70) * 3 = 360
            "points": 10,
        },
    ]

    # Fix the age problem to have a clean integer answer
    test_cases[5] = {
        "category": "GSM8K — Age Problem",
        "prompt": (
            "Solve step by step, then give the final answer after ####.\n\n"
            "Tom is 3 times as old as his son. In 12 years, Tom will be twice "
            "as old as his son. How old is Tom now?"
        ),
        "answer": 36,  # son=12, Tom=36. In 12 years: 48 = 2*24. ✓
        "points": 15,
    }

    results = {
        "model": model_name,
        "port": port,
        "benchmark": "GSM8K-style",
        "timestamp": time.time(),
        "tests": [],
        "total_score": 0,
        "max_score": sum(tc["points"] for tc in test_cases),
        "correct_count": 0,
    }

    print(f"\n{'='*70}")
    print(f"GSM8K-STYLE MATH BENCHMARK — {model_name}")
    print(f"Tests: {len(test_cases)}  Max score: {results['max_score']}")
    print(f"{'='*70}\n")

    for i, tc in enumerate(test_cases, 1):
        category = tc["category"]
        correct = tc["answer"]
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
            response = requests.post(url, json=payload, timeout=90)
            response.raise_for_status()
            elapsed = time.time() - t0
            data = response.json()
            response_text = data.get("response", "").strip()

            model_answer = extract_final_number(response_text)
            is_correct = model_answer == correct
            score = points if is_correct else 0
            status = "✓" if is_correct else "✗"

            if is_correct:
                results["correct_count"] += 1

            results["tests"].append({
                "category": category,
                "correct_answer": correct,
                "model_answer": model_answer,
                "response_text": response_text[:300],
                "score": score,
                "max_score": points,
                "time": round(elapsed, 2),
            })
            results["total_score"] += score

            print(f"  [{status}] Model: {model_answer}  Correct: {correct}  ({elapsed:.1f}s)")

        except requests.exceptions.RequestException as e:
            print(f"  [✗] Error: {e}")
            results["tests"].append({
                "category": category,
                "error": str(e),
                "score": 0,
                "max_score": points,
            })

    # Summary
    pct = (results["total_score"] / results["max_score"] * 100) if results["max_score"] > 0 else 0
    accuracy = (results["correct_count"] / len(test_cases) * 100) if test_cases else 0
    results["percentage"] = round(pct, 1)
    results["accuracy"] = round(accuracy, 1)

    print(f"\n{'='*70}")
    print(f"GSM8K RESULTS — {model_name}")
    print(f"{'='*70}")
    print(f"Score: {results['total_score']}/{results['max_score']} ({pct:.1f}%)")
    print(f"Accuracy: {results['correct_count']}/{len(test_cases)} ({accuracy:.1f}%)")

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

    output_file = f"results/gsm8k_{model_name.replace(':', '_')}_{int(time.time())}.json"
    try:
        with open(output_file, "w") as f:
            json.dump(results, f, indent=2)
        print(f"Results saved to: {output_file}\n")
    except Exception as e:
        print(f"Warning: Could not save results: {e}\n")

    return 0 if pct >= 50 else 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python benchmark_gsm8k_test.py <model_name> [port]")
        sys.exit(1)

    model = sys.argv[1]
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 11434
    sys.exit(test_gsm8k(model, port))
