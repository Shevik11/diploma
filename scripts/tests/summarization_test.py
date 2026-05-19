"""
Summarization and comprehension assessment for SLM models
Tests: text summarization, key point extraction, reading comprehension, paraphrasing
"""
import requests
import json
import sys
import os
import time
from pathlib import Path

try:
    from result_utils import save_results
except Exception:  # pragma: no cover
    save_results = None

RESULTS_DIR = Path(__file__).parent.parent.parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def test_summarization(model_name, port=11434):
    """Run summarization and comprehension tests"""
    host = os.environ.get("SLM_TEST_HOST", "localhost")
    url = f"http://{host}:{port}/api/generate"

    test_cases = [
        # === SUMMARIZATION ===
        {
            "category": "Short Text Summarization",
            "prompt": (
                "Summarize the following text in 1-2 sentences:\n\n"
                "Artificial intelligence has transformed many industries over the past decade. "
                "Healthcare uses AI for diagnostics and drug discovery. Finance relies on AI for "
                "fraud detection and algorithmic trading. Transportation is being revolutionized "
                "by self-driving vehicles. Education benefits from personalized learning platforms. "
                "Despite these advances, concerns about job displacement and ethical implications remain."
            ),
            "expected_keywords": ["ai", "artificial intelligence", "industries", "transform"],
            "max_response_length": 300,
            "points": 15
        },
        {
            "category": "Technical Text Summarization",
            "prompt": (
                "Summarize this technical paragraph in plain English:\n\n"
                "Transformer models use self-attention mechanisms to process input sequences in parallel, "
                "unlike recurrent neural networks which process tokens sequentially. The attention mechanism "
                "computes weighted relationships between all pairs of positions in a sequence, allowing the "
                "model to capture long-range dependencies efficiently. This architecture forms the basis of "
                "models like BERT, GPT, and T5."
            ),
            "expected_keywords": ["transformer", "attention", "parallel", "sequence"],
            "max_response_length": 250,
            "points": 20
        },
        {
            "category": "News Article Summarization",
            "prompt": (
                "Summarize the key points of this article:\n\n"
                "Scientists at MIT have developed a new type of solar cell that is thinner than a human hair "
                "and can be attached to any surface. The cells are made from organic materials and can generate "
                "18 watts per gram, which is about 18 times more power-per-weight than conventional solar panels. "
                "The researchers say this technology could be used on clothing, tents, sails, and even drones. "
                "However, the cells currently degrade faster than traditional silicon panels and need protective "
                "coatings to last longer."
            ),
            "expected_keywords": ["solar", "thin", "mit", "power", "surface"],
            "max_response_length": 300,
            "points": 15
        },

        # === KEY POINT EXTRACTION ===
        {
            "category": "Key Point Extraction",
            "prompt": (
                "Extract the 3 most important points from this text as a numbered list:\n\n"
                "Remote work has become increasingly common since 2020. Studies show that remote workers "
                "report higher job satisfaction but may struggle with work-life boundaries. Companies save "
                "on office costs but face challenges in team collaboration. Hybrid models combining office "
                "and remote work are emerging as the preferred solution. Employee productivity varies widely "
                "depending on the nature of the work and individual circumstances."
            ),
            "must_have": ["1", "2", "3"],
            "expected_keywords": ["remote", "work", "hybrid", "productivity", "satisfaction"],
            "points": 15
        },
        {
            "category": "Bullet Point Generation",
            "prompt": (
                "Convert this paragraph into 4-5 bullet points:\n\n"
                "Python is one of the most popular programming languages in the world. It is known for its "
                "simple syntax and readability. Python is widely used in web development, data science, "
                "machine learning, and automation. It has a large ecosystem of libraries including NumPy, "
                "Pandas, and TensorFlow. Python is also commonly used as a first programming language in "
                "education due to its gentle learning curve."
            ),
            "check_format": lambda text: text.count("-") >= 3 or text.count("•") >= 3 or text.count("*") >= 3 or text.count("1") >= 1,
            "expected_keywords": ["python", "syntax", "libraries", "data"],
            "points": 15
        },

        # === READING COMPREHENSION ===
        {
            "category": "Reading Comprehension - Factual",
            "prompt": (
                "Read the following passage and answer the question.\n\n"
                "Passage: Marie Curie was born in Warsaw, Poland in 1867. She moved to Paris in 1891 "
                "to study at the Sorbonne. She discovered two elements: polonium and radium. In 1903, "
                "she became the first woman to win a Nobel Prize in Physics. In 1911, she won a second "
                "Nobel Prize, this time in Chemistry.\n\n"
                "Question: How many Nobel Prizes did Marie Curie win and in which fields?"
            ),
            "expected_keywords": ["two", "2", "physics", "chemistry"],
            "points": 15
        },
        {
            "category": "Reading Comprehension - Inference",
            "prompt": (
                "Read the passage and answer the question.\n\n"
                "Passage: The restaurant was empty when we arrived at 6 PM. By 7 PM, every table was "
                "taken and there was a 30-minute wait. The chef came out to apologize for the delays, "
                "explaining that two cooks had called in sick.\n\n"
                "Question: Why were there delays at the restaurant? Was the restaurant popular?"
            ),
            "expected_keywords": ["sick", "cooks", "staff", "popular", "busy", "full"],
            "points": 15
        },
        {
            "category": "Reading Comprehension - Comparison",
            "prompt": (
                "Read and compare:\n\n"
                "Text A: 'Electric cars produce zero direct emissions and are cheaper to maintain, "
                "but have limited range and long charging times.'\n\n"
                "Text B: 'Gasoline cars have extensive refueling infrastructure and longer range, "
                "but produce harmful emissions and have higher fuel costs.'\n\n"
                "What are the main trade-offs between electric and gasoline cars based on these texts?"
            ),
            "expected_keywords": ["emission", "range", "cost", "charging", "fuel"],
            "points": 20
        },

        # === PARAPHRASING ===
        {
            "category": "Paraphrasing",
            "prompt": "Rewrite this sentence in simpler words: 'The ubiquitous proliferation of digital technology has fundamentally altered the paradigm of human communication.'",
            "check_no_copy": lambda orig, resp: orig.lower().strip("'\"") not in resp.lower(),
            "original_text": "The ubiquitous proliferation of digital technology has fundamentally altered the paradigm of human communication.",
            "expected_keywords": ["technology", "communication", "change", "digital", "spread"],
            "points": 15
        },
        {
            "category": "Formal to Informal",
            "prompt": "Rewrite this formal sentence in a casual, friendly tone: 'We regret to inform you that your application has not been successful on this occasion.'",
            "check_format": lambda text: len(text) > 10 and len(text) < 500,
            "points": 10
        },

        # === COMPRESSION ===
        {
            "category": "Extreme Summarization (TL;DR)",
            "prompt": (
                "Give a one-sentence TL;DR for this:\n\n"
                "Machine learning is a subset of artificial intelligence that enables systems to learn "
                "from data without being explicitly programmed. It uses algorithms to identify patterns "
                "in data and make predictions or decisions. Common types include supervised learning, "
                "unsupervised learning, and reinforcement learning. Applications range from image "
                "recognition to natural language processing to recommendation systems."
            ),
            "max_response_length": 200,
            "expected_keywords": ["machine learning", "data", "learn", "ai"],
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
    print(f"SUMMARIZATION & COMPREHENSION TEST: {model_name}")
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

            if len(response_text) < 5:
                reasons.append("Response too short")
            else:
                # Check expected keywords
                if "expected_keywords" in test_case:
                    found = [kw for kw in test_case["expected_keywords"]
                             if kw.lower() in response_text.lower()]
                    if found:
                        score += points // 2
                        reasons.append(f"Keywords found: {', '.join(found[:3])}")
                    else:
                        reasons.append("Expected keywords missing")

                # Check max response length (summarization should be concise)
                if "max_response_length" in test_case:
                    if len(response_text) <= test_case["max_response_length"]:
                        score += points // 4
                        reasons.append("Good length")
                    else:
                        reasons.append(f"Too long ({len(response_text)} chars)")

                # Check must-have elements
                if "must_have" in test_case:
                    missing = [elem for elem in test_case["must_have"] if elem not in response_text]
                    if not missing:
                        score += points // 4
                        reasons.append("All required elements present")
                    else:
                        reasons.append(f"Missing: {', '.join(missing[:2])}")

                # Check format
                if "check_format" in test_case:
                    try:
                        if test_case["check_format"](response_text):
                            score += points // 4
                            reasons.append("Format check passed")
                        else:
                            reasons.append("Format check failed")
                    except Exception:
                        pass

                # Check no-copy for paraphrasing
                if "check_no_copy" in test_case:
                    try:
                        if test_case["check_no_copy"](test_case["original_text"], response_text):
                            score += points // 4
                            reasons.append("Successfully paraphrased")
                        else:
                            reasons.append("Too similar to original")
                    except Exception:
                        pass

                # Default partial score for reasonable responses
                if score == 0 and len(response_text) > 20:
                    score = points // 4
                    reasons.append("Reasonable response")

            score = min(score, points)

            test_result = {
                "category": category,
                "prompt": prompt[:100],
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
    print(f"SUMMARIZATION & COMPREHENSION RESULTS")
    print(f"{'='*60}")
    print(f"Total Score: {results['total_score']}/{results['max_score']} ({percentage:.1f}%)")
    print(f"Rating: {rating}")
    print(f"{'='*60}\n")

    if save_results is not None:
        save_results(results, "summarization", model_name, "summarization")
    else:  # pragma: no cover
        output_file = RESULTS_DIR / f"summarization_{model_name.replace(':', '_')}_{int(time.time())}.json"
        try:
            with output_file.open('w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            print(f"Results saved to: {output_file}\n")
        except Exception as e:
            print(f"Warning: Could not save results: {e}\n")

    return 0 if percentage >= 40 else 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python summarization_test.py <model_name> [port]")
        sys.exit(1)

    model = sys.argv[1]
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 11434

    sys.exit(test_summarization(model, port))
