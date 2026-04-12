FROM ollama/ollama:latest

# Explicitly install curl for healthcheck resilience
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

EXPOSE 11434

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD curl -f http://localhost:11434/api/tags || exit 1