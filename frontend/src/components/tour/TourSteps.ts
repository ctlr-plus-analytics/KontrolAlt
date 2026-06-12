import type { Step } from "react-joyride";

// skipBeacon is set globally via options.skipBeacon in TourManager.
// All placements rely on flipOptions + shiftOptions in TourManager to stay
// clear of the 56px fixed TopBar and viewport edges.

// ─── Dashboard Tour (15 steps) ─────────────────────────────────────────────
export const DASHBOARD_STEPS: Step[] = [
  {
    target: "#tour-topbar",
    title: "Navigation Bar",
    content:
      "The top bar is your global navigation. KONTROL_ALT takes you back to the dashboard from anywhere. Your email and user avatar are shown on the right. The ? button lets you replay any tour at any time.",
    placement: "bottom",
  },
  {
    target: "#tour-nav",
    title: "Navigation Links",
    content:
      "Channels opens the Channel Discovery dashboard — the main research interface. Admin (visible to admin accounts only) opens the backend control panel for triggering jobs, adding channels, and configuring the system.",
    placement: "bottom",
  },
  {
    target: "#tour-help-button",
    title: "Guided Tour Menu",
    content:
      "Click ? at any time to replay a tour: the Dashboard tour covers this page, the Channel Detail tour covers the full channel profile, and the Admin tour covers the control panel. 'Reset all tours' clears your progress and shows the welcome screen on next login.",
    placement: "bottom",
  },
  {
    target: "#tour-filter-sidebar",
    title: "Filter Sidebar",
    content:
      "The sidebar is your primary research tool. Every filter here is applied live to the channel table on the right. Your selections are saved to session storage — refreshing the page restores your last filter state. The badge at the top of the sidebar shows how many filters are currently active, and the Clear button resets everything to defaults.",
    placement: "right",
  },
  {
    target: "#tour-filter-search",
    title: "Channel Search",
    content:
      "Search by channel name, URL fragment, or a word from the channel's about description. The results update the table in real time as you type. Clear the field to return to the full result set.",
    placement: "right",
  },
  {
    target: "#tour-filter-platform",
    title: "Platform Filter",
    content:
      "Filter by platform — Rumble or Substack — or show all. Platform determines which metrics are available: Rumble channels track video views; Substack channels track likes (post reactions). Some columns in the table will show a dash for metrics that don't apply to a platform.",
    placement: "right",
  },
  {
    target: "#tour-comment-tier-filter",
    title: "Comment Tiers",
    content:
      "Tiers segment channels by average comment count per post. Active (10+) means there is at least some audience participation. Sweet Spot (20–100) is the target for most partnership campaigns: engaged enough to signal real audience intent, small enough for efficient outreach. Whale (100+) channels have very high interaction but can be harder to reach and more expensive.",
    placement: "right",
  },
  {
    target: "#tour-filter-sort",
    title: "Sort Controls",
    content:
      "Sort By chooses the ranking metric: Avg Comments, Subscribers, Avg Views, 30-day View Velocity, 90-day View Velocity, or Last Active date. Order sets ascending (smallest first) or descending (largest first). The default is Avg Comments descending — the most engaged channels surface first, which is the most useful starting point for outreach research.",
    placement: "right",
  },
  {
    target: "#tour-filter-category",
    title: "Topic Category Filter",
    content:
      "Channels are tagged with broad topic categories by the AI classifier: Conservative Politics, Health & Wellness, Finance, Sports, and more. You can select multiple categories; the table shows channels that match any of the selected tags. Category counts shown next to each tag update to reflect how many channels match your other active filters.",
    placement: "right",
  },
  {
    target: "#tour-filter-ranges",
    title: "Numeric Range Filters",
    content:
      "Set minimum and maximum bounds for Subscribers, Average Views, and Average Comments. Use these to target a specific channel size tier. For example: Subscribers 50k–500k finds mid-tier channels; Avg Comments 20–100 exactly matches the Sweet Spot comment tier. Leave both ends blank to remove the filter for that metric.",
    placement: "right",
  },
  {
    target: "#tour-filter-last-active",
    title: "Last Active Date Range",
    content:
      "Filter by the date of the channel's most recent post. Set a From date to exclude channels that went inactive before that point, or a To date to find channels that haven't posted recently. Useful when you need to confirm a channel is currently active before outreach.",
    placement: "right",
  },
  {
    target: "#tour-filter-toggles",
    title: "Data Quality Filters",
    content:
      "'Exclude 90d+ Inactive' hides channels that haven't published in 90 days — on by default for outreach campaigns where you need currently active creators. 'Incomplete Only' shows channels where data collection failed and one or more key metrics are missing — useful for diagnosing scrape issues or finding channels that need a manual re-scrape.",
    placement: "right",
  },
  {
    target: "#tour-table-header",
    title: "Channel Discovery",
    content:
      "The heading shows the total number of channels that match all your active filters. This number updates every time you change a filter. The Refresh button re-fetches from the backend with your current filter state — useful right after a scrape run brings in new data.",
    placement: "bottom",
  },
  {
    target: "#tour-channel-table",
    title: "Channel Table",
    content:
      "Every channel that matches your filters is listed here. Columns: Channel name, Platform, Subscribers, Niche/Category tag, Avg Views, Likes (Substack only), Avg Comments, Engagement Rate (comments ÷ subscribers), and Last Active date. Click any column header to sort by that column — clicking the active column again toggles the sort direction. Click any row to open the full channel profile.",
    placement: "bottom",
  },
  {
    target: "#tour-pagination",
    title: "Pagination",
    content:
      "Results are paginated at 25 channels per page. Use Previous and Next to navigate, or type a page number directly into the input and press Enter to jump to any page. The count above the table shows how many channels match across all pages.",
    placement: "top",
  },
];

// ─── Channel Detail Tour (9 steps) ─────────────────────────────────────────
export const CHANNEL_DETAIL_STEPS: Step[] = [
  {
    target: "#tour-channel-header",
    title: "Channel Overview",
    content:
      "The header card shows the key stats at a glance: subscriber count, average views per post, engagement rate (avg comments ÷ subscribers as a percentage), average comments per post, posts per week cadence, and the date of the channel's last published post. The platform badge next to the name identifies Rumble or Substack. The Visit Channel button opens the original source URL in a new tab.",
    placement: "bottom",
  },
  {
    target: "#tour-ai-report",
    title: "AI Intelligence Report",
    content:
      "An AI-generated analysis of the channel covering its content focus, audience type, posting cadence, tone, and notable patterns. Generated by Claude during each full scrape run using the channel's about text and video titles as input. Newly-added channels show a placeholder until their first successful scrape completes.",
    placement: "bottom",
  },
  {
    target: "#tour-velocity-section",
    title: "Growth Velocity",
    content:
      "Velocity compares the average views or comments over a 30-day or 90-day window against the equivalent prior period. A positive percentage means the channel is growing in that metric; negative means declining. Four cards are shown: View Velocity 30-day, View Velocity 90-day, Comment Velocity 30-day, Comment Velocity 90-day. 'Insufficient Data' means the channel hasn't yet accumulated two full comparison periods — it's still building its baseline history.",
    placement: "bottom",
  },
  {
    target: "#tour-channel-about",
    title: "Channel About",
    content:
      "The creator's self-written about/bio text scraped directly from their channel page. Useful for confirming the channel's stated content focus, niche keywords, or any contact information the creator has chosen to publish. Shows 'No about description available' for channels that don't have public bio text.",
    placement: "top",
  },
  {
    target: "#tour-recent-videos",
    title: "Recent Videos",
    content:
      "The last 3 videos scraped from the channel, with view count, comment count, and publish date for each. Clicking a title opens the original post in a new tab. Use this to spot-check content quality, verify the channel is actively publishing on the subject matter you care about, and confirm scrape data is fresh.",
    placement: "top",
  },
  {
    target: "#tour-channel-links",
    title: "Other Channels & Links",
    content:
      "External URLs and contact information found on the channel page — other social profiles, personal websites, email addresses, and cross-platform links. This is the primary source for finding a creator's cross-platform presence and for locating direct contact details for outreach without relying on intermediaries.",
    placement: "top",
  },
  {
    target: "#tour-similar-channels",
    title: "Similar Channels",
    content:
      "Click 'Load Similar Channels' to query the lookalike engine. It finds other channels in the database that share audience overlap, topic tags, or keyword patterns with this channel. Each result card shows the similarity basis (topic match, keyword overlap, etc.) and the matched channel's key metrics. Use this for campaign expansion, competitor research, and building creator shortlists around a seed channel.",
    placement: "top",
  },
  {
    target: "#tour-scrape-history",
    title: "Scrape History",
    content:
      "A log of the 10 most recent scrape attempts for this channel. Each row shows the timestamp, outcome status (success, blocked, retry, failed), and the error message if the attempt failed. A pattern of 'blocked' usually means the platform is detecting automated access; 'failed' typically indicates a structural change in the page layout. Use this log to diagnose data freshness issues.",
    placement: "top",
  },
  {
    target: "#tour-data-cleanup",
    title: "Data Management",
    content:
      "'Delete History' removes snapshot and scrape log records while keeping the channel entry in the database — useful for resetting bad historical data before a fresh scrape. 'Delete Completely' removes the channel from the database entirely and cannot be undone — the page redirects to the dashboard after deletion. The 'Do Not Contact' panel tracks the channel's outreach status: 'Current Partner' flags an active deal, 'Hired and Canceled' blocks the channel from future outreach lists. Reset clears the flag.",
    placement: "top",
  },
];

// ─── Admin Tour (7 steps) ───────────────────────────────────────────────────
export const ADMIN_STEPS: Step[] = [
  {
    target: "#tour-manual-tasks",
    title: "Manual Task Triggers",
    content:
      "Trigger backend Celery jobs on demand. Full Scrape refreshes metrics for all active channels. Discovery runs the keyword + seed expansion pipeline to find new channels via Google Search. Never-Scraped Bootstrap queues Rumble and Substack channels that were added but have never been scraped. Weekly Velocity recalculates growth velocity scores for all channels. Affiliation Batch re-scans channel content for competitor brand links. AI Classify assigns or refreshes topic category tags. After triggering, task cards appear below the buttons with live status badges (Queued → Running → Success/Error) that auto-poll every 2.5 seconds.",
    placement: "bottom",
  },
  {
    target: "#tour-channel-intake",
    title: "Channel Intake",
    content:
      "Three methods to add channels to the database manually. 'Add Single Channel' takes a direct platform URL with optional notes. 'Bulk Add URLs' accepts a newline-separated list for mass imports. 'Creator Name Resolver' finds the channel URL when you only know the creator's name — it searches platform directories and returns matched URLs. All methods auto-detect duplicates and tag the entry with discovery source 'manual_frontend' so you can filter for manually-added channels later.",
    placement: "bottom",
  },
  {
    target: "#tour-worker-health",
    title: "Worker Health",
    content:
      "Real-time status of the backend Celery worker containers hosted on Render. Each row shows the service name, online/offline indicator, Docker container status, active tasks currently running in that worker, reserved tasks in the prefetch buffer, concurrency (max parallel tasks), and total tasks processed since the last restart. Click 'View Logs' to pull the last 150 log lines from the container's stdout — useful for debugging stuck tasks or scrape errors. The panel auto-refreshes every 10 seconds.",
    placement: "bottom",
  },
  {
    target: "#tour-danger-zone",
    title: "Danger Zone — Queue Purge",
    content:
      "The Purge button sends SIGKILL to all active and reserved tasks across worker containers, clears the Redis broker queue, deletes all scraper state keys from Redis (proxy health scores, platform scrape slots, channel scrape locks, byte budgets), and restarts the worker process pools to flush prefetch and zombie state. Use this before a fresh scrape run when the queue is stuck, tasks are looping, or the worker state is corrupted. A confirmation dialog appears first showing the full scope of what will be wiped.",
    placement: "bottom",
  },
  {
    target: "#tour-affiliation-config",
    title: "Affiliation Competitors",
    content:
      "The competitor brand list used by the affiliation detection engine. Each entry maps a brand name to one or more domains. During an affiliation batch run, the scraper checks each channel's about text, video descriptions, and discovered links against these domains — channels with matches are flagged as affiliated in the database. Add new competitors here before running an affiliation batch; changes take effect immediately on the next run. Use Edit to update domains for an existing brand, Delete to remove it entirely.",
    placement: "bottom",
  },
  {
    target: "#tour-category-keywords",
    title: "Category Keywords",
    content:
      "The keyword taxonomy used by the AI classifier to assign topic category tags. Each row maps a category name (e.g. 'Conservative Politics') to a comma-separated list of seed keywords. The classifier reads a channel's content and uses these keyword lists as category signals. Add new categories for niches you want to track, or expand existing keyword lists to improve classification recall for underrepresented topics. Changes apply on the next AI Classify run.",
    placement: "top",
  },
  {
    target: "#tour-admin-audit",
    title: "Recent Admin Audit",
    content:
      "A chronological log of the last 20 admin actions taken in this panel — task triggers, channel additions, competitor edits, taxonomy changes, queue purges. Each row records the UTC timestamp, the actor's email address, the specific action taken, and the target (channel ID, brand name, etc.). Use this log to track who triggered what and when, and to correlate backend behavior with specific admin actions during debugging.",
    placement: "top",
  },
];
