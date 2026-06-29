FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY pyproject.toml .
RUN pip install hatchling
RUN pip install fastapi>=0.111 "uvicorn[standard]>=0.30" pydantic>=2.7 pytest httpx

# We will mount the source code via docker-compose volume for hot reloading
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
