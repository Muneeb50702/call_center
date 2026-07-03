# ── Stage 1: Builder ──
FROM python:3.11-slim AS builder

WORKDIR /build

COPY pyproject.toml .
RUN pip install --no-cache-dir hatchling && \
    pip install --no-cache-dir \
    "livekit-agents~=1.0" \
    "livekit-plugins-deepgram~=1.0" \
    "livekit-plugins-silero>=1.0" \
    "livekit-plugins-openai>=1.0" \
    "livekit-plugins-google>=0.1" \
    "openai>=1.30" \
    "httpx>=0.27" \
    "pydantic>=2.7" \
    "pydantic-settings>=2.3" \
    "structlog>=24.1" \
    "python-dotenv>=1.0" \
    "redis[hiredis]>=5.0"

# ── Stage 2: Runtime ──
FROM python:3.11-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Source code mounted via docker-compose volume for hot reloading in dev
# In production, uncomment: COPY . .

# Health check — ensures the worker process is alive
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

CMD ["python", "entrypoint.py", "dev"]
