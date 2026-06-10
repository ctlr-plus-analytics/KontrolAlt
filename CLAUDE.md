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

<!-- rtk-instructions v2 -->
# RTK (Rust Token Killer) - Token-Optimized Commands

## Golden Rule

**Always prefix commands with `rtk`**. If RTK has a dedicated filter, it uses it. If not, it passes through unchanged. This means RTK is always safe to use.

**Important**: Even in command chains with `&&`, use `rtk`:
```bash
# ❌ Wrong
git add . && git commit -m "msg" && git push

# ✅ Correct
rtk git add . && rtk git commit -m "msg" && rtk git push
```

## RTK Commands by Workflow

### Build & Compile (80-90% savings)
```bash
rtk cargo build         # Cargo build output
rtk cargo check         # Cargo check output
rtk cargo clippy        # Clippy warnings grouped by file (80%)
rtk tsc                 # TypeScript errors grouped by file/code (83%)
rtk lint                # ESLint/Biome violations grouped (84%)
rtk prettier --check    # Files needing format only (70%)
rtk next build          # Next.js build with route metrics (87%)
```

### Test (60-99% savings)
```bash
rtk cargo test          # Cargo test failures only (90%)
rtk go test             # Go test failures only (90%)
rtk jest                # Jest failures only (99.5%)
rtk vitest              # Vitest failures only (99.5%)
rtk playwright test     # Playwright failures only (94%)
rtk pytest              # Python test failures only (90%)
rtk rake test           # Ruby test failures only (90%)
rtk rspec               # RSpec test failures only (60%)
rtk test <cmd>          # Generic test wrapper - failures only
```

### Git (59-80% savings)
```bash
rtk git status          # Compact status
rtk git log             # Compact log (works with all git flags)
rtk git diff            # Compact diff (80%)
rtk git show            # Compact show (80%)
rtk git add             # Ultra-compact confirmations (59%)
rtk git commit          # Ultra-compact confirmations (59%)
rtk git push            # Ultra-compact confirmations
rtk git pull            # Ultra-compact confirmations
rtk git branch          # Compact branch list
rtk git fetch           # Compact fetch
rtk git stash           # Compact stash
rtk git worktree        # Compact worktree
```

Note: Git passthrough works for ALL subcommands, even those not explicitly listed.

### GitHub (26-87% savings)
```bash
rtk gh pr view <num>    # Compact PR view (87%)
rtk gh pr checks        # Compact PR checks (79%)
rtk gh run list         # Compact workflow runs (82%)
rtk gh issue list       # Compact issue list (80%)
rtk gh api              # Compact API responses (26%)
```

### JavaScript/TypeScript Tooling (70-90% savings)
```bash
rtk pnpm list           # Compact dependency tree (70%)
rtk pnpm outdated       # Compact outdated packages (80%)
rtk pnpm install        # Compact install output (90%)
rtk npm run <script>    # Compact npm script output
rtk npx <cmd>           # Compact npx command output
rtk prisma              # Prisma without ASCII art (88%)
```

### Files & Search (60-75% savings)
```bash
rtk ls <path>           # Tree format, compact (65%)
rtk read <file>         # Code reading with filtering (60%)
rtk grep <pattern>      # Search grouped by file (75%). Format flags (-c, -l, -L, -o, -Z) run raw.
rtk find <pattern>      # Find grouped by directory (70%)
```

### Analysis & Debug (70-90% savings)
```bash
rtk err <cmd>           # Filter errors only from any command
rtk log <file>          # Deduplicated logs with counts
rtk json <file>         # JSON structure without values
rtk deps                # Dependency overview
rtk env                 # Environment variables compact
rtk summary <cmd>       # Smart summary of command output
rtk diff                # Ultra-compact diffs
```

### Infrastructure (85% savings)
```bash
rtk docker ps           # Compact container list
rtk docker images       # Compact image list
rtk docker logs <c>     # Deduplicated logs
rtk kubectl get         # Compact resource list
rtk kubectl logs        # Deduplicated pod logs
```

### Network (65-70% savings)
```bash
rtk curl <url>          # Compact HTTP responses (70%)
rtk wget <url>          # Compact download output (65%)
```

### Meta Commands
```bash
rtk gain                # View token savings statistics
rtk gain --history      # View command history with savings
rtk discover            # Analyze Claude Code sessions for missed RTK usage
rtk proxy <cmd>         # Run command without filtering (for debugging)
rtk init                # Add RTK instructions to CLAUDE.md
rtk init --global       # Add RTK to ~/.claude/CLAUDE.md
```

## Token Savings Overview

| Category | Commands | Typical Savings |
|----------|----------|-----------------|
| Tests | vitest, playwright, cargo test | 90-99% |
| Build | next, tsc, lint, prettier | 70-87% |
| Git | status, log, diff, add, commit | 59-80% |
| GitHub | gh pr, gh run, gh issue | 26-87% |
| Package Managers | pnpm, npm, npx | 70-90% |
| Files | ls, read, grep, find | 60-75% |
| Infrastructure | docker, kubectl | 85% |
| Network | curl, wget | 65-70% |

Overall average: **60-90% token reduction** on common development operations.
<!-- /rtk-instructions -->