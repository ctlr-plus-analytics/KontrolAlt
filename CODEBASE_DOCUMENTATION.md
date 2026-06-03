# KontrolAlt Codebase Documentation

This document explains the KontrolAlt application from database to backend to scraper workers to frontend. It is written as an engineering map of how the project works, where the important code lives, why the major pieces exist, and what happens during the main application workflows.

The repository is a full-stack creator discovery and lead intelligence system. Its current production direction is focused on Rumble and Substack creators. Older references to BitChute and some earlier product requirements still exist in documentation or historical migration context, but the active code and migrations remove BitChute and enforce Rumble/Substack as supported platforms.

## 1. High-Level Purpose

KontrolAlt helps discover, scrape, classify, filter, and review creators as potential lead targets for Goldco.

At a product level, it does the following:

1. Discovers possible creator channels from search results, seed expansion, known links, and leaderboard/import sources.
2. Stores candidate channels in Supabase Postgres.
3. Scrapes public channel data from Rumble and Substack.
4. Computes metrics such as subscribers, average views, average comments, posting cadence, engagement rate, and velocity.
5. Classifies creators into business-relevant niches.
6. Runs Gate0 checks to identify creators with existing precious-metals competitor affiliations.
7. Exposes the resulting data in a Next.js dashboard.
8. Gives admins operational controls for scraping, discovery, classification, Gate0 checks, worker status, logs, queue purge, competitors, and taxonomy.

The central object in the system is a channel row. Most workflows eventually read from or write to the `channels` table.

## 2. Runtime Architecture

The application is split into four major layers:

```text
Next.js frontend
  -> FastAPI backend
    -> Redis broker
      -> Celery workers
        -> Rumble/Substack scrapers, discovery, Gate0, AI classification, velocity
          -> Supabase Postgres
```

### Main Runtime Components

- `frontend/`: Next.js 16 dashboard written in TypeScript and React.
- `backend/`: FastAPI API that authenticates users, serves channel/admin APIs, and dispatches Celery tasks.
- `scraper/`: Celery worker application containing scrapers, discovery logic, Gate0 checks, classification, and velocity tasks.
- `database/migrations/`: root SQL migrations describing active database changes.
- `frontend/supabase/migrations/`: a second migration folder used by the frontend/Supabase workflow, currently lagging behind root migrations.
- `shared/types/`: cross-project TypeScript types, but currently stale compared with the frontend types.

### Docker Compose Topology

The root `docker-compose.yml` defines these services:

- `redis`: Celery broker/result backend.
- `backend`: FastAPI server running Uvicorn with reload.
- `worker-discovery`: Celery worker consuming discovery tasks.
- `worker-classify`: Celery worker consuming AI classification tasks.
- `worker-gate0`: Celery worker consuming Gate0 checks.
- `worker-rumble`: Celery worker consuming Rumble scrape tasks.
- `worker-substack`: Celery worker consuming Substack scrape tasks.
- `beat`: Celery beat scheduler.

This split matters because scraping is browser/proxy heavy, classification uses AI APIs, and discovery can produce bursts of work. Separate queues keep these workloads from blocking each other.

## 3. Repository Structure

### Root Files

- `AGENTS.md`: repository engineering guidelines.
- `RTK.md`: local instruction requiring shell commands to be prefixed with `rtk`.
- `CLAUDE.md`: architecture notes and operational guidance.
- `REQUIREMENTS.md`: historical/current product requirements. Some parts are outdated relative to implementation.
- `docker-compose.yml`: local multi-service orchestration.
- `.env`: environment configuration, not to be committed with secrets.
- `CODEBASE_DOCUMENTATION.md`: this document.

### Backend

Important directories:

- `backend/main.py`: FastAPI app entry point.
- `backend/api/v1/`: route handlers.
- `backend/services/`: business logic.
- `backend/models/`: Pydantic request/response models.
- `backend/core/`: config, auth, Supabase clients, logging, exceptions.
- `backend/workers/tasks.py`: Celery queue/task name constants used by backend dispatch code.
- `backend/tests/`: backend pytest suite.

### Scraper

Important directories:

- `scraper/worker.py`: Celery app setup.
- `scraper/tasks/`: Celery tasks and orchestration.
- `scraper/scrapers/`: Rumble/Substack scraper implementations and shared base class.
- `scraper/core/`: browser, proxy, Cloudflare, config, Supabase, runtime settings.
- `scraper/utils/`: URL canonicalization, keyword matching, contact extraction, AI response parsing.
- `scraper/schedules/`: beat schedule.
- `scraper/tests/`: scraper pytest suite.
- `scraper/scratch/`: local research/debug artifacts and HTML dumps.
- `scraper/output/`: generated importer reports.

### Frontend

Important directories:

- `frontend/src/app/`: Next.js app routes.
- `frontend/src/components/`: UI components.
- `frontend/src/hooks/`: React hooks for auth, channels, search, realtime, velocity.
- `frontend/src/lib/`: API client, Supabase clients, utility functions.
- `frontend/src/types/`: frontend domain types.
- `frontend/supabase/migrations/`: Supabase migration copy.

## 4. Environment and Configuration

### Root Environment

Both backend and scraper expect configuration from the root `.env`.

Important environment values:

- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`
- `REDIS_URL`
- `FRONTEND_ORIGIN`
- `SERP_API_KEY`
- `GOOGLE_API_KEY`
- `PROXY_LIST`
- `BROWSER_HEADLESS`

### Backend Configuration

Backend config lives in `backend/core/config.py`.

It uses Pydantic settings and loads from the root `.env`. Required values include Supabase URL, Supabase anon key, Supabase service role key, Redis URL, and frontend origin.

Why this exists:

- FastAPI needs Supabase anon key for JWT auth verification.
- Backend service code needs service role access for admin-level reads/writes.
- Backend task dispatch needs Redis/Celery connection details.
- CORS needs the frontend origin.

### Scraper Configuration

Scraper config lives in `scraper/core/config.py`.

It also loads from root `.env`. It requires service role Supabase credentials, Redis, proxy list, and Serper API key. Google AI is optional in config but required for AI classification features.

Why this exists:

- Scraper workers write directly to Supabase.
- Discovery and Gate0 use Serper.
- Browser scraping uses proxies and anti-blocking settings.
- Classification uses Gemini when enabled/configured.

### Runtime Settings

Static runtime defaults live in `scraper/core/runtime_settings.py`.

This file defines defaults such as:

- supported platforms: `substack`, `rumble`
- scrape slot limits
- retry delays
- discovery limits
- weekly velocity thresholds
- Gate0 competitor settings shape
- Cloudflare/proxy behavior flags

Some settings are also read from database tables such as `system_settings`, especially keyword taxonomy and Gate0 competitors.

## 5. Database Model and Migrations

The application uses Supabase Postgres. The canonical dashboard table is `channels`.

### Canonical Table: `channels`

The `channels` table is the center of the application. It stores:

- identity: `id`, `platform`, `channel_url`, `name`
- profile data: `description`, `subscriber_count`, `contact_info`, `secondary_urls`
- scrape status: `is_active`, `has_been_scraped`, `last_scraped_at`, `discovery_status`
- content metrics: `avg_views`, `avg_comments`, `video_titles`, `recent_videos`, `posts_per_week`, `last_active_date`
- classification: `niche_tags`, `comment_tier`, `ai_summary`, `ai_channel_report`
- discovery evidence: `discovery_source`, `last_discovery_source`, `discovery_confidence`, `discovery_evidence_count`, `discovery_quality_tier`, snippets/titles/hints
- Gate0 cache fields: `gate0_status`, `gate0_checked_at`, `gate0_flagged_brand`, `gate0_evidence_url`
- velocity cache fields: `view_velocity_30d`, `view_velocity_90d`, `comment_velocity_30d`, `comment_velocity_90d`, `velocity_computed_at`
- dashboard controls: `dashboard_eligible`, `do_not_contact`
- generated metric: `engagement_rate`

Why so much is cached on `channels`:

- The dashboard needs fast filtering/sorting.
- Supabase/PostgREST queries are simpler when the list page can select one table.
- Celery workers can update one canonical row after each workflow.

### Other Important Tables

The code refers to these additional tables:

- `channel_snapshots`: historical scrape snapshots used for velocity.
- `scrape_logs`: scrape attempt status/history.
- `gate0_results`: detailed Gate0 result history.
- `lookalike_matches`: older/persisted lookalike workflow.
- `seed_creators`: older lookalike seed workflow.
- `admin_actions_audit`: admin action log.
- `system_settings`: feature flags, keyword taxonomy, Gate0 competitors.
- `admin_operational_settings`: older operational settings table referenced by migrations.

### Active Root Migrations

Root migrations are in `database/migrations/`.

#### `021_remove_bitchute_platform.sql`

Removes BitChute data and restricts platform constraints to:

- `rumble`
- `substack`

It deletes BitChute-dependent rows from related tables, deletes BitChute channels, and updates platform-priority defaults.

#### `022_add_last_scraped_at.sql`

Adds `channels.last_scraped_at`, backfills from `channel_snapshots`, and indexes it.

Why:

- Daily scrape selection can avoid expensive snapshot lookups.

#### `023_add_recent_videos_json.sql`

Adds `channels.recent_videos jsonb`.

Why:

- Frontend detail pages can render recent videos/posts with URLs, titles, dates, comments, and views/likes.

#### `024_add_ai_summary.sql`

Adds `channels.ai_summary`.

Why:

- AI classification can store a short narrative summary.

#### `025_add_discovery_quality_fields.sql`

Adds discovery/classification fields:

- `discovery_quality_tier`
- `discovery_serp_snippet`
- `discovery_serp_title`
- `discovery_niche_hint`
- `classification_confidence`
- `classification_needs_review`
- `classification_context_score`

Why:

- Discovery and AI classification need evidence quality and confidence tracking.

#### `026_fix_engagement_rate_sort.sql`

Recreates `engagement_rate` as a generated column:

```sql
avg_comments / subscriber_count * 100
```

Why:

- Engagement sorting/filtering should be stable, generated by the database, and indexed.

#### `027_add_dashboard_query_indexes.sql`

Adds dashboard performance indexes:

- sorting indexes for comments, subscribers, views, last activity, velocity
- platform/comment tier/Gate0 indexes
- GIN index on `niche_tags`
- trigram indexes for search

Why:

- The dashboard does many filtered/sorted queries over `channels`.

#### `028_add_ai_channel_report.sql`

Adds `ai_channel_report` as JSONB.

#### `029_ai_channel_report_text.sql`

Drops JSONB report and recreates it as `TEXT`.

Why:

- The report shifted from structured JSON to narrative prose.

#### `030_add_do_not_contact.sql`

Adds `do_not_contact` with allowed statuses:

- `Hired and Canceled`
- `Current Partner`

Why:

- The dashboard needs a way to flag creators who should not be contacted.

#### `031_gate0_needs_review.sql`

Expands Gate0 to three tiers:

- `clean`
- `needs_review`
- `dirty`

Also adds confidence and evidence signals to `gate0_results`.

Why:

- Gate0 evidence is not always binary. Some signals are suspicious but not strong enough to mark a creator dirty.

### Migration Mismatch

`frontend/supabase/migrations/` contains copies of some root migrations but is missing at least:

- root `024_add_ai_summary.sql`
- root `031_gate0_needs_review.sql`

This matters because applying migrations from the frontend folder alone may not produce the schema expected by backend/scraper/frontend code.

## 6. Backend Application

The backend is a FastAPI app.

Entry point:

- `backend/main.py`

The backend does four main things:

1. Authenticates dashboard users with Supabase JWTs.
2. Exposes channel, velocity, Gate0, lookalike, scraper, and admin APIs.
3. Reads/writes Supabase through service modules.
4. Dispatches Celery tasks to Redis.

### Startup

On startup, `backend/main.py`:

- configures logging
- validates that Supabase connectivity works by querying `channels`
- logs a warning rather than crashing if Supabase is unavailable
- installs CORS middleware
- installs request logging middleware
- registers exception handlers
- mounts `/health`
- mounts `/api/v1`

Why it only warns on Supabase startup failure:

- Local development and container startup order can be imperfect.
- The app can start before the database is reachable, then recover.

### Authentication

Auth logic lives in `backend/core/security.py`.

Important functions:

- `get_current_user`
- `require_admin_user`

How auth works:

1. FastAPI extracts the bearer token.
2. The backend asks Supabase anon client to validate the token using `auth.get_user`.
3. Valid token responses are cached in memory for 60 seconds.
4. Admin checks read user/app metadata for `role=admin` or `is_admin`.

Why token caching exists:

- List/detail pages can generate repeated API calls.
- Supabase auth validation is remote.
- A tiny cache reduces latency and rate pressure.

### Supabase Clients

Supabase client setup lives in `backend/core/supabase.py`.

There are two clients:

- service role/admin client for trusted server-side data access
- anon client for JWT verification

The frontend must never receive the service role key.

### API Router

`backend/api/v1/router.py` mounts:

- `/channels`
- `/velocity`
- `/gate0`
- `/lookalike`
- `/scraper`
- `/admin`

### Health API

`backend/api/v1/health.py` checks:

- Supabase connectivity
- Redis connectivity

It returns `ok` or `degraded`.

### Channel API

Route file:

- `backend/api/v1/channels.py`

Service file:

- `backend/services/channel_service.py`

Model file:

- `backend/models/channel.py`

Main capabilities:

- list channels with filtering/sorting/pagination
- get channel detail
- create or resolve channel intake
- update do-not-contact status
- delete scrape history
- delete a channel
- fetch tag/status counts

#### Channel List Flow

Frontend calls:

- `GET /api/v1/channels`

The backend:

1. Parses filters into `ChannelFilters`.
2. Builds a Supabase query against `channels`.
3. Applies filters such as platform, category, subscriber range, average views/comments, engagement, Gate0 status, dates, incomplete-only, and inactive exclusion.
4. Applies sorting and pagination.
5. Maps flat database rows into response models.
6. Adds list-level Gate0 counts.

Important behavior:

- The list query uses `channels`, not a retired view.
- Category/niche filters use canonical broad taxonomy labels.
- If filtering includes `Unknown / Needs Review`, the service may fetch broader rows and filter in Python so empty/non-canonical tags are handled correctly.

Why this service exists:

- The frontend should not duplicate Supabase query rules.
- Filter behavior is complex enough to centralize.
- Response mapping keeps frontend contracts stable.

#### Channel Detail Flow

Backend detail endpoint reads:

- `channels.*`
- latest `scrape_logs`

It maps cached Gate0 and velocity fields into structured API response models.

However, the actual frontend channel detail page currently bypasses this backend endpoint in some places and reads Supabase directly server-side.

### Channel Intake

Service:

- `backend/services/channel_intake_service.py`

Models:

- `backend/models/channel_intake.py`

Intake supports:

- manual channel insert
- bulk channel insert
- seed name resolver

#### Manual/Bulk Intake

The service:

1. Accepts Rumble/Substack URLs.
2. Canonicalizes URLs.
3. Rejects platform mismatches.
4. Inserts or updates a minimal `channels` row.
5. Optionally queues immediate scrape.
6. Optionally queues Gate0 after scrape delay.

Rumble canonicalization accepts Rumble URLs. Substack canonicalization normalizes to:

```text
https://substack.com/@handle
```

#### Resolver Intake

Resolver flow:

1. User submits up to three seed names.
2. Backend searches existing active channels by normalized name.
3. If no strong existing match exists, it guesses likely Rumble/Substack URLs from slugs.
4. Frontend presents candidate rows for user confirmation.

Why this exists:

- Users often know creator names, not exact channel URLs.
- Intake should reduce manual URL hunting.

### Velocity API

Route:

- `backend/api/v1/velocity.py`

Service:

- `backend/services/velocity_service.py`

Velocity is read from cached columns on `channels`, not recomputed on demand.

The endpoint returns 404 if `velocity_computed_at` is missing.

Why:

- Velocity depends on historical snapshots.
- It is cheaper and more deterministic to compute asynchronously.

### Gate0 API

Route:

- `backend/api/v1/gate0.py`

Service:

- `backend/services/gate0_service.py`

Manual Gate0 check flow:

1. User requests a Gate0 check for a channel.
2. Backend checks feature flag.
3. Backend marks channel `gate0_status='pending'`.
4. Backend dispatches `TASK_RUN_GATE0` to the `gate0` queue.
5. Worker runs competitor evidence scan.
6. Worker writes `gate0_results`.
7. Worker updates flat Gate0 cache fields on `channels`.

Important mismatch:

- The response model expects status `pending`, but the disabled feature path can return `unchecked`.

### Lookalike API

Route:

- `backend/api/v1/lookalike.py`

Service:

- `backend/services/lookalike_service.py`

Current backend behavior is synchronous and ephemeral:

1. User submits seed names.
2. Backend finds matching seed channels.
3. Backend fetches active dashboard-eligible candidates.
4. Backend matches by niche overlap and subscriber similarity.
5. Backend returns results immediately.

Subscriber similarity band:

- candidates from 90 percent to 110 percent of the seed subscriber count qualify.

Important mismatch:

- `scraper/tasks/find_lookalikes.py` contains an older Celery/persisted lookalike workflow, including guest appearance matching helpers.
- The backend does not currently use that persisted task path.

### Scraper Trigger API

Route:

- `backend/api/v1/scraper.py`

Service:

- `backend/services/scraper_service.py`

This exposes admin-only endpoints for triggering scraping and discovery tasks.

### Admin API

Route:

- `backend/api/v1/admin.py`

Service:

- `backend/services/admin_service.py`

Admin capabilities:

- inspect current admin identity
- trigger daily scrape
- trigger discovery
- trigger never-scraped bootstrap
- trigger weekly velocity scrape
- trigger Gate0 batch
- trigger AI classification
- purge Celery queues
- inspect worker status
- fetch worker logs
- check task status
- read audit log
- read/update Gate0 competitors
- read/update keyword taxonomy

Admin service writes to `admin_actions_audit` for operational traceability.

### Queue Purge

Admin purge is aggressive. It:

- revokes active/reserved/scheduled Celery tasks
- can send terminate signals
- purges broker queues
- deletes Redis task metadata keys
- broadcasts pool restart

Why:

- Scraping/discovery queues can get stuck or overloaded.
- Admins need an emergency operational reset.

Risk:

- Purge can interrupt useful work.
- It should be treated as an operational danger action.

## 7. Backend Models

Backend Pydantic models live in `backend/models/`.

### `channel.py`

Defines:

- `Platform`
- `Gate0Status`
- `DoNotContactStatus`
- `DiscoveryStatus`
- `RecentVideo`
- `Channel`
- `ChannelWithMetrics`
- `ChannelFilters`
- paginated response models
- delete/update response models

Important logic:

- Filters validate numeric ranges.
- Platform is now `rumble` or `substack`.
- Gate0 includes `unchecked`, `pending`, `clean`, `needs_review`, `dirty`.

### `channel_intake.py`

Defines manual/bulk/resolver intake request and response contracts.

Important constraints:

- resolver seed names are capped at three.

### `gate0.py`

Defines Gate0 result/status models.

Important mismatch:

- Model supports `needs_review`, but it does not fully mirror newer `evidence_signals` fields that frontend detail reads directly from Supabase.

### `lookalike.py`

Defines lookalike request/result models.

The backend uses `guest_appearance` and `niche_overlap` as possible match types, but current service behavior is mostly niche/subscriber matching.

### `admin.py`

Defines admin response models and broad taxonomy categories.

The taxonomy category list is used to validate admin keyword taxonomy updates.

## 8. Scraper Worker Application

The Celery worker app lives in `scraper/worker.py`.

It configures:

- broker/result backend
- task imports
- task routes
- time limits
- worker prefetch behavior
- visibility timeout
- worker process initialization hooks

Why separate worker initialization exists:

- Browser scraping requires per-process Playwright setup.
- Proxy validation should happen once at startup.
- Browser pools should not be inherited incorrectly across forks.

## 9. Scraper Core Infrastructure

### Browser Control

File:

- `scraper/core/browser.py`

This module handles Playwright browser context creation.

Responsibilities:

- launch Chromium
- configure headless/headed behavior
- attach proxy settings
- set viewport, locale, timezone, user agent
- add stealth scripts
- block some resource types
- manage persistent Cloudflare/session storage state
- pre-warm target homepages
- detect cold sessions
- wait for usable content
- record telemetry
- use guarded navigation

Why:

- Rumble/Substack pages can block automation or trigger Cloudflare.
- Scrapers need consistent browser fingerprints.
- Persistent storage can reuse `cf_clearance` where possible.

### Browser Pool

File:

- `scraper/core/browser_pool.py`

The browser pool keeps one Chromium instance per Celery worker process and creates per-task contexts.

Why:

- Launching a browser per task is expensive.
- Reusing the browser process improves throughput.
- Per-task contexts isolate cookies/session state enough for scraping.

### Proxy Handling

File:

- `scraper/core/proxy.py`

Responsibilities:

- normalize proxy formats
- parse sticky session credentials
- validate proxies at startup
- track proxy health
- quarantine failed proxies
- choose weighted proxies
- create per-channel proxy session IDs
- mark blocked sessions

Why:

- Browser scraping at scale needs proxy rotation.
- Cloudflare/rate limits may apply to IP/session combinations.

### Cloudflare and Anti-Blocking

File:

- `scraper/core/cf_bypass.py`

Responsibilities:

- classify Cloudflare errors
- detect captcha/challenge pages
- provide realistic user agents
- add human-like delay/scroll/click helpers
- rate-limit per browser/proxy session
- verify fingerprint signals

Why:

- Scraping code needs to distinguish retryable challenge states from terminal bad pages.
- Reusing blocked sessions makes failures worse.

### Runtime Taxonomy

File:

- `scraper/utils/runtime_taxonomy.py`

It loads keyword taxonomy from `system_settings.keyword_taxonomy` with a 60-second cache.

Important behavior:

- On failure, it returns an empty taxonomy.
- Empty taxonomy means keyword classification falls back to `Unknown / Needs Review`.

## 10. Scraper Base Class

File:

- `scraper/scrapers/base.py`

`BaseScraper` defines common behavior for platform scrapers.

Responsibilities:

- abstract `scrape(channel_url)`
- save normalized scrape result to Supabase
- upsert/update `channels`
- insert `channel_snapshots`
- write scrape logs
- classify terminal page states
- enforce scrape quality
- compute median averages
- compute posting cadence
- reset Gate0 state after successful scrape when appropriate

Why:

- Rumble and Substack have different extraction logic but write the same data model.
- Common persistence logic avoids inconsistencies.

### Scrape Quality

`require_scrape_quality` rejects suspicious parses, for example:

- no videos parsed when the page looks like a valid channel
- missing average views
- banned/suspended/not found states

Why:

- A broken parser should not overwrite good channel data with empty metrics.
- Some failures should retry, while terminal states should deactivate a channel.

## 11. Rumble Scraper

File:

- `scraper/scrapers/rumble.py`

The Rumble scraper is DOM-heavy.

It extracts:

- channel name
- follower count
- description
- video cards
- latest video titles
- views
- comments
- upload dates
- recent videos
- contact links
- secondary URLs
- categories via keyword matcher
- posting cadence

How it works:

1. Normalize the channel base URL.
2. Open the channel page in a browser context.
3. Wait for content and classify terminal states.
4. Parse channel header/profile information.
5. Parse video cards from the channel/videos page.
6. Open a limited number of individual video pages to enrich comments/views if needed.
7. Open the about tab to extract description and external/social links.
8. Compute metrics and classification hints.
9. Save through `BaseScraper.save_to_supabase`.

Why individual video pages are sampled:

- Rumble list/card pages do not always expose accurate comment counts.
- Enriching a limited number keeps scraping cost controlled.

Important helper behavior:

- Count parsing supports `K`, `M`, commas, and text suffixes.
- Date parsing supports ISO dates, relative dates, and common display dates.
- Comment extraction avoids broad body-text fallbacks to reduce false positives.

## 12. Substack Scraper

File:

- `scraper/scrapers/substack.py`

The Substack scraper uses browser navigation for Cloudflare clearance and then calls Substack APIs from inside the browser using `page.evaluate(fetch(...))`.

It extracts:

- publication/profile id
- name
- bio/description
- subscriber count
- user links
- latest posts
- reaction count as views/likes proxy
- comment count
- post dates
- recent videos/posts
- categories via keyword matcher
- posting cadence

How it works:

1. Normalize to `https://substack.com/@handle`.
2. Open the profile URL in a browser to establish session/Cloudflare clearance.
3. Detect redirect to canonical handle if any.
4. Fetch public profile API through `page.evaluate`.
5. Fetch profile posts API through `page.evaluate`.
6. Reject hidden subscriber counts as terminal when needed.
7. Filter Substack internal links out of contact info.
8. Compute metrics and save through `BaseScraper`.

Why API calls are made through the browser:

- Direct raw HTTP can be blocked or miss required session context.
- In-browser fetch reuses browser cookies and clearance.

## 13. Discovery System

Main file:

- `scraper/tasks/discover_channels.py`

Compatibility wrappers:

- `scraper/tasks/discover_keyword_expansion.py`
- `scraper/tasks/discover_seed_expansion.py`

Discovery finds new possible channels and writes them directly into `channels`.

Discovery sources include:

- Serper search results
- keyword-based searches
- seed expansion from known channel contact links
- known channel secondary URLs
- descriptions
- video titles
- channel URLs
- relative links found in scraped content

Important behavior:

- Discovery now upserts directly into `channels`.
- Candidate staging concepts from older requirements are not the main implementation path.
- Discovery evidence is refreshed for existing rows.
- New rows are minimal until scraped.

### Discovery Quality

Discovery tracks:

- confidence
- evidence count
- source
- search snippet/title
- quality tier
- niche hint

Why:

- Not every discovered URL is equally likely to be useful.
- Scrape prioritization needs better candidates first.

### Keyword Discovery

Keyword discovery uses runtime taxonomy from database settings.

Flow:

1. Load taxonomy.
2. Build search queries.
3. Call Serper.
4. Extract supported Rumble/Substack URLs.
5. Optionally pre-classify with Gemini when configured.
6. Upsert discovered channels.
7. Optionally queue scrapes.

## 14. Scrape Task Flow

### Rumble Task

File:

- `scraper/tasks/scrape_rumble.py`

Flow:

1. Validate channel URL shape.
2. Acquire Redis scrape lock.
3. Acquire global/platform scrape slot.
4. Run `RumbleScraper.scrape` through browser pool.
5. Save result.
6. Release lock/slot.
7. Handle retryable/terminal failures.

Important:

- Task accepts only stricter Rumble channel paths such as `/c/` or `/user/`.
- Some URL utilities accept root slugs, so this is a mismatch.

### Substack Task

File:

- `scraper/tasks/scrape_substack.py`

Flow is similar to Rumble:

1. Validate `https://substack.com/@handle`.
2. Acquire lock/slot.
3. Run `SubstackScraper.scrape`.
4. Save result.
5. Handle failures.

Runtime defaults currently allow Substack to run without proxy.

### Shared Failure Policy

Files:

- `scraper/tasks/scrape_failure_policy.py`
- `scraper/tasks/scrape_helpers.py`

These modules handle:

- retry countdown with jitter
- blocked retry delays
- Redis locks
- slot counters
- scrape logging
- terminal deactivation
- proxy blocked-session marking
- daily byte usage tracking

Why:

- Scraper failures should be consistent across platforms.
- Some failures mean retry later; others mean the channel is invalid or unavailable.

## 15. Daily and Weekly Orchestration

File:

- `scraper/tasks/run_daily_scrape.py`

This file controls bigger workflows.

### Daily Scrape Flow

`run_daily_scrape` generally does:

1. Run discovery if enabled.
2. Select channels to scrape.
3. Prioritize never-scraped and incomplete candidates.
4. Stage scrape task signatures with batch countdowns.
5. Dispatch platform-specific scrapes.
6. Run post-scrape tasks.

### Post-Scrape Tasks

Post-scrape flow can queue:

- Gate0 checks
- AI classification

Why:

- Scrape output provides the evidence needed for Gate0 and classification.

### Never-Scraped Bootstrap

File:

- `scraper/tasks/scrape_never_scraped.py`

This task selects active Rumble/Substack rows that have not been scraped and queues platform-specific scrape tasks.

Why:

- Admins need a way to backfill imported/discovered channels.

### Weekly Velocity

Weekly velocity flow selects clean, qualified channels and scrapes them to refresh historical snapshots, then computes velocity.

Selection prefers:

- active channels
- clean Gate0
- stronger comment metrics
- stale enough snapshot history

Why:

- Velocity requires time-separated snapshots.
- Scraping every low-quality channel weekly would waste resources.

## 16. Velocity Computation

File:

- `scraper/tasks/compute_velocity.py`

Velocity uses `channel_snapshots`.

How it works:

1. Load all snapshots for a channel.
2. Find latest snapshot.
3. Find snapshots close to 30 and 90 days ago.
4. Compute percent change for views/comments.
5. Write results to flat velocity columns on `channels`.

Formula concept:

```text
(latest_value - historical_value) / historical_value * 100
```

If historical value is missing or zero, velocity is `null`.

Why cached on `channels`:

- Frontend filters/sorts need fast access.
- Velocity computation is asynchronous and snapshot-dependent.

## 17. Gate0 System

Main task:

- `scraper/tasks/run_gate0.py`

Backend dispatch:

- `backend/services/gate0_service.py`

Frontend display:

- `frontend/src/components/channels/Gate0Badge.tsx`
- `frontend/src/components/channels/ChannelDetail.tsx`

Gate0 answers:

> Does this creator appear to have a prior or current affiliation with a Goldco competitor?

### Gate0 Statuses

- `unchecked`: no check yet
- `pending`: task queued/running
- `clean`: no meaningful competitor evidence
- `needs_review`: suspicious but not definitive evidence
- `dirty`: strong competitor affiliation evidence

### Evidence Sources

Gate0 scans:

- contact links
- secondary URLs
- description text
- recent video/post titles
- shortlink redirects
- Serper search results

### Competitor Settings

Competitors come from `system_settings.gate0_competitors`.

If settings are unavailable, the task can fall back to empty competitors and clear pending status.

### Confidence Logic

Gate0 uses weighted signals.

Examples:

- domain in contact link is high-confidence dirty evidence
- domain in description may be needs-review or dirty
- one neutral title mention is usually below threshold
- promotional title context raises confidence
- negative context can suppress a match
- multiple Serper hits compound confidence

Confidence classification:

- `>= 0.95`: `dirty`
- `>= 0.80`: `needs_review`
- otherwise: `clean`

Why three tiers:

- A single casual mention of a brand is different from an affiliate link.
- Reviewers need to inspect ambiguous evidence instead of auto-excluding everything.

### Gate0 Persistence

The task writes:

- detailed row to `gate0_results`
- cached status/brand/evidence/check time to `channels`

Why both:

- `gate0_results` keeps detailed history.
- `channels` enables fast dashboard filters.

## 18. AI Classification and Channel Reports

File:

- `scraper/tasks/classify_channels.py`

This task uses Gemini to classify channels and produce an intelligence report.

It reads active scraped dashboard-eligible channels.

Classification updates:

- `niche_tags`
- `classification_confidence`
- `classification_needs_review`
- `classification_context_score`
- `ai_summary`

Report updates:

- `ai_channel_report`

### When Classification Runs

The task classifies when:

- tags are missing
- tags are unknown
- summary is missing
- context changed/improved
- admin forces reclassification

### Category Reconciliation

The system combines:

- keyword-derived category signals
- AI category output

Why:

- Keyword matching is deterministic and cheap.
- AI can infer meaning from titles/descriptions beyond exact keywords.
- Reconciliation reduces both false negatives and odd AI-only drift.

### AI Report

The report is written as plain text narrative.

The prompt is tailored to Goldco/Kelly lead intelligence use cases and asks for a structured channel evaluation.

Why:

- Sales/research users need more than raw metrics.
- A narrative report can explain why a channel may or may not be a fit.

## 19. Keyword Matching

File:

- `scraper/utils/keyword_matcher.py`

This module computes deterministic category hints.

It uses:

- channel name
- description
- recent titles
- runtime keyword taxonomy

Weights:

- name hits are strongest
- description hits are medium
- title hits are weaker

Important behavior:

- matching uses word boundaries to avoid substring false positives
- a single weak title keyword may not be enough
- categories are sorted by score
- no taxonomy means `Unknown / Needs Review`

Comment tiers:

- below 10 average comments: no tier
- 10 to below 20: `active`
- 20 to 100: `sweet_spot`
- above 100: `whale`

## 20. Contact and URL Extraction

### Contact Extraction

File:

- `scraper/utils/contact_extractor.py`

Extracts:

- emails
- URLs
- link-in-bio domains
- competitor-domain hints

It filters internal Rumble URLs.

Important note:

- General contact extractor filters Rumble internal links, but Substack has its own scraper-level contact filtering for Substack internal links.

### Channel URL Canonicalization

File:

- `scraper/utils/channel_urls.py`

Supports:

- Rumble URLs
- Substack `substack.com/@handle`
- Substack subdomains like `handle.substack.com`
- bare URLs found in search snippets/text

Canonical Substack format:

```text
https://substack.com/@handle
```

Important mismatch:

- URL extraction may accept Rumble root slugs like `https://rumble.com/LibertyDesk`.
- Scrape tasks and some importers require stricter `/c/` or `/user/` paths.

## 21. Importer and Utility Scripts

The scraper folder contains local/import helper scripts.

### `import_channel_names_serper.py`

Resolves creator names through Serper.

It:

- splits aliases
- extracts strict Rumble/Substack candidates
- rejects generic pages
- rejects ambiguous close scores
- can write resolution reports

### `import_goldco_influencer_xlsx_rumble.py`

Imports from a Goldco Excel influencer sheet.

It:

- reads workbook rows
- extracts direct Rumble URLs
- resolves missing URLs through Serper
- prefers Excel-provided URLs over search results
- deduplicates against primary and secondary URLs
- can write an import report

### `import_influencer_csv_serper.py`

Similar CSV-based importer for influencer names.

### `scrape_leaderboard.py`

Standalone Substack leaderboard scraper.

It:

- opens Substack leaderboard pages
- scrolls lazy-loaded cards
- extracts Substack publication links
- canonicalizes handles
- inserts or refreshes `channels`

Why these scripts exist:

- They support one-off or batch ingestion outside the normal discovery loop.
- They are useful for bootstrapping channel data from known source lists.

## 22. Frontend Application

The frontend is a Next.js 16 app.

Important files:

- `frontend/src/app/layout.tsx`
- `frontend/src/proxy.ts`
- `frontend/src/lib/api/backend.ts`
- `frontend/src/lib/supabase/client.ts`
- `frontend/src/lib/supabase/server.ts`
- `frontend/src/types/index.ts`

### Next.js Version Note

`frontend/AGENTS.md` warns that this Next.js version has breaking changes and docs should be checked before code edits.

### Environment

`frontend/next.config.ts` reads root `.env` and exposes:

- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`

It can fall back to backend-style env names.

Why:

- The frontend needs public Supabase configuration.
- The repo stores env at root rather than inside `frontend/`.

### Auth and Route Protection

Files:

- `frontend/src/proxy.ts`
- `frontend/src/hooks/useAuth.ts`
- `frontend/src/lib/supabase/client.ts`
- `frontend/src/lib/supabase/server.ts`

How it works:

1. Login page uses Supabase email/password.
2. Supabase session is stored in cookies.
3. Next proxy refreshes session cookies.
4. Unauthenticated users are redirected to `/login`.
5. Authenticated users visiting `/login` are redirected to `/`.
6. Admin route checks metadata server-side.

### API Client

File:

- `frontend/src/lib/api/backend.ts`

This is the centralized FastAPI client.

It handles:

- base URL selection
- bearer token headers
- JSON parsing
- `ApiError`
- channel list/detail/delete/update calls
- velocity calls
- Gate0 calls
- lookalike calls
- admin task/control calls
- competitor/taxonomy calls
- worker status/log calls

Why:

- UI components should not hand-roll fetch logic.
- API error handling should be consistent.

## 23. Frontend Routes

### Root Dashboard

File:

- `frontend/src/app/(dashboard)/page.tsx`

Flow:

1. Server component reads Supabase session.
2. If no session, redirect to login.
3. Fetch initial channel list from backend with bearer token.
4. Pass initial data into `ChannelTableView`.
5. If backend fetch fails, render with empty initial data and let client refresh.

Why server-side initial fetch:

- Faster first meaningful dashboard render.
- Auth token is available server-side.

### Channel Detail

File:

- `frontend/src/app/(dashboard)/channel/[id]/page.tsx`

This page reads Supabase directly server-side.

It loads:

- channel row
- latest Gate0 result
- scrape logs

It builds velocity data from flat channel columns.

Why it likely does this:

- The detail page needs rich data including evidence signals not fully represented in backend models.
- Direct Supabase read can fetch exactly what the page needs.

Risk:

- It bypasses backend business logic and API contracts.
- Auth/data access conventions differ from the rest of the frontend.

### Login

File:

- `frontend/src/app/(auth)/login/page.tsx`

Client component with email/password Supabase login.

### Admin

File:

- `frontend/src/app/(dashboard)/admin/page.tsx`

Server-side admin metadata check. Non-admin users are redirected away.

Renders `AdminControlPanel`.

### Lookalike

File:

- `frontend/src/app/(dashboard)/lookalike/page.tsx`

Client page that calls backend `searchLookalikes`.

Important note:

- `TopBar` currently exposes Channels and Admin navigation, but not Lookalike navigation.

### Health

File:

- `frontend/src/app/api/health/route.ts`

Returns frontend service health JSON.

## 24. Frontend Channel List

Main components:

- `frontend/src/components/channels/ChannelTableView.tsx`
- `frontend/src/components/channels/ChannelTable.tsx`
- `frontend/src/components/channels/ChannelRow.tsx`
- `frontend/src/components/filters/FilterSidebar.tsx`
- `frontend/src/components/filters/NumericRangeFilter.tsx`

### `ChannelTableView`

Responsibilities:

- hold filters/page/sort state
- persist filters/page/scroll in `sessionStorage`
- open manual/bulk intake modal
- fetch category counts
- fetch Gate0 status counts
- call `useChannels`
- render table and pagination
- subscribe to realtime refresh through hooks

Why:

- It is the page-level client controller for the channel dashboard.

### `useChannels`

File:

- `frontend/src/hooks/useChannels.ts`

Responsibilities:

- fetch channel pages
- debounce filter changes
- preserve old data during refresh
- avoid stale responses with request IDs
- avoid duplicate initial fetch after SSR data
- refresh from Supabase realtime events
- fall back to polling

Why:

- Dashboard filters can change rapidly.
- Realtime updates from scrapes/classification should appear without full reload.

### `FilterSidebar`

Provides filters for:

- search
- platform
- category/niche
- comment tier
- Gate0 status
- subscriber range
- average view range
- average comment range
- engagement rate range
- last active date
- inactive exclusion
- incomplete-only
- sorting

Default sort is average comments descending.

Why:

- The product goal is finding high-quality, relevant creators quickly.

### Channel Table Columns

`ChannelTable` renders:

- Channel
- Platform
- Subscribers
- Niche
- Avg Views or Likes
- Avg Comments
- Engagement Rate
- Previous Gold Affiliation
- Last Active

For Substack, `avg_views` is treated as likes/reactions.

## 25. Frontend Channel Detail

Main component:

- `frontend/src/components/channels/ChannelDetail.tsx`

It renders:

- channel header
- metric cards
- AI channel report
- velocity cards
- about/description
- recent videos/posts
- contact links
- secondary URLs
- categories
- lazy lookalike section
- scrape history
- Gate0 result and evidence
- cleanup/delete actions
- do-not-contact updates

It also listens for realtime updates and can refresh the route.

Important behavior:

- Delete scrape history resets cached channel fields via backend.
- Delete channel removes child data and channel row through backend.
- Do-not-contact status can be updated from detail UI.
- Gate0 evidence displays confidence and signal details from the latest Supabase result.

## 26. Frontend Admin Panel

Main component:

- `frontend/src/components/admin/AdminControlPanel.tsx`

Admin panel capabilities:

- show admin identity
- trigger daily scrape
- trigger discovery
- trigger never-scraped bootstrap
- trigger weekly velocity scrape
- trigger Gate0 checks
- trigger AI classification for unclassified or all channels
- poll task status
- display worker status
- fetch worker logs
- purge queues
- show audit log
- edit competitor settings
- edit keyword taxonomy

Task polling interval:

- 2500 ms

Worker/log refresh interval:

- roughly 10 seconds

Why:

- Scraping/discovery/classification are operational workflows.
- Non-engineering admins need controls without shell access.

## 27. Frontend UI Components

Shared UI components live in `frontend/src/components/ui/`.

- `Button.tsx`: styled button variants.
- `Badge.tsx`: styled status/category badge.
- `Table.tsx`: table wrapper with horizontal/vertical wheel handling.
- `Input.tsx`: labeled text input with error state.
- `Dropdown.tsx`: styled select element.
- `Spinner.tsx`: loading spinner.

Other important components:

- `Gate0Badge.tsx`: maps Gate0 status/brand to readable labels.
- `VelocityBadge.tsx`: shows direction and value.
- `CommentTierBadge.tsx`: labels activity tier.
- `ChannelIntakePanel.tsx`: manual/bulk/resolver channel intake UI.
- `TopBar.tsx`: primary navigation.

## 28. Utility Functions

Frontend utility file:

- `frontend/src/lib/utils.ts`

Provides:

- `formatNumber`
- `formatVelocity`
- `formatEngagementRate`
- `timeAgo`
- inactive date helpers
- color helpers
- text truncation
- `cn` class merging helper

Important:

- `formatEngagementRate` caps display at 100.

## 29. Types

### Frontend Types

File:

- `frontend/src/types/index.ts`

This is the most up-to-date TypeScript type set for the frontend.

It includes:

- platform types
- Gate0 statuses and result status
- channel fields
- recent videos
- admin/worker/task types
- intake types

### Shared Types

File:

- `shared/types/index.ts`

This file is stale.

Known issue:

- Gate0 types do not include newer `needs_review` and evidence fields.

Why this matters:

- If another app/package starts importing shared types, it may compile against outdated contracts.

## 30. Testing

### Backend Tests

Directory:

- `backend/tests/`

Coverage includes:

- channel service mapping and filtering
- channel intake canonicalization
- admin task dispatch and taxonomy validation
- lookalike matching

Run with:

```bash
cd backend
pytest
```

### Scraper Tests

Directory:

- `scraper/tests/`

Coverage includes:

- Rumble parser helpers
- Substack parser/API helpers
- Cloudflare classification
- proxy normalization
- scrape retry jitter
- never-scraped dispatch
- daily scrape prioritization
- Gate0 confidence logic
- keyword matching
- velocity computation
- importer ambiguity rejection
- AI response parsing

Run with:

```bash
cd scraper
pytest
```

### Frontend Tests

There is a test file:

- `frontend/src/lib/utils.test.ts`

It imports Vitest, but `frontend/package.json` does not currently include Vitest or a frontend test script.

Frontend available scripts:

```bash
cd frontend
npm run dev
npm run build
npm run lint
```

## 31. Main End-to-End Workflows

### Workflow A: User Logs In

1. User opens frontend.
2. Next proxy checks Supabase session cookies.
3. If unauthenticated, user is redirected to `/login`.
4. Login page signs in with Supabase email/password.
5. Session cookies are updated.
6. User is redirected to dashboard.

Where:

- `frontend/src/proxy.ts`
- `frontend/src/app/(auth)/login/page.tsx`
- `frontend/src/hooks/useAuth.ts`

### Workflow B: Dashboard Loads Channels

1. Dashboard server component gets Supabase session.
2. It calls backend `/channels` with bearer token.
3. Backend validates token through Supabase.
4. Channel service queries `channels`.
5. Backend returns paginated channels and Gate0 counts.
6. Client component renders table.
7. `useChannels` handles later refreshes.

Where:

- `frontend/src/app/(dashboard)/page.tsx`
- `frontend/src/components/channels/ChannelTableView.tsx`
- `frontend/src/hooks/useChannels.ts`
- `frontend/src/lib/api/backend.ts`
- `backend/api/v1/channels.py`
- `backend/services/channel_service.py`

### Workflow C: Admin Triggers Discovery

1. Admin clicks discovery trigger.
2. Frontend calls backend admin endpoint.
3. Backend verifies admin metadata.
4. Backend dispatches Celery discovery task.
5. Discovery worker queries Serper and existing channels.
6. It extracts supported Rumble/Substack URLs.
7. It inserts or refreshes `channels`.
8. Admin panel polls task status.

Where:

- `frontend/src/components/admin/AdminControlPanel.tsx`
- `backend/api/v1/admin.py`
- `backend/services/admin_service.py`
- `scraper/tasks/discover_channels.py`

### Workflow D: Admin Scrapes Never-Scraped Channels

1. Admin triggers never-scraped scrape.
2. Backend queues task.
3. Task selects active Rumble/Substack channels with missing scrape data.
4. Task dispatches platform-specific scrape tasks.
5. Rumble/Substack workers scrape channels.
6. Scrapers save metrics and snapshots.
7. Dashboard updates through realtime/polling.

Where:

- `scraper/tasks/scrape_never_scraped.py`
- `scraper/tasks/scrape_rumble.py`
- `scraper/tasks/scrape_substack.py`
- `scraper/scrapers/rumble.py`
- `scraper/scrapers/substack.py`

### Workflow E: Scraper Saves a Channel

1. Platform scraper returns normalized scrape data.
2. `BaseScraper.save_to_supabase` upserts `channels`.
3. It inserts a `channel_snapshots` row.
4. It writes scrape logs.
5. It updates scrape flags and timestamps.
6. It may reset old clean Gate0 status to unchecked.

Where:

- `scraper/scrapers/base.py`

### Workflow F: Gate0 Check Runs

1. Backend or post-scrape flow queues Gate0.
2. Gate0 worker loads channel and competitor settings.
3. It scans local channel evidence.
4. It follows redirect links where needed.
5. It runs Serper searches if local confidence is insufficient.
6. It computes confidence.
7. It classifies status as clean, needs_review, or dirty.
8. It writes `gate0_results`.
9. It updates cached Gate0 fields on `channels`.

Where:

- `backend/services/gate0_service.py`
- `scraper/tasks/run_gate0.py`

### Workflow G: AI Classification Runs

1. Admin or post-scrape orchestration queues classification.
2. Task selects active scraped dashboard-eligible channels.
3. It builds context from channel data.
4. It calls Gemini.
5. It parses response JSON/text robustly.
6. It reconciles AI and keyword categories.
7. It writes tags, confidence, summary, and report.

Where:

- `scraper/tasks/classify_channels.py`
- `scraper/utils/ai_response.py`
- `scraper/utils/keyword_matcher.py`

### Workflow H: Velocity Computes

1. Weekly velocity scrape refreshes snapshots for selected clean channels.
2. Velocity task loads snapshot history.
3. It finds latest, 30-day, and 90-day comparison snapshots.
4. It calculates percent changes.
5. It writes velocity fields to `channels`.
6. Frontend reads cached fields.

Where:

- `scraper/tasks/run_daily_scrape.py`
- `scraper/tasks/compute_velocity.py`
- `backend/services/velocity_service.py`
- `frontend/src/components/channels/VelocityBadge.tsx`

### Workflow I: Manual Channel Intake

1. User opens intake modal.
2. User submits one or many URLs, or seed names.
3. Frontend calls backend channel intake endpoints.
4. Backend canonicalizes URLs and inserts minimal rows.
5. Optional immediate scrape is queued.
6. Optional Gate0 check is queued after scrape delay.

Where:

- `frontend/src/components/channels/ChannelIntakePanel.tsx`
- `backend/api/v1/channels.py`
- `backend/services/channel_intake_service.py`

### Workflow J: Lookalike Search

1. User submits seed creator names.
2. Backend matches seed names to existing channels.
3. Backend finds active dashboard-eligible candidate channels.
4. Candidates with overlapping niche tags and similar subscriber count are returned.
5. Frontend renders match cards.

Where:

- `frontend/src/app/(dashboard)/lookalike/page.tsx`
- `backend/api/v1/lookalike.py`
- `backend/services/lookalike_service.py`

## 32. Important Design Decisions

### Why `channels` Is Denormalized

The dashboard needs fast list queries with many filters. Storing computed fields directly on `channels` makes these queries simple and indexable.

Tradeoff:

- Writes are more complex because tasks must keep cached fields current.
- Reads are much faster and simpler.

### Why Workers Write Directly to Supabase

Scraper tasks are long-running background jobs. They use the Supabase service role directly.

Why:

- Avoids routing high-volume scrape writes through FastAPI.
- Keeps background workflows independent of backend HTTP availability.

Tradeoff:

- Business rules can be split between backend services and worker code.
- Schema contracts must be kept carefully aligned.

### Why Browser Scraping Uses Playwright

Rumble and Substack pages can be dynamic and protected by anti-bot systems.

Why:

- Browser context can run JavaScript.
- Browser fetch can reuse cookies and clearance.
- DOM extraction is needed for Rumble.

Tradeoff:

- More resource intensive than HTTP scraping.
- Requires proxy and Cloudflare handling.

### Why Gate0 Has `needs_review`

Competitor evidence is often ambiguous.

Examples:

- A creator mentions a competitor in a negative context.
- A search result mentions a brand but no affiliate link.
- A video title references a brand without sponsorship language.

`needs_review` allows human review instead of false binary decisions.

### Why AI and Keyword Classification Coexist

Keyword matching is cheap, deterministic, and auditable. AI classification is flexible and can infer meaning.

Using both gives better coverage:

- deterministic rules catch obvious terms
- AI catches broader semantic fit
- reconciliation reduces weak classifications

## 33. Known Mismatches and Technical Debt

### Stale Shared Types

`shared/types/index.ts` does not match current frontend/backend Gate0 and channel fields.

Impact:

- Future shared package consumers may use wrong contracts.

### Frontend Migration Folder Lag

`frontend/supabase/migrations` lacks some root migrations.

Impact:

- Applying only frontend migrations can create a database missing fields the app expects.

### Lookalike Workflow Split

Backend lookalike search is immediate and ephemeral.

Scraper still contains older persisted Celery lookalike code.

Impact:

- Product behavior may be confusing.
- Old task code may not reflect current UI/API behavior.

### Channel Detail Bypasses Backend

Most frontend data flows through FastAPI, but channel detail reads Supabase directly.

Impact:

- Business logic and auth conventions are split.
- Backend models can drift from detail page needs.

### Some Destructive Channel Endpoints Are Not Admin-Only

Channel delete/history cleanup endpoints use authenticated user dependency rather than admin dependency.

Impact:

- Any authenticated user may be able to delete channel/history data if route access is not otherwise restricted.

### Rumble URL Shape Mismatch

URL canonicalization can accept Rumble root slugs, but scrape tasks/importers often require `/c/` or `/user/`.

Impact:

- Some discovered/imported URLs may insert successfully but fail scrape dispatch.

### Gate0 Response Model Mismatch

Manual Gate0 service can return `unchecked` when disabled, but response model is narrower.

Impact:

- Runtime validation or client expectations may fail in disabled-feature cases.

### Frontend Test Setup Incomplete

`utils.test.ts` uses Vitest, but Vitest is not installed and no test script exists.

Impact:

- Frontend tests are not currently runnable through package scripts.

### Runtime Taxonomy Has No Hardcoded Fallback

If DB taxonomy cannot load, keyword matching returns unknown.

Impact:

- Classification quality depends on admin/system settings availability.

### UI Palette and Styling Are Very Hardcoded

Frontend uses many direct hex Tailwind arbitrary classes.

Impact:

- Styling changes require many scattered edits.
- It is harder to enforce a design system.

## 34. Operational Commands

### Start All Services

```bash
docker compose up --build
```

Starts:

- Redis
- backend
- Celery workers
- Celery beat

### Run Frontend Locally

```bash
cd frontend
npm install
npm run dev
```

Frontend URL:

```text
http://localhost:3000
```

### Build Frontend

```bash
cd frontend
npm run build
```

### Lint Frontend

```bash
cd frontend
npm run lint
```

### Run Backend Tests

```bash
cd backend
pytest
```

### Run Scraper Tests

```bash
cd scraper
pytest
```

## 35. How to Trace a Bug

### Dashboard List Bug

Start with:

1. `frontend/src/components/channels/ChannelTableView.tsx`
2. `frontend/src/hooks/useChannels.ts`
3. `frontend/src/lib/api/backend.ts`
4. `backend/api/v1/channels.py`
5. `backend/services/channel_service.py`
6. database indexes/migrations if query performance is involved

### Channel Detail Bug

Start with:

1. `frontend/src/app/(dashboard)/channel/[id]/page.tsx`
2. `frontend/src/components/channels/ChannelDetail.tsx`
3. Supabase query shape in the page
4. backend delete/update endpoints if action buttons are involved

### Scrape Bug

Start with:

1. platform task: `scraper/tasks/scrape_rumble.py` or `scraper/tasks/scrape_substack.py`
2. platform scraper: `scraper/scrapers/rumble.py` or `scraper/scrapers/substack.py`
3. shared base persistence: `scraper/scrapers/base.py`
4. failure policy: `scraper/tasks/scrape_failure_policy.py`
5. browser/proxy/Cloudflare modules if blocked

### Discovery Bug

Start with:

1. `scraper/tasks/discover_channels.py`
2. `scraper/utils/channel_urls.py`
3. `scraper/utils/runtime_taxonomy.py`
4. Serper/API env config
5. `channels` discovery fields

### Gate0 Bug

Start with:

1. `backend/services/gate0_service.py` for dispatch
2. `scraper/tasks/run_gate0.py` for logic
3. `system_settings.gate0_competitors`
4. `gate0_results`
5. cached Gate0 fields on `channels`
6. `frontend/src/components/channels/Gate0Badge.tsx`

### AI Classification Bug

Start with:

1. `scraper/tasks/classify_channels.py`
2. `scraper/utils/ai_response.py`
3. `scraper/utils/keyword_matcher.py`
4. `system_settings.keyword_taxonomy`
5. `channels.ai_summary`, `channels.ai_channel_report`, `channels.niche_tags`

### Velocity Bug

Start with:

1. `scraper/tasks/compute_velocity.py`
2. `channel_snapshots`
3. flat velocity columns on `channels`
4. `backend/services/velocity_service.py`
5. `frontend/src/components/channels/VelocityBadge.tsx`

## 36. Current Mental Model

The simplest accurate mental model is:

```text
channels is the operational source of truth for dashboard rows.

scraper workers enrich channels.

channel_snapshots preserve history.

gate0_results preserve Gate0 evidence history.

FastAPI protects and shapes most app access.

Next.js renders the operational UI.

Supabase auth gates users.

Redis/Celery run long background workflows.
```

When trying to understand any feature, ask:

1. What column or table stores the state?
2. Which backend endpoint exposes it?
3. Which service owns the business rule?
4. Which Celery task mutates it asynchronously?
5. Which frontend component renders or triggers it?

That path will usually lead to the complete implementation.

