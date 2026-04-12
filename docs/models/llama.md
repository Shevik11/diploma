# Llama 2 - Testing via Ollama

### Basic Usage
```powershell
# Full test Llama 2 (7B)
.\scripts\make-llama.ps1 test

# For specific version (13B or 70B), edit the script or use test-ollama.ps1
.\scripts\test-ollama.ps1 -ModelName llama2:13b
```

### Step by Step Testing
```powershell
# 1. Start container
.\scripts\make-llama.ps1 start

# 2. Pull Llama 2 7B model
.\scripts\make-llama.ps1 pull

# 3. Quick test
.\scripts\make-llama.ps1 test-quick

# 4. Check status
.\scripts\make-llama.ps1 status
```

## Available Versions

### Llama 2 7B 
```powershell
# Standard model (preconfigured)
.\scripts\make-llama.ps1 test

# For other versions, use test-ollama.ps1
.\scripts\test-ollama.ps1 -ModelName llama2:7b

# Chat version (optimized for conversations)
.\scripts\test-ollama.ps1 -ModelName llama2:7b-chat
```

### Llama 2 13B 
```powershell
# 13B model
.\scripts\test-ollama.ps1 -ModelName llama2:13b

# Chat version
.\scripts\test-ollama.ps1 -ModelName llama2:13b-chat
```

### Llama 2 70B 
```powershell
# 70B model 
.\scripts\test-ollama.ps1 -ModelName llama2:70b
```

## Testing Examples

### Test 1: General Questions
```powershell
.\scripts\make-llama.ps1 test-quick
```

### Test 2: Text Generation
```powershell
# Via API
$body = @{
    model = "llama2"
    prompt = "Write a short story about a robot learning to paint"
    stream = $false
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:11434/api/generate" `
    -Method Post -ContentType "application/json" -Body $body
```

### Test 3: Dialogue (Chat version)
```powershell
# First pull chat version
.\scripts\test-ollama.ps1 -ModelName llama2:7b-chat

# Testing via API
$body = @{
    model = "llama2:7b-chat"
    messages = @(
        @{ role = "user"; content = "Hello! Can you help me with Python?" }
    )
} | ConvertTo-Json -Depth 3

Invoke-RestMethod -Uri "http://localhost:11434/api/chat" `
    -Method Post -ContentType "application/json" -Body $body
```

### Test 4: Long Context
```powershell
$body = @{
    model = "llama2"
    prompt = "Summarize the following text: [long text here]"
    stream = $false
    options = @{
        num_ctx = 4096  # Maximum context
    }
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:11434/api/generate" `
    -Method Post -ContentType "application/json" -Body $body
```

## Parameter Configuration

### Temperature (creativity)
```powershell
$body = @{
    model = "llama2"
    prompt = "Tell me a creative story"
    stream = $false
    options = @{
        temperature = 0.8  # 0.0 = deterministic, 1.0 = creative
    }
} | ConvertTo-Json
```

### Maximum Response Length
```powershell
$body = @{
    model = "llama2"
    prompt = "Explain quantum physics"
    stream = $false
    options = @{
        num_predict = 200  # Maximum tokens in response
    }
} | ConvertTo-Json
```

### Top-k and Top-p sampling
```powershell
$body = @{
    model = "llama2"
    prompt = "Write a poem"
    stream = $false
    options = @{
        top_k = 40      # Consider top-40 tokens
        top_p = 0.9     # Nucleus sampling
    }
} | ConvertTo-Json
```

### Model Running Slowly
```powershell
# Try smaller version
.\scripts\make-llama.ps1 clean
.\scripts\make-llama.ps1 test

# Check resource usage
docker stats ollama-test
```

### Out of Memory
```powershell
# Use quantized version
.\scripts\test-ollama.ps1 -ModelName llama2:7b-q4_0  # 4-bit quantization

# Or switch to smaller model
.\scripts\make-gemma.ps1 test
```

### Poor Quality Responses
```powershell
# Try Chat version
.\scripts\test-ollama.ps1 -ModelName llama2:7b-chat

# Or increase model size
.\scripts\test-ollama.ps1 -ModelName llama2:13b
```

## Back to Main Documentation

[← Back to README-OLLAMA.md](../../README-OLLAMA.md)
