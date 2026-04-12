# 🚀 Ollama Docker Testing Framework

Framework for testing LLM models via Ollama in Docker containers.

## 📋 Quick Start

**Model-specific scripts (recommended):**
```powershell
# Test Llama 2
.\scripts\make-llama.ps1 test

# Test Mistral
.\scripts\make-mistral.ps1 test

# Test Gemma
.\scripts\make-gemma.ps1 test

# Test Phi
.\scripts\make-phi.ps1 test
```

**Linux/WSL/Git Bash:**
```bash
# Test Llama 2
make -f scripts/Makefile-llama test

# Test Mistral
make -f scripts/Makefile-mistral test
```

## 📚 Документація

### Загальна документація
- [Інструкція по використанню Make](docs/makefile-guide.md) - детальний опис команд
- [Архітектура проекту](docs/architecture.md)
- [Методологія тестування](docs/testing-methodology.md)
- [Налаштування інфраструктури](docs/setup-guide.md)

### Model Documentation

Each model has dedicated scripts and documentation:

| Model | Size | Scripts | Port | Documentation |
|-------|------|---------|------|---------------|
| 🦙 **Llama 2** | 7B/13B/70B | `make-llama.ps1` / `Makefile-llama` | 11434 | [docs/models/llama.md](docs/models/llama.md) |
| ⚡ **Mistral** | 7B | `make-mistral.ps1` / `Makefile-mistral` | 11435 | [docs/models/mistral.md](docs/models/mistral.md) |
| 💎 **Gemma** | 2B/7B | `make-gemma.ps1` / `Makefile-gemma` | 11436 | [docs/models/gemma.md](docs/models/gemma.md) |
| 🔬 **Phi** | 2.7B | `make-phi.ps1` / `Makefile-phi` | 11437 | [docs/models/phi.md](docs/models/phi.md) |

All scripts are located in the `scripts/` folder.

## ⚡ Main Commands

Each model script supports the same commands:

### Container Management
```powershell
.\scripts\make-llama.ps1 start      # Start container
.\scripts\make-llama.ps1 stop       # Stop container
.\scripts\make-llama.ps1 status     # Show status
.\scripts\make-llama.ps1 logs       # Show logs
```

### Testing
```powershell
.\scripts\make-llama.ps1 test       # Full test (start + pull + test)
.\scripts\make-llama.ps1 test-quick # Quick test (no pull)
.\scripts\make-llama.ps1 pull       # Pull model only
```

### Cleanup
```powershell
.\scripts\make-llama.ps1 clean      # Remove container
.\scripts\make-llama.ps1 list-models # Show available models
```

### Run Multiple Models in Parallel

Each model uses a different port, so you can test them simultaneously:

```

## 📊 Model Comparison

| Model | Size | Speed | Quality | RAM Usage | Recommendations |
|-------|------|-------|---------|-----------|-----------------|
| Llama 2 7B | 3.8GB | ⭐⭐⭐ | ⭐⭐⭐⭐ | ~8GB | General purpose tasks |
| Mistral 7B | 4.1GB | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ~8GB | High-quality responses |
| Gemma 2B | 1.4GB | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ~4GB | Fast simple tasks |
| Phi 2.7B | 1.7GB | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ~4GB | Code and analysis |

## 🎯 Usage Examples

### Test Single Model
```powershell
# Simple - one command does everything
.\scripts\make-llama.ps1 test

# Or step by step:
.\scripts\make-llama.ps1 start
.\scripts\make-llama.ps1 pull
.\scripts\make-llama.ps1 test-quick
.\scripts\make-llama.ps1 status
```

### Compare Models
```powershell
# Test Llama 2
.\scripts\make-llama.ps1 test

# Test Mistral (different container/port)
.\scripts\make-mistral.ps1 test

# Test Gemma
.\scripts\make-gemma.ps1 test
```

### Parallel Testing

All models can run simultaneously (different ports):

```powershell
# Open 4 PowerShell terminals from root folder:

# Terminal 1
.\scripts\make-llama.ps1 test       # ollama-llama:11434

# Terminal 2
.\scripts\make-mistral.ps1 test     # ollama-mistral:11435

# Terminal 3
.\scripts\make-gemma.ps1 test       # ollama-gemma:11436

# Terminal 4
.\scripts\make-phi.ps1 test         # ollama-phi:11437
```

## 🐛 Troubleshooting

### Container Won't Start
```powershell
# Check Docker
docker info

# View logs
.\scripts\make-llama.ps1 logs

# Clean and retry
.\scripts\make-llama.ps1 clean
.\scripts\make-llama.ps1 start
```

### Model Not Responding
```powershell
# Check if model is loaded
.\scripts\make-llama.ps1 list-models

# Reload model
.\scripts\make-llama.ps1 pull

# Check status
.\scripts\make-llama.ps1 status
.\make.ps1 status
```

### Повільна робота
- Переконайтесь що Docker має достатньо RAM (мінімум 8GB)
- Спробуйте меншу модель (gemma:2b або phi)
- Перевірте чи не запущені інші контейнери: `.\make.ps1 ps`

.\scripts\make-llama.ps1 status
```

### Port Conflict
```powershell
# Check running containers
docker ps -a

# Stop and remove conflicting container
docker stop ollama-llama
docker rm ollama-llama

# Or use the script
.\scripts\make-llama.ps1 clean
```

## 📁 Project Structure

```
diploma/
├── README-OLLAMA.md           # This file
├── scripts/
│   ├── make-llama.ps1         # Llama 2 script (port 11434)
│   ├── make-mistral.ps1       # Mistral script (port 11435)
│   ├── make-gemma.ps1         # Gemma script (port 11436)
│   ├── make-phi.ps1           # Phi script (port 11437)
│   ├── Makefile-llama         # Linux/WSL version
│   ├── Makefile-mistral       # Linux/WSL version
│   ├── Makefile-gemma         # Linux/WSL version
│   ├── Makefile-phi           # Linux/WSL version
│   ├── test-ollama.ps1        # Alternative test script
│   └── test-ollama.sh         # Bash version
├── docs/
│   └── models/                # Model documentation
│       ├── llama.md
│       ├── mistral.md
│       ├── gemma.md
│       └── phi.md
└── docker/
    └── frameworks/ollama/
```

## 🔗 Useful Links

- [Ollama Documentation](https://github.com/ollama/ollama)
- [Available Models](https://ollama.ai/library)
- [Docker Hub - Ollama](https://hub.docker.com/r/ollama/ollama)

## 📝 License

This project was created for LNU diploma work.
