"""
MMLU-Style Benchmark — Massive Multitask Language Understanding
Based on the real MMLU benchmark used to evaluate SLMs in academic papers.
Tests broad knowledge across STEM, humanities, social sciences, and professional domains.
Each question is multiple-choice (A/B/C/D) — the model must pick the correct letter.

Reference: Hendrycks et al., "Measuring Massive Multitask Language Understanding" (2021)
"""
import requests
import json
import sys
import os
import time
import re


def test_mmlu(model_name, port=11434):
    """Run MMLU-style multiple-choice knowledge benchmark"""
    host = os.environ.get("SLM_TEST_HOST", "localhost")
    url = f"http://{host}:{port}/api/generate"

    test_cases = [
        # === STEM ===
        {
            "category": "STEM — Physics",
            "prompt": (
                "Answer with ONLY the letter (A, B, C, or D).\n\n"
                "A ball is thrown vertically upward. At the highest point of its trajectory, "
                "which of the following is true?\n"
                "A) Both velocity and acceleration are zero\n"
                "B) Velocity is zero but acceleration is non-zero\n"
                "C) Velocity is non-zero but acceleration is zero\n"
                "D) Both velocity and acceleration are non-zero"
            ),
            "answer": "B",
            "points": 10,
        },
        {
            "category": "STEM — Chemistry",
            "prompt": (
                "Answer with ONLY the letter (A, B, C, or D).\n\n"
                "What is the pH of a neutral solution at 25°C?\n"
                "A) 0\n"
                "B) 1\n"
                "C) 7\n"
                "D) 14"
            ),
            "answer": "C",
            "points": 10,
        },
        {
            "category": "STEM — Biology",
            "prompt": (
                "Answer with ONLY the letter (A, B, C, or D).\n\n"
                "Which organelle is responsible for producing ATP in eukaryotic cells?\n"
                "A) Ribosome\n"
                "B) Golgi apparatus\n"
                "C) Mitochondria\n"
                "D) Endoplasmic reticulum"
            ),
            "answer": "C",
            "points": 10,
        },
        {
            "category": "STEM — Computer Science",
            "prompt": (
                "Answer with ONLY the letter (A, B, C, or D).\n\n"
                "What is the worst-case time complexity of quicksort?\n"
                "A) O(n)\n"
                "B) O(n log n)\n"
                "C) O(n²)\n"
                "D) O(2^n)"
            ),
            "answer": "C",
            "points": 10,
        },
        {
            "category": "STEM — Mathematics",
            "prompt": (
                "Answer with ONLY the letter (A, B, C, or D).\n\n"
                "What is the derivative of f(x) = x³ + 2x?\n"
                "A) 3x² + 2\n"
                "B) 3x² + 2x\n"
                "C) x² + 2\n"
                "D) 3x + 2"
            ),
            "answer": "A",
            "points": 10,
        },

        # === HUMANITIES ===
        {
            "category": "Humanities — History",
            "prompt": (
                "Answer with ONLY the letter (A, B, C, or D).\n\n"
                "The Treaty of Westphalia (1648) is most significant for:\n"
                "A) Ending the American Revolution\n"
                "B) Establishing the concept of state sovereignty in international relations\n"
                "C) Creating the United Nations\n"
                "D) Ending World War I"
            ),
            "answer": "B",
            "points": 10,
        },
        {
            "category": "Humanities — Philosophy",
            "prompt": (
                "Answer with ONLY the letter (A, B, C, or D).\n\n"
                "The 'categorical imperative' is a central concept in the philosophy of:\n"
                "A) Aristotle\n"
                "B) John Stuart Mill\n"
                "C) Immanuel Kant\n"
                "D) Friedrich Nietzsche"
            ),
            "answer": "C",
            "points": 10,
        },
        {
            "category": "Humanities — Literature",
            "prompt": (
                "Answer with ONLY the letter (A, B, C, or D).\n\n"
                "In George Orwell's '1984', what is the name of the totalitarian ruling party's leader?\n"
                "A) Napoleon\n"
                "B) Big Brother\n"
                "C) The Commander\n"
                "D) O'Brien"
            ),
            "answer": "B",
            "points": 10,
        },

        # === SOCIAL SCIENCES ===
        {
            "category": "Social Science — Economics",
            "prompt": (
                "Answer with ONLY the letter (A, B, C, or D).\n\n"
                "When a country's central bank raises interest rates, the most likely "
                "immediate effect is:\n"
                "A) Increased consumer spending\n"
                "B) Decreased value of the domestic currency\n"
                "C) Reduced borrowing and slower economic growth\n"
                "D) Higher inflation"
            ),
            "answer": "C",
            "points": 10,
        },
        {
            "category": "Social Science — Psychology",
            "prompt": (
                "Answer with ONLY the letter (A, B, C, or D).\n\n"
                "The 'bystander effect' refers to the phenomenon where:\n"
                "A) People are more helpful in groups\n"
                "B) Individuals are less likely to help when others are present\n"
                "C) Witnesses always call emergency services\n"
                "D) Group decisions are always better than individual ones"
            ),
            "answer": "B",
            "points": 10,
        },

        # === PROFESSIONAL KNOWLEDGE ===
        {
            "category": "Professional — Law",
            "prompt": (
                "Answer with ONLY the letter (A, B, C, or D).\n\n"
                "In common law systems, the principle of 'stare decisis' means:\n"
                "A) All laws must be written down\n"
                "B) Courts should follow precedents set by previous decisions\n"
                "C) The accused is always presumed guilty\n"
                "D) Laws expire after a set period"
            ),
            "answer": "B",
            "points": 10,
        },
        {
            "category": "Professional — Medicine",
            "prompt": (
                "Answer with ONLY the letter (A, B, C, or D).\n\n"
                "Which vitamin deficiency causes scurvy?\n"
                "A) Vitamin A\n"
                "B) Vitamin B12\n"
                "C) Vitamin C\n"
                "D) Vitamin D"
            ),
            "answer": "C",
            "points": 10,
        },
        {
            "category": "Professional — Engineering",
            "prompt": (
                "Answer with ONLY the letter (A, B, C, or D).\n\n"
                "In electrical engineering, Ohm's law states that:\n"
                "A) Power equals voltage times current\n"
                "B) Voltage equals current times resistance\n"
                "C) Current equals voltage times resistance\n"
                "D) Resistance equals current divided by voltage"
            ),
            "answer": "B",
            "points": 10,
        },
        {
            "category": "Professional — Business",
            "prompt": (
                "Answer with ONLY the letter (A, B, C, or D).\n\n"
                "A company's 'burn rate' refers to:\n"
                "A) The rate at which it generates revenue\n"
                "B) The rate at which it spends cash reserves\n"
                "C) The speed of employee turnover\n"
                "D) The rate of product returns"
            ),
            "answer": "B",
            "points": 10,
        },
        {
            "category": "STEM — Statistics",
            "prompt": (
                "Answer with ONLY the letter (A, B, C, or D).\n\n"
                "In a normal distribution, approximately what percentage of data falls "
                "within one standard deviation of the mean?\n"
                "A) 50%\n"
                "B) 68%\n"
                "C) 95%\n"
                "D) 99.7%"
            ),
            "answer": "B",
            "points": 10,
        },
    ]

    results = {
        "model": model_name,
        "port": port,
        "benchmark": "MMLU-style",
        "timestamp": time.time(),
        "tests": [],
        "total_score": 0,
        "max_score": sum(tc["points"] for tc in test_cases),
        "breakdown": {},
    }

    print(f"\n{'='*70}")
    print(f"MMLU-STYLE BENCHMARK — {model_name}")
    print(f"Tests: {len(test_cases)}  Max score: {results['max_score']}")
    print(f"{'='*70}\n")

    for i, tc in enumerate(test_cases, 1):
        category = tc["category"]
        domain = category.split(" — ")[0]
        prompt = tc["prompt"]
        correct = tc["answer"]
        points = tc["points"]

        print(f"[{i:2d}/{len(test_cases)}] {category}")

        payload = {
            "model": model_name,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1, "top_p": 0.9},
        }

        try:
            t0 = time.time()
            response = requests.post(url, json=payload, timeout=60)
            response.raise_for_status()
            elapsed = time.time() - t0
            data = response.json()
            response_text = data.get("response", "").strip()

            # Extract the chosen letter
            chosen = None
            # Try to find a standalone letter at the start or after common patterns
            match = re.search(r'\b([A-D])\b', response_text[:30])
            if match:
                chosen = match.group(1)

            score = points if chosen == correct else 0
            status = "✓" if score > 0 else "✗"

            grp = results["breakdown"].setdefault(domain, {"correct": 0, "total": 0})
            grp["total"] += 1
            if score > 0:
                grp["correct"] += 1

            results["tests"].append({
                "category": category,
                "domain": domain,
                "correct_answer": correct,
                "model_answer": chosen,
                "response_text": response_text[:200],
                "score": score,
                "max_score": points,
                "time": round(elapsed, 2),
            })
            results["total_score"] += score

            print(f"  [{status}] Model: {chosen}  Correct: {correct}  ({elapsed:.1f}s)")

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
    results["percentage"] = round(pct, 1)

    print(f"\n{'='*70}")
    print(f"MMLU RESULTS — {model_name}")
    print(f"{'='*70}")
    print(f"Score: {results['total_score']}/{results['max_score']} ({pct:.1f}%)\n")

    print(f"{'Domain':<25} {'Accuracy':<15}")
    print("-" * 40)
    for domain, data in sorted(results["breakdown"].items()):
        acc = data["correct"] / data["total"] * 100 if data["total"] > 0 else 0
        print(f"{domain:<25} {data['correct']}/{data['total']} ({acc:.0f}%)")

    if pct >= 80:
        rating = "Excellent"
    elif pct >= 60:
        rating = "Good"
    elif pct >= 40:
        rating = "Fair"
    else:
        rating = "Poor"
    results["rating"] = rating
    print(f"\nRating: {rating}")
    print(f"{'='*70}\n")

    output_file = f"results/mmlu_{model_name.replace(':', '_')}_{int(time.time())}.json"
    try:
        with open(output_file, "w") as f:
            json.dump(results, f, indent=2)
        print(f"Results saved to: {output_file}\n")
    except Exception as e:
        print(f"Warning: Could not save results: {e}\n")

    return 0 if pct >= 50 else 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python benchmark_mmlu_test.py <model_name> [port]")
        sys.exit(1)

    model = sys.argv[1]
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 11434
    sys.exit(test_mmlu(model, port))
