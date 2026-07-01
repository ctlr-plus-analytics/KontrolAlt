# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Full stack (Redis + backend API + Celery worker + beat)
docker compose up --build

# Frontend (http://localhost:3000)
cd frontend && npm install && npm run dev
cd frontend && npm run build      # production build check
cd frontend && npm run lint       # ESLint

# Backend tests
cd backend && pytest

# Scraper tests
cd scraper && pytest

# Single test file
cd backend && pytest tests/test_channel_service.py
cd scraper && pytest tests/test_discover_channels.py
```

## Architecture

Four services communicate across two transports — **HTTP** (frontend → backend) and **Celery/Redis** (backend → scraper worker):

```
Next.js frontend
  └─ HTTP/Bearer JWT → FastAPI backend (port 8000)
                         └─ Celery.send_task() → Redis broker → Celery worker
                                                                 └─ Celery beat (scheduled triggers)
Both backend and scraper connect directly to Supabase (service-role key).
Frontend connects to Supabase as anon (JWT-gated via Supabase Auth).
```

### Backend (`backend/`)

- **Entry**: `main.py` — FastAPI app, CORS, request logging, global exception handlers.
- **Routes**: `api/v1/router.py` mounts sub-routers: `channels`, `velocity`, `gate0`, `lookalike`, `scraper`, `admin`.
- **Pattern**: Thin route handlers in `api/v1/*.py`; all business logic lives in `services/*.py`.
- **Cross-service dispatch**: `workers/tasks.py` holds Celery task name constants used with `celery.send_task()`. The backend never imports scraper code directly.
- **Auth**: `core/security.py` — `get_current_user` (JWT verify via Supabase SDK), `require_admin_user` (checks `app_metadata.role == "admin"` or `is_admin`).
- **Config**: `core/config.py` — `Settings` (Pydantic BaseSettings); reads root `.env` at repo level. Fails fast on missing vars.

### Scraper (`scraper/`)

- **Entry**: `worker.py` — Celery app, imports all task modules, validates proxy pool on worker startup.
- **Beat schedule**: `schedules/beat_schedule.py` — daily scrape + weekly velocity, times read from `RuntimeSettings`.
- **Task modules** (`tasks/`): `run_daily_scrape` orchestrates the full workflow using Celery `chord`; individual platform tasks (`scrape_rumble`, `scrape_bitchute`, `scrape_substack`) are dispatched with staggered `countdown` delays.
- **Runtime settings**: `core/runtime_settings.py` — frozen dataclass with all tunable operational parameters (slot limits, retry delays, CF bypass timing, discovery limits). Defaults are the live values; changes require a code deploy (no DB-driven hot-reload currently wired to the dataclass).
- **Browser layer** (`core/browser.py`): Camoufox (stealth Playwright) + proxy injection. Heavy media URLs are blocked. CF challenge detection and two-cycle retry live in `core/cf_bypass.py`.
- **Proxy system** (`core/proxy.py`): Redis-backed health scoring and quarantine; residential proxies for Rumble/BitChute.
- **Discovery pipeline**: `tasks/discover_channels.py` uses Serper (Google Search API) for keyword + seed expansion → `channels` table upsert. `tasks/find_lookalikes.py` is separate from discovery.

### Frontend (`frontend/`)

- **Framework**: Next.js 16 (App Router) + TypeScript + Tailwind CSS v4.
- **Route groups**: `(auth)/login` (public), `(dashboard)/*` (protected — channels, admin, lookalike pages).
- **API calls**: All FastAPI calls go through `src/lib/api/backend.ts` (typed client, Bearer token). Supabase direct queries go through `src/lib/supabase/`.
- **Auth**: `src/hooks/useAuth.ts` manages Supabase session; JWT is forwarded as Bearer to backend.
- **Env**: `next.config.ts` reads the root `.env` file and re-exports `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY`.

### Database

- Supabase (PostgreSQL). Migrations are in `database/migrations/` (numbered `NNN_*.sql`). Frontend has a parallel `frontend/supabase/migrations/` directory — keep both in sync.
- Primary table: `channels` — unified table for all platforms (Rumble, BitChute, Substack). Earlier `channel_discovery` view is retired; use `channels` directly.
- Admin control-plane tables (from migrations 005, 009, 010): runtime operational settings and competitor definitions are stored in Supabase and read at runtime by both backend and scraper.

## Deployment

| Service | Platform | Notes |
|---------|----------|-------|
| Frontend | Vercel | Auto-deploys from `main` |
| Backend API | Render | Docker, defined in `render.yaml` |
| Celery Beat | Render | Docker worker, defined in `render.yaml` |
| Celery Workers | Render | Per-queue workers (discovery, gate0, classify, rumble, substack), defined in `render.yaml` |
| Redis | Upstash | Managed Redis; `REDIS_URL` uses `rediss://` (TLS) |
| Database | Supabase | Managed PostgreSQL |

`render.yaml` defines all Render services and the `scraper-secrets` env var group (shared across backend + all workers).

## Key Conventions

- **Python**: PEP 8, snake_case, explicit typing. `get_logger(__name__)` from `core/logging.py`.
- **TypeScript**: 2-space indent, PascalCase components, camelCase hooks/utilities.
- Task names in `backend/workers/tasks.py` must match the string in `@celery_app.task(name=...)` decorators in `scraper/tasks/`.
- The backend dispatches scraper work via `celery.send_task(TASK_CONSTANT, args=[...])` — never by importing scraper modules.
- Supabase service-role key is server-only (backend + scraper). Never expose it in frontend code.