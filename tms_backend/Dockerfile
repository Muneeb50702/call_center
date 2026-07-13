FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir hatchling && \
    pip install --no-cache-dir \
    "fastapi>=0.111" \
    "uvicorn[standard]>=0.30" \
    "pydantic>=2.7" \
    "sqlalchemy[asyncio]>=2.0" \
    "asyncpg>=0.29" \
    "PyJWT>=2.8" \
    "httpx>=0.27" \
    "redis[hiredis]>=5.0" \
    "pytest>=8.0" \
    "pytest-asyncio>=0.23" \
    "alembic>=1.13" \
    "passlib[bcrypt]>=1.7" \
    "bcrypt<4.0.0" \
    "livekit-api>=1.0" \
    "structlog>=24.1.0"

# We will mount the source code via docker-compose volume for hot reloading
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
