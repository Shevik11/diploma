"""
Quality assessment for LLM responses
Tests: factual accuracy, coherence, instruction following
"""
import requests
import json
import sys
import time
import os
from pathlib import Path

RESULTS_DIR = Path(__file__).parent.parent.parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
def test_quality(model_name, port=11434):
    """Run quality assessment tests"""
    host = os.environ.get("SLM_TEST_HOST", "localhost")
    url = f"http://{host}:{port}/api/generate"
    
    # Test cases with expected characteristics
    test_cases = [
        {
            "category": "Factual Knowledge",
            "prompt": "What is the capital of France?",
            "expected_keywords": ["Paris", "paris"],
            "points": 10
        },
        {
            "category": "Math",
            "prompt": "Calculate: 15 + 27",
            "expected_keywords": ["42"],
            "points": 10
        },
        {
            "category": "Instruction Following",
            "prompt": "List exactly 3 colors, separated by commas.",
            "check_format": lambda text: text.count(',') >= 2,
            "points": 10
        },
        {
            "category": "Reasoning",
            "prompt": "If all cats are animals, and some animals fly, can all cats fly? Answer yes or no and explain briefly.",
            "expected_keywords": ["no", "not", "cannot", "No"],
            "points": 15
        },
        {
            "category": "Coherence",
            "prompt": "Explain in 2 sentences what machine learning is.",
            "check_format": lambda text: 10 < len(text) < 500,
            "points": 10
        },
        {
            "category": "Code Understanding",
            "prompt": "What does this Python code do: for i in range(5): print(i)",
            "expected_keywords": ["print", "0", "4", "loop", "numbers"],
            "points": 15
        }
    ]
    
    results = {
        "model": model_name,
        "port": port,
        "timestamp": time.time(),
        "tests": [],
        "total_score": 0,
        "max_score": sum(tc["points"] for tc in test_cases)
    }
    
    print(f"\n=== Quality Assessment: {model_name} ===\n")
    
    for i, test_case in enumerate(test_cases, 1):
        category = test_case["category"]
        prompt = test_case["prompt"]
        points = test_case["points"]
        
        print(f"[{i}/{len(test_cases)}] {category}")
        print(f"  Prompt: {prompt}")
        
        payload = {
            "model": model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.3  # Lower temperature for consistency
            }
        }
        
        try:
            response = requests.post(url, json=payload, timeout=60)
            response.raise_for_status()
            data = response.json()
            
            response_text = data.get('response', '').strip()
            print(f"  Response: {response_text[:100]}...")
            
            # Score the response
            score = 0
            reasons = []
            
            # Check for expected keywords
            if "expected_keywords" in test_case:
                found_keywords = [kw for kw in test_case["expected_keywords"] 
                                 if kw.lower() in response_text.lower()]
                if found_keywords:
                    score = points
                    reasons.append(f"Found keywords: {', '.join(found_keywords)}")
                else:
                    reasons.append("Expected keywords not found")
            
            # Check format requirements
            if "check_format" in test_case:
                if test_case["check_format"](response_text):
                    score = points
                    reasons.append("Format check passed")
                else:
                    reasons.append("Format check failed")
            
            # Basic quality checks
            if len(response_text) < 5:
                score = 0
                reasons.append("Response too short")
            elif len(response_text) > 1000:
                score = max(0, score - 2)
                reasons.append("Response too verbose")
            
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
            
            print(f"  Score: {score}/{points} - {', '.join(reasons)}")
            
        except requests.exceptions.RequestException as e:
            print(f"  вњ— Error: {e}")
            test_result = {
                "category": category,
                "error": str(e),
                "score": 0,
                "max_score": points
            }
            results["tests"].append(test_result)
    
    # Calculate final percentage
    percentage = (results["total_score"] / results["max_score"] * 100) if results["max_score"] > 0 else 0
    results["percentage"] = percentage
    
    print(f"\n=== Final Score ===")
    print(f"Total: {results['total_score']}/{results['max_score']} ({percentage:.1f}%)")
    
    # Rating
    if percentage >= 80:
        rating = "Excellent"
    elif percentage >= 60:
        rating = "Good"
    elif percentage >= 40:
        rating = "Fair"
    else:
        rating = "Poor"
    
    results["rating"] = rating
    print(f"Rating: {rating}")
    
    # Save results
    output_file = RESULTS_DIR / f"quality_{model_name.replace(':', '_')}_{int(time.time())}.json"
    try:
        with output_file.open('w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to: {output_file}")
    except Exception as e:
        print(f"Warning: Could not save results: {e}")
    
    return 0

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python quality_test.py <model_name> [port]")
        sys.exit(1)
    
    model = sys.argv[1]
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 11434
    
    sys.exit(test_quality(model, port))
