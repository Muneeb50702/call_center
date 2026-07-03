# Nexus Dispatch API Documentation

The TMS Backend exposes a robust REST API for tenant management, call analytics, and agent tool execution.

## Authentication

All endpoints under `/api/*` require a Bearer token in the `Authorization` header, except for `/api/auth/login`.

## Endpoints

### 1. Authentication
- `POST /api/auth/login`: Issue JWT token.

### 2. Tenants (Super Admin)
- `GET /api/tenants`: List all tenants.
- `POST /api/tenants`: Provision a new tenant.
- `GET /api/tenants/{tenant_id}`: Get tenant configuration (LLM rules, webhooks).

### 3. Freight / Loads
- `GET /api/loads`: List available loads (filtered by tenant).
- `POST /api/loads`: Add a new load to the board.
- `PUT /api/loads/{load_id}`: Update load status (e.g., booked).

### 4. Drivers
- `GET /api/drivers`: Search drivers by MC number.
- `POST /api/drivers`: Register a new driver/carrier.

### 5. Call History & Analytics
- `GET /api/calls`: List historical call transcripts and metadata.
- `GET /api/analytics/daily`: Aggregated metrics for dashboard charts.

### 6. Tools (Internal Agent Usage)
- `POST /api/detentions`: File a detention claim.
- `POST /api/documents`: Process requested document metadata.
