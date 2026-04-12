# AGENTS.md — Project Guide for AI Agents

## Project Overview

This is a diploma project that compares **Small Language Models (SLM)** running on **Docker** (containers) vs **Virtual Machines (VM)**. The goal is to benchmark performance, resource usage, cost, and quality across multiple models and deployment platforms.

## Source of Truth

The canonical project plan lives in [`agents/source_of_truth.md`](./source_of_truth.md). All development decisions must align with it.

## Agent Reference Files

| File | Purpose |
|------|---------|
| [`technology_stack.md`](./technology_stack.md) | Languages, frameworks, tools, and deployment platforms used |
| [`code_style.md`](./code_style.md) | Coding conventions and style rules |
| [`testing.md`](./testing.md) | Test types that must exist for every model and scenario |
| [`metrics.md`](./metrics.md) | All metrics to collect during benchmarks |
| [`model_docs_template.md`](./model_docs_template.md) | Template for creating per-model documentation in `docs/models/` |
| [`project_structure.md`](./project_structure.md) | Directory layout and file organization |
| [`monitoring.md`](./monitoring.md) | Monitoring and observability setup |
| [`security.md`](./security.md) | Security scanning and compliance requirements |
| [`deployment_docker.md`](./deployment_docker.md) | Ollama on Docker: install → start container → run benchmarks from frontend → save JSON |
| [`deployment_vm.md`](./deployment_vm.md) | Step-by-step: install model on VM → run benchmarks → save JSON results |

## Key Models

- **Phi**: 3.5 Mini, 4.8B, 3 Vision
- **Gemma 2**: 2B, 9B
- **Llama**: 3.2, 3.1
- **Mistral**: 7B, v0.3, 3B, 8B
- **Qwen 2.5**: 0.5B, 1.5B, 3B, 7B
- **StableLM 2**: 1.6B, 12B
- **Falcon**: 1B, 7B
- **Others**: Zephyr 7B, OpenELM, Grok-mini

### Paid Models (for comparison baseline)

- GPT-4o mini, Claude 3 Haiku, Gemini 1.5 Flash, Mistral Small

## Deployment Platforms

- **Containers**: Docker, Podman, containerd
- **VMs**: Traditional VM, Xen, Firecracker, microVM, LXC/LXD
- **Cloud**: AWS Lambda, AWS Fargate, Google Cloud Run, Vercel AI
- **Experimental**: WASM

## ML Frameworks

- llama.cpp, vLLM, Ollama, Transformers, ONNX Runtime

## Quick Start for Agents

1. Read this file first.
2. Check the relevant reference `.md` file for your task area.
3. Follow `code_style.md` for all code changes.
4. Every model benchmark must collect all metrics from `metrics.md`.
5. Every model must have tests defined in `testing.md`.
6. Every model must have a doc file following `model_docs_template.md`.
