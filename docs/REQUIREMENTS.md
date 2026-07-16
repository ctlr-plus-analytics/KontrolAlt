# Kontrol_Alt Requirements

## 1. Purpose

Kontrol_Alt is a creator intelligence and discovery platform for talent hunters. It collects creator data from Rumble and BitChute, computes engagement and growth signals, runs Gate 0 competitor checks, infers niche and 55+ audience indicators, and presents the results in a protected dashboard.

The product is a research and discovery tool. It is not a CRM, pipeline manager, outreach system, Kanban board, email tool, export product, or general social listening platform.

## 2. Scope

### In Scope

- Authenticated dashboard for browsing discovered creator channels.
- Rumble and BitChute channel scraping.
- Daily scrape orchestration through Celery Beat and Redis.
- Channel snapshots and velocity calculation.
- Gate 0 competitor relationship checks.
- Keyword-based niche taxonomy and 55+ audience inference.
- Contact and outbound URL extraction.
- Lookalike search using guest appearance and niche overlap signals.
- Manual, bulk, and seed-resolver channel intake.
- Automated discovery expansion through known-channel links and keyword search.
- Admin-only scrape trigger.
- Structured FastAPI backend for protected APIs.
- Supabase PostgreSQL storage and Supabase Auth.

### Out of Scope

- CRM functionality.
- Outreach, email sending, campaign management, or task assignment.
- Pipeline or Kanban views.
- YouTube, Instagram, Substack, or Telegram scraping for the MVP.
- Overlapping audience detection.
- CSV/PDF export unless explicitly requested later.
- Mobile responsive requirements.
- Uptime monitoring and alerting.

## 3. Users And Roles

### Authenticated Hunter

- Can sign in with Supabase email/password authentication.
- Can access the dashboard, channel detail pages, lookalike search, and channel intake workflows.
- Can view channel, velocity, Gate 0, contact, niche, and scrape-history data.
- Can queue Gate 0 checks.
- Can submit manual, bulk, and resolved channel intake.
- Cannot delete data from the frontend.

### Admin User

- Has Supabase user metadata with `role=admin` or `is_admin=true`.
- Can call the backend scrape trigger endpoint.
- Inherits authenticated hunter capabilities.

### Service Role

- Used by backend and scraper services for server-side database reads/writes.
- Bypasses Supabase RLS.
- Can delete records if server-side maintenance workflows require it.

## 4. Functional Requirements

### 4.1 Authentication And Authorization

- The frontend must protect dashboard routes with Supabase Auth middleware.
- Unauthenticated users must be redirected to `/login`.
- Authenticated users visiting `/login` must be redirected to `/`.
- Backend routes under `/api/v1` must require a valid `Authorization: Bearer <token>` header, except `/health`.
- The backend must verify JWTs through Supabase Auth.
- Admin-only routes must validate admin metadata before executing.

### 4.2 Dashboard Navigation

- The dashboard must provide a sidebar with at least:
  - Channels
  - Lookalike
- The dashboard must provide a top bar showing the current page title and signed-in user initial.
- Users must be able to sign out from the dashboard.

### 4.3 Channel Discovery Table

- The main dashboard must display discovered channels in a paginated table.
- Table rows must include:
  - Channel name
  - Platform
  - Subscriber count
  - Average views
  - Average comments
  - Comment tier
  - 30-day view velocity
  - 90-day view velocity
  - Gate 0 status
  - 55+ signal
  - Last active date
  - Detail action
- Default sort must be `view_velocity_30d` descending.
- The table must support server-backed pagination.
- Empty states must explain when no channels match the filters.
- Null velocity values must display as `N/A - building history` or equivalent, not as `0`.

### 4.4 Channel Filtering And Search

- Users must be able to filter channels by:
  - Platform
  - Comment tier
  - Gate 0 status
  - 55+ audience flag
  - Inactive channels older than 90 days
  - Niche tag, where supported by API query parameters
  - Last active date range, where supported by API query parameters
- Users must be able to sort by:
  - Subscriber count
  - Average views
  - Average comments
  - 30-day view velocity
  - 90-day view velocity
  - Last active date
- Search must query the backend by channel name, URL, or description.
- Filters and search must be applied server-side rather than filtering a full dataset in the client.

### 4.5 Channel Detail

- Users must be able to open a channel detail page.
- The detail page must display:
  - Channel identity and platform
  - Subscriber, average view, average comment, posting cadence, and last active metrics
  - Gate 0 badge and latest Gate 0 result
  - 30-day and 90-day view/comment velocity metrics
  - Contact information and secondary URLs
  - Niche tags
  - Latest scrape logs
- Users must be able to open the original platform channel URL.
- Users must be able to manually queue a Gate 0 check from the detail page.
- Detail data should refresh when related Supabase tables change.

### 4.6 Channel Intake

- Users must be able to manually add one supported channel URL.
- Manual intake must require a selected platform and channel URL.
- Manual intake may accept notes and comma-separated tags.
- Manual intake may optionally trigger immediate scraping.
- Users must be able to bulk add supported channel URLs from newline- or comma-separated input.
- Bulk intake may optionally trigger immediate scraping.
- Users must be able to resolve up to 3 seed creator names into candidate channel URLs.
- Resolver candidates must include platform, URL, channel name, confidence, and source.
- Users must confirm resolver candidates before insertion.
- Intake must canonicalize supported Rumble and BitChute URLs.
- Intake must reject unsupported hosts, malformed URLs, and platform mismatches.
- Intake responses must summarize inserted, duplicate, and invalid records.

### 4.7 Scraping

- The scraper must support Rumble and BitChute channels.
- Each channel scrape must run in its own browser context.
- Browser sessions must use Patchright/Chromium.
- Browser sessions must use configured residential proxies.
- Browser sessions must apply stealth behavior, randomized user agents, and human-like delays.
- Scrapes must collect, when available:
  - Channel name
  - Description
  - Subscriber count
  - Last 20 video titles
  - View counts
  - Comment counts
  - Upload dates
  - External links
  - Contact information
- Scrapes must compute:
  - Median average views
  - Median average comments
  - Posting cadence
  - Last active date
  - Comment tier
  - Niche tags
  - 55+ audience flag
- Scraped channel data must be upserted by `channel_url`.
- Every successful scrape must insert a `channel_snapshots` row.
- Every scrape attempt must be logged with success, blocked, retry, or failed status.
- Missing fields must be stored as `null`, not `0`.
- Terminal page states such as 404, deleted, banned, suspended, or unavailable channels must be classified and handled without infinite retries.
- Terminal failures must deactivate affected channels.

### 4.8 Scrape Orchestration

- Celery Beat must schedule the daily scrape workflow at 2:00 UTC.
- The daily workflow must fetch active channels from Supabase.
- The workflow must dispatch platform-specific scrape tasks for supported platforms.
- Unsupported platforms must be skipped.
- The workflow must respect configured batch size, dispatch pause, max channels, retry limits, and optional daily byte budget.
- After scraping, the system must run post-scrape tasks:
  - Seed expansion discovery
  - Keyword expansion discovery
  - Discovery candidate promotion
  - Due Gate 0 queueing
  - Velocity computation

### 4.9 Retry And Failure Handling

- Rumble and BitChute scrape tasks must retry up to 3 times for retryable failures.
- Retry delays must use exponential backoff with jitter.
- Blocked/challenge errors must obey the configured per-channel block retry limit.
- Final failures must be logged.
- Failed scrape logging must create a minimal channel row when needed so failures remain observable.

### 4.10 Velocity Computation

- Velocity must be computed from `channel_snapshots`.
- The system must calculate:
  - `view_velocity_30d`
  - `view_velocity_90d`
  - `comment_velocity_30d`
  - `comment_velocity_90d`
- Velocity formula must be:
  - `((current - past) / past) * 100`
- Historical snapshots may match the target date within a plus or minus 1 day tolerance.
- Missing history, malformed values, or zero historical values must produce `null`.
- Velocity rows must be upserted by `channel_id`.
- The frontend must present null velocity as unavailable/history-building, not as zero growth.

### 4.11 Comment Tiering

- Comment tier must be assigned from average comments:
  - `active`: `>= 10` and `< 20`
  - `sweet_spot`: `>= 20` and `<= 100`
  - `whale`: `> 100`
  - `null`: `< 10` or unavailable
- Comment tier badges must use distinct visual treatments.

### 4.12 Keyword Taxonomy And 55+ Audience Signal

- The scraper must concatenate channel name, description, and recent video titles before keyword matching.
- Keyword matching must be case-insensitive substring matching.
- Matched keyword categories must be stored as `niche_tags`.
- The 55+ audience flag must be true when at least 2 keyword categories match.
- The taxonomy must include alternative media, politics, preparedness, finance, retirement, gold investment, health, faith, military, legal, culture, privacy, and related niches represented in `scraper/utils/keyword_matcher.py`.

### 4.13 Contact Extraction

- The scraper must extract email addresses from channel text.
- The scraper must extract outbound URLs from channel text and descriptions.
- Internal Rumble and BitChute URLs must be excluded from contact URLs.
- Link-in-bio URLs such as Linktree, Beacons, Bio.link, and Campsite must be identifiable.
- Extracted contacts must be deduplicated and stored as a flat string list.

### 4.14 Gate 0 Compliance

- Gate 0 must determine whether a creator has a relationship with competitor brands.
- Competitor brands/domains must include:
  - Noble Gold / `noblegold.com`
  - Birch Gold / `birchgold.com`
  - Patriot Gold / `patriotgold.com`
  - Kirk Elliot / `kirkelliot.com`
- Gate 0 must scan stored channel contact info, secondary URLs, and description for competitor references.
- If local scanning finds no competitor reference, Gate 0 must query Serper with:
  - `"<channel_name>" "gold IRA"`
- Gate 0 must inspect the top 10 organic search results.
- A competitor hit must create a dirty `gate0_results` row and set `channels.gate0_status` to `dirty`.
- No competitor hit must create a clean `gate0_results` row and set `channels.gate0_status` to `clean`.
- Manual Gate 0 checks must run regardless of previous status.
- Automatic Gate 0 checks must skip dirty channels.
- Automatic Gate 0 checks may skip recently clean channels checked within the last 7 days.
- Queueing a Gate 0 check must set channel status to `pending`.

### 4.15 Lookalike Search

- Users must be able to submit up to 3 seed creator names.
- The backend must persist seed creators per user.
- Lookalike matching must use only:
  - Guest appearance signal: seed name appears in a channel's recent video titles.
  - Niche overlap signal: seed channel shares at least 2 niche tags with another channel.
- Lookalike matches must be upserted by seed, matched channel, and match type.
- Lookalike results must include matched channel data and seed data when available.
- The frontend must show match type, match detail, Gate 0 status, 55+ signal, subscriber count, and average comments.
- Results should refresh when related Supabase tables change.
- The system must not implement overlapping audience detection.

### 4.16 Automated Discovery Expansion

- Seed expansion must scan known channel descriptions, video titles, contact info, secondary URLs, and channel URLs for supported Rumble/BitChute channel candidates.
- Keyword expansion must use Serper search queries generated from the keyword taxonomy.
- Discovery candidates must be staged before promotion.
- Staged candidates must track URL, platform, source, source reference, title, category, confidence, evidence count, status, and timestamps.
- Existing channel URLs must not be re-promoted as duplicates.
- Promotion must verify channel-shaped URLs and perform lightweight HTTP validation.
- Candidates may be rejected for invalid shape or failed HTTP verification.
- Verified candidates above the configured confidence threshold may be promoted into `channels`.

### 4.17 Backend API

- The backend must expose:
  - `GET /health`
  - `GET /api/v1/channels`
  - `GET /api/v1/channels/{channel_id}`
  - `POST /api/v1/channels/intake/manual`
  - `POST /api/v1/channels/intake/bulk`
  - `POST /api/v1/channels/intake/resolve`
  - `POST /api/v1/channels/intake/resolve/confirm`
  - `GET /api/v1/velocity/{channel_id}`
  - `POST /api/v1/gate0/check/{channel_id}`
  - `POST /api/v1/lookalike/search`
  - `GET /api/v1/lookalike/results`
  - `POST /api/v1/scraper/trigger`
- Route handlers must stay thin and delegate business logic to service modules.
- API request and response bodies must use Pydantic models.
- Backend errors must be returned in a structured JSON format with `error`, `detail`, and `timestamp`.

### 4.18 Health Checks

- The backend `/health` endpoint must report:
  - Overall status
  - Timestamp
  - Supabase connectivity
  - Redis connectivity
  - Environment
- The frontend `/api/health` route must report frontend service status and timestamp.

### 4.19 Data Storage

- Supabase PostgreSQL must store:
  - `channels`
  - `channel_snapshots`
  - `velocity_scores`
  - `gate0_results`
  - `scrape_logs`
  - `seed_creators`
  - `lookalike_matches`
  - `discovery_candidates`
- A `channel_discovery` view must join channel data with velocity and latest Gate 0 result for table queries.
- All primary keys must be UUIDs.
- Foreign keys referencing channels must cascade on delete unless explicitly defined otherwise.
- RLS must be enabled on core tables.
- Authenticated users may select, insert, and update.
- Deletes must be reserved for service role policies.

## 5. Non-Functional Requirements

### 5.1 Security

- Secrets must be loaded from environment variables, never hardcoded.
- `.env` files must not be committed.
- Backend and scraper must use Supabase service role keys only server-side.
- Frontend must use only public Supabase environment variables.
- API routes must reject missing or invalid bearer tokens.
- Admin-only endpoints must enforce admin metadata checks.
- Logs must not expose secret values.

### 5.2 Configuration

- Python services must fail fast when required environment variables are missing.
- Scraper startup must fail if `PROXY_LIST` is empty.
- Environment variables must support Supabase, Redis, Serper, proxy, frontend origin, and frontend API configuration.
- Docker Compose must run Redis, backend, worker, and beat services.
- The frontend must run locally outside Docker.

### 5.3 Reliability

- Scrape tasks must use retry policies for transient failures.
- Circuit breakers must prevent repeated platform-level failures from overwhelming proxies or target sites.
- Scrape attempts must be logged even when scraping fails before full extraction.
- Discovery and post-scrape tasks must isolate failures so one failed discovery phase does not prevent velocity scheduling.
- Missing or partial platform data must be represented as `null` and logged, not treated as zero.

### 5.4 Performance And Scalability

- Channel list APIs must be paginated.
- Channel filters must be applied in backend/Supabase queries.
- Search must be debounced in the frontend.
- Scrape dispatch must support batch sizing and pauses.
- Daily proxy byte usage must be tracked and may enforce an optional byte budget.
- Worker prefetch should be limited to avoid over-concurrency.

### 5.5 Observability

- Backend must log request method, path, status code, and duration.
- Backend must log Supabase and Redis health issues.
- Scraper must log extraction quality, failures, retries, blocked states, and transfer estimates.
- Scrape logs must retain recent operational history per channel.
- Gate 0 and lookalike task dispatches must log task IDs.

### 5.6 Maintainability

- Backend business logic must live in `services/`, not route handlers.
- Backend data contracts must live in `models/`.
- Scraper platform logic must live in scraper classes extending `BaseScraper`.
- Cross-service Celery task names must be shared through constants rather than direct imports from scraper code into backend code.
- Frontend backend calls must go through `lib/api/backend.ts`.
- Domain interfaces must be centralized in TypeScript type files.
- Code should use explicit typing and structured errors.

### 5.7 Usability

- The dashboard must be read-oriented and optimized for scanning channels.
- Badges must clearly communicate Gate 0, comment tier, and 55+ states.
- Loading, empty, and error states must be present for dashboard workflows.
- Users must be able to navigate from search results and table rows to detail pages.
- Long channel names and URLs must be truncated safely in tables and cards.

### 5.8 Data Integrity

- `channel_url` must be unique.
- Velocity scores must be unique per channel.
- Lookalike matches must be unique by seed, matched channel, and match type.
- Discovery candidates must be unique by candidate URL.
- Intake must detect duplicates before insertion.
- Upsert operations must preserve existing channel identity by URL.

### 5.9 Compatibility

- Backend and scraper require Python 3.11+.
- Redis is required for Celery broker/backend.
- Supabase is required for Auth and PostgreSQL persistence.
- Patchright/Chromium is required for scraping.
- The implemented frontend package currently uses Next.js 16, React 19, and Tailwind 4, while the project guidance references Next.js 14 and Tailwind 3. This version discrepancy should be resolved before formal release planning.

## 6. External Integrations

- Supabase Auth for user authentication.
- Supabase PostgreSQL for application data.
- Supabase Realtime for frontend refresh subscriptions.
- Redis for Celery broker, result backend, scraper state, and scrape byte usage.
- Serper Search API for Gate 0 and keyword discovery.
- Residential proxy provider for scraper browser traffic.
- Rumble and BitChute as source platforms.

## 7. Key Business Rules

- A channel is a useful dashboard lead when it has meaningful comment activity, Gate 0 risk context, velocity data when available, and niche/demographic signals.
- Growth velocity is not meaningful until enough historical snapshots exist.
- Missing historical data must never be represented as zero velocity.
- BitChute fields may be unavailable; unavailable values must be stored as `null`.
- Gate 0 should be run aggressively for new or due channels, but dirty channels should not be automatically rechecked.
- Lookalikes must never be inferred through overlapping audience assumptions.
- Scraper stability should not block non-scraper product features.

## 8. Open Issues And Implementation Notes

- The root instructions mention `database/migrations/001_initial_schema.sql`, but the checked-in initial schema is under `frontend/supabase/migrations/001_initial_schema.sql`; root `database/migrations` currently contains later migrations only.
- The frontend uses raw hex Tailwind classes in many places even though the project guidance requests semantic palette names.
- Some frontend components and pages use default exports because Next.js route files require them, while the stricter component guidance prefers named exports for reusable components.
- `useRealtimeRefresh` implements real-time refresh behavior even though real-time WebSocket updates are listed as out of scope in the MVP guidance.
- The dashboard includes channel intake controls, so the implemented frontend is not strictly read-only.
- The seed SQL creates a default admin user with a hardcoded password for local/dev seeding; this must not be used as a production credential.
