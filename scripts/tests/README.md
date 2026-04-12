# Python Test Scripts

Advanced testing scripts for Ollama models with automated benchmarks and quality assessments.

## 🚀 Quick Start

### 1. Install Requirements

```powershell
pip install -r scripts/tests/requirements.txt
```

Or:
```powershell
pip install requests tabulate
```

### 2. Run Tests

**Via model scripts (recommended):**
```powershell
# Performance benchmark
.\scripts\make-llama.ps1 benchmark

# Quality assessment
.\scripts\make-llama.ps1 quality

# Same for other models
.\scripts\make-mistral.ps1 benchmark
.\scripts\make-gemma.ps1 quality
```

**Directly:**
```powershell
# Performance test
python scripts/tests/performance_test.py llama2 11434

# Quality test
python scripts/tests/quality_test.py mistral 11435

# Compare models
python scripts/tests/compare_models.py llama2:11434 mistral:11435
```

## 📊 Available Tests

### 1. Performance Benchmark

**What it tests:**
- Response time
- Tokens per second
- Generation latency
- Throughput

**Usage:**
```powershell
.\scripts\make-llama.ps1 benchmark
```

**Output:**
- Console summary with metrics
- JSON file saved to `results/performance_<model>_<timestamp>.json`

**Metrics:**
- Average response time
- Average tokens/sec
- Success rate
- Total tokens generated

### 2. Quality Assessment

**What it tests:**
- Factual accuracy
- Math capabilities
- Instruction following
- Reasoning ability
- Coherence
- Code understanding

**Usage:**
```powershell
.\scripts\make-llama.ps1 quality
```

**Output:**
- Score out of 100
- Rating (Excellent/Good/Fair/Poor)
- Detailed per-test breakdown
- JSON file saved to `results/quality_<model>_<timestamp>.json`

**Test Categories:**
- Factual Knowledge (10 pts)
- Math (10 pts)
- Instruction Following (10 pts)
- Reasoning (15 pts)
- Coherence (10 pts)
- Code Understanding (15 pts)

### 3. Model Comparison

**What it tests:**
- Side-by-side comparison of multiple models
- Same prompts across different models
- Performance and quality comparison

**Usage:**
```powershell
python scripts/tests/compare_models.py llama2:11434 mistral:11435 gemma:2b:11436
```

**Output:**
- Comparison table with metrics
- Detailed responses from each model
- JSON file saved to `results/comparison_<timestamp>.json`

## 📁 Results

All test results are saved to the `results/` folder:

```
results/
├── performance_llama2_1234567890.json
├── quality_mistral_1234567891.json
└── comparison_1234567892.json
```

## 🎯 Usage Examples

### Full Testing Workflow

```powershell
# 1. Start model
.\scripts\make-llama.ps1 start

# 2. Run quick test
.\scripts\make-llama.ps1 test-quick

# 3. Run performance benchmark
.\scripts\make-llama.ps1 benchmark

# 4. Run quality assessment
.\scripts\make-llama.ps1 quality

# 5. Check status
.\scripts\make-llama.ps1 status
```

### Compare All Models

```powershell
# Start all models on different ports
.\scripts\make-llama.ps1 start       # 11434
.\scripts\make-mistral.ps1 start     # 11435
.\scripts\make-gemma.ps1 start       # 11436
.\scripts\make-phi.ps1 start         # 11437

# Run comparison
python scripts/tests/compare_models.py llama2:11434 mistral:11435 gemma:2b:11436 phi:11437
```

### Automated Testing Suite

```powershell
# Test all models
foreach ($model in @("llama", "mistral", "gemma", "phi")) {
    Write-Host "`n=== Testing $model ===`n"
    .\scripts\make-$model.ps1 test
    .\scripts\make-$model.ps1 benchmark
    .\scripts\make-$model.ps1 quality
}
```

## 🔧 Customization

### Add Custom Test Cases

Edit `scripts/tests/quality_test.py`:

```python
test_cases = [
    {
        "category": "Your Category",
        "prompt": "Your test prompt",
        "expected_keywords": ["keyword1", "keyword2"],
        "points": 10
    }
]
```

### Adjust Performance Test Count

```powershell
# Run 10 tests instead of default 5
python scripts/tests/performance_test.py llama2 11434 10
```

### Custom Comparison Prompts

Edit `scripts/tests/compare_models.py`:

```python
test_prompts = [
    "Your custom prompt 1",
    "Your custom prompt 2",
    "Your custom prompt 3"
]
```

## 📈 Interpreting Results

### Performance Benchmark

**Good scores:**
- Response time: < 5s for simple prompts
- Tokens/sec: > 20 for 7B models, > 10 for 13B+
- Success rate: 100%

### Quality Assessment

**Score interpretation:**
- 80-100%: Excellent - Suitable for production
- 60-79%: Good - Reliable for most tasks
- 40-59%: Fair - Limited use cases
- 0-39%: Poor - Needs improvement

## 🐛 Troubleshooting

### Python Not Found

```powershell
# Install Python from python.org or:
winget install Python.Python.3.12
```

### Module Not Found

```powershell
pip install -r scripts/tests/requirements.txt
```

### Connection Refused

```powershell
# Make sure container is running
.\scripts\make-llama.ps1 status

# Check port
docker ps
```

### Results Folder Missing

```powershell
# Create manually
New-Item -ItemType Directory -Force -Path "results"
```

## 📚 Related Documentation

- [Main README](../../README-OLLAMA.md)
- [Llama Guide](../../docs/models/llama.md)
- [Mistral Guide](../../docs/models/mistral.md)
- [Gemma Guide](../../docs/models/gemma.md)
- [Phi Guide](../../docs/models/phi.md)
