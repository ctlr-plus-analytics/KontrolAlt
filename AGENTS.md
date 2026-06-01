# Repository Guidelines

## Project Structure & Module Organization
- `frontend/`: Next.js 16 + TypeScript dashboard (`src/app`, `src/components`, `src/hooks`, `src/lib`).
- `backend/`: FastAPI API (`api/v1` routes, `services` business logic, `models` data contracts, `core` config/auth/logging).
- `scraper/`: Celery worker/beat tasks, platform scrapers, and parsing utilities.
- `database/migrations/` and `frontend/supabase/migrations/`: SQL schema and operational migrations.
- `shared/types/`: cross-project TypeScript types.
- Keep feature logic in the owning service/module; avoid route-handler bloat.

## Build, Test, and Development Commands
- `docker compose up --build`: starts Redis, backend API, Celery worker, and beat.
- `cd frontend && npm install && npm run dev`: runs frontend on `http://localhost:3000`.
- `cd frontend && npm run build`: production build check.
- `cd frontend && npm run lint`: ESLint for frontend TS/React code.
- `cd backend && pytest`: runs backend test suite.
- `cd scraper && pytest`: runs scraper/parser/task tests.

## Coding Style & Naming Conventions
- Python: PEP 8, 4-space indentation, snake_case for functions/files, explicit typing where practical.
- TypeScript/React: 2-space indentation, PascalCase components (e.g., `ChannelTable.tsx`), camelCase hooks/utilities (e.g., `useChannels.ts`).
- Keep API handlers thin; place business rules in `backend/services/`.
- Reuse centralized clients/helpers (`frontend/src/lib/api/backend.ts`, Supabase helpers) instead of ad hoc calls.

## Testing Guidelines
- Framework: `pytest` (backend and scraper).
- Test files follow `test_*.py` naming and mirror module scope (examples: `test_channel_service.py`, `test_discover_channels.py`).
- Add or update tests with every behavior change, especially for scraping parsers, task orchestration, and API services.

## Commit & Pull Request Guidelines
- Follow concise, imperative commit subjects as seen in history (e.g., `Add unified channel discovery workflow`).
- Keep commits focused by subsystem (`frontend`, `backend`, `scraper`, `migrations`).
- PRs should include:
  - clear summary of behavior changes,
  - linked issue/task,
  - test evidence (`pytest`, `npm run lint`, build output),
  - screenshots for UI-affecting frontend changes.

## Security & Configuration Tips
- Store secrets in `.env`; never commit credentials.
- Treat Supabase service-role keys as server-only (`backend`/`scraper`), never expose them in frontend code.
- Validate migration order and run migrations consistently across both migration directories before release.

@RTK.md
