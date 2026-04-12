# Code Style Guide

## General Rules

- **Language**: Python 3.11+
- **Formatter**: Follow PEP 8
- **Line length**: 120 characters max
- **Encoding**: UTF-8
- **Newline**: LF (Unix-style)

## Naming Conventions

| Element | Convention | Example |
|---------|-----------|---------|
| Variables | `snake_case` | `model_name`, `cpu_percent` |
| Functions | `snake_case` | `get_container_stats()`, `start_vm()` |
| Classes | `PascalCase` | `MetricsCollector`, `BenchmarkRunner` |
| Constants | `UPPER_SNAKE_CASE` | `MODELS`, `DOCKER_TECHNOLOGIES` |
| Files | `snake_case` or `kebab-case` | `cold-start-test.py`, `performance_test.py` |
| Directories | `kebab-case` | `load-generator`, `data-processing` |

> **Note**: The project uses both `snake_case` and `kebab-case` for files. For new files, prefer `snake_case` for Python modules and `kebab-case` for script/tool directories.

## Imports

Order imports as:
1. Standard library
2. Third-party packages
3. Local modules

```python
import time
import json
from datetime import datetime

import docker
import psutil
import pandas as pd
import plotly.graph_objects as go

from backend.benchmarks import run_benchmark
```

## Functions

- Every function must have a **docstring** (one-line or multi-line).
- Use type hints for function signatures.

```python
def get_container_stats(container_name: str = "ollama") -> tuple[float, float, float]:
    """Get real-time stats from Docker container."""
    ...
```

## Error Handling

- Use `try/except` with specific exceptions where possible.
- For non-critical failures (e.g., Docker not available), return safe defaults.

```python
try:
    container = docker_client.containers.get(container_name)
except docker.errors.NotFound:
    return 0, 0, 0
```

## Data Structures

- Use `dict` for global state and configuration.
- Use `pydantic.BaseModel` for validated data structures and API models.
- Use `pandas.DataFrame` for tabular benchmark results.

## Configuration

- Keep model lists and technology options as module-level constants.
- Use environment variables or config files for deployment-specific settings (see `config/`).

## Comments

- Use comments sparingly — only when the code is not self-explanatory.
- Write comments in English.
- Use `# TODO:` for planned improvements.

## Testing

- Test files go in `scripts/tests/` or alongside the module.
- Use `pytest` conventions: `test_` prefix for test functions.
- See [`testing.md`](./testing.md) for required test types.

## Documentation Style

- Documentation style inspired by **Vue.js docs** — clear, structured, with examples.
- Every model must have a dedicated `.md` file in `docs/models/`.
- See [`model_docs_template.md`](./model_docs_template.md) for the template.
