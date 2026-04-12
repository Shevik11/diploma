# Model Documentation Template

Use this template when creating a new model doc file in `docs/models/`. Name the file `<model-name>.md` (lowercase, kebab-case).

---

## Template

```markdown
# <Model Name>

## Overview

- **Developer**: <Company/Organization>
- **Parameters**: <size, e.g., 3.8B>
- **Architecture**: <e.g., Transformer decoder-only>
- **License**: <e.g., Apache 2.0, MIT, proprietary>
- **Release Date**: <YYYY-MM>
- **HuggingFace**: <link>
- **Ollama Tag**: <e.g., `phi3:mini`>

## Variants Tested

| Variant | Parameters | Format | Quantization |
|---------|-----------|--------|-------------|
| <name> | <size> | GGUF/AWQ/EXL2 | Q4/Q8/FP16 |

## Deployment

### Docker

\```bash
# Ollama example
docker run -d --name <model> ollama/ollama
docker exec <model> ollama pull <model-tag>
\```

### VM

\```bash
# Setup steps for VM deployment
\```

## Benchmark Results

### Inference Performance

| Platform | First Token (ms) | Throughput (tok/s) | Response Time (ms) | Model Load (s) |
|----------|------------------|--------------------|---------------------|-----------------|
| Docker   |                  |                    |                     |                 |
| VM       |                  |                    |                     |                 |

### Resource Usage

| Platform | CPU (%) | RAM (MB) | Peak RAM (MB) | Disk (GB) |
|----------|---------|----------|---------------|-----------|
| Docker   |         |          |               |           |
| VM       |         |          |               |           |

### Quality

| Platform | BLEU | ROUGE | Multilingual |
|----------|------|-------|-------------|
| Docker   |      |       |             |
| VM       |      |       |             |

## Notes

- <Any model-specific observations, quirks, or configuration tips>

## References

- <Links to official docs, papers, benchmarks>
```

---

## Existing Model Docs

Files in `docs/models/`:
- `phi.md` — Phi family
- `gemma.md` — Gemma family
- `llama.md` — Llama family
- `mistral.md` — Mistral family

## Models Still Needing Docs

- `qwen.md` — Qwen 2.5 (0.5B, 1.5B, 3B, 7B)
- `stablelm.md` — StableLM 2 (1.6B, 12B)
- `falcon.md` — Falcon (1B, 7B)
- `zephyr.md` — Zephyr 7B
- `openelm.md` — OpenELM
- `grok-mini.md` — Grok-mini
