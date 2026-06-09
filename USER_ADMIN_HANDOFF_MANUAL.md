# KontrolAlt User, Admin, and Handoff Manual

This manual explains how to use, maintain, and hand off KontrolAlt. It is written for Kelly, Marcus, operators, admins, and engineers who need practical guidance rather than code-level architecture.

Repository:

```text
https://github.com/ctlr-plus-analytics/KontrolAlt
```

## Quick Start

1. Log in with the Supabase account provided by the project owner.
2. Open the main Channel Discovery dashboard.
3. Use search to find a creator by name or URL.
4. Use filters to narrow the list by platform, topic, audience size, activity, engagement, and Previous Gold Affiliation.
5. Sort by Avg Comments when looking for creators with stronger audience response.
6. Open a profile to review metrics, scrape history, AI report, Similar Channels, and Previous Gold Affiliation.
7. Do not contact a creator until manual relationship status and Previous Gold Affiliation have both been reviewed.

### Search Behavior

Search is for finding existing creator records already in the database.

Search can match:

- creator/channel name
- channel URL
- description text, when available

Search does not create new creators. If a creator is not found, add them through Manual Add, Bulk URLs, or Seed Name Resolver.

Search quality depends on stored data. A creator with a sparse profile may be harder to find by description or topic until the scraper and classifier have run.

## Manual Relationship Status vs Automated Previous Gold Affiliation

KontrolAlt has two different concepts that should not be confused.

| Concept | Type | Meaning | Who/What Sets It | Outreach Impact |
|---|---|---|---|---|
| Current Partner | Manual relationship status | The creator is already an active partner. | User/admin on profile page | Do not treat as a new prospect. |
| Hired and Canceled | Manual relationship status | The creator previously worked with the business and should not be contacted again without approval. | User/admin on profile page | Do not contact. |
| Prior Relationship | Business concept | A creator has a known past relationship. In the current app this is handled either through manual do-not-contact status or automated Previous Gold Affiliation evidence. | Manual review or Gate0 evidence | Review before outreach. |
| Reset | Manual action | Clear the manual relationship status back to no manual status. | User/admin on profile page | Allows the creator to be considered again, but automated affiliation still must be reviewed. |
| Previous Gold Affiliation | Automated Gate0 status | The system detected or did not detect evidence of a precious-metals competitor affiliation. | Gate0 automation | Must be reviewed before outreach. |

Manual outreach status overrides automated prospecting decisions.

That means:

- If a creator is marked `Current Partner`, do not treat them as a new lead even if Gate0 says clean.
- If a creator is marked `Hired and Canceled`, do not contact them even if Gate0 says clean.
- If manual status is reset, the creator still needs normal review before outreach.
- If Gate0 says `dirty` or `needs_review`, review the evidence before outreach even if there is no manual status.

The current code stores manual status in `channels.do_not_contact` with these values:

- `Current Partner`
- `Hired and Canceled`

The current code does not have a separate first-class manual field named `Prior Relationship`. If that needs to be tracked separately from do-not-contact, it should be scoped as a product change.

## Previous Gold Affiliation Status

Previous Gold Affiliation is the user-facing meaning of Gate0.

It is not a general compliance check. It answers:

> Does this creator appear to already have, or previously have had, a gold or precious-metals competitor affiliation?

| Status | Plain English Meaning | Outreach Guidance |
|---|---|---|
| Unchecked | No automated check has completed yet. | Run Gate0 before relying on the record. |
| Pending | The check is queued or running. | Wait for the result. |
| Clean | No strong competitor affiliation evidence was found. | Still review manual status and profile quality. |
| Needs Review | Some possible evidence was found, but confidence is not high enough for an automatic dirty decision. | Human review required. |
| Dirty / Competitor | Strong evidence of competitor affiliation was found. | Use for benchmarking/research unless approved for outreach. |

The system checks contact links, secondary links, descriptions, video titles, redirected links, affiliate-style URLs, and search evidence.

If the system flags a creator, open the profile and review:

- flagged brand
- source URL
- confidence
- evidence signals
- scrape history
- AI report

If a label says "brand risk" anywhere in older language, read it as "Previous Gold Affiliation" or "Competitor Affiliation." That is the more accurate product label.

## How to Add and Scrape a Creator

Use the intake panel when a creator does not already exist in search.

### Manual Add

Use Manual Add when you know the exact Rumble or Substack URL.

Steps:

1. Open Add / Resolve Channel.
2. Choose platform.
3. Paste the creator URL.
4. Leave Trigger Scrape Immediately enabled when you want data now.
5. Submit.

What happens:

- The backend canonicalizes the URL.
- The app inserts or refreshes the channel record.
- The source is marked as `manual_frontend`.
- If Trigger Scrape Immediately is enabled, the platform scrape task is queued.
- A Gate0 check may be queued after the scrape delay.

### Bulk URLs

Use Bulk URLs when adding many known Rumble/Substack URLs.

Steps:

1. Open Add / Resolve Channel.
2. Choose Bulk URLs.
3. Paste one URL per line.
4. Choose whether to trigger scraping immediately.
5. Submit.

What happens:

- Each URL is parsed independently.
- Valid URLs are accepted.
- Invalid or unsupported URLs are rejected.
- Accepted rows can be queued for scraping.

### Seed Name Resolver

Use Seed Name Resolver when you know names but not exact platform URLs.

Steps:

1. Open Add / Resolve Channel.
2. Enter up to three creator names.
3. Run resolver.
4. Review suggested candidates.
5. Select the correct candidate URLs.
6. Confirm selected candidates.

What happens:

- The app first searches existing records by name.
- If no good existing match is found, it guesses likely Rumble/Substack URLs from the name.
- The user must confirm candidates before they are inserted.

### Trigger Scrape Immediately

Turn this on when you want the scraper to fetch profile data now.

When enabled:

- Rumble URLs go to the Rumble scrape queue.
- Substack URLs go to the Substack scrape queue.
- The profile may first appear with limited data and then fill in after scrape completion.

When disabled:

- The record exists, but metrics may remain incomplete until a later scrape or admin task runs.

### What Happens If Previous Gold Affiliation Is Unchecked

Unchecked means Gate0 has not completed for that creator.

To check it:

- wait for the post-scrape Gate0 task if the creator was just scraped
- or run Previous Gold Affiliation Batch from Admin
- or trigger the per-channel Gate0 endpoint if exposed to the operator workflow

Do not treat unchecked as clean.

### How to Verify a New Creator

Open the creator profile and check:

1. Profile header: name, platform, URL.
2. Metrics: subscribers, views/likes, comments, engagement, last active.
3. Recent videos/posts.
4. Scrape history.
5. Previous Gold Affiliation status and evidence.
6. AI summary and AI report.
7. Manual relationship status.
8. Similar Channels.

### If Data Does Not Appear

Use this checklist:

1. Refresh the page after a minute.
2. Check scrape history on the profile.
3. Check whether the record is still incomplete.
4. Confirm the URL is a supported Rumble or Substack channel URL.
5. Check Admin worker status.
6. Check Admin worker logs.
7. If the job is stuck, run the appropriate admin task again.
8. Use Purge only as a maintenance/reset action when workers or queues are clearly stuck.

Common causes:

- scraper is still running
- worker is offline
- platform blocked or rate-limited the scraper
- profile is private, hidden, suspended, or missing
- Substack hides subscriber count
- Rumble page shape changed
- URL is not a supported channel/publication URL
- AI report has not run yet

## How to Use Filters

Filters narrow the creator list. They do not permanently change data.

| Filter | Meaning | How to Use It |
|---|---|---|
| Topic Category | Uses the channel's stored category/niche tags. | Use this to focus on Financial / Macro, Conservative Politics, Health / Wellness, etc. |
| Subscribers | Filters by audience size. | Use min/max to find creators above or below a reach threshold. |
| Avg Views | Filters by average views for Rumble or reactions/likes-style metric for Substack. | Use this for reach and content consumption. |
| Avg Comments | Filters by average audience response. | Sort or filter by this when looking for engaged audiences. |
| Last Active | Filters by the most recent detected post/video date. | Use this to avoid stale creators. |
| Exclude 90d+ Inactive / Active Last 90 Days | Keeps creators active in roughly the last 90 days. | Turn on for active prospecting lists. |
| Incomplete Only | Shows records missing important scrape/enrichment data. | Use this for cleanup and backfill operations. |
| Previous Gold Affiliation | Filters by Gate0 status. | Use Clean for cleaner outreach review, Needs Review for manual review, Competitor/Dirty for research or exclusion. |

Suggested prospecting flow:

1. Set platform if needed.
2. Turn on Active Last 90 Days.
3. Filter Previous Gold Affiliation to Clean.
4. Sort by Avg Comments descending.
5. Review profile manually before outreach.

## Similar Channels

Similar Channels helps find creators related by category, audience size, or engagement.

Similar does not mean clean for outreach.

Always review Previous Gold Affiliation before contacting.

Flagged similar channels are useful for:

- benchmarking
- audience research
- understanding competitor ecosystems
- finding adjacent creators to investigate

Flagged similar channels should not be treated as direct outreach targets unless a human approves the affiliation context.

## Why Profiles May Look Different

Profiles may differ in completeness because each record depends on several independent steps.

| Reason | Effect |
|---|---|
| Public platform data varies | Some creators expose subscribers, links, posts, or comments; others do not. |
| Scrape status varies | A newly added or blocked creator may have sparse data. |
| AI classification may not have run | Category, AI summary, or AI report may be missing. |
| Previous Gold Affiliation may be unchecked | Gate0 evidence may not exist yet. |
| Historical snapshots may be missing | Velocity may be unavailable until enough history exists. |
| Platform behavior differs | Rumble, Substack, and legacy BitChute sources expose different data and have different scraping reliability. |

## Where the Creator Records Come From

| Source Type | What It Means | Count | Example Record | Limitation |
|---|---:|---:|---|---|
| Keyword Discovery | Automatic discovery from taxonomy keywords. Uses Google-indexed Serper queries such as `site:rumble.com` and `site:substack.com`. | Runtime variable | `discovery_source=auto_keyword` | Finds what Google indexed; may miss unindexed creators. |
| Serper/Search | Google search API provider used by discovery and import resolvers. | Runtime/API dependent | Search result candidate URL | Search results can be ambiguous or stale. |
| Seed Expansion | Automatic extraction from existing channels' contact links, secondary URLs, descriptions, video titles, and channel URLs. | Runtime variable | `discovery_source=auto_seed` | Quality depends on existing scraped data. |
| Substack Leaderboard | Standalone scraper for configured Substack leaderboard pages. | Runtime variable | `discovery_source=leaderboard_business_paid` | Only covers configured leaderboard categories. |
| Manual Intake | User manually adds one creator URL. | User-driven | `discovery_source=manual_frontend` | Requires correct URL. |
| Bulk URL Intake | User pastes multiple known URLs. | User-driven | `discovery_source=manual_frontend` | Unsupported URLs are rejected. |
| Spreadsheet Import | Excel workbook import into Rumble records. | Latest local report: 1,676 rows reviewed; 363 inserted | `xlsx_rumble_import`, `xlsx_rumble_serper_import` | Strict Rumble matching; many rows unresolved. |
| Name Resolver | CSV/name resolver using Serper to find channels. | Latest local reports: 110 do-not-contact seeds and 475 influencer rows | `csv_name_serper_resolver` | Ambiguous names require manual review. |

## Platform Status

| Platform | Status | Notes |
|---|---|---|
| Rumble | Supported now | Main video platform source. Scraper and queue are active. |
| Substack | Supported now | Replaced/expanded the usable V1 source set. Scraper and discovery are active. |
| BitChute | Limited/tested with caveat | Removed from active platform constraints. Historically considered, but limited by scraping reliability. |
| Truth Social | Not supported as primary platform | Can appear as external link/manual note only. |
| Telegram | Not supported as primary platform | Can appear as external link/manual note only. |
| X/Twitter | Not supported as primary platform | Can appear as external link/manual note only. |
| YouTube | Not supported as primary platform | Can appear as external link/manual note only. |
| Instagram | Not supported as primary platform | Can appear as external link/manual note only. |
| Facebook | Not supported as primary platform | Can appear as external link/manual note only. |
| LinkedIn | Not supported as primary platform | Can appear as external link/manual note only. |

Substack replaced or expanded the practical V1 source set because it is more usable in the current scraper/discovery code than BitChute. BitChute remains a limited legacy/caveat platform because scraping reliability was not strong enough for active support.

## Import Reconciliation Report

### Goldco Master Influencer Workbook

Local report:

```text
scraper/output/goldco_xlsx_rumble_import_report.json
```

Workbook:

```text
scraper/GoldCo Master Influencer List 2025-26 V1.xlsx
```

Tabs scanned:

- `Q1 HANDOFFS (Ready for Close)`
- `Q1 HUNT (targets)`
- `Q2 HUNT (targets)`
- `Q2 HANDOFFS (Ready for Close)`

Latest local summary:

| Metric | Count |
|---|---:|
| Rows reviewed | 1,676 |
| Rows with Excel URL | 185 |
| Rows needing Serper | 1,491 |
| Records resolved/matched | 609 |
| Records imported | 363 |
| Duplicates skipped | 246 |
| Unresolved / missing or no confident URL | 1,067 |
| Candidate URLs found | 424 |
| Below threshold | 0 |
| Generated at | 2026-06-03T06:47:40Z |

Current report limitations:

- Unsupported URLs are not separately counted in the summary.
- Missing URLs are represented inside unresolved/no confident match outcomes, not as a separate top-level count.
- Failed rows are not separately summarized beyond unresolved/error row records.
- Queued-for-scraping count is not part of this report summary.
- Manual-review count is implied by unresolved/ambiguous rows, not separately summarized.

### Do Not Contact / Current Partners CSV

Local report:

```text
scraper/output/channel_name_resolution_report.json
```

Source:

```text
scraper/DO NOT CONTACT_CURRENT PARTNERS.csv
```

Latest local summary:

| Metric | Count |
|---|---:|
| Seeds reviewed | 110 |
| Records inserted | 8 |
| Records updated | 28 |
| Duplicates skipped | 28 |
| Unresolved | 74 |
| Ambiguous | 54 |
| Candidate URLs found | 420 |
| Generated at | 2026-06-02T19:56:17Z |

### Influencer CSV Serper Import

Local report:

```text
scraper/scraper/output/influencer_serper_matches.json
```

Latest local summary:

| Metric | Count |
|---|---:|
| Rows reviewed | 475 |
| Matched rows | 333 |
| Unmatched rows | 142 |
| Candidate URLs found | 1,014 |
| Duplicates | 418 |
| Records inserted | 596 |
| Mode | write |

## Admin Guide

The Admin page is for maintenance, not daily prospecting.

Use Admin when you need to:

- trigger discovery
- trigger scraping
- backfill never-scraped records
- run Previous Gold Affiliation checks
- run AI classification
- refresh velocity
- inspect worker status
- inspect logs
- update category keywords
- update competitor settings
- purge stuck queues

### Category Keywords

Category Keywords affect both discovery and classification.

Discovery uses keywords to find new records. It builds search queries from category keywords and uses Serper/Google results to find Rumble and Substack channels.

Classification uses keywords to assign or support category tags after a channel has been scraped.

Existing records may need reclassification after keyword edits. Updating keywords does not automatically rewrite every old record unless a classification task runs again.

### Does Adding 5x More Keywords Improve Future Discovery?

Usually yes, if the new keywords are relevant and specific.

More good keywords can:

- create more search queries
- discover creators in more niches
- improve category coverage
- improve classification support

More bad or broad keywords can:

- create noisy search results
- waste Serper credits
- import irrelevant records
- increase manual review work

When keyword changes take effect:

- Future discovery runs use the updated keywords.
- Future scrape/classification runs can use updated taxonomy.
- Existing records need AI classification or reclassification to reflect major taxonomy changes.

## Admin Button Reference

| Button | What It Does | When To Click It | What Happens Next | Expected Timing | Uses Credits/Resources? | What Can Go Wrong | How To Confirm It Worked |
|---|---|---|---|---|---|---|---|
| Trigger Full Scrape | Starts the main scrape workflow. | When refreshing the database broadly. | Discovery/scrape orchestration dispatches platform tasks. | Minutes to hours depending on volume. | Yes: workers, proxies, platform requests, possible search/AI downstream. | Workers offline, platform blocks, queues stuck. | Check task status, worker logs, updated scrape history. |
| Trigger Discovery | Finds new creators. | When adding fresh candidates. | Runs seed and/or keyword discovery. | Minutes to longer depending on Serper query limits. | Yes: Serper/search API, possible AI pre-classification. | Search quota, noisy results, no taxonomy. | New records appear with discovery source and timestamps. |
| Bootstrap Never-Scraped | Scrapes records that exist but have no scrape data. | After imports or bulk adds. | Queues Rumble/Substack scrape tasks. | Minutes to hours depending on count. | Yes: workers, proxies, platform requests. | Unsupported URLs, platform blocks, worker capacity. | Records switch from incomplete to scraped; scrape logs appear. |
| Weekly Velocity | Refreshes qualified clean channels and computes velocity. | Weekly or before reporting. | Scrapes selected clean channels, then computes velocity from snapshots. | Longer-running batch. | Yes: scraper workers/proxies. | Not enough historical snapshots, recent snapshot skip. | Velocity fields appear on profiles. |
| Previous Gold Batch | Runs Gate0 checks. | Before outreach or after new scrape/import. | Queues previous gold affiliation checks. | Usually faster than scraping; depends on Serper usage. | Yes: Serper for search evidence. | Quota, no competitors configured, ambiguous evidence. | Previous Gold Affiliation changes from unchecked/pending to clean/review/competitor. |
| AI Classify | Classifies unclassified records. | After scraping new records. | Calls AI for missing/unknown categories and reports. | Depends on record count and AI latency. | Yes: Google AI/model credits. | Missing API key, cost, parsing errors, low-quality inputs. | Category, AI summary, and report appear. |
| AI Reclassify All | Re-runs classification broadly. | After major taxonomy/prompt changes. | Calls AI across eligible records. | Potentially long. | Yes: significant AI/model credits. | Cost spike, quota, noisy output. | Updated classification timestamps/content. |
| Purge | Clears stuck Celery queues/tasks. | Only when workers/queues are stuck. | Revokes tasks, purges broker queues, may restart pools. | Immediate to a few minutes. | Uses infrastructure resources, no model credits directly. | Can cancel useful running jobs. | Queues clear; worker status/logs stabilize. |

## Timing, Limits, and Performance

Current default expectations from code/runtime settings:

| Workflow | Current Limit / Expectation | Notes |
|---|---|---|
| Discovery | Serper query limit default: 480; insert limit default: 1,000; new scrape queue limit default: 500 | Actual runtime depends on search API and taxonomy size. |
| Rumble scraping | Platform slot limit default: 4 | Rumble uses browser scraping and may require proxy/Cloudflare handling. |
| Substack scraping | Platform slot limit default: 4 | Substack uses browser clearance plus in-browser API fetches. |
| Global scraping | Global slot limit default: 8 | Caps total concurrent scrape load. |
| Bulk intake | No fixed UI timing; accepted URLs can queue scrapes | Large batches complete in phases as workers process queues. |
| Previous Gold batch | Gate0 daily queue limit default: 200 | Uses local evidence and Serper when needed. |
| AI classification | Depends on eligible record count and Google AI latency | Uses model credits. |
| AI reclassify all | Potentially expensive and long-running | Use only after approval or major taxonomy/prompt changes. |
| Velocity runs | Weekly workflow targets qualified clean channels | Requires historical snapshots to produce useful results. |
| BitChute | Not active in current platform set | Historically slower/less reliable; no active worker queue in current code. |

Rumble, Substack, and BitChute behave differently. Rumble and Substack are active. BitChute remains limited/legacy and should be assumed slower and less reliable if revisited.

## Included in This MVP

| Feature | MVP Status | Usage / Decision |
|---|---|---|
| Channel Discovery dashboard | Included | Main list page with filters and profile links. |
| Manual Add | Included | Use Add / Resolve Channel with exact URL. |
| Bulk URL Intake | Included | Paste multiple URLs into bulk intake. |
| Seed Name Resolver | Included | Enter up to three names and confirm candidates. |
| Scraping Rumble/Substack | Included | Trigger immediately or via admin batches. |
| Previous Gold Affiliation | Included | Review Gate0 status and evidence before outreach. |
| AI report | Included as research aid | Use for research, not final outreach decisions. |
| Similar Channels | Included | Use for adjacent research and benchmarking. |
| Lists | Partial / Needs Marcus Decision | Filtering creates working lists, but saved named lists are not a clear first-class feature in current code. |
| CSV import | Partial | Supported through scripts/importers, not a polished dashboard workflow. |
| CSV export | Partial / V2 | No clear dashboard export workflow found in current code. Decide before Kelly sees it as a promised feature. |

## Note for Kelly About AI Reports

The AI report is functional as a research aid.

AI reports are research aids, not final outreach decisions.

I want to improve model quality further, but I do not want to run up additional AI/model costs without approval. If you want deeper model tuning or expanded AI reports, I would ask to charge those direct model/API costs to you or scope them into V2.

## Operating Costs

KontrolAlt has these cost categories:

| Cost Area | Dependency | Why It Exists |
|---|---|---|
| Frontend hosting | Next.js host | Serves dashboard UI. |
| Backend hosting | FastAPI host/container | Serves authenticated API and admin controls. |
| Database | Supabase Postgres | Stores channels, snapshots, logs, Gate0, settings, auth. |
| Redis/workers | Redis plus Celery workers | Runs queues and background jobs. |
| Scraper/proxy | Proxy provider plus browser workers | Needed for Rumble/Substack scraping and anti-blocking. |
| Search/discovery API | Serper / Google search API | Used for discovery and Gate0 search evidence. |
| AI/model credits | Google AI/Gemini | Used for classification, AI reports, and optional discovery pre-classification. |
| Domain | DNS/domain registrar | Public access URL. |
| Logs/monitoring | Host logs, Docker logs, optional monitoring provider | Debugging, uptime, and incident response. |

## Deployment Guide

The codebase supports a containerized deployment model.

### Components

| Component | Role |
|---|---|
| Frontend host | Runs Next.js dashboard. |
| Backend host | Runs FastAPI API. |
| Database | Supabase project. |
| Redis | Celery broker and task result backend. |
| Workers | Celery discovery, classify, Gate0, Rumble, Substack, and beat processes. |
| Scraper setup | Playwright Chromium, proxy list, browser profile storage. |
| Domain | Points users to frontend; backend API may use separate URL. |

### Required Environment Variables

Backend:

```text
SUPABASE_URL
SUPABASE_ANON_KEY
SUPABASE_SERVICE_ROLE_KEY
REDIS_URL
FRONTEND_ORIGIN
APP_ENV
LOG_LEVEL
```

Frontend:

```text
NEXT_PUBLIC_API_URL
NEXT_PUBLIC_SUPABASE_URL
NEXT_PUBLIC_SUPABASE_ANON_KEY
```

Scraper/workers:

```text
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
REDIS_URL
SERP_API_KEY
GOOGLE_API_KEY
PROXY_LIST
BROWSER_HEADLESS
BROWSER_PROFILE_DIR
PROXY_SESSION_MINUTES
PROXY_ACTIVE_SINCE_MINUTES
```

Do not commit real secrets. Provide only placeholder values in `.env.example`.

### Restart Steps

Local/container deployment:

```bash
docker compose up --build
```

Typical restart sequence:

1. Restart Redis only if broker state is broken or intentionally being reset.
2. Restart backend after API/config changes.
3. Restart workers after scraper/task/config changes.
4. Restart frontend after UI/env changes.
5. Check health endpoint.
6. Check Admin worker status.
7. Run a small scrape or Gate0 check as a smoke test.

### Logs

Use these logs during operations:

- backend container logs
- Celery worker logs
- Celery beat logs
- Redis logs
- frontend host logs
- Supabase logs
- proxy provider dashboard/logs
- Serper usage/quota dashboard
- Google AI usage/quota dashboard

### Known Failure Modes

| Failure | Symptom | Response |
|---|---|---|
| Missing env var | Service fails at startup or feature returns error. | Check env and redeploy/restart. |
| Supabase unavailable | API health degraded or data fails to load. | Check Supabase project and keys. |
| Redis unavailable | Tasks do not queue or status fails. | Restart Redis/workers. |
| Worker offline | Admin task queues but no progress. | Restart worker containers. |
| Proxy bad/blocked | Scrapes fail or block repeatedly. | Rotate/check proxy list. |
| Serper quota | Discovery/Gate0 search fails. | Check search API quota/billing. |
| Google AI quota/key | AI report/classification fails. | Check `GOOGLE_API_KEY` and billing. |
| Platform markup changed | Scrape parses empty/missing data. | Update scraper selectors/tests. |
| Queue stuck | Pending tasks do not move. | Inspect workers/logs; purge only if needed. |

## GitHub and Handoff Notes

### Code Ownership

Code should be owned by the engineering/development owner responsible for this repository.

Repository:

```text
https://github.com/ctlr-plus-analytics/KontrolAlt
```

### Data Ownership

Data ownership belongs to the business/project owner. This includes:

- creator records
- imported spreadsheets/CSVs
- manual relationship statuses
- admin taxonomy decisions
- Gate0 competitor settings
- outreach decisions

### Deployment Access

Deployment access should be documented outside the repo because it may include secrets.

Track who has access to:

- frontend host
- backend host
- Supabase project
- Redis/worker host
- domain/DNS
- Serper account
- Google AI account
- proxy provider
- logs/monitoring

### Excluded Secrets

Do not put these in GitHub:

- Supabase service role key
- Supabase JWT secrets
- Serper API key
- Google AI API key
- proxy credentials
- production database URLs with credentials
- admin user passwords
- host SSH keys

### README Notes

The repository should include or maintain README coverage for:

- project overview
- supported platforms
- local setup
- frontend commands
- backend commands
- scraper commands
- Docker Compose startup
- test commands
- deployment overview
- admin login/access expectations

### `.env.example` Notes

The repository should include an `.env.example` with placeholder values only.

It should include:

- Supabase URL and keys placeholders
- Redis URL placeholder
- frontend origin placeholder
- public frontend env placeholders
- Serper key placeholder
- Google AI key placeholder
- proxy list placeholder
- browser headless/profile placeholders

### Migration and Schema Notes

Use root `database/migrations/` as the primary schema reference.

Important caution:

- `frontend/supabase/migrations/` may lag behind root migrations.
- Confirm migration order before release.
- Confirm `channels` has the current Gate0, AI, recent videos, do-not-contact, and velocity columns.

### Setup Instructions

Developer setup:

```bash
docker compose up --build
cd frontend
npm install
npm run dev
```

Backend tests:

```bash
cd backend
pytest
```

Scraper tests:

```bash
cd scraper
pytest
```

Frontend checks:

```bash
cd frontend
npm run lint
npm run build
```

### Deployment Instructions

Deployment should:

1. Apply database migrations.
2. Configure production environment variables.
3. Deploy frontend.
4. Deploy backend.
5. Deploy Redis.
6. Deploy Celery workers.
7. Deploy Celery beat.
8. Run health checks.
9. Confirm admin login.
10. Confirm worker status.
11. Run a small operational smoke test.

### Admin Access Instructions

Admin access is controlled through Supabase user metadata.

An admin user must have metadata indicating admin status, such as:

- `role=admin`
- or `is_admin=true`

After granting admin metadata:

1. User logs out.
2. User logs back in.
3. User opens Admin page.
4. User confirms admin controls are visible.

## Loom Walkthrough Script

The requested 5-8 minute Loom is not recorded in this repository, but this is the exact recording checklist/script.

Target length: 5-8 minutes.

1. Login.
2. Open Channel Discovery.
3. Explain search.
4. Turn on Active Last 90 Days.
5. Use platform filter.
6. Sort by Avg Comments.
7. Open a profile.
8. Review profile metrics and scrape history.
9. Explain Previous Gold Affiliation.
10. Explain Similar Channels.
11. Add or resolve a channel.
12. Show Admin as maintenance-only.
13. Show Deployment Snapshot: frontend, backend, database, Redis/workers, scraper.
14. Explain known limitations.
15. End with outreach rule: manual status and Previous Gold Affiliation must be reviewed before contacting.

