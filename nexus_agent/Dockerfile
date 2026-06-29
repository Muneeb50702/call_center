FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY pyproject.toml .
RUN pip install hatchling
RUN pip install "livekit-agents~=1.0" "livekit-plugins-deepgram~=1.0" "livekit-plugins-silero~=1.0" "livekit-plugins-openai~=1.0" "openai>=1.30" "httpx>=0.27" "pydantic>=2.7" "pydantic-settings>=2.3" "structlog>=24.1" "python-dotenv>=1.0"

# We will mount the source code via docker-compose volume for hot reloading
CMD ["python", "entrypoint.py", "dev"]
