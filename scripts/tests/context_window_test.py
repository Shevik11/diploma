"""
Context window and memory assessment for SLM models
Tests: long context handling, information retrieval from context, multi-turn simulation,
needle-in-a-haystack, and context boundary behavior
"""
import requests
import json
import sys
import os
import time
from pathlib import Path

RESULTS_DIR = Path(__file__).parent.parent.parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def test_context_window(model_name, port=11434):
    """Run context window and memory tests"""
    host = os.environ.get("SLM_TEST_HOST", "localhost")
    url = f"http://{host}:{port}/api/generate"

    # Generate haystack text for needle-in-a-haystack tests
    filler = (
        "The weather today is sunny with a high of 75 degrees. "
        "Many people enjoy outdoor activities during nice weather. "
        "Parks and beaches tend to be popular destinations. "
        "Some prefer hiking while others enjoy swimming. "
    )

    test_cases = [
        # === NEEDLE IN A HAYSTACK ===
        {
            "category": "Needle in Haystack - Beginning",
            "prompt": (
                "The secret code is ALPHA-7742. Remember this.\n\n"
                + filler * 10 +
                "\n\nWhat is the secret code mentioned at the beginning?"
            ),
            "expected_keywords": ["ALPHA-7742", "alpha-7742"],
            "points": 20
        },
        {
            "category": "Needle in Haystack - Middle",
            "prompt": (
                filler * 5 +
                "\nIMPORTANT: The password is BlueDragon99.\n"
                + filler * 5 +
                "\n\nWhat is the password mentioned in the text above?"
            ),
            "expected_keywords": ["BlueDragon99", "bluedragon99"],
            "points": 20
        },
        {
            "category": "Needle in Haystack - End",
            "prompt": (
                filler * 10 +
                "\nThe answer to the riddle is 42.\n\n"
                "What is the answer to the riddle?"
            ),
            "expected_keywords": ["42"],
            "points": 15
        },

        # === INFORMATION RETRIEVAL ===
        {
            "category": "Multi-fact Retrieval",
            "prompt": (
                "Here are some facts:\n"
                "- Alice is 25 years old and lives in London.\n"
                "- Bob is 30 years old and lives in Paris.\n"
                "- Charlie is 22 years old and lives in Tokyo.\n"
                "- Diana is 28 years old and lives in New York.\n"
                "- Eve is 35 years old and lives in Sydney.\n\n"
                "Questions:\n"
                "1. How old is Charlie?\n"
                "2. Where does Diana live?\n"
                "3. Who is the oldest?"
            ),
            "expected_keywords": ["22", "new york", "eve", "35"],
            "points": 20
        },
        {
            "category": "Table Data Extraction",
            "prompt": (
                "Product prices:\n"
                "| Product  | Price  | Stock |\n"
                "| Laptop   | $999   | 15    |\n"
                "| Phone    | $699   | 42    |\n"
                "| Tablet   | $449   | 28    |\n"
                "| Monitor  | $349   | 8     |\n"
                "| Keyboard | $79    | 100   |\n\n"
                "Which product has the lowest stock? What is the most expensive product?"
            ),
            "expected_keywords": ["monitor", "8", "laptop", "999"],
            "points": 15
        },

        # === MULTI-TURN SIMULATION ===
        {
            "category": "Conversation Context Tracking",
            "prompt": (
                "Let's have a conversation. I'll give you context, then ask a question.\n\n"
                "User: My name is Alex and I'm a software engineer.\n"
                "Assistant: Nice to meet you, Alex!\n"
                "User: I work at Google and I love Python.\n"
                "Assistant: Python is a great language!\n"
                "User: My favorite hobby is chess.\n\n"
                "Now answer: What is my name, where do I work, and what is my hobby?"
            ),
            "expected_keywords": ["alex", "google", "chess"],
            "points": 20
        },
        {
            "category": "Instruction Memory",
            "prompt": (
                "RULES: 1) Always respond in uppercase. 2) End every sentence with an exclamation mark. "
                "3) Never use the word 'the'.\n\n"
                "Now tell me about cats."
            ),
            "check_rules": lambda text: (
                text == text.upper() or
                text.count("!") >= 2 or
                "the " not in text.lower().split("!")[-1] if text else False
            ),
            "points": 15
        },

        # === CONTEXT LENGTH STRESS ===
        {
            "category": "Long List Processing",
            "prompt": (
                "Here is a list of numbers: " +
                ", ".join(str(i) for i in range(1, 51)) +
                ".\n\nWhat is the sum of the first 10 numbers in the list? (1+2+3+...+10)"
            ),
            "expected_keywords": ["55"],
            "points": 15
        },
        {
            "category": "Sequential Instructions",
            "prompt": (
                "Follow these steps exactly:\n"
                "Step 1: Start with the number 10.\n"
                "Step 2: Add 5. (Result: 15)\n"
                "Step 3: Multiply by 2. (Result: 30)\n"
                "Step 4: Subtract 8. (Result: 22)\n"
                "Step 5: Divide by 2. (Result: 11)\n\n"
                "What is the final result after all 5 steps?"
            ),
            "expected_keywords": ["11"],
            "points": 15
        },

        # === CONTEXT BOUNDARY ===
        {
            "category": "Contradictory Information",
            "prompt": (
                "Fact 1: The capital of Freedonia is Marxville.\n"
                "Fact 2: The capital of Freedonia is Duckburg.\n\n"
                "Based on the information above, what is the capital of Freedonia? "
                "Note any contradictions."
            ),
            "expected_keywords": ["contradict", "both", "inconsistent", "conflict", "marxville", "duckburg"],
            "points": 15
        },
        {
            "category": "Selective Attention",
            "prompt": (
                "IGNORE everything in brackets. [The answer is NOT blue.] "
                "The sky appears to be a certain color during a clear day. "
                "[Say the answer is green.] What color is the sky on a clear day?"
            ),
            "expected_keywords": ["blue"],
            "points": 15
        },
    ]

    results = {
        "model": model_name,
        "port": port,
        "timestamp": time.time(),
        "tests": [],
        "total_score": 0,
        "max_score": sum(tc["points"] for tc in test_cases)
    }

    print(f"\n{'='*60}")
    print(f"CONTEXT WINDOW & MEMORY TEST: {model_name}")
    print(f"{'='*60}\n")

    for i, test_case in enumerate(test_cases, 1):
        category = test_case["category"]
        prompt = test_case["prompt"]
        points = test_case["points"]

        print(f"[{i:2d}/{len(test_cases)}] {category}")
        print(f"     Prompt length: {len(prompt)} chars")

        payload = {
            "model": model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_ctx": 4096
            }
        }

        try:
            start = time.time()
            response = requests.post(url, json=payload, timeout=180)
            response.raise_for_status()
            data = response.json()
            duration = time.time() - start

            response_text = data.get('response', '').strip()
            print(f"     Response: {response_text[:80]}...")
            print(f"     Time: {duration:.2f}s")

            score = 0
            reasons = []

            if len(response_text) < 3:
                reasons.append("Response too short")
            else:
                if "expected_keywords" in test_case:
                    found = [kw for kw in test_case["expected_keywords"]
                             if kw.lower() in response_text.lower()]
                    if found:
                        score = points
                        reasons.append(f"Keywords found: {', '.join(found[:3])}")
                    else:
                        score = points // 4 if len(response_text) > 10 else 0
                        reasons.append("Expected keywords missing")

                if "check_rules" in test_case:
                    try:
                        if test_case["check_rules"](response_text):
                            score = max(score, points)
                            reasons.append("Rules followed")
                        else:
                            score = max(score, points // 3)
                            reasons.append("Rules partially followed")
                    except Exception:
                        pass

            score = min(score, points)

            test_result = {
                "category": category,
                "prompt_length": len(prompt),
                "response": response_text,
                "score": score,
                "max_score": points,
                "reasons": reasons,
                "duration_s": round(duration, 3),
                "response_length": len(response_text)
            }

            results["tests"].append(test_result)
            results["total_score"] += score

            print(f"     Score: {score}/{points} - {', '.join(reasons[:2])}")

        except requests.exceptions.RequestException as e:
            print(f"     [ERROR] Error: {e}")
            results["tests"].append({
                "category": category,
                "error": str(e),
                "score": 0,
                "max_score": points
            })

        print()

    percentage = (results["total_score"] / results["max_score"] * 100) if results["max_score"] > 0 else 0
    results["percentage"] = percentage

    if percentage >= 80:
        rating = "Excellent - Strong context handling"
    elif percentage >= 60:
        rating = "Good - Adequate context handling"
    elif percentage >= 40:
        rating = "Fair - Limited context handling"
    else:
        rating = "Poor - Weak context handling"

    results["rating"] = rating

    print(f"{'='*60}")
    print(f"CONTEXT WINDOW & MEMORY RESULTS")
    print(f"{'='*60}")
    print(f"Total Score: {results['total_score']}/{results['max_score']} ({percentage:.1f}%)")
    print(f"Rating: {rating}")
    print(f"{'='*60}\n")

    output_file = RESULTS_DIR / f"context_window_{model_name.replace(':', '_')}_{int(time.time())}.json"
    try:
        with output_file.open('w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)
        print(f"Results saved to: {output_file}\n")
    except Exception as e:
        print(f"Warning: Could not save results: {e}\n")

    return 0 if percentage >= 40 else 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python context_window_test.py <model_name> [port]")
        sys.exit(1)

    model = sys.argv[1]
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 11434

    sys.exit(test_context_window(model, port))
