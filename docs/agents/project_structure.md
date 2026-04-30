# Project Structure

```
diploma/
├── agents/                          # AI agent guidance files
│   ├── AGENTS.md                    # Main agent entry point
│   ├── source_of_truth.md           # Canonical project plan
│   ├── technology_stack.md          # Tech stack reference
│   ├── code_style.md               # Coding conventions
│   ├── testing.md                   # Test requirements
│   ├── metrics.md                   # Metrics to collect
│   ├── model_docs_template.md       # Template for model docs
│   ├── project_structure.md         # This file
│   ├── monitoring.md                # Monitoring setup
│   └── security.md                  # Security requirements
│
├── analysis/                        # Data analysis and reporting
│   ├── data-processing/
│   │   ├── cost-calculator.py       # TCO and cost analysis
│   │   ├── metrics-aggregator.py    # Aggregate raw metrics
│   │   └── performance-analyzer.py  # Performance comparison
│   ├── reports/
│   │   └── generate-report.py       # Generate final reports
│   └── visualization/
│       ├── comparative-plots.py     # Docker vs VM comparison charts
│       └── generate-charts.py       # General chart generation
│
├── backend/                         # FastAPI backend
│   ├── main.py                      # API server entry point
│   └── benchmarks.py                # Benchmark API endpoints
│
├── benchmarks/                      # Benchmark test scripts
│   ├── load-generator/
│   │   ├── cold-start-test.py       # Cold start benchmarks
│   │   ├── concurrent-test.py       # Parallel request tests
│   │   ├── sequential-test.py       # Sequential request tests
│   │   └── stress-test.py           # Stress/limit tests
│   └── scenarios/
│       ├── chatbot-simulation.py    # Chatbot usage simulation
│       ├── failure-scenarios.py     # Failure and recovery tests
│       └── real-world-use-cases.py  # Real-world task benchmarks
│
├── config/                          # Configuration files
│
├── docker/                          # Docker-related files (Dockerfiles, compose)
│
├── docs/                            # Documentation
│   └── models/                      # Per-model documentation
│       ├── doc.md
│       ├── gemma.md
│       ├── llama.md
│       ├── mistral.md
│       └── phi.md
│
├── frontend/                        # Frontend assets (if any)
│
├── monitoring/                      # Prometheus, Grafana configs
│
├── results/                         # Raw benchmark results (JSON/CSV)
│
├── scripts/                         # Utility and test scripts
│   └── tests/
│       ├── compare_models.py        # Cross-model comparison
│       ├── performance_test.py      # Performance test runner
│       └── quality_test.py          # Quality evaluation
│
├── vm/                              # VM configurations and scripts
│
├── main.py                          # Main entry point
├── pyproject.toml                   # Python project config
├── requirements.txt                 # Dependencies
└── uv.lock                          # uv lockfile
```

## Key Conventions

- **benchmarks/**: All benchmark scripts, organized by type
- **analysis/**: Post-processing of results, never modifies raw data
- **results/**: Raw output only — never commit processed data here
- **docs/models/**: One `.md` file per model family (see `model_docs_template.md`)
- **config/**: Environment-specific settings, not code
- **docker/**: Dockerfiles and docker-compose files for deployment
- **vm/**: VM provisioning scripts (Terraform, Ansible, Vagrant)
