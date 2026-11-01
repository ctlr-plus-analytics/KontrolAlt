# Repository Guidelines

## Project Overview
KontrolAlt's Next.js dashboard supports Rumble/Substack channel research, lookalike matching, intake, and administration. This guide supplements `../AGENTS.md`; use the root guide for backend, scraper, and canonical database conventions.

## Architecture & Data Flow
- Next.js App Router pages under `src/app/` mix server-side initial fetches with client feature views. `src/app/(dashboard)/page.tsx` obtains a Supabase session, fetches initial channels, and passes them to `ChannelTableView`; `useChannels` handles later queries and refreshes.
- `src/proxy.ts` enforces login at request time. Server code uses `src/lib/supabase/server.ts`; browser code uses `src/lib/supabase/client.ts` and `useAuth`. UI admin checks do not replace backend authorization.
- Route requests to FastAPI through `src/lib/api/backend.ts`, passing the session bearer token. That module owns HTTP errors (`ApiError`), filter serialization, and wire-to-UI normalization (including `gate0_*` → `affiliation_*`). Update `src/types/index.ts` and actual consumers when changing contracts; do not add a second HTTP client convention.
- Supabase Realtime signals refetches; `useChannels` also polls, debounces filters, rejects stale responses, and preserves visible rows on background errors. Keep feature state in its owning view/hook rather than a new global store.

## Key Directories
- `src/app/`: App Router routes, layouts, auth/dashboard groups, and health handler.
- `src/components/`: feature UI (`channels/`, `filters/`, `lookalike/`, `admin/`, `tour/`, `layout/`, `ui/`).
- `src/hooks/`: client auth, channel queries/search, Realtime refresh, velocity, and tour behavior.
- `src/lib/api/`, `src/lib/supabase/`, `src/types/`: backend boundary, Supabase clients, and frontend contracts.
- `supabase/migrations/`: checked-in frontend copies are not authoritative; put SQL changes in `../database/migrations/` and reconcile consumers with those numbered migrations.

## Development Commands
| Command (from `frontend/`) | Purpose |
| --- | --- |
| `npm ci` | Install committed lockfile dependencies |
| `npm run dev` | Start Next.js development server |
| `npm run build` | Build production app |
| `npm run start` | Serve a previously built app |
| `npm run lint` | Run ESLint |

## Code Conventions & Common Patterns
- Strict TypeScript with `@/` imports rooted at `src/`; components/types use `PascalCase`, hooks `useX`, functions `camelCase`, and API/domain fields generally `snake_case`. Follow existing Tailwind CSS v4 styles in `src/app/globals.css`.
- `ChannelTableView` owns dashboard filters, pagination, and `sessionStorage` restoration; `FilterSidebar` defines defaults. Tour progress uses `localStorage`. Preserve `useChannels`' debouncing, stale-request guard, Realtime/poll fallback, and 401 refresh behavior when changing queries.
- Handle errors at the feature boundary: API helpers throw `ApiError`; client actions typically surface inline messages, while server dashboard/detail reads have their own fallback states. Async effects should prevent obsolete requests from replacing current data.
- Supabase clients are split by execution context rather than injected through a general container. Never expose service-role credentials in browser code or `NEXT_PUBLIC_*` variables.

## Important Files
- `src/app/layout.tsx`, `src/app/(dashboard)/page.tsx`, `src/proxy.ts`: root composition, initial dashboard data, and login gate.
- `src/components/channels/ChannelTableView.tsx`, `src/hooks/useChannels.ts`, `src/hooks/useRealtimeRefresh.ts`: list state and refresh policy.
- `src/lib/api/backend.ts`, `src/types/index.ts`, `src/lib/supabase/{client,server,env}.ts`: service contracts and auth clients.
- `next.config.ts`, `tsconfig.json`, `eslint.config.mjs`, `postcss.config.mjs`, `package.json`: environment, compiler, lint, CSS, and command configuration.

## Runtime/Tooling Preferences
- Use Node.js >=20.9.0 and npm with `package-lock.json` (Next.js 16, React 19); Bun is not configured. `next.config.ts` additionally reads the repository-root `.env` and maps public Supabase values. Set `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, and the target `NEXT_PUBLIC_API_URL` deliberately: config can inject an empty API URL, so the client's localhost fallback may not apply. Backend client paths append `/api/v1`; keep deployment routing and API origin aligned.
- Tailwind v4 uses `@tailwindcss/postcss`; ESLint uses Next Core Web Vitals/TypeScript presets. Do not commit generated `.next/` or environment secrets.

## Testing & QA
- `npm run lint` and `npm run build` are the declared checks. No test, coverage, typecheck, or E2E script is configured. `src/lib/utils.test.ts` imports Vitest, but Vitest is not declared; do not claim `npm test` runs it.
- Exercise changed UI flows directly in a running app; check authenticated and relevant error/refresh states. Add deterministic behavior-focused tests only with an explicitly configured runner, and avoid live-service dependencies for unit tests.
