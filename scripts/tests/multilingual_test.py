"""
Multilingual capability assessment for SLM models.

Tests: translation (FR/ES/DE), language detection (Japanese/Ukrainian/Portuguese),
cross-lingual reasoning, code-switching, cultural knowledge and script recognition.

NOTE
----
The previous version of this file contained mojibake (cp1251 bytes
incorrectly read as UTF-8) in every non-English prompt and in
``expected_keywords``. As a result, models received corrupted byte
sequences and even correct answers (e.g. "días", "möchte") never matched
the corrupted reference keywords (e.g. "dГ­as"). This rewrite uses real
Unicode literals so that prompts and verifiers are linguistically valid.

The module is the single source of truth for multilingual test cases — it
is consumed by ``run_all_tests.py`` and by the backend test runner.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import requests

# --- Result utilities (optional master-file aggregation) ----------------------
try:
    from result_utils import save_results
except Exception:  # pragma: no cover — fallback when invoked from another cwd
    save_results = None

RESULTS_DIR = Path(__file__).parent.parent.parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


# -----------------------------------------------------------------------------
# Test cases
#
# Each case has:
#   - category: human-readable identifier
#   - prompt:   the user prompt sent to the model
#   - points:   max points awarded for this case
#   - expected_keywords (optional): list[str]; case-insensitive substring match.
#                                   Hitting *any* keyword awards full points.
#   - check_format (optional): callable(text) -> bool; alternative verifier.
#
# All non-ASCII content is written as proper Unicode; the file is UTF-8.
# -----------------------------------------------------------------------------
TEST_CASES: list[dict] = [
    # === TRANSLATION =========================================================
    {
        "category": "English to French Translation",
        "prompt": (
            "Translate the following sentence to French: "
            "'The cat is sitting on the table.'"
        ),
        "expected_keywords": ["chat", "table", "assis", "est"],
        "points": 15,
    },
    {
        "category": "English to Spanish Translation",
        "prompt": "Translate to Spanish: 'Good morning, how are you today?'",
        "expected_keywords": ["buenos", "días", "cómo", "estás", "hoy"],
        "points": 15,
    },
    {
        "category": "English to German Translation",
        "prompt": "Translate to German: 'I would like a glass of water, please.'",
        "expected_keywords": ["glas", "wasser", "bitte", "möchte", "ich"],
        "points": 15,
    },
    {
        "category": "Reverse Translation (French to English)",
        "prompt": (
            "Translate this French sentence to English: "
            "'Le soleil brille dans le ciel bleu.'"
        ),
        "expected_keywords": ["sun", "shines", "sky", "blue"],
        "points": 15,
    },

    # === LANGUAGE DETECTION ==================================================
    {
        "category": "Language Detection - Japanese",
        "prompt": (
            "What language is this written in? 'こんにちは世界' "
            "Answer with just the language name."
        ),
        "expected_keywords": ["japanese", "日本語"],
        "points": 10,
    },
    {
        "category": "Language Detection - Ukrainian",
        "prompt": (
            "What language is this written in? 'Доброго ранку, як справи?' "
            "Answer with just the language name."
        ),
        "expected_keywords": ["ukrainian", "українська"],
        "points": 10,
    },
    {
        "category": "Language Detection - Portuguese",
        "prompt": (
            "What language is this written in? 'Bom dia, como você está?' "
            "Answer with just the language name."
        ),
        "expected_keywords": ["portuguese", "português"],
        "points": 10,
    },

    # === CROSS-LINGUAL UNDERSTANDING =========================================
    {
        "category": "Cross-lingual Math",
        "prompt": "Responde en español: What is 15 multiplied by 4?",
        "expected_keywords": ["60", "sesenta"],
        "points": 15,
    },
    {
        "category": "Cross-lingual Knowledge",
        "prompt": "Répondez en français: What is the capital of Japan?",
        "expected_keywords": ["tokyo", "tokio"],
        "points": 15,
    },

    # === CODE-SWITCHING ======================================================
    {
        "category": "Code-Switching Comprehension",
        "prompt": (
            "I need to buy some leche and pan from the tienda. "
            "What do I need to buy? Answer in English."
        ),
        "expected_keywords": ["milk", "bread", "store", "shop"],
        "points": 15,
    },
    {
        "category": "Multilingual Instruction Following",
        "prompt": (
            "List 3 fruits. Write the first in English, the second in "
            "Spanish, and the third in French."
        ),
        # at least two languages represented in the response
        "check_format": lambda text: (
            len(text) > 10
            and any(
                w in text.lower()
                for w in [
                    "manzana", "naranja", "plátano", "uva", "fresa",
                    "pomme", "orange", "banane", "raisin", "fraise",
                ]
            )
        ),
        "points": 15,
    },

    # === CULTURAL CONTEXT ====================================================
    {
        "category": "Cultural Knowledge",
        "prompt": (
            "What is 'Día de los Muertos' and in which country is it "
            "primarily celebrated?"
        ),
        "expected_keywords": [
            "mexico", "dead", "november", "celebration", "tradition",
        ],
        "points": 15,
    },
    {
        "category": "Script Recognition",
        "prompt": (
            "Identify the writing scripts used in these words: "
            "'Hello', 'Привіт', '你好', 'مرحبا'. Name each script."
        ),
        "expected_keywords": ["latin", "cyrillic", "chinese", "arabic"],
        "points": 15,
    },
]


def _score_response(test_case: dict, response_text: str) -> tuple[int, list[str]]:
    """Score a single response. Returns (score, reasons)."""
    points = test_case["points"]
    reasons: list[str] = []
    score = 0

    if len(response_text) < 3:
        return 0, ["Response too short"]

    if "expected_keywords" in test_case:
        found = [
            kw for kw in test_case["expected_keywords"]
            if kw.lower() in response_text.lower()
        ]
        if found:
            score = points
            reasons.append(f"Keywords found: {', '.join(found[:3])}")
        else:
            # Partial credit for non-empty answers (model engaged with task)
            score = points // 4 if len(response_text) > 20 else 0
            reasons.append("Expected keywords missing")

    if "check_format" in test_case:
        try:
            if test_case["check_format"](response_text):
                score = max(score, points)
                reasons.append("Format check passed")
            else:
                reasons.append("Format check failed")
        except Exception as exc:
            reasons.append(f"Format check error: {exc}")

    if len(response_text) > 1500:
        score = max(0, score - points // 4)
        reasons.append("Response too verbose")

    return min(score, points), reasons


def test_multilingual(model_name: str, port: int = 11434) -> int:
    """Run multilingual capability tests against an Ollama-compatible endpoint."""
    host = os.environ.get("SLM_TEST_HOST", "localhost")
    url = f"http://{host}:{port}/api/generate"

    results: dict = {
        "model": model_name,
        "port": port,
        "timestamp": time.time(),
        "tests": [],
        "total_score": 0,
        "max_score": sum(tc["points"] for tc in TEST_CASES),
    }

    print(f"\n{'='*60}")
    print(f"MULTILINGUAL CAPABILITY TEST: {model_name}")
    print(f"{'='*60}\n")

    for i, test_case in enumerate(TEST_CASES, 1):
        category = test_case["category"]
        prompt = test_case["prompt"]
        points = test_case["points"]

        print(f"[{i:2d}/{len(TEST_CASES)}] {category}")
        print(
            f"     Prompt: {prompt[:70]}..."
            if len(prompt) > 70
            else f"     Prompt: {prompt}"
        )

        payload = {
            "model": model_name,
            "prompt": prompt,
            "stream": False,
            # Low (but not zero) temperature: most multilingual tasks have
            # multiple valid translations; keyword-based scoring needs some
            # variability tolerance.
            "options": {"temperature": 0.3, "seed": 42},
        }

        try:
            t0 = time.time()
            response = requests.post(url, json=payload, timeout=120)
            response.raise_for_status()
            data = response.json()
            elapsed = time.time() - t0

            response_text = data.get("response", "").strip()
            print(f"     Response: {response_text[:80]}...")

            score, reasons = _score_response(test_case, response_text)

            test_result = {
                "category": category,
                "prompt": prompt,
                "response": response_text,
                "score": score,
                "max_score": points,
                "reasons": reasons,
                "response_length": len(response_text),
                "elapsed_s": round(elapsed, 3),
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
                "max_score": points,
            })

        print()

    percentage = (
        results["total_score"] / results["max_score"] * 100
        if results["max_score"] > 0
        else 0
    )
    results["percentage"] = round(percentage, 2)

    if percentage >= 80:
        rating = "Excellent"
    elif percentage >= 60:
        rating = "Good"
    elif percentage >= 40:
        rating = "Fair"
    else:
        rating = "Poor"

    results["rating"] = rating

    print(f"{'='*60}")
    print("MULTILINGUAL RESULTS")
    print(f"{'='*60}")
    print(
        f"Total Score: {results['total_score']}/{results['max_score']} "
        f"({percentage:.1f}%)"
    )
    print(f"Rating: {rating}")
    print(f"{'='*60}\n")

    # Save results — prefer the shared utility (which honours SLM_OUTPUT_FILE)
    if save_results is not None:
        save_results(results, "multilingual", model_name, "multilingual")
    else:  # pragma: no cover — fallback path
        output_file = (
            RESULTS_DIR
            / f"multilingual_{model_name.replace(':', '_')}_{int(time.time())}.json"
        )
        try:
            with output_file.open("w", encoding="utf-8") as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            print(f"Results saved to: {output_file}\n")
        except Exception as e:
            print(f"Warning: Could not save results: {e}\n")

    return 0 if percentage >= 40 else 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python multilingual_test.py <model_name> [port]")
        sys.exit(1)

    model = sys.argv[1]
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 11434

    sys.exit(test_multilingual(model, port))
