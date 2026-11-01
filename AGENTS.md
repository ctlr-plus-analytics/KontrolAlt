# Repository Guidelines

## Project Overview
KontrolAlt discovers and tracks Rumble channels and Substack publications, with a dashboard for channel research, lookalike matching, intake, and administration. Supabase provides authentication and PostgreSQL storage; Celery workers handle discovery, scraping, classification, and Gate 0 checks.

## Architecture & Data Flow
- **Web → API → database:** Next.js App Router pages obtain Supabase session tokens and call FastAPI through `frontend/src/lib/api/backend.ts`. The dashboard fetches initial data server-side; client hooks handle subsequent queries and refreshes. Supabase Realtime triggers refetches, with polling as a fallback.
- **API → queue → scraper → database:** backend services dispatch named Celery tasks through Redis. Dedicated `discovery`, `rumble`, `substack`, `classify`, and `gate0` queues run platform scrapers and processing tasks. Scrapes upsert `channels`, append `channel_snapshots`, and record `scrape_logs`; velocity calculations derive channel metrics from snapshots.
- **Boundaries:** FastAPI routes validate/authenticate requests, Pydantic models define contracts, and service modules own business/database operations. Platform scrapers extend `scraper/scrapers/base.py`; Celery tasks orchestrate them.
- SQL changes belong in numbered `database/migrations/` files. `channels` is the canonical channel table; `channel_url` is its uniqueness key. The checked-in migrations are incremental, not a complete baseline schema.
- Beat is deployed, but `scraper/schedules/beat_schedule.py` currently defines an empty schedule. Do not assume automatic daily/weekly scraping; admin triggers are separate.

## Key Directories
- `frontend/src/app/`, `components/`, `hooks/`, `lib/`: routes, feature UI, client state, API/auth helpers.
- `backend/api/v1/`, `models/`, `services/`, `core/`: HTTP contracts, business logic, settings/auth/shared clients.
- `scraper/tasks/`, `scrapers/`, `core/`, `utils/`: job orchestration, platform parsing, browser/proxy infrastructure, extraction helpers.
- `shared/`: cross-service Python matching logic and a separate TypeScript type set.
- `backend/tests/`, `scraper/tests/`: isolated Python suites. `scraper/scratch/` contains experiments, not the standard QA suite.

## Development Commands
Run these from the indicated directory; service commands require configured environment variables.

| Directory | Command | Purpose |
| --- | --- | --- |
| `frontend/` | `npm ci` | Install locked frontend dependencies |
| `frontend/` | `npm run dev` | Next.js development server |
| `frontend/` | `npm run build` / `npm run start` | Production build / serve built app |
| `frontend/` | `npm run lint` | ESLint |
| `backend/` | `python -m pip install -r requirements.txt` | Install API dependencies in its virtualenv |
| `backend/` | `uvicorn main:app --host 0.0.0.0 --port 8000 --reload` | Run API locally |
| `backend/` | `python -m pytest tests/` | Backend unit suite |
| `scraper/` | `python -m pip install -r requirements.txt` | Install worker dependencies in its virtualenv |
| `scraper/` | `python -m playwright install --with-deps chromium` | Install browser/runtime dependencies |
| `scraper/` | `celery -A worker.celery_app worker --loglevel=info -Q rumble --concurrency=2` | Run a queue-specific worker; choose the required queue |
| `scraper/` | `python -m pytest tests/` | Scraper unit suite; requires `pytest-asyncio` separately |
| repository root | `docker compose up --build` | Start configured Redis, API, workers, and Beat; frontend runs separately |

Manual preview: from `scraper/`, `python scrape_leaderboard.py --dry-run` fetches live pages without database upserts. Import utilities such as `scraper/import_channel_names_serper.py` default to report-only mode; `--write` enables database changes. Even dry runs use network services and write reports. Pass explicit input/output paths to importers because defaults depend on the working directory.

## Code Conventions & Common Patterns
- Follow surrounding formatting; no standalone formatter or Python lint configuration is declared. Frontend uses strict TypeScript, Next Core Web Vitals/TypeScript ESLint presets, and Tailwind CSS v4.
- Python modules/functions/fields use `snake_case`; classes/models and React components use `PascalCase`; React hooks use `useX`. Frontend imports use `@/` for `src/`.
- Centralize frontend HTTP calls in `frontend/src/lib/api/backend.ts`; it attaches bearer tokens, normalizes wire fields, and raises `ApiError` with status. Database/backend `gate0_*` fields map to UI `affiliation_*` fields here. Frontend imports local `frontend/src/types/index.ts`, not `shared/types/index.ts`; update actual consumers when changing contracts.
- Keep dashboard query state in existing hooks/components. `useChannels` debounces filters, guards against stale responses, and preserves visible data on background-refresh failures. Dashboard filters/page use `sessionStorage`; tour progress uses `localStorage`.
- Backend authentication/authorization uses FastAPI `Depends` with `get_current_user` / `require_admin_user`. Services import configured client singletons; there is no general dependency-injection container. Global API errors use `{error, detail, timestamp}`; services log/wrap database failures as `SupabaseError`.
- Backend `async` functions can still contain synchronous Supabase `.execute()` and Celery dispatch calls. Worker tasks bridge async scraper coroutines through `worker_pool.run`; preserve existing browser lifecycle and failure/retry policies in `scraper/tasks/scrape_failure_policy.py` and `scrape_helpers.py`.
- Celery task names and queues are cross-service string contracts. Keep `backend/workers/tasks.py`, `scraper/worker.py`, and `scraper/tasks/task_queues.py` aligned.

## Important Files
- `backend/main.py`: FastAPI entrypoint, middleware, exception handlers; mounts `/api/v1` and `/api/backend/api/v1`.
- `frontend/src/app/(dashboard)/page.tsx`, `frontend/src/proxy.ts`: initial dashboard fetch and request-level login enforcement.
- `backend/services/channel_service.py`, `channel_intake_service.py`, `lookalike_service.py`: channel queries, intake/deduplication, synchronous lookalike matching.
- `scraper/worker.py`, `scraper/tasks/run_daily_scrape.py`, `scraper/scrapers/base.py`: worker entrypoint, pipeline orchestration, persistence contract.
- `backend/core/config.py`, `scraper/core/config.py`, `frontend/next.config.ts`: environment loading and validation.
- `docker-compose.yml`, `render.yaml`, `vercel.json`: local service topology, hosted workers/API, frontend/backend routing. Docker builds use repository-root context to include `shared/`.

## Runtime/Tooling Preferences
- Use **npm and Node.js >=20.9.0** for the frontend (Next.js 16 / React 19, committed `frontend/package-lock.json`). Bun is not configured.
- Match **Python 3.11**, as used by both Dockerfiles. Use separate backend/scraper virtualenvs: their Supabase/httpx dependency requirements differ.
- Settings load repository-root `.env` and validate at import. Backend requires `SUPABASE_URL`, `SUPABASE_ANON_KEY`, and `SUPABASE_SERVICE_ROLE_KEY`; scraper additionally requires `REDIS_URL`, a nonempty `PROXY_LIST`, and `SERP_API_KEY`. Keep credentials out of source and logs.
- Frontend supports `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, and `NEXT_PUBLIC_API_URL`; Supabase values can fall back to root settings. Never expose service-role credentials to browser code. The API client defaults to `http://localhost:8000` when no API URL is supplied.
- `backend/.env.example` points to a root example that is not present; use the settings definitions as the authoritative variable list.

## Testing & QA
- Both Python suites use pytest, monkeypatching, fake Supabase/Celery clients, and mocked browser pages. Extend these patterns for parsing, business rules, task transitions, and error paths without requiring live services.
- Explicitly target `tests/`. Bare pytest discovery under `scraper/` can collect live browser/network probes in `test_browser_approaches.py` and `scratch/`.
- `scraper/pytest.ini` sets `asyncio_mode = auto`, and parser tests use `@pytest.mark.asyncio`, but requirements do not declare `pytest-asyncio`; install that plugin in the test environment. Test fixtures use `os.environ.setdefault`, so exported real credentials are not overwritten.
- `frontend/src/lib/utils.test.ts` imports Vitest, but no Vitest dependency or test script is declared. There is no configured frontend test command; do not claim `npm test` works. Use the declared lint/build commands and exercise changed UI flows directly, noting setup failures rather than hiding them.
- No coverage runner, percentage threshold, or configured end-to-end suite is present. Focus regression coverage on affected behavior and boundaries; live scraper probes are manual integration diagnostics, not deterministic unit tests.
