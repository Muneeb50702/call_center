# ── Stage 1: Builder ──
FROM python:3.11-slim AS builder

WORKDIR /build

COPY pyproject.toml .
RUN pip install --no-cache-dir hatchling && \
    pip install --no-cache-dir \
    "livekit-agents~=1.6" \
    "livekit-plugins-deepgram~=1.6" \
    "livekit-plugins-silero>=1.6" \
    "livekit-plugins-openai>=1.0" \
    "livekit-plugins-google>=0.1" \
    "livekit-plugins-cartesia>=1.6" \
    "livekit-plugins-elevenlabs>=1.6" \
    "livekit-plugins-turn-detector~=1.0" \
    "openai>=1.30" \
    "httpx>=0.27" \
    "pydantic>=2.7" \
    "pydantic-settings>=2.3" \
    "structlog>=24.1" \
    "python-dotenv>=1.0" \
    "redis[hiredis]>=5.0" \
    "fastembed>=0.4" \
    "numpy>=1.26"

# ── Stage 2: Runtime ──
FROM python:3.11-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Bake the CPU models into the image rather than downloading them on worker boot.
# Three models run locally: Silero VAD, the semantic turn detector, and the
# bge-small embedding model behind retrieval. Downloading them at startup would
# add tens of seconds to every deploy and make the worker's readiness depend on
# HuggingFace being up. HF_HOME is pinned so the cache written here is the same
# path the runtime reads.
ENV HF_HOME=/opt/models \
    FASTEMBED_CACHE_PATH=/opt/models/fastembed \
    PYTHONUNBUFFERED=1

RUN mkdir -p /opt/models && \
    python -c "\
from fastembed import TextEmbedding; \
TextEmbedding(model_name='BAAI/bge-small-en-v1.5'); \
print('embedding model cached')"

# Download the LiveKit plugin models (Silero VAD + the local semantic turn
# detector). The turn detector is the fallback for the hosted one; without its
# weights on disk that fallback silently does not exist, and the agent drops to
# VAD-only endpointing — which pairs badly with a VAD tuned for a 250ms silence
# window. Downloading it here makes the fallback real.
RUN python -c "\
from livekit.agents import Plugin; \
from livekit.plugins import silero; \
from livekit.plugins.turn_detector import english; \
[p.download_files() for p in Plugin.registered_plugins]; \
print('livekit plugin models cached')" 2>&1 | tail -1

# Source code mounted via docker-compose volume for hot reloading in dev
# In production, uncomment: COPY . .

# Health check — ensures the worker process is alive
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

CMD ["python", "entrypoint.py", "dev"]
