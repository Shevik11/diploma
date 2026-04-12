"""
Advanced Quality Assessment for LLM responses
Tests: complex reasoning, consistency, edge cases, writing quality, and specialized domains
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


def test_advanced_quality(model_name, port=11434):
    """Run advanced quality assessment tests"""
    host = os.environ.get("SLM_TEST_HOST", "localhost")
    url = f"http://{host}:{port}/api/generate"
    
    # Complex test cases grouped by difficulty
    test_cases = [
        # === TIER 1: Complex Reasoning ===
        {
            "category": "Logical Reasoning - Complex",
            "prompt": "In a race, Alice finished before Bob. Charlie finished before Diana. Alice finished after Charlie. Diana finished before Bob. Rank them in order from first to last place.",
            "expected_keywords": ["Charlie", "Alice", "Diana", "Bob"],
            "verify_order": True,
            "points": 20
        },
        {
            "category": "Mathematical Reasoning",
            "prompt": "A farmer has chickens and cows. He counts 18 animals total and 50 legs. How many chickens and how many cows does he have?",
            "expected_keywords": ["7", "11"],
            "explanation_required": True,
            "points": 20
        },
        {
            "category": "Logical Fallacy Detection",
            "prompt": "Evaluate this argument: 'Most people like pizza. John is a person. Therefore, John likes pizza.' Is this a valid logical argument? Explain why or why not.",
            "should_explain": ["not valid", "invalid", "fallacy", "hasty generalization", "inductive"],
            "points": 15
        },
        
        # === TIER 2: Consistency & Coherence ===
        {
            "category": "Consistency Under Contradiction",
            "prompt": "I tell you: 'All birds can fly except penguins.' Later I say: 'Some birds cannot fly.' Are these statements consistent? Explain your reasoning.",
            "expected_keywords": ["consistent", "compatible", "agree"],
            "points": 15
        },
        {
            "category": "Multi-part Task Following",
            "prompt": "Do the following in order: 1) Name a capital city in Europe, 2) List 2 facts about that city, 3) Suggest a reason to visit it. Format clearly with numbers.",
            "must_have": ["1)", "2)", "3)"],
            "points": 15
        },
        
        # === TIER 3: Code & Technical ===
        {
            "category": "Code Bug Identification",
            "prompt": "Find the bug in this Python code and explain why it's wrong:\ndef count_vowels(text):\n    count = 0\n    for char in text:\n        if char in 'aeiou':\n            count = count + 1\n    return count\ntext = 'Hello World'\nprint(count_vowels(text))",
            "check_code_logic": lambda text: "case" in text.lower() or "uppercase" in text.lower() or "capital" in text.lower() or text.count("e") == 0,
            "points": 20
        },
        {
            "category": "SQL Query Understanding",
            "prompt": "Explain what this SQL query does: SELECT name, COUNT(*) as order_count FROM customers JOIN orders ON customers.id = orders.customer_id GROUP BY customers.id HAVING COUNT(*) > 5",
            "expected_keywords": ["customers", "orders", "count", "group", "join", "having"],
            "points": 15
        },
        
        # === TIER 4: Writing Quality ===
        {
            "category": "Professional Writing",
            "prompt": "Write a professional email to a client explaining that their project deadline has been delayed by 2 weeks due to resource constraints. Be empathetic but clear.",
            "must_not_contain": ["unfortunately", "sorry"],
            "quality_checks": ["professional tone", "clear reason", "new timeline"],
            "points": 20
        },
        {
            "category": "Creative Writing",
            "prompt": "Write a short 3-sentence story about a robot discovering rain for the first time. Make it emotionally engaging.",
            "min_length": 80,
            "max_length": 200,
            "points": 15
        },
        
        # === TIER 5: Domain-Specific Knowledge ===
        {
            "category": "Medical Knowledge",
            "prompt": "What are the main symptoms of Type 2 diabetes and how does it differ from Type 1?",
            "expected_keywords": ["blood sugar", "glucose", "insulin"],
            "points": 15
        },
        {
            "category": "Physics Concepts",
            "prompt": "Explain the difference between speed and velocity. Give an example where they would have different values.",
            "expected_keywords": ["speed", "velocity", "direction", "vector"],
            "points": 15
        },
        
        # === TIER 6: Edge Cases & Tricky Questions ===
        {
            "category": "Handling Ambiguity",
            "prompt": "What comes next in this sequence: 2, 4, 8, 16, ? Explain your reasoning.",
            "expected_keywords": ["32", "double", "multiply by 2"],
            "explanation_required": True,
            "points": 15
        },
        {
            "category": "Trick Question Awareness",
            "prompt": "I have 10 apples. I give 3 to Alice, 2 to Bob, and 5 to Charlie. How many apples do I have left? Explain your math.",
            "expected_keywords": ["0", "zero"],
            "points": 10
        },
        {
            "category": "Opinion vs Fact",
            "prompt": "Is the following statement a fact or opinion? 'The Great Wall of China is an impressive structure.' Explain the difference between facts and opinions.",
            "expected_keywords": ["opinion", "subjective", "impressive"],
            "points": 15
        },
    ]
    
    results = {
        "model": model_name,
        "port": port,
        "timestamp": time.time(),
        "tests": [],
        "total_score": 0,
        "max_score": sum(tc["points"] for tc in test_cases),
        "breakdown_by_tier": {}
    }
    
    print(f"\n{'='*60}")
    print(f"ADVANCED QUALITY ASSESSMENT: {model_name}")
    print(f"{'='*60}\n")
    
    for i, test_case in enumerate(test_cases, 1):
        category = test_case["category"]
        prompt = test_case["prompt"]
        points = test_case["points"]
        
        # Extract tier from category
        tier = "Other"
        if "Complex" in category or "Logical" in category or "Reasoning" in category:
            tier = "Reasoning"
        elif "Consistency" in category or "Multi-part" in category:
            tier = "Consistency"
        elif "Code" in category or "SQL" in category:
            tier = "Technical"
        elif "Writing" in category or "Creative" in category:
            tier = "Writing"
        elif "Knowledge" in category:
            tier = "Domain"
        elif "Ambiguity" in category or "Trick" in category or "Opinion" in category:
            tier = "EdgeCases"
        
        if tier not in results["breakdown_by_tier"]:
            results["breakdown_by_tier"][tier] = {"total": 0, "max": 0}
        
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
            print(f"     Response: {response_text[:60]}...")
            
            score = 0
            reasons = []
            
            # Basic validity check
            if len(response_text) < 3:
                reasons.append("Response too short")
                score = 0
            elif len(response_text) > 2000:
                reasons.append("Response too verbose")
                score = max(0, points // 2)
            else:
                # Check expected keywords
                if "expected_keywords" in test_case:
                    found_keywords = [kw for kw in test_case["expected_keywords"] 
                                    if kw.lower() in response_text.lower()]
                    if found_keywords:
                        score += points // 2
                        reasons.append(f"Keywords found: {', '.join(found_keywords[:2])}")
                    else:
                        reasons.append("Expected keywords missing")
                
                # Check for order verification (ranking tasks)
                if test_case.get("verify_order"):
                    keywords = test_case["expected_keywords"]
                    positions = [response_text.lower().find(kw.lower()) for kw in keywords if kw.lower() in response_text.lower()]
                    if len(positions) == len(keywords) and positions == sorted(positions):
                        score = points
                        reasons.append("Correct order")
                    else:
                        reasons.append("Order may be incorrect")
                
                # Check explanation requirement
                if test_case.get("explanation_required") and len(response_text) < 50:
                    score = max(0, score - points // 3)
                    reasons.append("Explanation too brief")
                
                # Check must-have elements
                if "must_have" in test_case:
                    missing = [elem for elem in test_case["must_have"] if elem not in response_text]
                    if not missing:
                        score += points // 2
                        reasons.append("All required elements present")
                    else:
                        reasons.append(f"Missing: {', '.join(missing[:2])}")
                
                # Check code logic function
                if "check_code_logic" in test_case:
                    try:
                        if test_case["check_code_logic"](response_text):
                            score = min(points, score + points // 2)
                            reasons.append("Code logic identified")
                        else:
                            reasons.append("Incorrect code analysis")
                    except:
                        pass
                
                # Check domain-specific keywords
                if "should_explain" in test_case:
                    found_explanations = [kw for kw in test_case["should_explain"] 
                                        if kw.lower() in response_text.lower()]
                    if found_explanations:
                        score = max(score, points // 2)
                        reasons.append("Proper explanation provided")
                
                # Check length constraints
                if "min_length" in test_case and len(response_text) < test_case["min_length"]:
                    score = max(0, score - points // 3)
                    reasons.append("Response too short")
                if "max_length" in test_case and len(response_text) > test_case["max_length"]:
                    score = max(0, score - points // 3)
                    reasons.append("Response too long")
                
                # Must not contain
                if "must_not_contain" in test_case:
                    forbidden = [word for word in test_case["must_not_contain"] 
                               if word.lower() in response_text.lower()]
                    if forbidden:
                        score = max(0, score - points // 2)
                        reasons.append(f"Contains forbidden words: {', '.join(set(forbidden))}")
                
                # Default full score if no specific checks failed
                if score == 0 and len(response_text) > 20:
                    score = points // 2
                    reasons.append("Reasonable response")
            
            # Cap score at max points
            score = min(score, points)
            
            test_result = {
                "category": category,
                "tier": tier,
                "prompt": prompt,
                "response": response_text,
                "score": score,
                "max_score": points,
                "reasons": reasons,
                "response_length": len(response_text)
            }
            
            results["tests"].append(test_result)
            results["total_score"] += score
            results["breakdown_by_tier"][tier]["total"] += score
            results["breakdown_by_tier"][tier]["max"] += points
            
            print(f"     Score: {score}/{points} - {', '.join(reasons[:2])}")
            
        except requests.exceptions.RequestException as e:
            print(f"     [ERROR] Error: {e}")
            test_result = {
                "category": category,
                "tier": tier,
                "error": str(e),
                "score": 0,
                "max_score": points
            }
            results["tests"].append(test_result)
            results["breakdown_by_tier"][tier]["max"] += points
        
        print()
    
    # Calculate final metrics
    percentage = (results["total_score"] / results["max_score"] * 100) if results["max_score"] > 0 else 0
    results["percentage"] = percentage
    
    print(f"\n{'='*60}")
    print(f"FINAL RESULTS")
    print(f"{'='*60}")
    print(f"Total Score: {results['total_score']}/{results['max_score']} ({percentage:.1f}%)\n")
    
    print("Breakdown by Category:")
    print(f"{'Category':<15} {'Score':<12} {'Percentage':<12}")
    print("-" * 40)
    for tier in sorted(results["breakdown_by_tier"].keys()):
        data = results["breakdown_by_tier"][tier]
        tier_pct = (data["total"] / data["max"] * 100) if data["max"] > 0 else 0
        print(f"{tier:<15} {data['total']}/{data['max']:<8} {tier_pct:>6.1f}%")
    
    # Rating
    if percentage >= 85:
        rating = "Outstanding"
    elif percentage >= 75:
        rating = "Excellent"
    elif percentage >= 65:
        rating = "Very Good"
    elif percentage >= 55:
        rating = "Good"
    elif percentage >= 45:
        rating = "Fair"
    elif percentage >= 30:
        rating = "Poor"
    else:
        rating = "Very Poor"
    
    results["rating"] = rating
    print(f"\nOverall Rating: {rating}")
    print(f"{'='*60}\n")
    
    # Save results
    output_file = RESULTS_DIR / f"advanced_quality_{model_name.replace(':', '_')}_{int(time.time())}.json"
    try:
        with output_file.open('w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)
        print(f"Results saved to: {output_file}\n")
    except Exception as e:
        print(f"Warning: Could not save results: {e}\n")
    
    return 0 if percentage >= 50 else 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python advanced_quality_test.py <model_name> [port]")
        sys.exit(1)
    
    model = sys.argv[1]
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 11434
    
    sys.exit(test_advanced_quality(model, port))
