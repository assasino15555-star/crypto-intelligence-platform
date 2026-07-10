# Crypto Intelligence Platform

Read-only crypto wallet intelligence and monitoring, delivered as a Telegram
Mini App. Add public wallet addresses, track balances and transactions, set
alerts, and get AI-generated explanations of on-chain activity — without ever
touching a private key.

The platform never requests, stores, or processes private keys, seed phrases,
recovery phrases, or wallet passwords. It does not sign transactions or trade.
All data comes from public blockchain APIs.

## Features

- Telegram Mini App with HMAC-verified initData authentication
- Wallet monitoring on Ethereum and Base (EIP-55 checksum addresses)
- Native balance, token holdings, recent transactions
- Portfolio snapshots (point-in-time historical state)
- Configurable alerts: incoming/outgoing above threshold, activity, token transfers
- Telegram push notifications when alerts fire
- AI explanations of wallet activity with strict input/output boundaries
- Transaction risk indicators based on on-chain facts
- Background workers with idempotent tasks and distributed locking
- Distributed rate limiting backed by Redis
- SSRF protection with DNS resolution validation
- Full Docker setup with non-root containers, resource limits, and network isolation

## Architecture

```
Telegram user → aiogram bot (onboarding)
             → React Mini App → FastAPI API → PostgreSQL
                                                → Redis (rate limits, locks, replay cache)
                                                → blockchain provider (Etherscan)
                                                → AI provider (OpenAI-compatible)
             ← worker sends alert notifications via bot
```

Repository layout:

```
apps/
  api/     FastAPI backend + Alembic migrations + tests
  bot/     aiogram 3.x Telegram bot
  web/     React + TypeScript + Vite Mini App
  worker/  Background task processor
packages/
  shared/  Domain types shared across services
infra/     Dockerfiles, nginx config
.github/   CI pipeline
```

## Tech stack

**Backend:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 async, Alembic,
asyncpg, Redis, httpx, aiogram 3.x.

**Frontend:** React 18, TypeScript 5, Vite 5, TanStack Query 5, Tailwind CSS 3.

**Infra:** Docker (multi-stage, non-root, read-only), PostgreSQL 16, Redis 7,
nginx unprivileged, internal + frontend network separation.

## Security model

- Identity is derived exclusively from cryptographically verified Telegram
  initData. The backend never trusts client-supplied user IDs.
- Session tokens are HMAC-signed, short-lived, capped at a maximum lifetime,
  and only the SHA-256 hash is stored server-side. Sessions support revoke,
  revoke-all, and per-user quotas.
- Every endpoint that touches a wallet, alert, transaction, or AI analysis
  verifies ownership. Cross-user access returns 404 (no existence leak).
- Outbound HTTP goes through a custom transport that resolves DNS and rejects
  loopback, private, link-local, multicast, and metadata-service IPs. Redirects
  are disabled. AI provider URLs are validated against a production allowlist.
- Rate limiting is Redis-backed with atomic Lua scripts, per-user keys for
  authenticated endpoints, per-IP keys for login, and a global AI budget.
  Trusted proxy configuration uses CIDR networks and right-to-left XFF parsing.
- AI input is structured JSON with all fields sanitized and length-bounded
  before serialization. Output is stripped of URLs, HTML, markdown, control
  characters, and word-count-limited.
- Telegram initData replay is blocked via Redis nonce cache with TTL matching
  the freshness window.
- No secrets in the repository. `.env.example` has only placeholders.
- Production refuses to start without a strong APP_SECRET, real providers,
  HTTPS-only CORS, and TRUSTED_HOSTS. Dev auth bypass cannot run in production.

## Quick start with Docker

```bash
cp .env.example .env
# fill in all required values

docker compose up -d db redis
docker compose --profile migrate run --rm migrate
docker compose up -d api worker web
docker compose --profile bot up -d bot  # optional
```

- Web app: http://localhost:5173
- API health: http://localhost:8000/api/v1/health/live
- API docs: http://localhost:8000/docs (non-production only)

## Local development

```bash
# Backend
python -m venv .venv && source .venv/bin/activate
pip install -e packages/shared -e .[dev]
alembic upgrade head
uvicorn apps.api.app.main:app --reload --port 8000

# Worker
python -m apps.worker.worker.run_worker

# Bot
python -m apps.bot.bot.main

# Frontend
cd apps/web
npm ci
npm run dev
```

## Environment variables

See `.env.example` for the full list. Key variables:

| Variable | Purpose |
|---|---|
| `ENVIRONMENT` | `development` / `staging` / `production` |
| `APP_SECRET` | HMAC secret for session tokens (≥32 chars in production) |
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather |
| `DATABASE_URL` | Async SQLAlchemy URL |
| `REDIS_URL` | Redis URL (must include password in production) |
| `BLOCKCHAIN_PROVIDER` | `etherscan` or `mock` |
| `BLOCKCHAIN_API_KEY` | Etherscan API key (required when provider=etherscan) |
| `AI_PROVIDER` | `openai` or `mock` |
| `AI_API_KEY` | OpenAI-compatible API key (required when provider=openai) |
| `CORS_ORIGINS` | Comma-separated HTTPS origins (no wildcard in production) |
| `TRUSTED_HOSTS` | Comma-separated allowed Host header values (required in production) |
| `RATE_LIMIT_TRUSTED_PROXIES` | CIDR networks of trusted reverse proxies |
| `MAX_WALLETS_PER_USER` | Wallet quota (default 20) |
| `MAX_ALERTS_PER_USER` | Alert quota (default 100) |
| `MAX_SESSIONS_PER_USER` | Active session quota (default 5) |

## Development commands

```bash
# Backend
ruff format apps packages
ruff check apps packages
mypy apps/api/app apps/worker/worker apps/bot/bot packages/shared/shared
pytest apps/api/tests -ra
alembic upgrade head

# Frontend
cd apps/web
npm run lint
npm run typecheck
npm run test
npm run build
```

## Tests

Backend tests (122): address validation and EIP-55 normalization, Telegram
initData verification (valid, tampered, expired, future, malformed, duplicate
params, oversized, replay), session token lifecycle (max lifetime, excessive
exp, old iat, rotation, revoke), settings validation (production constraints,
dev fallback secret rejection, HTTPS-only CORS, TRUSTED_HOSTS requirement),
URL/SSRF safety (DNS rebinding, IPv4-mapped IPv6, metadata endpoints, all
private ranges), HTTP retry classification (429 with Retry-After, transport
errors, oversized response rejection, Content-Type validation, negative
Retry-After), rate limiter (XFF spoofing, trusted proxy CIDR, per-user vs
per-IP, concurrency), alert evaluation idempotency, worker sync idempotency
with distributed locking, AI prompt injection resistance (label injection,
malicious transaction text, oversized input), AI output sanitization (URLs,
HTML, markdown, javascript/data schemes, word count), API integration (CRUD,
IDOR, pagination bounds, quota enforcement, active_only filter, revoke-all).

Frontend tests (9): format helpers, wallet form validation.

Tests use an in-memory SQLite database and a mock provider. No external API
calls are required.

## Limitations

- The worker uses an in-process task broker. For multi-process production,
  switch to TaskiqRedisBroker — task signatures are unchanged.
- Token holdings are derived from Etherscan `tokentx` transfer history, not
  direct `balanceOf` calls.
- USD pricing is not fetched. Adding a price oracle is a provider extension
  point.
- No live demo is provided. No real production deployment is claimed.
- Docker base images are pinned to specific version tags. For full supply-chain
  hardening, pin by `@sha256:` digest in production deployments.

## License

MIT — see [LICENSE](LICENSE).
