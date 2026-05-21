
# GEMINI.md — Kontrol_Alt Intelligence & Discovery Engine

## What This Project Is

Kontrol_Alt is a creator intelligence platform that scrapes alternative media platforms (Rumble and BitChute), computes growth velocity metrics, runs automated compliance checks (Gate 0), infers audience demographics via keyword matching, and presents findings on a read-only dashboard for a talent hunting team.

This is not a CRM. There is no pipeline, no Kanban, no email sending. It is strictly a research and discovery tool.

---

## Monorepo Structure

```
kontrol-alt/
├── frontend/          # Next.js 14, TypeScript, App Router
├── backend/           # Python FastAPI
├── scraper/           # Python, Patchright, Celery worker
├── shared/            # Shared TypeScript types
├── database/
│   └── migrations/
│       └── 001_initial_schema.sql
├── docker-compose.yml
├── .env.example
└── README.md
```

Never mix code between services. The frontend never imports from backend/ or scraper/. The backend never imports from scraper/ directly — it communicates via Celery task dispatch. The scraper never calls the FastAPI backend — it writes directly to Supabase.

---

## Tech Stack

| Layer | Technology | Version |
|---|---|---|
| Frontend | Next.js + TypeScript | 14 |
| Auth | Supabase Auth + @supabase/ssr | latest |
| Backend | Python + FastAPI | 3.11 / 0.111+ |
| Database | Supabase (PostgreSQL) | cloud-hosted |
| Scraper | Python + Patchright | 3.11 |
| Job Queue | Celery + Redis | 5.x / 7-alpine |
| Gate 0 | SERPER API |
| Proxies | Residential proxies (BrightData or Oxylabs) | — |
| Styling | Tailwind CSS | 3.x |

---

## Environment Variables

All env vars live in a single `.env` at the repo root. Docker Compose loads them automatically. For local development copy `.env.example` to `.env` and fill in values.

Never hardcode credentials. Never commit `.env`. Never log env var values.

```
# Supabase
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=

# Serper
SERP_API_KEY=

# Redis
REDIS_URL=redis://localhost:6379/0

# Proxies (comma-separated)
PROXY_LIST=http://user:pass@host1:port,http://user:pass@host2:port

# Frontend
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
NEXT_PUBLIC_API_URL=http://localhost:8000

# Backend
FRONTEND_ORIGIN=http://localhost:3000
```

All Python services load env vars through `core/config.py` using Pydantic `BaseSettings`. The app must fail fast on startup if any required variable is missing — never silently fall back to None.

---

## Dev Commands

### Frontend
```bash
cd frontend
npm install
npm run dev          # http://localhost:3000
npm run build
npm run lint
npm run type-check   # tsc --noEmit
```

### Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Scraper Worker
```bash
cd scraper
source venv/bin/activate
pip install -r requirements.txt
celery -A worker worker --loglevel=info
```

### Celery Beat Scheduler
```bash
cd scraper
celery -A worker beat --loglevel=info --schedule=/tmp/celerybeat-schedule
```

### Docker (Redis + Backend + Worker + Beat)
```bash
docker-compose up --build
```

Frontend always runs locally, never in Docker.

### Database Migration
Apply `database/migrations/001_initial_schema.sql` directly in the Supabase SQL editor or via the Supabase CLI:
```bash
supabase db push
```

---

## Frontend Architecture

### Routing (App Router)
```
app/
├── (auth)/login/page.tsx          # Public — login form
├── (dashboard)/page.tsx           # Protected — channel discovery table
├── (dashboard)/lookalike/page.tsx # Protected — lookalike results
├── (dashboard)/channel/[id]/page.tsx
└── api/health/route.ts
```

All routes inside `(dashboard)/` are protected by `middleware.ts`. If no Supabase session exists the user is redirected to `/login`.

### Component Rules
- All components in `app/` are Server Components by default
- Mark client components explicitly with `"use client"` at the top of the file
- Never fetch data inside a Client Component — pass data as props from a Server Component or use a custom hook backed by Supabase client
- One component per file. File name matches the exported component name exactly

### Supabase Clients
- `lib/supabase/server.ts` — used in Server Components and API routes. Uses `createServerClient` from `@supabase/ssr`
- `lib/supabase/client.ts` — used in Client Components. Uses `createBrowserClient` from `@supabase/ssr`
- Never import the server client in a Client Component. Never import the browser client in a Server Component

### Types
All shared TypeScript interfaces live in `types/index.ts`. Never define inline types for domain objects. Import from `types/index.ts` everywhere.

Core interfaces:
```typescript
Channel
ChannelSnapshot
VelocityScore
Gate0Result
ScrapeLog
SeedCreator
LookalikeMatch
CommentTier        // "active" | "sweet_spot" | "whale"
Gate0Status        // "unchecked" | "pending" | "clean" | "dirty"
ScrapeStatus       // "success" | "blocked" | "retry" | "failed"
MatchType          // "guest_appearance" | "niche_overlap"
Platform           // "rumble" | "bitchute"
```

### Styling
Tailwind only. No inline styles. No CSS modules. Custom palette is configured in `tailwind.config.ts`:
```
dark-navy:   #1A1A2E
gold:        #C9A84C
off-white:   #F7F4EE
mid-gray:    #2E2E2E
muted:       #6B6B6B
```

Use semantic color names (`text-gold`, `bg-dark-navy`) not raw hex values in JSX.

### Backend API Calls from Frontend
All calls to FastAPI go through `lib/api/backend.ts`. Never use raw `fetch` with the API URL in a component. The wrapper handles the base URL, auth headers, and error parsing.

---

## Backend Architecture

### Route Structure
All routes are mounted under `/api/v1/`. The router is assembled in `api/v1/router.py` and included in `main.py`.

```
GET  /health
GET  /api/v1/channels
GET  /api/v1/channels/{id}
GET  /api/v1/velocity/{channel_id}
POST /api/v1/gate0/check/{channel_id}
POST /api/v1/lookalike/search
GET  /api/v1/lookalike/results
POST /api/v1/scraper/trigger          # admin only
```

### Auth Dependency
Every route except `/health` must declare the auth dependency:
```python
from core.security import get_current_user

@router.get("/channels")
async def get_channels(user=Depends(get_current_user)):
    ...
```

`get_current_user` in `core/security.py` verifies the Supabase JWT from the `Authorization: Bearer <token>` header. It raises HTTP 401 if the token is missing or invalid. Never skip this dependency on protected routes.

### Service Layer
Route handlers must not contain business logic. They call service functions and return results. All database queries live in service files under `services/`. Route handlers stay thin:
```python
@router.get("/channels", response_model=list[ChannelResponse])
async def get_channels(user=Depends(get_current_user)):
    return await channel_service.get_all_channels()
```

### Pydantic Models
All request and response bodies use Pydantic models from `models/`. Never use raw dicts as response types. Every model field must have an explicit type annotation.

### Error Handling
A global exception handler in `main.py` catches all unhandled exceptions and returns:
```json
{ "error": "message", "detail": "...", "timestamp": "..." }
```
Never let FastAPI return its default unstructured error responses.

### Supabase Client
The Supabase client is a singleton initialized in `core/supabase.py`. Use `SUPABASE_SERVICE_ROLE_KEY` in the backend and scraper (bypasses RLS for server-side writes). Use `SUPABASE_ANON_KEY` only on the frontend.

---

## Scraper Architecture

### How Scraping Works
1. Celery Beat triggers a daily task at 2am UTC
2. The task fetches all active channel URLs from Supabase
3. It dispatches one Celery task per channel (scrape_rumble or scrape_bitchute)
4. Each task launches a Patchright browser session with a random proxy and scrapes the channel
5. Results are written directly to Supabase — channels table and channel_snapshots table
6. The scrape attempt is logged to scrape_logs regardless of success or failure
7. After all channel scrapes complete a separate task computes velocity scores for each channel

### Base Scraper Class
All scrapers extend `scrapers/base.py`:
```python
class BaseScraper(ABC):
    @abstractmethod
    async def scrape(self, channel_url: str) -> dict: ...
    async def save_to_supabase(self, data: dict) -> None: ...
    async def log_scrape_attempt(self, channel_id, status, error=None) -> None: ...
```

Never write Supabase logic directly inside a scraper class. Always call `self.save_to_supabase()` and `self.log_scrape_attempt()`.

### Browser Configuration
Patchright is launched in `core/browser.py`. Every session must:
- Run in headless mode
- Use stealth flags (navigator.webdriver = false, no automation user agent)
- Load a randomly selected proxy from `core/proxy.py`
- Use a randomized user agent
- Apply a random delay of 2 to 8 seconds between page navigations via `human_delay()`

Never reuse a browser session across different channels. One channel = one browser context = one proxy session.

### Proxy Rotation
`core/proxy.py` loads the `PROXY_LIST` env variable (comma-separated proxy strings) and exposes:
```python
def get_random_proxy() -> str: ...
```

If `PROXY_LIST` is empty the scraper must raise a configuration error on startup, not silently run without proxies.

### Retry Logic
Each Celery scrape task retries up to 3 times with exponential backoff on failure. After 3 failures the channel is logged as `status="failed"` in `scrape_logs`. The channel record is not deleted. It will be retried in the next daily run.

### Keyword Matcher
`utils/keyword_matcher.py` defines the full taxonomy:
```python
KEYWORD_TAXONOMY = {
    "gold_investment":       [...],
    "retirement":            [...],
    "conservative_finance":  [...],
    "health_age_related":    [...],
}

def match_keywords(text: str) -> list[str]: ...
def is_55_plus_audience(matched_categories: list[str]) -> bool: ...
    # Returns True if len(matched_categories) >= 2
```

This function runs on the concatenation of: channel name + description + last 20 video titles. Never run it on each field separately.

### Contact Extractor
`utils/contact_extractor.py` uses regex to extract:
- Email addresses
- URLs containing "linktree", "beacons", "bio.link", "campsite"
- Any outbound links from the channel bio and description

Returns a flat `list[str]`. The caller stores this in `channels.contact_info` (text[]).

---

## Database Rules

### Schema Conventions
- All primary keys: `uuid` with default `gen_random_uuid()`
- All timestamps: `timestamptz` with default `now()`
- All foreign keys: `ON DELETE CASCADE`
- Indexes on `channel_id` for every table that references channels
- Index on `scraped_at` for `channel_snapshots`
- Row Level Security (RLS) enabled on every table

### RLS Policies
Authenticated users can SELECT, INSERT, UPDATE on all tables. No DELETE for anyone except service_role. The backend and scraper use the service role key so they bypass RLS. The frontend uses the anon key and is subject to RLS.

### Velocity Computation
Velocity is computed by the Celery task in `tasks/compute_velocity.py` after each daily scrape. It queries `channel_snapshots` for records 30 and 90 days prior and computes:

```
view_velocity_30d  = ((current_avg_views - views_30d) / views_30d) * 100
view_velocity_90d  = ((current_avg_views - views_90d) / views_90d) * 100
comment_velocity_30d = ((current_avg_comments - comments_30d) / comments_30d) * 100
comment_velocity_90d = ((current_avg_comments - comments_90d) / comments_90d) * 100
```

If no snapshot exists 30 or 90 days prior the field is stored as `null`. The frontend displays `null` velocity as "N/A — building history". Never display 0 or a misleading value for missing history.

### Comment Tier Assignment
Assigned on every scrape based on `avg_comments`:
```
>= 10 and < 20  → "active"
>= 20 and <= 100 → "sweet_spot"
> 100            → "whale"
< 10             → null (excluded from dashboard by default)
```

---

## Gate 0 Logic

Gate 0 determines whether a creator has an existing relationship with a competitor brand.

### Two-Part Check
**Part 1 — Serper Search:**
Query: `"{channel_name}" "gold IRA"` via Serper Search API.
Scan top 10 results for competitor brand names: Noble Gold, Birch Gold, Patriot Gold, Kirk Elliot.

**Part 2 — Description Scan:**
Scan `channels.contact_info` and the raw description text for any URL or mention of competitor brand domains.

If either check finds a hit the channel is marked `gate0_status = "dirty"` and a `gate0_results` row is inserted with the flagged brand and source URL.

### API Usage Policy
Serper queries are currently unrestricted for this project phase. Gate 0 checks should run whenever requested by discovery/scrape workflows without quota-based throttling or priority gating.

The `gate0_checked_at` field remains available for observability and scheduling metadata, but it should not block or defer checks due to quota concerns.

---

## Lookalike Mapping

Users input up to 3 seed creator names via the dashboard. The system scans for lookalike channels using two signals only:

**Guest Appearance Signal:**
Scan `video_titles` text of all channels in the database for a case-insensitive mention of the seed creator name. Match type stored as `"guest_appearance"`.

**Niche Tag Overlap:**
Find all channels that share 2 or more `niche_tags` array values with the seed creator channel. Match type stored as `"niche_overlap"`.

There is no overlapping audience detection. These platforms expose no shared subscriber data. Do not attempt to build it or approximate it with any other signal. It is out of scope.

---

## Dashboard Features

The dashboard is read-only. Hunters view data, they do not modify it from the frontend.

### Channel Discovery Table
Columns: name, platform, subscriber count, avg views, avg comments, comment tier badge, Gate 0 badge, 55+ badge, view velocity 30d, view velocity 90d, last active date, posting cadence.

Default sort: view velocity 30d descending (fastest growing first).

### Filters
Platform, comment tier, Gate 0 status, 55+ tag, niche tag, last active date range. All filters are applied server-side via Supabase query parameters. Never filter a full dataset on the client.

### Badges
- Gate 0 Clean: green badge labeled "Clean Lead"
- Gate 0 Dirty: red badge labeled "Brand Risk"
- Gate 0 Pending: yellow badge labeled "Checking..."
- Gate 0 Unchecked: gray badge labeled "Not Checked"
- 55+ Audience: gold badge labeled "55+ Signal"
- Comment tiers: gray (active), blue (sweet spot), purple (whale)

### Velocity Indicators
Color-coded percentage with directional arrow. Green + upward arrow for positive velocity. Red + downward arrow for negative. Gray dash for null (no history yet).

---

## What Not To Build

These are explicitly out of scope for this MVP. Do not add them even if they seem useful:

- CRM features of any kind
- Pipeline or Kanban views
- Email sending or outreach tools
- YouTube or Instagram scraping
- Overlapping audience detection
- CSV or PDF export (unless client explicitly requests it)
- Mobile responsive layout
- Real-time WebSocket updates
- Any uptime monitoring or alerting

---

## Code Quality Rules

### Python
- Type hints on every function signature, no exceptions
- Pydantic models for all data that crosses a service boundary
- Async functions everywhere in FastAPI and Patchright scraper
- No bare `except:` clauses — always catch specific exception types
- Never use `print()` for logging — use Python `logging` module

### TypeScript
- No use of `any` anywhere
- Explicit return types on all functions
- Interfaces over type aliases for object shapes
- `const` by default, `let` only when reassignment is required
- No default exports from component files — named exports only

### General
- One responsibility per file
- No business logic in route handlers or React page components
- All secrets in env vars, never in code
- All API calls wrapped in try/catch with structured error handling
- Never suppress an error silently — log it and propagate it

---

## Known Constraints

**Velocity data is not available on day one.** The system needs 30 to 90 days of daily snapshots before velocity scores are meaningful. Display "N/A — building history" until snapshots exist. Never show 0 or a misleading value.

**Serper quota is intentionally not enforced right now.** Run Gate 0 coverage aggressively to maximize channel expansion while this mode is active.

**Rumble and BitChute use Cloudflare bot protection.** Patchright with residential proxies is the current best bypass. Blocking is still possible. Budget 3 to 5 days in week 1 for scraper debugging and tuning. Do not block other features on scraper stability.

**BitChute has inconsistent HTML structure.** Comment counts and view counts may not be available on all channel pages. When a field cannot be extracted store it as `null`, not 0. Log the missing field in the scrape log.

**Substack and Telegram are secondary.** Only build their scrapers if both Rumble and BitChute scrapers are stable before the end of week 2. If week 2 is still being spent debugging Rumble or BitChute scrapers, drop secondary platforms without discussion.
