# zrun-bff

Backend For Frontend (BFF) service for zrun WMS.

## Architecture

```
┌─────────┐      ┌─────────┐      ┌─────────┐      ┌──────────────┐
│  PDA    │ ───> │   BFF   │ ───> │ Casdoor │      │  Internal    │
│   Web   │ ───> │(FastAPI)│ ───> │(OAuth2) │ ───> │  Services    │
│ MiniApp │ ───> │         │      └─────────┘      │(gRPC)        │
└─────────┘      └─────────┘                       └──────────────┘
                      │
                      ├── OAuth2 Authentication
                      ├── JWT Re-issuance (Internal tokens)
                      ├── API Aggregation
                      └── Protocol Translation (HTTP → gRPC)
```

## Responsibilities

1. **OAuth2 Authentication**
   - Handle login flow with Casdoor
   - Validate Casdoor JWT tokens
   - Issue internal JWT tokens for microservices

2. **Client-Specific APIs**
   - `api/pda/` - PDA endpoints (inbound, picking, transfer)
   - `api/web_admin/` - Web admin endpoints (dashboard, settings, reports)
   - `api/mini_app/` - Mini app endpoints (inventory, notifications)

3. **gRPC Client Layer**
   - Encapsulate connections to internal services
   - Handle retries and circuit breaking
   - Propagate user context

## Configuration

Environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `CASDOOR_CLIENT_ID` | Casdoor OAuth2 client ID | - |
| `CASDOOR_CLIENT_SECRET` | Casdoor OAuth2 client secret | - |
| `CASDOOR_REDIRECT_URI` | OAuth2 callback URL | - |
| `CASDOOR_AUTHORIZATION_ENDPOINT` | Casdoor authorize URL | - |
| `CASDOOR_TOKEN_ENDPOINT` | Casdoor token endpoint | - |
| `JWT_PRIVATE_KEY_PATH` | Path to JWT signing private key | - |
| `JWT_ISSUER` | JWT issuer claim | `zrun-bff` |
| `JWT_AUDIENCE` | JWT audience claim | `zrun-services` |
| `JWT_EXPIRATION_SECONDS` | Internal JWT TTL | `3600` |

## Running

```bash
just dev zrun-bff
```

## API Endpoints

### Authentication

- `GET /auth/login` - Redirect to Casdoor login
- `GET /auth/callback` - OAuth2 callback, issues internal JWT
- `GET /.well-known/jwks.json` - JWKS endpoint for internal services
- `GET /health` - Health check

### PDA APIs

- `POST /api/pda/inbound` - Receive goods
- `POST /api/pda/picking` - Pick orders
- `POST /api/pda/transfer` - Transfer inventory

### Web Admin APIs

- `GET /api/web/dashboard` - Dashboard data
- `GET /api/web/settings` - System settings
- `GET /api/web/reports` - Reports

### Mini App APIs

- `GET /api/mini/inventory` - Inventory query
- `GET /api/mini/notifications` - User notifications
