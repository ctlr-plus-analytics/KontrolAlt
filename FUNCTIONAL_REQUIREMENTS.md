# KontrolAlt Functional Requirements

This document lists the functional requirements of the KontrolAlt application at an atomic level. Each requirement is written so it has one responsibility and can be reviewed, implemented, or tested independently.

Requirement IDs use this format:

```text
FR-<AREA>-<NUMBER>
```

## Scope

The application is a creator discovery, scraping, enrichment, classification, previous-gold-affiliation, and dashboard system for Rumble and Substack creators.

The application must support:

- authenticated dashboard access
- creator/channel storage
- creator discovery
- Rumble scraping
- Substack scraping
- metric computation
- Gate0 previous gold affiliation checks
- AI classification and reporting
- velocity calculation
- lookalike matching
- admin operations
- auditability
- operational recovery

## 1. Platform Requirements

### Supported Platforms

- FR-PLAT-001: The application must support Rumble channels.
- FR-PLAT-002: The application must support Substack publications.
- FR-PLAT-003: The application must reject BitChute as an active supported platform.
- FR-PLAT-004: The application must store platform values as `rumble` or `substack`.
- FR-PLAT-005: The application must route Rumble scrape jobs to the Rumble queue.
- FR-PLAT-006: The application must route Substack scrape jobs to the Substack queue.
- FR-PLAT-007: The application must allow platform filtering in the dashboard.
- FR-PLAT-008: The application must display the creator platform in channel lists.
- FR-PLAT-009: The application must display platform-specific labels for metrics where semantics differ.
- FR-PLAT-010: The application must treat Substack reaction counts as the Substack equivalent of likes/views in frontend display.

## 2. Data Storage Requirements

### Channel Storage

- FR-DATA-001: The application must store creators as rows in the `channels` table.
- FR-DATA-002: The application must use `channels` as the canonical dashboard source table.
- FR-DATA-003: The application must store a unique channel identifier.
- FR-DATA-004: The application must store the channel platform.
- FR-DATA-005: The application must store the canonical channel URL.
- FR-DATA-006: The application must store the channel name.
- FR-DATA-007: The application must store the channel description when available.
- FR-DATA-008: The application must store subscriber count when available.
- FR-DATA-009: The application must store average views when available.
- FR-DATA-010: The application must store average comments when available.
- FR-DATA-011: The application must store recent video or post titles.
- FR-DATA-012: The application must store structured recent video or post metadata.
- FR-DATA-013: The application must store contact information.
- FR-DATA-014: The application must store secondary URLs.
- FR-DATA-015: The application must store posting cadence.
- FR-DATA-016: The application must store last active date.
- FR-DATA-017: The application must store whether the channel is active.
- FR-DATA-018: The application must store whether the channel has been scraped.
- FR-DATA-019: The application must store when the channel was last scraped.
- FR-DATA-020: The application must store when the channel was created.
- FR-DATA-021: The application must store when the channel was updated.
- FR-DATA-022: The application must store whether the channel is dashboard eligible.
- FR-DATA-023: The application must store the discovery status.
- FR-DATA-024: The application must store the discovery source.
- FR-DATA-025: The application must store the latest discovery source.
- FR-DATA-026: The application must store discovery confidence.
- FR-DATA-027: The application must store discovery evidence count.
- FR-DATA-028: The application must store discovery category.
- FR-DATA-029: The application must store discovery quality tier.
- FR-DATA-030: The application must store discovery search result snippet when available.
- FR-DATA-031: The application must store discovery search result title when available.
- FR-DATA-032: The application must store discovery niche hints when available.
- FR-DATA-033: The application must store the source channel ID for seed-expanded discoveries when available.
- FR-DATA-034: The application must store niche/category tags.
- FR-DATA-035: The application must store comment tier.
- FR-DATA-036: The application must store AI summary.
- FR-DATA-037: The application must store AI channel report.
- FR-DATA-038: The application must store classification confidence.
- FR-DATA-039: The application must store whether classification needs review.
- FR-DATA-040: The application must store classification context score.
- FR-DATA-041: The application must store Gate0 status.
- FR-DATA-042: The application must store Gate0 checked time.
- FR-DATA-043: The application must store Gate0 flagged brand.
- FR-DATA-044: The application must store Gate0 evidence URL.
- FR-DATA-045: The application must store latest Gate0 result ID.
- FR-DATA-046: The application must store latest Gate0 search query.
- FR-DATA-047: The application must store latest Gate0 result status.
- FR-DATA-048: The application must store view velocity over 30 days.
- FR-DATA-049: The application must store view velocity over 90 days.
- FR-DATA-050: The application must store comment velocity over 30 days.
- FR-DATA-051: The application must store comment velocity over 90 days.
- FR-DATA-052: The application must store velocity computation time.
- FR-DATA-053: The application must store do-not-contact status.
- FR-DATA-054: The application must restrict do-not-contact status to allowed business values.
- FR-DATA-055: The application must compute engagement rate from average comments and subscribers.
- FR-DATA-056: The application must keep engagement rate sortable.

### Snapshot Storage

- FR-DATA-057: The application must store scrape snapshots for historical metrics.
- FR-DATA-058: Each snapshot must be linked to a channel.
- FR-DATA-059: Each snapshot must store scrape time.
- FR-DATA-060: Each snapshot must preserve metrics required for velocity calculation.
- FR-DATA-061: The application must use snapshots for velocity computation.

### Scrape Log Storage

- FR-DATA-062: The application must store scrape logs.
- FR-DATA-063: Each scrape log must be linked to a channel when possible.
- FR-DATA-064: Each scrape log must store platform.
- FR-DATA-065: Each scrape log must store status.
- FR-DATA-066: Each scrape log must store error information when available.
- FR-DATA-067: Each scrape log must store timestamps.
- FR-DATA-068: The channel detail page must display recent scrape logs.

### Gate0 Result Storage

- FR-DATA-069: The application must store detailed Gate0 results.
- FR-DATA-070: Each Gate0 result must be linked to a channel.
- FR-DATA-071: Each Gate0 result must store result status.
- FR-DATA-072: Each Gate0 result must store checked time.
- FR-DATA-073: Each Gate0 result must store search query when applicable.
- FR-DATA-074: Each Gate0 result must store flagged brand when applicable.
- FR-DATA-075: Each Gate0 result must store source URL when applicable.
- FR-DATA-076: Each Gate0 result must store confidence.
- FR-DATA-077: Each Gate0 result must store evidence signals.

### Admin Settings Storage

- FR-DATA-078: The application must store feature flags in settings.
- FR-DATA-079: The application must store Gate0 competitor settings.
- FR-DATA-080: The application must store keyword taxonomy settings.
- FR-DATA-081: The application must allow admin updates to Gate0 competitor settings.
- FR-DATA-082: The application must allow admin updates to keyword taxonomy settings.

### Audit Storage

- FR-DATA-083: The application must store admin action audit entries.
- FR-DATA-084: Each audit entry must identify the actor when available.
- FR-DATA-085: Each audit entry must identify the action.
- FR-DATA-086: Each audit entry must store relevant action metadata.
- FR-DATA-087: The admin UI must display audit entries.

## 3. Authentication and Authorization Requirements

### User Authentication

- FR-AUTH-001: The frontend must provide a login page.
- FR-AUTH-002: The login page must authenticate users with Supabase email and password.
- FR-AUTH-003: The application must store authenticated sessions in Supabase cookies.
- FR-AUTH-004: The application must redirect unauthenticated users to `/login`.
- FR-AUTH-005: The application must redirect authenticated users away from `/login`.
- FR-AUTH-006: The frontend must refresh Supabase session cookies through the Next proxy.
- FR-AUTH-007: The backend must require bearer tokens for protected APIs.
- FR-AUTH-008: The backend must validate bearer tokens with Supabase auth.
- FR-AUTH-009: The backend must reject invalid tokens.
- FR-AUTH-010: The backend must cache valid token lookups briefly.
- FR-AUTH-011: The frontend must sign users out through Supabase.

### Admin Authorization

- FR-AUTH-012: The backend must distinguish admin users from normal users.
- FR-AUTH-013: The backend must identify admins from Supabase user metadata.
- FR-AUTH-014: Admin-only endpoints must require admin authorization.
- FR-AUTH-015: The admin page must redirect non-admin users.
- FR-AUTH-016: Admin task triggers must require admin authorization.
- FR-AUTH-017: Worker status APIs must require admin authorization.
- FR-AUTH-018: Queue purge APIs must require admin authorization.
- FR-AUTH-019: Competitor settings updates must require admin authorization.
- FR-AUTH-020: Keyword taxonomy updates must require admin authorization.

## 4. API Requirements

### Health API

- FR-API-001: The backend must expose a health endpoint.
- FR-API-002: The health endpoint must check Supabase connectivity.
- FR-API-003: The health endpoint must check Redis connectivity.
- FR-API-004: The health endpoint must return `ok` when dependencies are healthy.
- FR-API-005: The health endpoint must return `degraded` when a dependency check fails.
- FR-API-006: The frontend must expose a frontend health endpoint.

### Channel List API

- FR-API-007: The backend must expose an authenticated channel list endpoint.
- FR-API-008: The channel list endpoint must return paginated channels.
- FR-API-009: The channel list endpoint must return total row count.
- FR-API-010: The channel list endpoint must support page number.
- FR-API-011: The channel list endpoint must support page size.
- FR-API-012: The channel list endpoint must support search text.
- FR-API-013: The channel list endpoint must support platform filter.
- FR-API-014: The channel list endpoint must support category tag filters.
- FR-API-015: The channel list endpoint must support niche tag filter aliases.
- FR-API-016: The channel list endpoint must support subscriber minimum filter.
- FR-API-017: The channel list endpoint must support subscriber maximum filter.
- FR-API-018: The channel list endpoint must support average views minimum filter.
- FR-API-019: The channel list endpoint must support average views maximum filter.
- FR-API-020: The channel list endpoint must support average comments minimum filter.
- FR-API-021: The channel list endpoint must support average comments maximum filter.
- FR-API-022: The channel list endpoint must support engagement rate minimum filter.
- FR-API-023: The channel list endpoint must support engagement rate maximum filter.
- FR-API-024: The channel list endpoint must support comment tier filter.
- FR-API-025: The channel list endpoint must support Gate0 status filter.
- FR-API-026: The channel list endpoint must support last active from-date filter.
- FR-API-027: The channel list endpoint must support last active to-date filter.
- FR-API-028: The channel list endpoint must support inactive exclusion.
- FR-API-029: The channel list endpoint must support incomplete-only filter.
- FR-API-030: The channel list endpoint must support dashboard-eligible filtering.
- FR-API-031: The channel list endpoint must support sorting.
- FR-API-032: The channel list endpoint must support ascending sort order.
- FR-API-033: The channel list endpoint must support descending sort order.
- FR-API-034: The channel list endpoint must map flat velocity fields into velocity response data.
- FR-API-035: The channel list endpoint must map flat Gate0 fields into Gate0 response data.
- FR-API-036: The channel list endpoint must include Gate0 status counts.

### Channel Detail API

- FR-API-037: The backend must expose an authenticated channel detail endpoint.
- FR-API-038: The channel detail endpoint must return channel fields.
- FR-API-039: The channel detail endpoint must return latest scrape logs.
- FR-API-040: The channel detail endpoint must return Gate0 data when available.
- FR-API-041: The channel detail endpoint must return velocity data when available.
- FR-API-042: The channel detail endpoint must return 404 for missing channels.

### Channel Metadata APIs

- FR-API-043: The backend must expose category tag options.
- FR-API-044: Category tag options must include counts.
- FR-API-045: Category tag options must respect active filter scope when supported.
- FR-API-046: The backend must expose Gate0 status options.
- FR-API-047: Gate0 status options must include counts.

### Channel Update APIs

- FR-API-048: The backend must allow updating a channel Gate0 status.
- FR-API-049: The backend must allow updating a channel do-not-contact status.
- FR-API-050: The backend must validate do-not-contact status values.
- FR-API-051: The backend must allow clearing do-not-contact status.

### Channel Delete APIs

- FR-API-052: The backend must allow deleting channel scrape history.
- FR-API-053: Deleting scrape history must remove snapshots.
- FR-API-054: Deleting scrape history must remove scrape logs.
- FR-API-055: Deleting scrape history must remove Gate0 results.
- FR-API-056: Deleting scrape history must reset scrape-derived channel fields.
- FR-API-057: The backend must allow deleting a channel.
- FR-API-058: Deleting a channel must delete dependent snapshots.
- FR-API-059: Deleting a channel must delete dependent scrape logs.
- FR-API-060: Deleting a channel must delete dependent Gate0 results.
- FR-API-061: Deleting a channel must delete dependent lookalike matches.

### Velocity API

- FR-API-062: The backend must expose a channel velocity endpoint.
- FR-API-063: The velocity endpoint must return cached velocity metrics.
- FR-API-064: The velocity endpoint must return 404 when velocity has not been computed.

### Gate0 API

- FR-API-065: The backend must expose a manual Gate0 check endpoint.
- FR-API-066: The manual Gate0 endpoint must mark a channel as pending before dispatch.
- FR-API-067: The manual Gate0 endpoint must queue the Gate0 task.
- FR-API-068: The manual Gate0 endpoint must clear pending status if dispatch fails.
- FR-API-069: The manual Gate0 endpoint must return task ID when queued.
- FR-API-070: The manual Gate0 endpoint must handle disabled Gate0 feature state.

### Lookalike API

- FR-API-071: The backend must expose lookalike search.
- FR-API-072: Lookalike search must accept seed creator names.
- FR-API-073: Lookalike search must reject an empty seed list.
- FR-API-074: Lookalike search must enforce a maximum seed count.
- FR-API-075: Lookalike search must resolve seed names to existing channels.
- FR-API-076: Lookalike search must return matched channels.
- FR-API-077: Lookalike search must return empty results when no seed channel is found.
- FR-API-078: The backend must expose channel-specific lookalikes.
- FR-API-079: Channel-specific lookalikes must use the selected channel as the seed.

### Scraper Trigger APIs

- FR-API-080: The backend must expose an admin endpoint to trigger scraping.
- FR-API-081: The backend must expose an admin endpoint to trigger discovery.
- FR-API-082: Scraper trigger endpoints must dispatch Celery tasks.
- FR-API-083: Scraper trigger endpoints must return task IDs.

### Admin APIs

- FR-API-084: The backend must expose current admin identity.
- FR-API-085: The backend must expose daily scrape trigger.
- FR-API-086: The backend must expose discovery trigger.
- FR-API-087: The backend must expose never-scraped bootstrap trigger.
- FR-API-088: The backend must expose weekly velocity trigger.
- FR-API-089: The backend must expose Gate0 batch trigger.
- FR-API-090: The backend must expose AI classification trigger.
- FR-API-091: The backend must expose queue purge.
- FR-API-092: The backend must expose worker status.
- FR-API-093: The backend must expose worker logs.
- FR-API-094: The backend must expose task status.
- FR-API-095: The backend must expose admin audit logs.
- FR-API-096: The backend must expose Gate0 competitor settings.
- FR-API-097: The backend must expose keyword taxonomy settings.
- FR-API-098: The backend must support updating Gate0 competitor settings.
- FR-API-099: The backend must support updating keyword taxonomy settings.

## 5. Channel Intake Requirements

### Manual Intake

- FR-INTAKE-001: The frontend must provide manual channel intake.
- FR-INTAKE-002: Manual intake must accept a channel URL.
- FR-INTAKE-003: Manual intake must accept a platform.
- FR-INTAKE-004: Manual intake must validate the URL.
- FR-INTAKE-005: Manual intake must canonicalize Rumble URLs.
- FR-INTAKE-006: Manual intake must canonicalize Substack URLs.
- FR-INTAKE-007: Manual intake must reject URLs that do not match the selected platform.
- FR-INTAKE-008: Manual intake must insert a minimal channel row.
- FR-INTAKE-009: Manual intake must update an existing channel row when the URL already exists.
- FR-INTAKE-010: Manual intake must mark source as `manual_frontend`.
- FR-INTAKE-011: Manual intake must optionally queue an immediate scrape.
- FR-INTAKE-012: Manual intake must optionally queue Gate0 after scrape delay.
- FR-INTAKE-013: Manual intake must return channel creation or update result.

### Bulk Intake

- FR-INTAKE-014: The frontend must provide bulk channel intake.
- FR-INTAKE-015: Bulk intake must accept multiple URLs.
- FR-INTAKE-016: Bulk intake must parse URLs from newline-separated input.
- FR-INTAKE-017: Bulk intake must canonicalize each URL independently.
- FR-INTAKE-018: Bulk intake must report accepted rows.
- FR-INTAKE-019: Bulk intake must report rejected rows.
- FR-INTAKE-020: Bulk intake must optionally queue scrapes for accepted rows.
- FR-INTAKE-021: Bulk intake must optionally queue Gate0 for accepted rows.

### Seed Resolver Intake

- FR-INTAKE-022: The frontend must provide seed-name resolver intake.
- FR-INTAKE-023: Seed resolver must accept creator names.
- FR-INTAKE-024: Seed resolver must enforce a maximum of three seed names.
- FR-INTAKE-025: Seed resolver must search existing channels by name.
- FR-INTAKE-026: Seed resolver must score exact normalized name matches.
- FR-INTAKE-027: Seed resolver must score partial/token name matches.
- FR-INTAKE-028: Seed resolver must guess likely Rumble URLs when no existing match is found.
- FR-INTAKE-029: Seed resolver must guess likely Substack URLs when no existing match is found.
- FR-INTAKE-030: Seed resolver must return candidates grouped by seed.
- FR-INTAKE-031: The frontend must allow users to select resolver candidates.
- FR-INTAKE-032: The frontend must submit selected resolver candidates for intake.

## 6. Discovery Requirements

### Unified Discovery

- FR-DISC-001: The scraper must provide a unified discovery task.
- FR-DISC-002: Unified discovery must support `all` mode.
- FR-DISC-003: Unified discovery must support `seed` mode.
- FR-DISC-004: Unified discovery must support `keyword` mode.
- FR-DISC-005: Unified discovery must reject unsupported modes.
- FR-DISC-006: Unified discovery must support platform restriction.
- FR-DISC-007: Unified discovery must support Rumble discovery.
- FR-DISC-008: Unified discovery must support Substack discovery.
- FR-DISC-009: Unified discovery must reject unsupported discovery platforms.
- FR-DISC-010: Unified discovery must return inserted count.
- FR-DISC-011: Unified discovery must return refreshed count.
- FR-DISC-012: Unified discovery must return duplicate count.
- FR-DISC-013: Unified discovery must return invalid count.
- FR-DISC-014: Unified discovery must return new URL metadata.
- FR-DISC-015: Unified discovery must optionally queue discovered scrapes.

### Discovered Channel Upsert

- FR-DISC-016: Discovery must canonicalize candidate URLs.
- FR-DISC-017: Discovery must look up existing channels by canonical URL.
- FR-DISC-018: Discovery must insert new discovered channels.
- FR-DISC-019: Discovery must refresh discovery evidence for existing channels.
- FR-DISC-020: Discovery must preserve scraped identity data for already-scraped channels.
- FR-DISC-021: Discovery must update latest discovery source.
- FR-DISC-022: Discovery must increment evidence count for existing channels.
- FR-DISC-023: Discovery must store discovery confidence.
- FR-DISC-024: Discovery must store discovery source.
- FR-DISC-025: Discovery must store discovery source reference when available.
- FR-DISC-026: Discovery must store discovery category when available.
- FR-DISC-027: Discovery must store discovery quality tier when available.
- FR-DISC-028: Discovery must store SERP title when available.
- FR-DISC-029: Discovery must store SERP snippet when available.

### Seed Expansion Discovery

- FR-DISC-030: Seed expansion must read existing channels from the database.
- FR-DISC-031: Seed expansion must collect candidate URLs from `contact_info`.
- FR-DISC-032: Seed expansion must collect candidate URLs from `secondary_urls`.
- FR-DISC-033: Seed expansion must collect candidate URLs from `description`.
- FR-DISC-034: Seed expansion must collect candidate URLs from `video_titles`.
- FR-DISC-035: Seed expansion must collect candidate URLs from `channel_url`.
- FR-DISC-036: Seed expansion must extract absolute supported URLs.
- FR-DISC-037: Seed expansion must extract relative Rumble URLs from Rumble source channels.
- FR-DISC-038: Seed expansion must extract relative Substack URLs from Substack source channels.
- FR-DISC-039: Seed expansion must skip self-links.
- FR-DISC-040: Seed expansion must skip expansion from dirty channels.
- FR-DISC-041: Seed expansion must calculate confidence by source field.
- FR-DISC-042: Seed expansion must apply seed quality tier boost.
- FR-DISC-043: Seed expansion must mark source as `auto_seed`.
- FR-DISC-044: Seed expansion must store source channel ID.
- FR-DISC-045: Seed expansion must track field-level metrics.
- FR-DISC-046: Seed expansion must track self-link metrics.
- FR-DISC-047: Seed expansion must respect discovery insert limit.

### Keyword Discovery

- FR-DISC-048: Keyword discovery must read runtime keyword taxonomy.
- FR-DISC-049: Keyword discovery must generate search queries from taxonomy categories.
- FR-DISC-050: Keyword discovery must generate Rumble search queries using Google site search.
- FR-DISC-051: Keyword discovery must generate Substack search queries using Google site search.
- FR-DISC-052: Keyword discovery must exclude Rumble video pages from channel discovery queries.
- FR-DISC-053: Keyword discovery must exclude Substack post pages from publication discovery queries.
- FR-DISC-054: Keyword discovery must use Serper as the Google search provider.
- FR-DISC-055: Keyword discovery must retry transient Serper failures.
- FR-DISC-056: Keyword discovery must parse organic search results.
- FR-DISC-057: Keyword discovery must extract candidate URLs from result links.
- FR-DISC-058: Keyword discovery must extract candidate URLs from result title and snippet text.
- FR-DISC-059: Keyword discovery must validate candidate platform.
- FR-DISC-060: Keyword discovery must mark source as `auto_keyword`.
- FR-DISC-061: Keyword discovery must store discovery category.
- FR-DISC-062: Keyword discovery must store SERP query metadata.
- FR-DISC-063: Keyword discovery must track category metrics.
- FR-DISC-064: Keyword discovery must track inserted count by platform.
- FR-DISC-065: Keyword discovery must stop at discovery insert limit.
- FR-DISC-066: Keyword discovery must stop when query stagnation limit is reached.
- FR-DISC-067: Keyword discovery must generate feedback queries from successful discoveries.
- FR-DISC-068: Keyword discovery must record query statistics.

### Discovery Pre-Classification

- FR-DISC-069: Discovery must optionally pre-classify newly discovered URLs with Google AI.
- FR-DISC-070: Discovery pre-classification must skip high-quality-tier channels.
- FR-DISC-071: Discovery pre-classification must mark off-topic candidates.
- FR-DISC-072: Discovery pre-classification must attach niche hints to candidates.
- FR-DISC-073: Discovery pre-classification must update database rows with niche hints.
- FR-DISC-074: Discovery pre-classification must preserve candidates when AI is unavailable.

### Discovery Scrape Queueing

- FR-DISC-075: Discovery must optionally queue scrapes for new URLs.
- FR-DISC-076: Discovery scrape queueing must prioritize candidates.
- FR-DISC-077: Discovery scrape queueing must route Rumble candidates to Rumble scrape tasks.
- FR-DISC-078: Discovery scrape queueing must route Substack candidates to Substack scrape tasks.
- FR-DISC-079: Discovery scrape queueing must respect new scrape limit.
- FR-DISC-080: Discovery scrape queueing must update channel discovery status when queued.

## 7. Rumble Scraping Requirements

### Rumble Task Dispatch

- FR-RUMBLE-001: The application must provide a Rumble scrape Celery task.
- FR-RUMBLE-002: The Rumble scrape task must validate Rumble channel URL shape.
- FR-RUMBLE-003: The Rumble scrape task must reject unsupported Rumble URL shapes.
- FR-RUMBLE-004: The Rumble scrape task must acquire a scrape lock before scraping.
- FR-RUMBLE-005: The Rumble scrape task must acquire a global scrape slot.
- FR-RUMBLE-006: The Rumble scrape task must acquire a Rumble platform scrape slot.
- FR-RUMBLE-007: The Rumble scrape task must release scrape locks after completion.
- FR-RUMBLE-008: The Rumble scrape task must release platform slots after completion.
- FR-RUMBLE-009: The Rumble scrape task must retry retryable failures.
- FR-RUMBLE-010: The Rumble scrape task must log terminal failures.
- FR-RUMBLE-011: The Rumble scrape task must deactivate terminal invalid channels when appropriate.

### Rumble Browser Scraping

- FR-RUMBLE-012: The Rumble scraper must launch a browser context.
- FR-RUMBLE-013: The Rumble scraper must normalize channel tab URLs.
- FR-RUMBLE-014: The Rumble scraper must load the channel page.
- FR-RUMBLE-015: The Rumble scraper must wait for page content.
- FR-RUMBLE-016: The Rumble scraper must detect Cloudflare or blocking states.
- FR-RUMBLE-017: The Rumble scraper must detect terminal not-found states.
- FR-RUMBLE-018: The Rumble scraper must detect banned or suspended states.
- FR-RUMBLE-019: The Rumble scraper must extract channel name.
- FR-RUMBLE-020: The Rumble scraper must extract follower count.
- FR-RUMBLE-021: The Rumble scraper must parse abbreviated follower counts.
- FR-RUMBLE-022: The Rumble scraper must extract video cards.
- FR-RUMBLE-023: The Rumble scraper must extract video titles.
- FR-RUMBLE-024: The Rumble scraper must extract video URLs.
- FR-RUMBLE-025: The Rumble scraper must extract video views.
- FR-RUMBLE-026: The Rumble scraper must extract video upload dates.
- FR-RUMBLE-027: The Rumble scraper must parse relative dates.
- FR-RUMBLE-028: The Rumble scraper must parse ISO dates.
- FR-RUMBLE-029: The Rumble scraper must parse display dates.
- FR-RUMBLE-030: The Rumble scraper must enrich latest videos from video pages when needed.
- FR-RUMBLE-031: The Rumble scraper must extract video page title.
- FR-RUMBLE-032: The Rumble scraper must extract video page view count.
- FR-RUMBLE-033: The Rumble scraper must extract video page comment count.
- FR-RUMBLE-034: The Rumble scraper must treat explicit empty-comment markers as zero comments.
- FR-RUMBLE-035: The Rumble scraper must avoid broad body-text comment count fallbacks.
- FR-RUMBLE-036: The Rumble scraper must extract about-page description.
- FR-RUMBLE-037: The Rumble scraper must extract about-page social/external links.
- FR-RUMBLE-038: The Rumble scraper must filter internal Rumble links from external links.
- FR-RUMBLE-039: The Rumble scraper must calculate average views.
- FR-RUMBLE-040: The Rumble scraper must calculate average comments.
- FR-RUMBLE-041: The Rumble scraper must calculate posting cadence.
- FR-RUMBLE-042: The Rumble scraper must calculate last active date.
- FR-RUMBLE-043: The Rumble scraper must generate recent video metadata.
- FR-RUMBLE-044: The Rumble scraper must classify channel categories using keyword matching.
- FR-RUMBLE-045: The Rumble scraper must save normalized data to Supabase.

## 8. Substack Scraping Requirements

### Substack Task Dispatch

- FR-SUBSTACK-001: The application must provide a Substack scrape Celery task.
- FR-SUBSTACK-002: The Substack scrape task must validate Substack handle URL shape.
- FR-SUBSTACK-003: The Substack scrape task must reject unsupported Substack URL shapes.
- FR-SUBSTACK-004: The Substack scrape task must acquire a scrape lock before scraping.
- FR-SUBSTACK-005: The Substack scrape task must acquire a global scrape slot.
- FR-SUBSTACK-006: The Substack scrape task must acquire a Substack platform scrape slot.
- FR-SUBSTACK-007: The Substack scrape task must release scrape locks after completion.
- FR-SUBSTACK-008: The Substack scrape task must release platform slots after completion.
- FR-SUBSTACK-009: The Substack scrape task must retry retryable failures.
- FR-SUBSTACK-010: The Substack scrape task must log terminal failures.
- FR-SUBSTACK-011: The Substack scrape task must deactivate terminal invalid channels when appropriate.

### Substack Browser and API Scraping

- FR-SUBSTACK-012: The Substack scraper must normalize publication URLs to `https://substack.com/@handle`.
- FR-SUBSTACK-013: The Substack scraper must reject invalid non-handle URLs.
- FR-SUBSTACK-014: The Substack scraper must launch a browser context.
- FR-SUBSTACK-015: The Substack scraper must navigate to the handle URL.
- FR-SUBSTACK-016: The Substack scraper must use browser navigation to establish Cloudflare/session clearance.
- FR-SUBSTACK-017: The Substack scraper must detect redirected handles.
- FR-SUBSTACK-018: The Substack scraper must fetch public profile data through in-browser `page.evaluate`.
- FR-SUBSTACK-019: The Substack scraper must fetch profile posts through in-browser `page.evaluate`.
- FR-SUBSTACK-020: The Substack scraper must extract publication name.
- FR-SUBSTACK-021: The Substack scraper must extract biography/description.
- FR-SUBSTACK-022: The Substack scraper must extract subscriber count.
- FR-SUBSTACK-023: The Substack scraper must reject hidden subscriber counts when treated as terminal.
- FR-SUBSTACK-024: The Substack scraper must extract user links.
- FR-SUBSTACK-025: The Substack scraper must filter internal Substack links.
- FR-SUBSTACK-026: The Substack scraper must deduplicate contact links.
- FR-SUBSTACK-027: The Substack scraper must extract recent post titles.
- FR-SUBSTACK-028: The Substack scraper must extract recent post URLs.
- FR-SUBSTACK-029: The Substack scraper must extract reaction counts.
- FR-SUBSTACK-030: The Substack scraper must extract comment counts.
- FR-SUBSTACK-031: The Substack scraper must extract post dates.
- FR-SUBSTACK-032: The Substack scraper must parse Substack date formats.
- FR-SUBSTACK-033: The Substack scraper must calculate average reactions/views.
- FR-SUBSTACK-034: The Substack scraper must calculate average comments.
- FR-SUBSTACK-035: The Substack scraper must calculate posting cadence.
- FR-SUBSTACK-036: The Substack scraper must calculate last active date.
- FR-SUBSTACK-037: The Substack scraper must generate recent post metadata.
- FR-SUBSTACK-038: The Substack scraper must classify categories using keyword matching.
- FR-SUBSTACK-039: The Substack scraper must save normalized data to Supabase.

## 9. Shared Scraper Persistence Requirements

- FR-SCRAPE-001: The base scraper must save successful scrape data to the `channels` table.
- FR-SCRAPE-002: The base scraper must upsert channel data by canonical URL.
- FR-SCRAPE-003: The base scraper must set `has_been_scraped` after successful scrape.
- FR-SCRAPE-004: The base scraper must set `last_scraped_at` after successful scrape.
- FR-SCRAPE-005: The base scraper must set `discovery_status` to scraped after successful scrape.
- FR-SCRAPE-006: The base scraper must update metrics after successful scrape.
- FR-SCRAPE-007: The base scraper must update recent videos after successful scrape.
- FR-SCRAPE-008: The base scraper must update contact info after successful scrape.
- FR-SCRAPE-009: The base scraper must update secondary URLs after successful scrape.
- FR-SCRAPE-010: The base scraper must update category tags after successful scrape.
- FR-SCRAPE-011: The base scraper must update comment tier after successful scrape.
- FR-SCRAPE-012: The base scraper must insert a channel snapshot after successful scrape.
- FR-SCRAPE-013: The base scraper must write a successful scrape log.
- FR-SCRAPE-014: The base scraper must write failed scrape logs.
- FR-SCRAPE-015: The base scraper must classify terminal page states.
- FR-SCRAPE-016: The base scraper must reject low-quality parses.
- FR-SCRAPE-017: The base scraper must allow explicit empty channels when configured.
- FR-SCRAPE-018: The base scraper must allow missing external links for otherwise valid channels.
- FR-SCRAPE-019: The base scraper must reset clean Gate0 status to unchecked after new scrape data.

## 10. Browser, Proxy, and Anti-Blocking Requirements

### Browser Requirements

- FR-BROWSER-001: The scraper must launch Chromium through Playwright.
- FR-BROWSER-002: The scraper must support headless browser mode.
- FR-BROWSER-003: The scraper must default to headless mode on Linux.
- FR-BROWSER-004: The scraper must default to headed mode on non-Linux unless overridden.
- FR-BROWSER-005: The scraper must allow environment override for headless mode.
- FR-BROWSER-006: The scraper must configure viewport.
- FR-BROWSER-007: The scraper must configure locale.
- FR-BROWSER-008: The scraper must configure timezone.
- FR-BROWSER-009: The scraper must configure user agent.
- FR-BROWSER-010: The scraper must inject stealth JavaScript.
- FR-BROWSER-011: The scraper must support persistent browser storage state.
- FR-BROWSER-012: The scraper must reuse Cloudflare clearance when possible.
- FR-BROWSER-013: The scraper must pre-warm target homepages for cold sessions.
- FR-BROWSER-014: The scraper must wait for usable page content.
- FR-BROWSER-015: The scraper must collect browser telemetry.

### Browser Pool Requirements

- FR-BROWSER-016: The scraper must maintain a browser pool per worker process.
- FR-BROWSER-017: The browser pool must create isolated contexts per task.
- FR-BROWSER-018: The browser pool must reset safely after worker fork.

### Proxy Requirements

- FR-PROXY-001: The scraper must load proxies from configuration.
- FR-PROXY-002: The scraper must normalize proxy URLs.
- FR-PROXY-003: The scraper must support host-port-user-password proxy format.
- FR-PROXY-004: The scraper must preserve sticky proxy session suffixes.
- FR-PROXY-005: The scraper must validate proxies at startup.
- FR-PROXY-006: The scraper must track proxy success.
- FR-PROXY-007: The scraper must track proxy failure.
- FR-PROXY-008: The scraper must quarantine failing proxies.
- FR-PROXY-009: The scraper must choose proxies by health weighting.
- FR-PROXY-010: The scraper must generate channel-specific proxy sessions.
- FR-PROXY-011: The scraper must mark blocked proxy sessions.
- FR-PROXY-012: The scraper must respect proxy cooldown.

### Cloudflare Requirements

- FR-CF-001: The scraper must detect Cloudflare rate limits.
- FR-CF-002: The scraper must detect Cloudflare JavaScript challenges.
- FR-CF-003: The scraper must detect captchas.
- FR-CF-004: The scraper must classify Cloudflare block reason.
- FR-CF-005: The scraper must identify retryable Cloudflare states.
- FR-CF-006: The scraper must apply human-like delays.
- FR-CF-007: The scraper must apply session rate limiting.
- FR-CF-008: The scraper must rotate sessions when rotation can help.

## 11. Gate0 Requirements

### Gate0 Purpose

- FR-GATE0-001: Gate0 must identify previous gold or precious-metals competitor affiliation.
- FR-GATE0-002: Gate0 must not be treated as a general compliance check.
- FR-GATE0-003: Gate0 must use configured competitor brands and domains.
- FR-GATE0-004: Gate0 must support clean results.
- FR-GATE0-005: Gate0 must support needs-review results.
- FR-GATE0-006: Gate0 must support dirty results.
- FR-GATE0-007: Gate0 must support unchecked channel status.
- FR-GATE0-008: Gate0 must support pending channel status.

### Gate0 Eligibility

- FR-GATE0-009: Gate0 must skip dirty channels during automatic rechecks.
- FR-GATE0-010: Gate0 must skip needs-review channels during automatic rechecks.
- FR-GATE0-011: Gate0 must skip recently checked clean channels.
- FR-GATE0-012: Gate0 must allow manual override for dirty channels.
- FR-GATE0-013: Gate0 must allow manual override for needs-review channels.
- FR-GATE0-014: Gate0 must clear pending status when runtime settings are unavailable.
- FR-GATE0-015: Gate0 must clear pending status when Gate0 is disabled.
- FR-GATE0-016: Gate0 must clear pending status when no competitors are configured.

### Local Evidence Scanning

- FR-GATE0-017: Gate0 must scan contact links.
- FR-GATE0-018: Gate0 must scan secondary URLs.
- FR-GATE0-019: Gate0 must scan description text.
- FR-GATE0-020: Gate0 must scan video titles.
- FR-GATE0-021: Gate0 must detect competitor domains in contact links.
- FR-GATE0-022: Gate0 must detect competitor domains in secondary URLs.
- FR-GATE0-023: Gate0 must detect competitor brand names in contact links.
- FR-GATE0-024: Gate0 must detect competitor domains in description text.
- FR-GATE0-025: Gate0 must detect competitor brand names in description text.
- FR-GATE0-026: Gate0 must detect competitor brand names in video titles.
- FR-GATE0-027: Gate0 must detect redirected links to competitor domains.
- FR-GATE0-028: Gate0 must detect affiliate URL patterns.
- FR-GATE0-029: Gate0 must increase confidence when promo language appears near competitor mentions.
- FR-GATE0-030: Gate0 must suppress some matches when negative context appears near competitor mentions.
- FR-GATE0-031: Gate0 must produce evidence signals for local matches.

### Search Evidence Scanning

- FR-GATE0-032: Gate0 must build affiliation-targeted Serper queries.
- FR-GATE0-033: Gate0 must build competitor-specific queries.
- FR-GATE0-034: Gate0 must build site queries against competitor domains.
- FR-GATE0-035: Gate0 must run Serper searches when local evidence is below dirty threshold.
- FR-GATE0-036: Gate0 must skip Serper search when local evidence already reaches dirty threshold.
- FR-GATE0-037: Gate0 must detect channel appearances on competitor websites.
- FR-GATE0-038: Gate0 must detect competitor domains in third-party search result text.
- FR-GATE0-039: Gate0 must detect brand plus promo language in search results.
- FR-GATE0-040: Gate0 must deduplicate repeated search-result source URLs.
- FR-GATE0-041: Gate0 must compound independent Serper hits.
- FR-GATE0-042: Gate0 must stop search early when dirty threshold is reached.
- FR-GATE0-043: Gate0 must produce evidence signals for search matches.

### Gate0 Confidence

- FR-GATE0-044: Gate0 must compound confidence from independent evidence weights.
- FR-GATE0-045: Gate0 must classify confidence greater than or equal to `0.95` as dirty.
- FR-GATE0-046: Gate0 must classify confidence greater than or equal to `0.80` and below `0.95` as needs review.
- FR-GATE0-047: Gate0 must classify confidence below `0.80` as clean.
- FR-GATE0-048: Gate0 must only store flagged brand on non-clean results.
- FR-GATE0-049: Gate0 must only store source URL on non-clean results.

### Gate0 Persistence

- FR-GATE0-050: Gate0 must insert a detailed result row.
- FR-GATE0-051: Gate0 must update cached channel Gate0 status.
- FR-GATE0-052: Gate0 must update cached channel flagged brand.
- FR-GATE0-053: Gate0 must update cached channel source URL.
- FR-GATE0-054: Gate0 must update cached channel checked time.
- FR-GATE0-055: Gate0 must update cached latest Gate0 result ID.
- FR-GATE0-056: Gate0 must update cached latest Gate0 search query.
- FR-GATE0-057: Gate0 must update cached latest Gate0 result status.

### Gate0 Batch

- FR-GATE0-058: Gate0 batch must fetch eligible channels.
- FR-GATE0-059: Gate0 batch must normally queue unchecked and pending channels.
- FR-GATE0-060: Gate0 batch must support rechecking clean channels.
- FR-GATE0-061: Gate0 batch must support force-all mode.
- FR-GATE0-062: Gate0 batch must support dashboard-eligible-only mode.
- FR-GATE0-063: Gate0 batch must mark queued channels pending.
- FR-GATE0-064: Gate0 batch must dispatch one task per queued channel.

## 12. AI Classification Requirements

### Classification Selection

- FR-AI-001: The classification task must select active scraped dashboard-eligible channels.
- FR-AI-002: The classification task must classify channels with missing tags.
- FR-AI-003: The classification task must classify channels with unknown tags.
- FR-AI-004: The classification task must classify channels missing AI summary.
- FR-AI-005: The classification task must classify channels when context improves.
- FR-AI-006: The classification task must support forced reclassification.
- FR-AI-007: The classification task must support classifying all eligible channels.

### AI Classification Output

- FR-AI-008: The classification task must call Google AI.
- FR-AI-009: The classification task must ask for primary channel category.
- FR-AI-010: The classification task must ask for channel summary.
- FR-AI-011: The classification task must ask for confidence.
- FR-AI-012: The classification task must parse fenced JSON responses.
- FR-AI-013: The classification task must parse prefixed JSON responses.
- FR-AI-014: The classification task must parse candidate-part response text.
- FR-AI-015: The classification task must reconcile AI categories with keyword categories.
- FR-AI-016: The classification task must store final niche tags.
- FR-AI-017: The classification task must store AI summary.
- FR-AI-018: The classification task must store classification confidence.
- FR-AI-019: The classification task must store needs-review classification flag.
- FR-AI-020: The classification task must store classification context score.

### AI Channel Report

- FR-AI-021: The classification task must generate an AI channel report.
- FR-AI-022: The AI report must use channel metrics as input.
- FR-AI-023: The AI report must use channel description as input.
- FR-AI-024: The AI report must use recent titles as input.
- FR-AI-025: The AI report must use contact links as input.
- FR-AI-026: The AI report must use category tags as input.
- FR-AI-027: The AI report must use scrape history as input.
- FR-AI-028: The AI report must use Gate0 status as input.
- FR-AI-029: The AI report must mention previous gold affiliation when detected.
- FR-AI-030: The AI report must avoid calling competitor-affiliated channels clean outreach targets without review.
- FR-AI-031: The AI report must store narrative text in `ai_channel_report`.

## 13. Keyword Matching Requirements

- FR-KEYWORD-001: The application must load keyword taxonomy from runtime settings.
- FR-KEYWORD-002: The application must cache keyword taxonomy briefly.
- FR-KEYWORD-003: The application must match keywords against channel name.
- FR-KEYWORD-004: The application must match keywords against channel description.
- FR-KEYWORD-005: The application must match keywords against video or post titles.
- FR-KEYWORD-006: The application must use word-boundary matching.
- FR-KEYWORD-007: The application must avoid substring false positives.
- FR-KEYWORD-008: The application must weight channel name matches higher than description matches.
- FR-KEYWORD-009: The application must weight description matches higher than single title matches.
- FR-KEYWORD-010: The application must require enough weak title evidence before assigning a category.
- FR-KEYWORD-011: The application must sort categories by score.
- FR-KEYWORD-012: The application must return `Unknown / Needs Review` when no category matches.
- FR-KEYWORD-013: The application must compute comment tier from average comments.
- FR-KEYWORD-014: The application must classify 10 to below 20 average comments as `active`.
- FR-KEYWORD-015: The application must classify 20 to 100 average comments as `sweet_spot`.
- FR-KEYWORD-016: The application must classify above 100 average comments as `whale`.

## 14. Velocity Requirements

### Velocity Computation

- FR-VEL-001: The application must compute velocity from channel snapshots.
- FR-VEL-002: Velocity computation must load snapshots for a channel.
- FR-VEL-003: Velocity computation must identify the latest snapshot.
- FR-VEL-004: Velocity computation must identify a 30-day comparison snapshot.
- FR-VEL-005: Velocity computation must identify a 90-day comparison snapshot.
- FR-VEL-006: Velocity computation must calculate 30-day view velocity.
- FR-VEL-007: Velocity computation must calculate 90-day view velocity.
- FR-VEL-008: Velocity computation must calculate 30-day comment velocity.
- FR-VEL-009: Velocity computation must calculate 90-day comment velocity.
- FR-VEL-010: Velocity computation must return null when historical value is missing.
- FR-VEL-011: Velocity computation must return null when historical value is zero.
- FR-VEL-012: Velocity computation must update velocity fields on `channels`.
- FR-VEL-013: Velocity computation must set velocity computed time.

### Weekly Velocity Workflow

- FR-VEL-014: The application must provide a weekly velocity workflow.
- FR-VEL-015: Weekly velocity workflow must select clean channels.
- FR-VEL-016: Weekly velocity workflow must select channels with sufficient comment metrics.
- FR-VEL-017: Weekly velocity workflow must skip channels with recent snapshots.
- FR-VEL-018: Weekly velocity workflow must queue platform scrapes for selected channels.
- FR-VEL-019: Weekly velocity workflow must compute velocity after scrape refresh.

## 15. Lookalike Requirements

- FR-LOOK-001: The application must accept seed creator names for lookalike search.
- FR-LOOK-002: The application must normalize seed names.
- FR-LOOK-003: The application must find seed channels by exact normalized name.
- FR-LOOK-004: The application must find seed channels by token overlap fallback.
- FR-LOOK-005: The application must fetch active dashboard-eligible candidate channels.
- FR-LOOK-006: The application must exclude the seed channel from matches.
- FR-LOOK-007: The application must require at least one overlapping niche tag.
- FR-LOOK-008: The application must require subscriber count similarity.
- FR-LOOK-009: The application must accept candidates at 90 percent of seed subscribers.
- FR-LOOK-010: The application must accept candidates at 110 percent of seed subscribers.
- FR-LOOK-011: The application must reject candidates outside the subscriber similarity band.
- FR-LOOK-012: The application must include match detail text.
- FR-LOOK-013: The application must enrich matches with channel data.
- FR-LOOK-014: The application must return no matches when the seed channel is missing.

## 16. Admin Requirements

### Admin Task Control

- FR-ADMIN-001: Admins must be able to trigger daily scrape.
- FR-ADMIN-002: Admins must be able to trigger discovery.
- FR-ADMIN-003: Admins must be able to trigger never-scraped bootstrap.
- FR-ADMIN-004: Admins must be able to trigger weekly velocity scrape.
- FR-ADMIN-005: Admins must be able to trigger Gate0 batch.
- FR-ADMIN-006: Admins must be able to trigger AI classification for unclassified channels.
- FR-ADMIN-007: Admins must be able to trigger AI classification for all eligible channels.
- FR-ADMIN-008: Admin task triggers must display queued task information.
- FR-ADMIN-009: Admin task triggers must poll task status.
- FR-ADMIN-010: Admin task polling must stop for terminal task states.

### Admin Worker Operations

- FR-ADMIN-011: Admins must be able to view worker status.
- FR-ADMIN-012: Admins must be able to view worker queues.
- FR-ADMIN-013: Admins must be able to view worker logs.
- FR-ADMIN-014: Admin worker status must refresh periodically.
- FR-ADMIN-015: Admin worker logs must refresh periodically when requested.

### Admin Queue Purge

- FR-ADMIN-016: Admins must be able to purge queues.
- FR-ADMIN-017: Queue purge must revoke active tasks.
- FR-ADMIN-018: Queue purge must revoke reserved tasks.
- FR-ADMIN-019: Queue purge must revoke scheduled tasks.
- FR-ADMIN-020: Queue purge must purge broker queues.
- FR-ADMIN-021: Queue purge must delete stale Redis task metadata.
- FR-ADMIN-022: Queue purge must support worker pool restart.
- FR-ADMIN-023: Queue purge must be treated as a danger action in the UI.

### Admin Competitor Settings

- FR-ADMIN-024: Admins must be able to view Gate0 competitors.
- FR-ADMIN-025: Admins must be able to add Gate0 competitors.
- FR-ADMIN-026: Admins must be able to edit Gate0 competitor brands.
- FR-ADMIN-027: Admins must be able to edit Gate0 competitor domains.
- FR-ADMIN-028: Admins must be able to remove Gate0 competitors.
- FR-ADMIN-029: Gate0 competitor updates must be audited.

### Admin Taxonomy Settings

- FR-ADMIN-030: Admins must be able to view keyword taxonomy.
- FR-ADMIN-031: Admins must be able to update keywords per taxonomy category.
- FR-ADMIN-032: Keyword taxonomy updates must validate allowed broad categories.
- FR-ADMIN-033: Keyword taxonomy updates must be audited.

### Admin Audit

- FR-ADMIN-034: Admins must be able to view recent audit entries.
- FR-ADMIN-035: Admin audit entries must include action names.
- FR-ADMIN-036: Admin audit entries must include timestamps.
- FR-ADMIN-037: Admin audit entries must include metadata when available.

## 17. Frontend Layout Requirements

### App Shell

- FR-FE-001: The frontend must render a root app layout.
- FR-FE-002: The frontend must load global styles.
- FR-FE-003: The frontend must use the configured font.
- FR-FE-004: The dashboard layout must include a top navigation bar.
- FR-FE-005: The dashboard layout must render protected dashboard content.
- FR-FE-006: The auth layout must center the login form.
- FR-FE-007: The frontend must provide a 404 page.
- FR-FE-008: The frontend must provide a dashboard loading state.
- FR-FE-009: The frontend must provide a dashboard error boundary.

### Navigation

- FR-FE-010: The top bar must link to the channel dashboard.
- FR-FE-011: The top bar must show admin navigation for admins when available.
- FR-FE-012: The top bar must provide sign-out behavior.

## 18. Frontend Channel Dashboard Requirements

### Channel Table View

- FR-FE-013: The dashboard must render a channel table.
- FR-FE-014: The dashboard must render filter controls.
- FR-FE-015: The dashboard must render pagination controls.
- FR-FE-016: The dashboard must render loading state during initial load.
- FR-FE-017: The dashboard must preserve existing rows during background refresh.
- FR-FE-018: The dashboard must persist filters in session storage.
- FR-FE-019: The dashboard must persist current page in session storage.
- FR-FE-020: The dashboard must persist scroll position in session storage.
- FR-FE-021: The dashboard must restore persisted filters when revisited.
- FR-FE-022: The dashboard must restore persisted page when revisited.
- FR-FE-023: The dashboard must restore persisted scroll position when revisited.
- FR-FE-024: The dashboard must fetch category options.
- FR-FE-025: The dashboard must fetch Gate0 status options.
- FR-FE-026: The dashboard must support opening channel intake modal.

### Channel Table Columns

- FR-FE-027: The channel table must display channel identity.
- FR-FE-028: The channel table must display platform.
- FR-FE-029: The channel table must display subscriber count.
- FR-FE-030: The channel table must display primary niche/category.
- FR-FE-031: The channel table must display average views or likes.
- FR-FE-032: The channel table must display average comments.
- FR-FE-033: The channel table must display engagement rate.
- FR-FE-034: The channel table must display previous gold affiliation status.
- FR-FE-035: The channel table must display last active time.
- FR-FE-036: The channel table must link rows to channel detail pages.
- FR-FE-037: The channel table must render an empty state when no rows match.

### Filters

- FR-FE-038: The filter sidebar must support search.
- FR-FE-039: The filter sidebar must support platform filtering.
- FR-FE-040: The filter sidebar must support category filtering.
- FR-FE-041: The filter sidebar must support comment tier filtering.
- FR-FE-042: The filter sidebar must support previous gold affiliation filtering.
- FR-FE-043: The filter sidebar must support subscriber range filtering.
- FR-FE-044: The filter sidebar must support average views range filtering.
- FR-FE-045: The filter sidebar must support average comments range filtering.
- FR-FE-046: The filter sidebar must support engagement rate range filtering.
- FR-FE-047: The filter sidebar must support last active date filtering.
- FR-FE-048: The filter sidebar must support inactive exclusion.
- FR-FE-049: The filter sidebar must support incomplete-only filtering.
- FR-FE-050: The filter sidebar must support sorting.
- FR-FE-051: The filter sidebar must show active filter count.
- FR-FE-052: The filter sidebar must allow clearing all filters.
- FR-FE-053: Numeric range filters must support slider input.
- FR-FE-054: Numeric range filters must support manual min input.
- FR-FE-055: Numeric range filters must support manual max input.

### Realtime Refresh

- FR-FE-056: The channel dashboard must subscribe to channel row changes.
- FR-FE-057: The channel dashboard must subscribe to Gate0 result changes.
- FR-FE-058: The channel dashboard must debounce realtime refreshes.
- FR-FE-059: The channel dashboard must use polling as a fallback refresh mechanism.
- FR-FE-060: The channel dashboard must avoid stale response overwrites.

## 19. Frontend Channel Detail Requirements

- FR-FE-061: The channel detail page must require authentication.
- FR-FE-062: The channel detail page must fetch channel data.
- FR-FE-063: The channel detail page must fetch latest Gate0 evidence.
- FR-FE-064: The channel detail page must fetch recent scrape logs.
- FR-FE-065: The channel detail page must render channel header.
- FR-FE-066: The channel detail page must render core metrics.
- FR-FE-067: The channel detail page must render subscriber count.
- FR-FE-068: The channel detail page must render average views or likes.
- FR-FE-069: The channel detail page must render average comments.
- FR-FE-070: The channel detail page must render engagement rate.
- FR-FE-071: The channel detail page must render posting cadence.
- FR-FE-072: The channel detail page must render last active date.
- FR-FE-073: The channel detail page must render velocity metrics.
- FR-FE-074: The channel detail page must render AI summary.
- FR-FE-075: The channel detail page must render AI channel report.
- FR-FE-076: The channel detail page must render description.
- FR-FE-077: The channel detail page must render recent videos or posts.
- FR-FE-078: The channel detail page must render contact information.
- FR-FE-079: The channel detail page must render secondary URLs.
- FR-FE-080: The channel detail page must render category tags.
- FR-FE-081: The channel detail page must render lookalike matches.
- FR-FE-082: The channel detail page must render scrape history.
- FR-FE-083: The channel detail page must render previous gold affiliation history.
- FR-FE-084: The channel detail page must render Gate0 confidence.
- FR-FE-085: The channel detail page must render Gate0 evidence signals.
- FR-FE-086: The channel detail page must render Gate0 source URL as a link when available.
- FR-FE-087: The channel detail page must allow updating do-not-contact status.
- FR-FE-088: The channel detail page must allow clearing do-not-contact status.
- FR-FE-089: The channel detail page must allow deleting scrape history.
- FR-FE-090: The channel detail page must allow deleting the channel.
- FR-FE-091: The channel detail page must subscribe to channel changes.
- FR-FE-092: The channel detail page must subscribe to Gate0 result changes.
- FR-FE-093: The channel detail page must refresh after relevant realtime changes.

## 20. Frontend Lookalike Requirements

- FR-FE-094: The frontend must provide a lookalike search page.
- FR-FE-095: The lookalike page must accept seed creator names.
- FR-FE-096: The lookalike page must enforce a maximum of three seed rows.
- FR-FE-097: The lookalike page must allow adding seed rows.
- FR-FE-098: The lookalike page must allow removing seed rows.
- FR-FE-099: The lookalike page must reject empty searches.
- FR-FE-100: The lookalike page must call the backend lookalike API.
- FR-FE-101: The lookalike page must render lookalike results.
- FR-FE-102: The lookalike page must render empty state.
- FR-FE-103: The lookalike page must render errors.
- FR-FE-104: Lookalike match cards must display channel information.
- FR-FE-105: Lookalike match cards must display match type.
- FR-FE-106: Lookalike match cards must display match detail.
- FR-FE-107: Lookalike match cards must display Gate0 badge when available.

## 21. Frontend Admin Requirements

- FR-FE-108: The admin page must require admin authorization.
- FR-FE-109: The admin page must render admin identity.
- FR-FE-110: The admin page must render manual task controls.
- FR-FE-111: The admin page must render task status feedback.
- FR-FE-112: The admin page must render worker status.
- FR-FE-113: The admin page must render worker logs.
- FR-FE-114: The admin page must render queue purge controls.
- FR-FE-115: The admin page must render audit log.
- FR-FE-116: The admin page must render Gate0 competitor editor.
- FR-FE-117: The admin page must render keyword taxonomy editor.
- FR-FE-118: The admin page must support manual channel IDs for Gate0 batch.
- FR-FE-119: The admin page must support classify-unclassified action.
- FR-FE-120: The admin page must support classify-all action.
- FR-FE-121: The admin page must show success messages.
- FR-FE-122: The admin page must show error messages.
- FR-FE-123: The admin page must poll task state until terminal.

## 22. UI Component Requirements

- FR-UI-001: The application must provide reusable buttons.
- FR-UI-002: Buttons must support variants.
- FR-UI-003: Buttons must support sizes.
- FR-UI-004: Buttons must support disabled state.
- FR-UI-005: The application must provide reusable badges.
- FR-UI-006: Badges must support variants.
- FR-UI-007: The application must provide reusable tables.
- FR-UI-008: Tables must support horizontal overflow.
- FR-UI-009: Tables must support wheel handling for scrollable content.
- FR-UI-010: The application must provide reusable inputs.
- FR-UI-011: Inputs must support labels.
- FR-UI-012: Inputs must support error messages.
- FR-UI-013: The application must provide reusable dropdowns.
- FR-UI-014: Dropdowns must support labeled options.
- FR-UI-015: The application must provide a loading spinner.
- FR-UI-016: Gate0 badge must display unchecked state.
- FR-UI-017: Gate0 badge must display pending state.
- FR-UI-018: Gate0 badge must display clean state.
- FR-UI-019: Gate0 badge must display needs-review state.
- FR-UI-020: Gate0 badge must display dirty state.
- FR-UI-021: Gate0 badge must show competitor-specific label when brand is known.
- FR-UI-022: Velocity badge must display unavailable state.
- FR-UI-023: Velocity badge must display positive movement.
- FR-UI-024: Velocity badge must display negative movement.
- FR-UI-025: Comment tier badge must display known tiers.

## 23. Formatting and Utility Requirements

- FR-UTIL-001: The frontend must format large numbers for display.
- FR-UTIL-002: The frontend must format velocity percentages.
- FR-UTIL-003: The frontend must format engagement rates.
- FR-UTIL-004: The frontend must cap displayed engagement rate at 100 percent.
- FR-UTIL-005: The frontend must format relative times.
- FR-UTIL-006: The frontend must identify inactive channels.
- FR-UTIL-007: The frontend must truncate long text.
- FR-UTIL-008: The frontend must merge class names safely.
- FR-UTIL-009: The scraper must parse abbreviated count text.
- FR-UTIL-010: The scraper must parse comma-formatted count text.
- FR-UTIL-011: The scraper must parse relative dates.
- FR-UTIL-012: The scraper must parse ISO dates.
- FR-UTIL-013: The scraper must extract emails from text.
- FR-UTIL-014: The scraper must extract URLs from text.
- FR-UTIL-015: The scraper must canonicalize supported channel URLs.
- FR-UTIL-016: The scraper must extract supported channel URLs from text.
- FR-UTIL-017: The scraper must extract JSON text from AI responses.

## 24. Import and Bootstrap Requirements

### CSV Name Resolver

- FR-IMPORT-001: The CSV resolver must read influencer names from CSV.
- FR-IMPORT-002: The CSV resolver must normalize seed names.
- FR-IMPORT-003: The CSV resolver must split aliases.
- FR-IMPORT-004: The CSV resolver must search Serper for Rumble candidates.
- FR-IMPORT-005: The CSV resolver must search Serper for Substack candidates.
- FR-IMPORT-006: The CSV resolver must reject generic platform pages.
- FR-IMPORT-007: The CSV resolver must reject ambiguous close-score candidates.
- FR-IMPORT-008: The CSV resolver must verify selected candidates when possible.
- FR-IMPORT-009: The CSV resolver must insert resolved channels when requested.
- FR-IMPORT-010: The CSV resolver must update existing channels when requested.
- FR-IMPORT-011: The CSV resolver must write a resolution report.

### XLSX Rumble Import

- FR-IMPORT-012: The XLSX importer must read influencer rows from workbook sheets.
- FR-IMPORT-013: The XLSX importer must detect header columns.
- FR-IMPORT-014: The XLSX importer must extract direct Rumble URLs from cells.
- FR-IMPORT-015: The XLSX importer must canonicalize direct Rumble URLs.
- FR-IMPORT-016: The XLSX importer must prefer direct Excel URLs over search results.
- FR-IMPORT-017: The XLSX importer must use Serper when no direct URL exists.
- FR-IMPORT-018: The XLSX importer must reject ambiguous search candidates.
- FR-IMPORT-019: The XLSX importer must deduplicate against existing primary channel URLs.
- FR-IMPORT-020: The XLSX importer must deduplicate against existing secondary URLs.
- FR-IMPORT-021: The XLSX importer must insert selected channels when requested.
- FR-IMPORT-022: The XLSX importer must produce an import report.

### Substack Leaderboard Import

- FR-IMPORT-023: The Substack leaderboard scraper must open configured leaderboard pages.
- FR-IMPORT-024: The Substack leaderboard scraper must scroll lazy-loaded leaderboard entries.
- FR-IMPORT-025: The Substack leaderboard scraper must extract publication links.
- FR-IMPORT-026: The Substack leaderboard scraper must canonicalize publication handles.
- FR-IMPORT-027: The Substack leaderboard scraper must deduplicate handles.
- FR-IMPORT-028: The Substack leaderboard scraper must insert new leaderboard channels.
- FR-IMPORT-029: The Substack leaderboard scraper must refresh existing leaderboard channels.
- FR-IMPORT-030: The Substack leaderboard scraper must support dry-run mode.

## 25. Scheduling Requirements

- FR-SCHED-001: The application must provide a daily scrape schedule.
- FR-SCHED-002: The application must provide a weekly velocity schedule.
- FR-SCHED-003: Scheduled tasks must dispatch through Celery beat.
- FR-SCHED-004: Scheduled daily scrape must respect runtime feature settings.
- FR-SCHED-005: Scheduled weekly velocity must target clean qualified channels.

## 26. Queue and Task Requirements

- FR-TASK-001: The application must use Redis as Celery broker.
- FR-TASK-002: The application must define a discovery queue.
- FR-TASK-003: The application must define a classify queue.
- FR-TASK-004: The application must define a Gate0 queue.
- FR-TASK-005: The application must define a Rumble queue.
- FR-TASK-006: The application must define a Substack queue.
- FR-TASK-007: The application must route discovery tasks to the discovery queue.
- FR-TASK-008: The application must route classification tasks to the classify queue.
- FR-TASK-009: The application must route Gate0 tasks to the Gate0 queue.
- FR-TASK-010: The application must route Rumble scrape tasks to the Rumble queue.
- FR-TASK-011: The application must route Substack scrape tasks to the Substack queue.
- FR-TASK-012: Tasks must support late acknowledgements.
- FR-TASK-013: Workers must limit prefetch to avoid over-reservation.
- FR-TASK-014: Tasks must define time limits.
- FR-TASK-015: The application must expose task status to admins.

## 27. Error Handling Requirements

- FR-ERR-001: The backend must return structured errors for domain exceptions.
- FR-ERR-002: The backend must return 404 for missing resources.
- FR-ERR-003: The backend must return validation errors for invalid requests.
- FR-ERR-004: The backend must log unexpected errors.
- FR-ERR-005: The frontend must display login errors.
- FR-ERR-006: The frontend must display dashboard load errors.
- FR-ERR-007: The frontend must display admin task errors.
- FR-ERR-008: Scrapers must classify retryable errors.
- FR-ERR-009: Scrapers must classify terminal errors.
- FR-ERR-010: Scrapers must retry retryable failures with jitter.
- FR-ERR-011: Scrapers must avoid overwriting good data with failed parse output.
- FR-ERR-012: Tasks must clear stuck pending Gate0 state when appropriate.
- FR-ERR-013: Discovery must continue when one phase fails and the other phase succeeds.
- FR-ERR-014: Discovery must return error metadata when a phase fails.

## 28. Observability Requirements

- FR-OBS-001: The backend must log incoming requests.
- FR-OBS-002: The backend must log startup dependency failures.
- FR-OBS-003: Scraper tasks must log task start and completion.
- FR-OBS-004: Scraper tasks must log scrape failures.
- FR-OBS-005: Discovery must log progress.
- FR-OBS-006: Gate0 must log completed results.
- FR-OBS-007: Admin UI must expose worker status.
- FR-OBS-008: Admin UI must expose worker logs.
- FR-OBS-009: Admin UI must expose task status.
- FR-OBS-010: Admin UI must expose audit history.

## 29. Security Requirements

- FR-SEC-001: Supabase service role key must only be used server-side.
- FR-SEC-002: Frontend must only use public Supabase anon credentials.
- FR-SEC-003: Backend protected endpoints must require bearer tokens.
- FR-SEC-004: Admin endpoints must require admin role metadata.
- FR-SEC-005: Secrets must be loaded from environment variables.
- FR-SEC-006: Secrets must not be committed.
- FR-SEC-007: CORS must restrict allowed frontend origins.
- FR-SEC-008: Service-role writes must be performed only by backend or scraper code.

## 30. Performance Requirements

- FR-PERF-001: Channel dashboard queries must use indexed fields where available.
- FR-PERF-002: Engagement rate sorting must use a stored generated column.
- FR-PERF-003: Name search must support trigram search.
- FR-PERF-004: URL search must support trigram search.
- FR-PERF-005: Description search must support trigram search.
- FR-PERF-006: Category filtering must use GIN index on niche tags.
- FR-PERF-007: Dashboard filters must debounce client requests.
- FR-PERF-008: Realtime refreshes must debounce updates.
- FR-PERF-009: Scrape dispatch must batch and stagger jobs.
- FR-PERF-010: Browser pool must reduce browser launch overhead.
- FR-PERF-011: Scrape slots must limit concurrent platform load.
- FR-PERF-012: Global scrape slots must limit total scraper load.
- FR-PERF-013: Token validation cache must reduce repeated auth calls.

## 31. Compatibility and Legacy Requirements

- FR-COMPAT-001: The backend must preserve legacy category/niche filter aliases.
- FR-COMPAT-002: The backend must expose legacy category tag route aliases where present.
- FR-COMPAT-003: Discovery wrapper tasks must continue to call unified discovery.
- FR-COMPAT-004: Existing scraped channels must not lose identity data during discovery refresh.
- FR-COMPAT-005: Existing migration constraints must be safely dropped before replacement.

## 32. Non-Goals Implied by Current Code

These are not functional requirements of the current implementation, based on the active code.

- NFR-NONGOAL-001: The application is not required to support BitChute as an active platform.
- NFR-NONGOAL-002: Gate0 is not a general compliance review.
- NFR-NONGOAL-003: Discovery is not based on RSS feeds.
- NFR-NONGOAL-004: Discovery is not based on Rumble category pages in the active discovery task.
- NFR-NONGOAL-005: Discovery is not based on a Rumble discovery API in the active discovery task.
- NFR-NONGOAL-006: Backend lookalike search is not required to persist matches in the current active service path.

## 33. Acceptance Coverage Checklist

The functional coverage is complete only when these areas are represented by tests, manual QA, or operational verification:

- FR-CHECK-001: Authentication and route protection.
- FR-CHECK-002: Admin authorization.
- FR-CHECK-003: Channel list filters.
- FR-CHECK-004: Channel sorting.
- FR-CHECK-005: Channel detail rendering.
- FR-CHECK-006: Manual intake.
- FR-CHECK-007: Bulk intake.
- FR-CHECK-008: Seed resolver intake.
- FR-CHECK-009: Discovery seed expansion.
- FR-CHECK-010: Discovery keyword expansion.
- FR-CHECK-011: Discovery scrape queueing.
- FR-CHECK-012: Rumble scrape parsing.
- FR-CHECK-013: Substack scrape parsing.
- FR-CHECK-014: Scrape persistence.
- FR-CHECK-015: Scrape failure handling.
- FR-CHECK-016: Browser/proxy startup.
- FR-CHECK-017: Cloudflare classification.
- FR-CHECK-018: Gate0 local evidence.
- FR-CHECK-019: Gate0 search evidence.
- FR-CHECK-020: Gate0 status persistence.
- FR-CHECK-021: AI classification.
- FR-CHECK-022: AI report generation.
- FR-CHECK-023: Keyword matching.
- FR-CHECK-024: Velocity computation.
- FR-CHECK-025: Weekly velocity workflow.
- FR-CHECK-026: Lookalike matching.
- FR-CHECK-027: Admin task triggering.
- FR-CHECK-028: Worker status and logs.
- FR-CHECK-029: Queue purge.
- FR-CHECK-030: Competitor settings.
- FR-CHECK-031: Keyword taxonomy settings.
- FR-CHECK-032: Audit logging.
- FR-CHECK-033: Importer dry runs.
- FR-CHECK-034: Importer live insert/update behavior.
- FR-CHECK-035: Frontend realtime refresh.
- FR-CHECK-036: Frontend error states.

