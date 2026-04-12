"""
Multilingual capability assessment for SLM models
Tests: translation, language detection, cross-lingual understanding, code-switching
"""
import requests
import json
import sys
import os
import time
from pathlib import Path

RESULTS_DIR = Path(__file__).parent.parent.parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def test_multilingual(model_name, port=11434):
    """Run multilingual capability tests"""
    host = os.environ.get("SLM_TEST_HOST", "localhost")
    url = f"http://{host}:{port}/api/generate"

    test_cases = [
        # === TRANSLATION ===
        {
            "category": "English to French Translation",
            "prompt": "Translate the following sentence to French: 'The cat is sitting on the table.'",
            "expected_keywords": ["chat", "table", "assis", "est"],
            "points": 15
        },
        {
            "category": "English to Spanish Translation",
            "prompt": "Translate to Spanish: 'Good morning, how are you today?'",
            "expected_keywords": ["buenos", "dГ­as", "cГіmo", "estГЎs", "hoy"],
            "points": 15
        },
        {
            "category": "English to German Translation",
            "prompt": "Translate to German: 'I would like a glass of water, please.'",
            "expected_keywords": ["glas", "wasser", "bitte", "mГ¶chte", "ich"],
            "points": 15
        },
        {
            "category": "Reverse Translation (French to English)",
            "prompt": "Translate this French sentence to English: 'Le soleil brille dans le ciel bleu.'",
            "expected_keywords": ["sun", "shines", "sky", "blue"],
            "points": 15
        },

        # === LANGUAGE DETECTION ===
        {
            "category": "Language Detection - Japanese",
            "prompt": "What language is this written in? 'гЃ“г‚“гЃ«гЃЎгЃЇдё–з•Њ' Answer with just the language name.",
            "expected_keywords": ["japanese", "ж—Ґжњ¬иЄћ"],
            "points": 10
        },
        {
            "category": "Language Detection - Ukrainian",
            "prompt": "What language is this written in? 'Р”РѕР±СЂРѕРіРѕ СЂР°РЅРєСѓ, СЏРє СЃРїСЂР°РІРё?' Answer with just the language name.",
            "expected_keywords": ["ukrainian", "СѓРєСЂР°С—РЅСЃСЊРєР°"],
            "points": 10
        },
        {
            "category": "Language Detection - Portuguese",
            "prompt": "What language is this written in? 'Bom dia, como vocГЄ estГЎ?' Answer with just the language name.",
            "expected_keywords": ["portuguese", "portuguГЄs"],
            "points": 10
        },

        # === CROSS-LINGUAL UNDERSTANDING ===
        {
            "category": "Cross-lingual Math",
            "prompt": "Responde en espaГ±ol: What is 15 multiplied by 4?",
            "expected_keywords": ["60", "sesenta"],
            "points": 15
        },
        {
            "category": "Cross-lingual Knowledge",
            "prompt": "RГ©pondez en franГ§ais: What is the capital of Japan?",
            "expected_keywords": ["tokyo", "tokio"],
            "points": 15
        },

        # === CODE-SWITCHING ===
        {
            "category": "Code-Switching Comprehension",
            "prompt": "I need to buy some leche and pan from the tienda. What do I need to buy? Answer in English.",
            "expected_keywords": ["milk", "bread", "store", "shop"],
            "points": 15
        },
        {
            "category": "Multilingual Instruction Following",
            "prompt": "List 3 fruits. Write the first in English, the second in Spanish, and the third in French.",
            "check_format": lambda text: len(text) > 10 and any(w in text.lower() for w in ["manzana", "naranja", "plГЎtano", "uva", "fresa", "pomme", "orange", "banane", "raisin", "fraise"]),
            "points": 15
        },

        # === CULTURAL CONTEXT ===
        {
            "category": "Cultural Knowledge",
            "prompt": "What is 'DГ­a de los Muertos' and in which country is it primarily celebrated?",
            "expected_keywords": ["mexico", "dead", "november", "celebration", "tradition"],
            "points": 15
        },
        {
            "category": "Script Recognition",
            "prompt": "Identify the writing scripts used in these words: 'Hello', 'РџСЂРёРІС–С‚', 'дЅ еҐЅ', 'Щ…Ш±Ш­ШЁШ§'. Name each script.",
            "expected_keywords": ["latin", "cyrillic", "chinese", "arabic"],
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
    print(f"MULTILINGUAL CAPABILITY TEST: {model_name}")
    print(f"{'='*60}\n")

    for i, test_case in enumerate(test_cases, 1):
        category = test_case["category"]
        prompt = test_case["prompt"]
        points = test_case["points"]

        print(f"[{i:2d}/{len(test_cases)}] {category}")
        print(f"     Prompt: {prompt[:70]}..." if len(prompt) > 70 else f"     Prompt: {prompt}")

        payload = {
            "model": model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.3
            }
        }

        try:
            response = requests.post(url, json=payload, timeout=120)
            response.raise_for_status()
            data = response.json()

            response_text = data.get('response', '').strip()
            print(f"     Response: {response_text[:80]}...")

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
                        score = points // 4 if len(response_text) > 20 else 0
                        reasons.append("Expected keywords missing")

                if "check_format" in test_case:
                    try:
                        if test_case["check_format"](response_text):
                            score = max(score, points)
                            reasons.append("Format check passed")
                        else:
                            reasons.append("Format check failed")
                    except Exception:
                        pass

                if len(response_text) > 1500:
                    score = max(0, score - points // 4)
                    reasons.append("Response too verbose")

            score = min(score, points)

            test_result = {
                "category": category,
                "prompt": prompt,
                "response": response_text,
                "score": score,
                "max_score": points,
                "reasons": reasons,
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
        rating = "Excellent"
    elif percentage >= 60:
        rating = "Good"
    elif percentage >= 40:
        rating = "Fair"
    else:
        rating = "Poor"

    results["rating"] = rating

    print(f"{'='*60}")
    print(f"MULTILINGUAL RESULTS")
    print(f"{'='*60}")
    print(f"Total Score: {results['total_score']}/{results['max_score']} ({percentage:.1f}%)")
    print(f"Rating: {rating}")
    print(f"{'='*60}\n")

    output_file = RESULTS_DIR / f"multilingual_{model_name.replace(':', '_')}_{int(time.time())}.json"
    try:
        with output_file.open('w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)
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
