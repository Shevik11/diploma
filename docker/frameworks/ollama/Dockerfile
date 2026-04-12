FROM ollama/ollama:latest

EXPOSE 11434

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD curl -f http://localhost:11434/api/tags || exit 1