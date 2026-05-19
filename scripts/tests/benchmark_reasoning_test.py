"""
Reasoning & Commonsense Benchmark — ARC + HellaSwag + Winogrande style
Based on real benchmarks used to evaluate SLMs in the Open LLM Leaderboard.

- ARC (AI2 Reasoning Challenge): Grade-school science multiple-choice
- HellaSwag: Commonsense sentence completion
- Winogrande: Pronoun resolution requiring world knowledge

References:
  Clark et al., "Think you have Solved Question Answering?" (ARC, 2018)
  Zellers et al., "HellaSwag" (2019)
  Sakaguchi et al., "WinoGrande" (2020)
"""
import requests
import json
import sys
import os
import time
import re
from pathlib import Path

RESULTS_DIR = Path(__file__).parent.parent.parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

def test_reasoning_benchmarks(model_name, port=11434):
    """Run ARC + HellaSwag + Winogrande style reasoning tests"""
    host = os.environ.get("SLM_TEST_HOST", "localhost")
    url = f"http://{host}:{port}/api/generate"

    test_cases = [
        # ── ARC-style (grade-school science reasoning) ───────────────────────
        {
            "category": "ARC — Earth Science",
            "prompt": (
                "Answer with ONLY the letter (A, B, C, or D).\n\n"
                "Which layer of Earth's atmosphere contains the ozone layer that "
                "protects us from ultraviolet radiation?\n"
                "A) Troposphere\n"
                "B) Stratosphere\n"
                "C) Mesosphere\n"
                "D) Thermosphere"
            ),
            "answer": "B",
            "points": 10,
            "benchmark": "ARC",
        },
        {
            "category": "ARC — Physical Science",
            "prompt": (
                "Answer with ONLY the letter (A, B, C, or D).\n\n"
                "A student pushes a box across the floor. The box moves at a constant speed. "
                "What can be concluded?\n"
                "A) The push force is greater than friction\n"
                "B) The push force equals the friction force\n"
                "C) There is no friction acting on the box\n"
                "D) The box is accelerating"
            ),
            "answer": "B",
            "points": 10,
            "benchmark": "ARC",
        },
        {
            "category": "ARC — Life Science",
            "prompt": (
                "Answer with ONLY the letter (A, B, C, or D).\n\n"
                "Which process allows plants to convert carbon dioxide and water "
                "into glucose and oxygen using sunlight?\n"
                "A) Cellular respiration\n"
                "B) Fermentation\n"
                "C) Photosynthesis\n"
                "D) Decomposition"
            ),
            "answer": "C",
            "points": 10,
            "benchmark": "ARC",
        },
        {
            "category": "ARC — Space Science",
            "prompt": (
                "Answer with ONLY the letter (A, B, C, or D).\n\n"
                "What causes the phases of the Moon?\n"
                "A) Earth's shadow falling on the Moon\n"
                "B) The Moon's changing distance from Earth\n"
                "C) The relative positions of the Sun, Earth, and Moon\n"
                "D) The Moon rotating on its axis"
            ),
            "answer": "C",
            "points": 10,
            "benchmark": "ARC",
        },
        {
            "category": "ARC — Chemistry",
            "prompt": (
                "Answer with ONLY the letter (A, B, C, or D).\n\n"
                "When iron is left outside in the rain, it rusts. This is an example of:\n"
                "A) A physical change\n"
                "B) A chemical change\n"
                "C) A change of state\n"
                "D) Evaporation"
            ),
            "answer": "B",
            "points": 10,
            "benchmark": "ARC",
        },

        # ── HellaSwag-style (commonsense completion) ─────────────────────────
        {
            "category": "HellaSwag — Daily Activity",
            "prompt": (
                "Choose the most plausible continuation. Answer with ONLY the letter.\n\n"
                "A person walks into a kitchen and opens the refrigerator. They take out "
                "eggs, butter, and milk. They then turn on the stove. What happens next?\n"
                "A) They start vacuuming the living room\n"
                "B) They begin cooking or preparing a meal\n"
                "C) They go outside to mow the lawn\n"
                "D) They put the items back and leave"
            ),
            "answer": "B",
            "points": 10,
            "benchmark": "HellaSwag",
        },
        {
            "category": "HellaSwag — Social Situation",
            "prompt": (
                "Choose the most plausible continuation. Answer with ONLY the letter.\n\n"
                "Two friends meet at a coffee shop. One of them looks upset and says "
                "'I just got some bad news.' The other friend:\n"
                "A) Starts talking about their own vacation plans\n"
                "B) Asks 'What happened? Are you okay?'\n"
                "C) Orders a coffee and ignores them\n"
                "D) Starts laughing loudly"
            ),
            "answer": "B",
            "points": 10,
            "benchmark": "HellaSwag",
        },
        {
            "category": "HellaSwag — Physical World",
            "prompt": (
                "Choose the most plausible continuation. Answer with ONLY the letter.\n\n"
                "A glass is placed on the edge of a table. A cat jumps onto the table "
                "and bumps into the glass. What most likely happens?\n"
                "A) The glass floats in the air\n"
                "B) The glass falls off the table and may break\n"
                "C) The glass becomes heavier\n"
                "D) The cat turns into a dog"
            ),
            "answer": "B",
            "points": 10,
            "benchmark": "HellaSwag",
        },
        {
            "category": "HellaSwag — Work Context",
            "prompt": (
                "Choose the most plausible continuation. Answer with ONLY the letter.\n\n"
                "An employee finishes writing a report and clicks 'Send' to email it "
                "to their manager. The next morning, the manager:\n"
                "A) Receives and reviews the report\n"
                "B) Forgets how to use a computer\n"
                "C) The report transforms into a poem\n"
                "D) The email travels back in time"
            ),
            "answer": "A",
            "points": 10,
            "benchmark": "HellaSwag",
        },
        {
            "category": "HellaSwag — Cause and Effect",
            "prompt": (
                "Choose the most plausible continuation. Answer with ONLY the letter.\n\n"
                "Heavy rain has been falling for three days straight in a low-lying area "
                "near a river. The river level has been rising steadily. What is most "
                "likely to happen next?\n"
                "A) The area experiences a drought\n"
                "B) The river may overflow and cause flooding\n"
                "C) The rain turns into snow immediately\n"
                "D) The river dries up"
            ),
            "answer": "B",
            "points": 10,
            "benchmark": "HellaSwag",
        },

        # ── Winogrande-style (pronoun resolution / world knowledge) ──────────
        {
            "category": "Winogrande — Pronoun Resolution 1",
            "prompt": (
                "Answer with ONLY the letter (A or B).\n\n"
                "The trophy doesn't fit in the suitcase because it is too big. "
                "What does 'it' refer to?\n"
                "A) The trophy\n"
                "B) The suitcase"
            ),
            "answer": "A",
            "points": 10,
            "benchmark": "Winogrande",
        },
        {
            "category": "Winogrande — Pronoun Resolution 2",
            "prompt": (
                "Answer with ONLY the letter (A or B).\n\n"
                "The trophy doesn't fit in the suitcase because it is too small. "
                "What does 'it' refer to?\n"
                "A) The trophy\n"
                "B) The suitcase"
            ),
            "answer": "B",
            "points": 10,
            "benchmark": "Winogrande",
        },
        {
            "category": "Winogrande — Pronoun Resolution 3",
            "prompt": (
                "Answer with ONLY the letter (A or B).\n\n"
                "The city council refused the demonstrators a permit because they "
                "feared violence. Who feared violence?\n"
                "A) The city council\n"
                "B) The demonstrators"
            ),
            "answer": "A",
            "points": 10,
            "benchmark": "Winogrande",
        },
        {
            "category": "Winogrande — Pronoun Resolution 4",
            "prompt": (
                "Answer with ONLY the letter (A or B).\n\n"
                "The doctor told the nurse that she had been overworking herself. "
                "Who had been overworking?\n"
                "A) The doctor\n"
                "B) The nurse"
            ),
            "answer": "B",
            "points": 10,
            "benchmark": "Winogrande",
        },
        {
            "category": "Winogrande — Pronoun Resolution 5",
            "prompt": (
                "Answer with ONLY the letter (A or B).\n\n"
                "Sam broke the window because he was careless. "
                "Who was careless?\n"
                "A) Sam\n"
                "B) The window"
            ),
            "answer": "A",
            "points": 10,
            "benchmark": "Winogrande",
        },
    ]

    results = {
        "model": model_name,
        "port": port,
        "benchmark": "ARC+HellaSwag+Winogrande",
        "timestamp": time.time(),
        "tests": [],
        "total_score": 0,
        "max_score": sum(tc["points"] for tc in test_cases),
        "breakdown": {},
    }

    print(f"\n{'='*70}")
    print(f"REASONING BENCHMARK (ARC + HellaSwag + Winogrande) — {model_name}")
    print(f"Tests: {len(test_cases)}  Max score: {results['max_score']}")
    print(f"{'='*70}\n")

    for i, tc in enumerate(test_cases, 1):
        category = tc["category"]
        bench = tc["benchmark"]
        correct = tc["answer"]
        points = tc["points"]

        print(f"[{i:2d}/{len(test_cases)}] {category}")

        payload = {
            "model": model_name,
            "prompt": tc["prompt"],
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

            # Extract chosen letter
            chosen = None
            match = re.search(r'\b([A-D])\b', response_text[:30])
            if match:
                chosen = match.group(1)

            score = points if chosen == correct else 0
            status = "[SUCCESS]" if score > 0 else "[ERROR]"

            grp = results["breakdown"].setdefault(bench, {"correct": 0, "total": 0})
            grp["total"] += 1
            if score > 0:
                grp["correct"] += 1

            results["tests"].append({
                "category": category,
                "benchmark": bench,
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
            print(f"  [ERROR] Error: {e}")
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
    print(f"REASONING BENCHMARK RESULTS — {model_name}")
    print(f"{'='*70}")
    print(f"Score: {results['total_score']}/{results['max_score']} ({pct:.1f}%)\n")

    print(f"{'Benchmark':<20} {'Accuracy':<15}")
    print("-" * 35)
    for bench, data in sorted(results["breakdown"].items()):
        acc = data["correct"] / data["total"] * 100 if data["total"] > 0 else 0
        print(f"{bench:<20} {data['correct']}/{data['total']} ({acc:.0f}%)")

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

    output_file = RESULTS_DIR / f"reasoning_{model_name.replace(':', '_')}_{int(time.time())}.json"
    try:
        with output_file.open('w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)
        print(f"Results saved to: {output_file}\n")
    except Exception as e:
        print(f"Warning: Could not save results: {e}\n")

    return 0 if pct >= 50 else 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python benchmark_reasoning_test.py <model_name> [port]")
        sys.exit(1)

    model = sys.argv[1]
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 11434
    sys.exit(test_reasoning_benchmarks(model, port))
