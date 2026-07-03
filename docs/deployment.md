# Nexus Dispatch Deployment Guide

## Architecture Overview

Nexus Dispatch is a multi-tenant AI call center platform containing:
1. **Nexus Agent**: Python LiveKit workers running the LLM/TTS/STT pipelines.
2. **TMS Backend**: FastAPI application handling REST endpoints, tool invocations, and tenant routing.
3. **Dashboard**: Next.js 14 frontend for tenant and super-admin management.
4. **PostgreSQL & Redis**: State and data storage.
5. **Nginx**: Reverse proxy and API rate limiter.

## Production Requirements

- **VPS**: 4+ CPU Cores, 8GB+ RAM (e.g., DigitalOcean Premium Droplet)
- **Domain**: Registered domain name pointing to the VPS IP
- **LiveKit Server**: Self-hosted or LiveKit Cloud (Cloud recommended for production)
- **API Keys**: OpenAI, Deepgram, ElevenLabs, Resend

## Deployment Steps

1. **Clone the Repository on your VPS:**
   ```bash
   git clone https://github.com/your-org/Call_Center.git
   cd Call_Center
   ```

2. **Configure Environment:**
   ```bash
   cp .env.example .env
   nano .env
   ```
   Fill out all necessary keys. Ensure `JWT_SECRET` and `POSTGRES_PASSWORD` are secure.

3. **Deploy with Docker Compose:**
   ```bash
   # Build and start all services in detached mode
   docker compose -f docker-compose.prod.yml up --build -d
   ```

4. **Setup SSL with Certbot:**
   Since Nginx is handling the reverse proxy, you can attach an SSL cert using Certbot.
   ```bash
   sudo apt install certbot
   sudo certbot certonly --standalone -d app.yourdomain.com
   ```
   Update `nginx/nginx.conf` to map to the cert paths and reload Nginx.

## Scaling
To handle up to 50 concurrent calls, the architecture is designed to scale horizontally. 
The `docker-compose.prod.yml` spins up 3 replicas of `nexus-agent` by default. 
To increase this:
```bash
docker compose -f docker-compose.prod.yml up --scale nexus-agent=5 -d
```
LiveKit natively load-balances incoming connections across all connected workers.
