# Performance Optimization Audit — Channel Scraper (BitChute + Rumble)

Date: 2026-05-25  
Targets: `scraper/scrapers/bitchute.py`, `scraper/scrapers/rumble.py`, `scraper/core/browser.py`

## Section 1 — Critical Path Analysis

### 1A) Current Critical Path (Rumble)

| Step | Operation | Type | Est. Duration | Parallelizable? | Skippable? |
|---|---|---:|---:|---|---|
| 1 | `context.new_page()` then `page.goto(channel_url)` (`rumble.py:265-270`) | NAVIGATION + NETWORK | 3-8s | No | No |
| 2 | `human_delay(0.2,0.8)` (`272`) | SLEEP | 0.2-0.8s | No | Replaceable |
| 3 | `wait_for_content` primary (`274-276`) | RENDER | 0.5-6s | No | No |
| 4 | `wait_for_selector(video card)` + `human_delay(0.15,0.6)` (`320-324`) | RENDER + SLEEP | 0.3-2.0s | No | Delay replaceable |
| 5 | `_collect_videos_with_scroll` (`331`, `661-712`) with repeated `page.content()+BS` + scroll delays | INTERACTION + PARSE + SLEEP | 2-9s | Partial | Partial |
| 6 | About fetch loop (`359-410`) incl. `new_page`, `goto`, delay, `wait_for_content`, parse | NAVIGATION + NETWORK + SLEEP + PARSE | 2-10s | Yes (vs step 5) | No |
| 7 | Fallback video page loop serial (`434-467`, `889-929`) | NAVIGATION + NETWORK + RENDER + SLEEP + PARSE | 0-60s | Yes (bounded) | Partial |
| 8 | Aggregations + quality checks + persistence (`469-608`) | PARSE/CPU + NETWORK(write) | 0.2-1.5s | No | No |

**Sequential baseline estimate (Rumble):**
- Best-case (no fallback): ~8-20s
- Worst-case (fallback 10 pages): ~45-90s

### 1B) Current Critical Path (BitChute)

| Step | Operation | Type | Est. Duration | Parallelizable? | Skippable? |
|---|---|---:|---:|---|---|
| 1 | `context.new_page()` + `goto(channel)` (`bitchute.py:142-148`) | NAVIGATION + NETWORK | 4-12s | No | No |
| 2 | `human_delay(0.2,0.8)` (`150`) | SLEEP | 0.2-0.8s | No | Replaceable |
| 3 | `wait_for_content` primary (`153-155`) | RENDER | 1-10s | No | No |
| 4 | 3 scroll cycles + delay (`210-214`) | INTERACTION + SLEEP | 1.4-4.2s | No | Conservative |
| 5 | Hydration wait (`220-223`) + card extraction loop (live locators) (`227-321`) | RENDER + PARSE | 1-6s | No | No |
| 6 | Optional Videos tab click + delay (`230-247`) | INTERACTION + SLEEP | 0-2s | No | Conservative |
| 7 | API fallback + optional `_collect_videos_with_scroll` (`367-386`, `856+`) | NETWORK + PARSE + INTERACTION | 0-10s | Partial | Partial |
| 8 | Serial video-page fallback (`391-430`, `1096-1204`) | NAVIGATION + NETWORK + SLEEP + RENDER + PARSE | 0-20s | Yes (bounded) | Partial |
| 9 | About tab extraction retry sequence (`443+`, includes waits/delays) | INTERACTION + RENDER + PARSE + SLEEP | 1-8s | Yes (parallel page option) | No |
| 10 | Aggregations + quality checks + persist (`430+`) | PARSE/CPU + NETWORK(write) | 0.3-2s | No | No |

**Sequential baseline estimate (BitChute):**
- Best-case (no fallback): ~10-30s
- Worst-case (fallback + retries): ~35-95s

### 1C) Theoretical Minimum and Optimization Budget

Assumptions for theoretical minimum:
- Replace `REPLACEABLE` sleeps with deterministic waits (finish near readiness, not max bound).
- Run About fetch concurrently with card collection.
- Run fallback video fetches with bounded concurrency (Rumble K=3, BitChute K=2).

| Platform | Sequential baseline | Theoretical minimum | Optimization budget |
|---|---:|---:|---:|
| Rumble best-case | 8-20s | 5-9s | 3-11s |
| Rumble worst-case | 45-90s | 15-28s | 30-62s |
| BitChute best-case | 10-30s | 7-14s | 3-16s |
| BitChute worst-case | 35-95s | 16-38s | 19-57s |

### 1D) Optimized Critical Path (Grouped Concurrency)

1. `goto + wait_for_content + card readiness` (serial, challenge-safe)
2. **Parallel Group A:**
   - A1: card collection / scroll parse
   - A2: About page fetch (separate page)
3. merge + quality gate
4. **Parallel Group B (bounded):** fallback video pages only for incomplete items
5. aggregate + persist

---

## Section 2 — Optimization Findings

## Category 1 — Eliminate Unjustified Sleeps

### Delay Audit Table

| File | Line | Current delay | Classification | Replacement / New value | Time saved (est.) |
|---|---:|---|---|---|---:|
| `rumble.py` | 272 | `human_delay(0.2,0.8)` | REPLACEABLE | `wait_for_selector(VIDEO_CARD_SELECTOR, state='attached', timeout=3000)` | 0.1-0.6s |
| `rumble.py` | 282 | `human_delay(0.4,1.0)` | CONSERVATIVE | reduce to `0.15-0.35` after reload; keep CF flow | 0.2-0.6s |
| `rumble.py` | 301/305 | `human_delay(second_pre/post)` | NECESSARY | keep (runtime-configured CF settle) | 0 |
| `rumble.py` | 324 | `human_delay(0.15,0.6)` | REPLACEABLE | remove; rely on selector readiness already satisfied | 0.15-0.6s |
| `rumble.py` | 375 | `human_delay(0.15,0.6)` | REPLACEABLE | `wait_for_content(about_page, min_bytes=3000)` immediately | 0.1-0.5s |
| `rumble.py` | 695 | `human_delay(0.2,0.7)` | CONSERVATIVE | reduce to `0.05-0.2` + `wait_for_function(card_count grows)` | 0.2-0.5s/iter |
| `rumble.py` | 707 | `human_delay(0.15,0.6)` | REPLACEABLE | `wait_for_selector(VIDEO_CARD_SELECTOR, timeout=2500)` | 0.1-0.5s |
| `rumble.py` | 895 | `human_delay(0.1,0.4)` | CONSERVATIVE | reduce to `0.05-0.15` pre-video-page navigation jitter | 0.05-0.25s/page |
| `rumble.py` | 899 | `human_delay(0.2,0.8)` | REPLACEABLE | `wait_for_content(page,min_bytes=5000)` already present | 0.2-0.8s/page |
| `bitchute.py` | 150 | `human_delay(0.2,0.8)` | REPLACEABLE | `wait_for_content` is immediate next; remove delay | 0.2-0.8s |
| `bitchute.py` | 164 | `human_delay(0.4,1.0)` | CONSERVATIVE | reduce to `0.15-0.35` post-reload | 0.2-0.6s |
| `bitchute.py` | 183/187 | `human_delay(second_pre/post)` | NECESSARY | keep CF challenge settle | 0 |
| `bitchute.py` | 213 | `human_delay(0.25,0.7)` ×3 | CONSERVATIVE | `0.08-0.2` + count-growth wait | 0.15-0.5 each |
| `bitchute.py` | 246 | `human_delay(0.2,0.7)` | REPLACEABLE | wait for card selector/hydration function | 0.15-0.6s |
| `bitchute.py` | 451 | `human_delay(0.2,0.8)` | REPLACEABLE | replace with deterministic about-content predicate | 0.2-0.8s |
| `bitchute.py` | 884 | `human_delay(0.2,0.7)` | CONSERVATIVE | reduce and gate on card-count growth | 0.2-0.5s/iter |
| `bitchute.py` | 910 | `human_delay(0.15,0.5)` | REPLACEABLE | rely on `wait_for_content(page,...)` right after | 0.15-0.5s |
| `bitchute.py` | 1102 | `human_delay(0.1,0.4)` | CONSERVATIVE | reduce to `0.05-0.15` | 0.05-0.25s/page |
| `bitchute.py` | 1106 | `human_delay(0.2,0.8)` | REPLACEABLE | rely on existing `wait_for_content` | 0.2-0.8s/page |
| `bitchute.py` | 1119 | `human_delay(0.15,0.45)` | NECESSARY | keep minimal (comments lazy-render after scroll) | 0-0.1s |
| `bitchute.py` | 1064 | `human_delay(0.2,0.7)` | REPLACEABLE | selector/hydration wait post-tab-click | 0.2-0.6s |

**Total estimated saving from delay optimization:**
- Rumble: ~2-6s no-fallback; ~6-20s with fallback
- BitChute: ~3-10s no-fallback; ~8-25s with fallback

### Deterministic replacements (examples)
```python
# Before
await human_delay(0.2, 0.8)

# After
await page.wait_for_selector(self.VIDEO_CARD_SELECTOR, state="attached", timeout=3000)
```
```python
# Before
await human_delay(0.2, 0.8)
await wait_for_content(page, min_bytes=5000, timeout_s=10.0)

# After
await wait_for_content(page, min_bytes=5000, timeout_s=10.0)
```

---

## Category 2 — Parallelize Independent Operations

### Opportunities

| Operations | Current time (sequential) | Time after gather | Saving | Risk |
|---|---:|---:|---:|---|
| Main page parse + About page fetch | A + B | max(A,B) | min(A,B) (~2-8s) | LOW |
| Rumble fallback video pages (N=5) serial | ~20-35s | ~7-12s (K=3) | ~13-23s | MEDIUM |
| BitChute fallback video pages (N=3) serial | ~9-15s | ~6-10s (K=2) | ~3-7s | MEDIUM |
| API fallback call + video tab prep (BitChute) | A + B | max(A,B) | ~0.5-2s | LOW |

### Refactor pattern
```python
# About and cards concurrently
about_task = asyncio.create_task(self._fetch_about_with_retry(context, about_url))
video_task = asyncio.create_task(self._collect_videos_with_scroll(page))
video_data_map, about_data = await asyncio.gather(video_task, about_task, return_exceptions=False)
```

```python
# Bounded fallback concurrency
sem = asyncio.Semaphore(3)  # rumble; use 2 for bitchute

async def _limited_fetch(url):
    async with sem:
        await human_delay(0.05, 0.15)  # keep jitter
        return await self._extract_video_page_signals(context, url)

results = await asyncio.gather(*[_limited_fetch(u) for u in fallback_urls])
```

**Total estimated saving from parallelization:**
- Rumble: ~10-28s worst-case channels
- BitChute: ~5-14s worst-case channels

---

## Category 3 — Eliminate Redundant Page Loads and Re-Parses

| File | Lines | Redundant operation | Times | Fix | Saving |
|---|---|---|---:|---|---:|
| `rumble.py` | 676-678 | `page.content()` + BS parse each scroll pass | up to 18 | parse incremental card HTML or count-gated extraction | 1-3s |
| `bitchute.py` | 856-884 | same pattern in scroll collector | up to 10 | same incremental strategy | 0.8-2.5s |
| `bitchute.py` | 469 + about retries | repeated `page.content()` for about after click attempts | 1-2 per attempt | isolate about fetch helper with one content parse per attempt | clarity + <1s |
| `rumble.py` | 332 + 676 | parse full page after collector already parsed repeatedly | 1 extra | reuse latest soup from collector return tuple `(map,soup)` | 0.1-0.3s |

Incremental scroll pattern:
```python
prev_count = 0
while True:
    await page.mouse.wheel(0, 3200)
    await page.wait_for_function(
        "(sel, prev) => document.querySelectorAll(sel).length > prev",
        self.VIDEO_CARD_SELECTOR,
        prev_count,
        timeout=3000,
    )
    current_count = await page.eval_on_selector_all(self.VIDEO_CARD_SELECTOR, "els => els.length")
    if current_count <= prev_count:
        break
    # only read new nodes if needed
    prev_count = current_count
```

---

## Category 4 — Reduce Video-Page Fallback Invocations

### Data availability audit
- **Rumble cards**: titles, URLs, views (`data-views`), dates (`time[datetime]`) mostly present; comments partially missing on some cards.
- **BitChute cards**: titles/views/dates present in many cases; comments often absent/weak.

### Changes
1. Trigger fallback only for incomplete items (already partially done; keep strict).
2. Reduce fallback sample size target:
   - Rumble: from current `VIDEO_PAGE_FALLBACK_LIMIT=15` to **5** max, with early stop at 3 valid additions.
   - BitChute: keep **1-3** (currently 1) and only raise to 3 when both views/comments samples are below threshold.
3. Do not fetch fallback pages for fields already complete (views/comments/date all present).

Estimated saving:
- Rumble: ~8-30s/channel (high variance)
- BitChute: ~0-8s/channel

---

## Category 5 — Parser and CPU Performance

### Findings
1. **Parser backend**: both scrapers currently use `BeautifulSoup(..., "html.parser")` in hot paths (e.g., `rumble.py:333,677,903`; `bitchute.py:324,863,911,1111`).
   - Recommendation: switch hot-path parse calls to `"lxml"`.
   - Saving: small per parse, but aggregate ~0.5-2s/channel on heavy paths.
2. **Selector scope**: card subfields are generally scoped to card nodes in BS paths; no critical full-doc misuse in tight loops found.
3. **Regex compilation**: repeated regex in inner/high-call methods (`_parse_bitchute_count`, `_extract_comment_count_from_text`, relative-date patterns, etc.).
   - compile at module level for repeated patterns.
   - saving: typically <1s alone; implement where touched for clarity and consistency.

---

## Category 6 — Request and Navigation Efficiency

### Navigation classification
- Channel main load: `NEW-URL`
- Rumble about fetch (`about_page.goto`): `PARALLEL-PAGE`
- BitChute about via tab click: currently `IN-PAGE` (keep)
- Video page fallback fetches: `PARALLEL-PAGE` (bounded)

### Resource blocking verification (`core/browser.py`)
- Currently blocks conditional resource types: images/media/texttrack/fonts (`47-58`, `218-231`).
- Not blocking stylesheet/scripts globally (correct for SPA safety).

### Additional safe blocking
Add URL pattern blocklist for analytics/telemetry only:
```python
BLOCK_PATTERNS = [
    "**/*google-analytics*", "**/*doubleclick*", "**/*facebook.com/tr*",
    "**/*hotjar*", "**/*segment.io*", "**/*mixpanel*", "**/*sentry.io*",
    "**/*cloudflareinsights.com*",
]
for p in BLOCK_PATTERNS:
    await context.route(p, lambda route: route.abort())
```
Estimated benefit: 3-10% network chatter reduction; low timing gain per channel (~0.3-1.5s) but reduces variance.

---

## Section 3 — Risk Assessment

| Optimization | Detection risk | Mitigation |
|---|---|---|
| Replace post-goto delays with selector/content waits | MEDIUM | keep jitter only on navigation transitions; preserve request cadence |
| Reduce scroll-loop delays | MEDIUM | retain minimal jitter + growth-based waits |
| Parallelize About fetch with card collection | LOW | separate page, no burst increase to same endpoint |
| Parallel fallback pages (bounded) | HIGH | semaphore cap (Rumble K=3, BitChute K=2), jitter, retry per task |
| Add analytics URL blocking | LOW | block only known non-essential trackers, not app/XHR |
| Move to `lxml` parser | LOW | parser fallback test coverage, compare extraction outputs |

**Net-negative guardrail:** do not exceed semaphore caps; if block/challenge rate rises >5% over baseline, automatically degrade K by 1.

---

## Section 4 — Implementation Roadmap (Impact-to-Risk)

| Priority | Optimization | Time saved | Risk | Effort | Implement first? |
|---|---|---:|---|---|---|
| 1 | Replace REPLACEABLE sleeps with deterministic waits | 5-20s | LOW-MED | Low | Yes |
| 2 | Parallelize About fetch and card collection | 2-8s | LOW | Medium | Yes |
| 3 | Bounded parallel fallback fetch (K=3/2) | 8-30s | MED-HIGH | Medium | Yes |
| 4 | Tighten fallback limits (Rumble 15?5, early stop at 3) | 5-20s | MED | Low | Yes |
| 5 | Scroll-loop incremental parsing/count-gating | 1-5s | MED | Medium | Yes |
| 6 | Switch hot-path BS parser to `lxml` | 0.5-2s | LOW | Low | Conditional |
| 7 | Analytics URL blocklist | 0.3-1.5s | LOW | Low | Conditional |

Go/No-Go recommendation:
- **Go** for priorities 1-5 immediately.
- 6-7 are optional unless perf variance remains high after first wave.

---

## Section 5 — Projected Performance After Optimizations

| Scenario | Before | After | Reduction |
|---|---:|---:|---:|
| BitChute — best case (no fallback) | 10-30s | 7-14s | 30-53% |
| BitChute — worst case (fallback/retries) | 35-95s | 16-38s | 46-60% |
| Rumble — best case | 8-20s | 5-9s | 37-55% |
| Rumble — worst case (max fallback path) | 45-90s | 15-28s | 62-69% |
| 100-channel batch (1 worker mixed) | 0.9-2.3h | 0.4-1.0h | 50-60% |

## Constraint Compliance Check
- Data completeness: preserved (fallback remains, only triaged + bounded parallel).
- Anti-bot posture: preserved (bounded same-domain concurrency + jitter retained).
- Retry safety: preserved (task-level fallback retries; do not fuse unrelated retries).
- Cloudflare handling: preserved (initial wait/reload/second-cycle logic unchanged).
- <1s changes: only included when clarity or variance reduction justifies.
