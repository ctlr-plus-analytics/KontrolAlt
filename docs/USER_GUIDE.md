# KontrolAlt — User Guide

This guide walks through every feature in KontrolAlt step by step, written for first-time users with no technical background. Each section covers one task from start to finish.

---

## Table of Contents

1. [Signing In](#1-signing-in)
2. [Navigating the App](#2-navigating-the-app)
3. [Replaying the Guided Tour](#3-replaying-the-guided-tour)
4. [Searching for a Creator](#4-searching-for-a-creator)
5. [Filtering by Platform](#5-filtering-by-platform)
6. [Filtering by Comment Tier](#6-filtering-by-comment-tier)
7. [Sorting Channels](#7-sorting-channels)
8. [Filtering by Topic Category](#8-filtering-by-topic-category)
9. [Filtering by Channel Size (Numeric Ranges)](#9-filtering-by-channel-size-numeric-ranges)
10. [Filtering by Last Active Date](#10-filtering-by-last-active-date)
11. [Hiding Inactive Channels](#11-hiding-inactive-channels)
12. [Showing Only Incomplete Channels](#12-showing-only-incomplete-channels)
13. [Clearing All Filters](#13-clearing-all-filters)
14. [Refreshing the Channel List](#14-refreshing-the-channel-list)
15. [Navigating Between Pages of Results](#15-navigating-between-pages-of-results)
16. [Opening a Channel Profile](#16-opening-a-channel-profile)
17. [Reading the Channel Stats Header](#17-reading-the-channel-stats-header)
18. [Reading the AI Intelligence Report](#18-reading-the-ai-intelligence-report)
19. [Understanding Growth Velocity](#19-understanding-growth-velocity)
20. [Reading the Channel About](#20-reading-the-channel-about)
21. [Viewing Recent Videos](#21-viewing-recent-videos)
22. [Finding Other Channels and Links](#22-finding-other-channels-and-links)
23. [Loading Similar Channels](#23-loading-similar-channels)
24. [Reading the Scrape History](#24-reading-the-scrape-history)
25. [Setting Do Not Contact Status](#25-setting-do-not-contact-status)
26. [Deleting a Channel's History](#26-deleting-a-channels-history)
27. [Deleting a Channel Completely](#27-deleting-a-channel-completely)
28. [Signing Out](#28-signing-out)
29. [Admin — Triggering a Full Scrape](#29-admin--triggering-a-full-scrape)
30. [Admin — Triggering Channel Discovery](#30-admin--triggering-channel-discovery)
31. [Admin — Bootstrapping Never-Scraped Channels](#31-admin--bootstrapping-never-scraped-channels)
32. [Admin — Recalculating Weekly Velocity](#32-admin--recalculating-weekly-velocity)
33. [Admin — Running an Affiliation Batch](#33-admin--running-an-affiliation-batch)
34. [Admin — AI Classifying Channels](#34-admin--ai-classifying-channels)
35. [Admin — Monitoring Task Progress](#35-admin--monitoring-task-progress)
36. [Admin — Adding a Single Channel Manually](#36-admin--adding-a-single-channel-manually)
37. [Admin — Bulk Adding Channels by URL](#37-admin--bulk-adding-channels-by-url)
38. [Admin — Resolving a Creator Name to a URL](#38-admin--resolving-a-creator-name-to-a-url)
39. [Admin — Checking Worker Health](#39-admin--checking-worker-health)
40. [Admin — Viewing Worker Logs](#40-admin--viewing-worker-logs)
41. [Admin — Purging All Tasks (Danger Zone)](#41-admin--purging-all-tasks-danger-zone)
42. [Admin — Adding a Competitor for Affiliation Detection](#42-admin--adding-a-competitor-for-affiliation-detection)
43. [Admin — Editing or Removing a Competitor](#43-admin--editing-or-removing-a-competitor)
44. [Admin — Adding a Category Keyword Set](#44-admin--adding-a-category-keyword-set)
45. [Admin — Editing or Removing a Category](#45-admin--editing-or-removing-a-category)
46. [Admin — Reading the Audit Log](#46-admin--reading-the-audit-log)

---

## 1. Signing In

1. Open the KontrolAlt URL in your browser.
2. You will be taken to the login page automatically if you are not already signed in.
3. Enter your email address and password in the fields provided.
4. Click **Sign In**.
5. If this is your first time logging in, a Welcome screen will appear explaining what KontrolAlt is. Click **Start Tour** to take a guided walkthrough of the app, or **Skip for now** to go straight to the dashboard.

---

## 2. Navigating the App

The black bar at the very top of every page is the navigation bar.

- **KONTROL_ALT** (gold text, top left) — clicking this always takes you back to the main channel list from anywhere in the app.
- **Channels** link — opens the Channel Discovery dashboard, which is the main page for browsing and filtering creators.
- **Admin** link — only visible to admin accounts. Opens the backend control panel.
- Your email address and a gold circle with your initial are shown on the top right so you can confirm which account is logged in.

---

## 3. Replaying the Guided Tour

The **?** button in the top-right corner of the navigation bar opens the tour menu.

1. Click the **?** button.
2. A small menu appears with the following options:
   - **Dashboard tour** — walks you through every filter and table feature on the Channels page.
   - **Channel detail tour** — walks you through the full channel profile page (triggers the next time you open any channel).
   - **Admin tour** — walks you through the admin control panel (admin accounts only).
   - **Reset all tours** — clears your progress so the welcome screen appears again on next login, and all tours become available from the beginning.
3. Click the tour you want to launch.
4. Inside any tour, use **Next** to advance, **Back** to go to the previous step, and **Skip** to exit the tour early.

---

## 4. Searching for a Creator

1. Go to the **Channels** page (click **Channels** in the top navigation bar).
2. Look at the dark sidebar on the left side of the page — this is the Filter Sidebar.
3. At the top of the sidebar, find the search box with placeholder text *Name, URL, description...*.
4. Click inside the search box.
5. Type the creator's name, part of their channel URL, or a word from their channel description.
6. The channel list on the right updates automatically as you type — no need to press Enter.
7. To clear the search and return to the full list, delete all the text in the search box.

> **Tip:** If you know the creator's name but can't find them, they may not be in the database yet. See [Admin — Adding a Single Channel Manually](#36-admin--adding-a-single-channel-manually) to add them.

---

## 5. Filtering by Platform

Rumble is a video platform. Substack is a newsletter and blog platform. This filter lets you show channels from one platform or both.

1. Go to the **Channels** page.
2. In the Filter Sidebar, find the **Platform** section.
3. Click one of the three buttons:
   - **All** — shows channels from both platforms (default).
   - **Rumble** — shows only Rumble video channels.
   - **Substack** — shows only Substack newsletter channels.
4. The channel list updates immediately.

---

## 6. Filtering by Comment Tier

A "comment tier" groups channels by how much audience participation they get — measured by the average number of comments per post.

1. Go to the **Channels** page.
2. In the Filter Sidebar, find the **Comment Tier** section.
3. Click one of the four options:
   - **All Tiers** — no filter applied (default).
   - **Active (10+)** — channels that receive at least 10 comments per post on average. The audience is participating.
   - **Sweet Spot (20–100)** — the range most useful for partnership campaigns. Engaged enough to signal real audience intent, but not so large that outreach becomes expensive.
   - **Whale (100+)** — high-interaction channels with very active audiences. These tend to be larger, higher-profile creators.
4. The channel list updates immediately.

---

## 7. Sorting Channels

By default, channels are sorted by average comment count (highest first). You can change both what the list is sorted by and whether it goes highest-to-lowest or lowest-to-highest.

1. Go to the **Channels** page.
2. In the Filter Sidebar, find the **Sort** section.
3. **Sort By** — click the dropdown to choose the sorting metric:
   - **Avg Comments** — sort by how many comments each post receives on average.
   - **Subscribers** — sort by total subscriber or follower count.
   - **Avg Views** — sort by how many views each video gets on average (Rumble channels).
   - **View Velocity 30d** — sort by how much a channel's views have grown or declined over the last 30 days.
   - **View Velocity 90d** — same as above but over 90 days.
   - **Last Active** — sort by when the channel last published something.
4. **Order** — click one of the two buttons:
   - **High → Low** — largest values appear first (default).
   - **Low → High** — smallest values appear first.
5. You can also sort by clicking any column header in the table directly — clicking the same header a second time reverses the direction.

---

## 8. Filtering by Topic Category

Channels are automatically tagged with broad topic categories by an AI classifier. You can filter the list to show only channels in specific categories.

1. Go to the **Channels** page.
2. In the Filter Sidebar, scroll down to the **Advanced** section and find **Topic Category**.
3. Click the dropdown button (it shows *Any / All Categories* by default).
4. A list of available categories appears, each showing how many channels belong to that category under your current filters.
5. Click any category name to select it. You can select more than one — the list will show channels that match any of the selected categories.
6. To remove a category, click it again to deselect it.
7. To go back to all categories, click **Any / All Categories** at the top of the dropdown.
8. Click anywhere outside the dropdown to close it.

> **Note:** Category counts update to reflect your other active filters. If a category shows 0 channels under your current filters, it will appear dimmed and cannot be selected.

---

## 9. Filtering by Channel Size (Numeric Ranges)

You can set minimum and maximum values for three channel metrics to target a specific size of creator.

1. Go to the **Channels** page.
2. In the Filter Sidebar, scroll down to the **Advanced** section.
3. Find the **Subscribers**, **Avg Views**, and **Avg Comments** sliders.
4. For each one, you can:
   - Type a number into the **Min** field to hide channels below that value.
   - Type a number into the **Max** field to hide channels above that value.
   - Leave either field blank to remove that boundary.
5. The channel list updates as you adjust each value.

**Example:** To find mid-sized channels with meaningful engagement, set Subscribers Min to 50,000 and Max to 500,000, and Avg Comments Min to 20.

---

## 10. Filtering by Last Active Date

"Last active" is the date when a channel last published a post or video. Use this to show only channels that were active within a specific time window.

1. Go to the **Channels** page.
2. In the Filter Sidebar, scroll down to the **Advanced** section and find **Last Active**.
3. Click the **From** date field and choose a start date — this hides channels that were last active before that date.
4. Click the **To** date field and choose an end date — this hides channels that were last active after that date.
5. You can set just a From date, just a To date, or both.
6. To remove a date filter, clear the date field.

---

## 11. Hiding Inactive Channels

Channels that haven't published anything in 90 or more days are considered inactive. By default, these are hidden from the list.

1. Go to the **Channels** page.
2. In the Filter Sidebar, scroll to the bottom of the **Advanced** section and find the **Exclude 90d+ Inactive** toggle.
3. The toggle is **on** by default (shown with a red background). Inactive channels are hidden.
4. Click the toggle to turn it **off** — inactive channels will appear in the list alongside active ones.
5. Click again to turn it back on.

---

## 12. Showing Only Incomplete Channels

"Incomplete" channels are those where data collection failed — they may be missing subscriber count, average views, or average comments. This filter is mainly used for diagnosing data gaps.

1. Go to the **Channels** page.
2. In the Filter Sidebar, scroll to the bottom of the **Advanced** section and find **Incomplete Only**.
3. Click the toggle to turn it **on** — the list will show only channels that have missing metrics.
4. Click again to turn it off.

---

## 13. Clearing All Filters

When multiple filters are active, a number badge appears at the top of the Filter Sidebar (e.g., **3**) showing how many filters are in use. A **Clear** button also appears next to it.

1. Go to the **Channels** page.
2. Look at the top of the Filter Sidebar. If there is a number badge and a **Clear** button, one or more filters are active.
3. Click **Clear** to reset every filter back to its default state.

Alternatively, you can remove filters one by one by clicking the active selection again (e.g., clicking the selected platform button, or deleting text from the search box).

---

## 14. Refreshing the Channel List

The channel list loads automatically when you open the page. If new channels have been added or scraped since you opened the page, click Refresh to pull in the latest data.

1. Go to the **Channels** page.
2. In the top-right area of the main content (above the table), find the **Refresh** button with a circular arrow icon.
3. Click **Refresh**. The list reloads using your current filters.

---

## 15. Navigating Between Pages of Results

The channel list shows 25 channels per page. If your filters match more than 25 channels, use the pagination controls to see the rest.

1. Go to the **Channels** page.
2. Scroll to the very bottom of the channel table.
3. The row below the table shows:
   - How many channels are showing out of the total (e.g., *Showing 25 of 412 channels*).
   - **← Previous** and **Next →** buttons to move one page at a time.
   - A page number input (e.g., *1 / 17*). Click the number, type a page number, and press **Enter** to jump directly to that page.
4. The **Previous** button is greyed out on the first page; **Next** is greyed out on the last page.

---

## 16. Opening a Channel Profile

Each row in the channel table represents one creator. Clicking a row opens the full channel profile page.

1. Go to the **Channels** page.
2. Find the channel you want to view. You can use search and filters to narrow the list.
3. Click anywhere on the channel's row.
4. The full channel profile page opens, showing detailed stats, AI analysis, growth data, and more.
5. To go back to the channel list, click **KONTROL_ALT** in the top navigation bar or use your browser's Back button.

---

## 17. Reading the Channel Stats Header

The first card at the top of every channel profile shows the channel's key metrics at a glance.

| Label | What it means |
|---|---|
| **Subscribers** | Total number of subscribers or followers. |
| **Avg Views** | Average number of views per video (Rumble only; shows — for Substack). |
| **Engagement Rate** | Average comments per post divided by subscriber count, shown as a percentage. Higher means a more active audience relative to size. |
| **Avg Comments** | Average number of comments per post. |
| **Posts/Week** | How frequently the channel publishes, calculated from recent activity. |
| **Last Active** | How long ago the channel published its most recent post (e.g., *3 days ago*). |

The platform badge (orange **Rumble** or brown-orange **Substack**) next to the channel name shows which platform the channel is on.

The **Visit Channel** button in the top-right corner of the card opens the channel's original page on Rumble or Substack in a new browser tab.

---

## 18. Reading the AI Intelligence Report

Below the stats header, most channels have an AI-generated analysis written by Claude (an AI assistant).

1. Open a channel profile.
2. Scroll down past the stats header.
3. The section labelled **Channel Intelligence Report** (with an **AI** badge) contains the analysis.
4. The report covers: the channel's content focus, the type of audience it attracts, posting cadence and consistency, and any notable patterns in the content.
5. If the report says *AI report not yet generated for this channel*, the channel was recently added and hasn't been fully scraped yet.

> **Note:** The report is regenerated every time the channel is scraped. It reflects the state of the channel at the time of the last scrape.

---

## 19. Understanding Growth Velocity

Velocity measures whether a channel is growing or shrinking in terms of views and comments.

1. Open a channel profile.
2. Scroll down to the **Growth Velocity** section.
3. You will see four cards:
   - **View Velocity — 30 Day**: compares average views over the last 30 days against the 30 days before that.
   - **View Velocity — 90 Day**: same comparison over 90 days.
   - **Comment Velocity — 30 Day**: compares average comments over the last 30 days against the prior 30 days.
   - **Comment Velocity — 90 Day**: same over 90 days.
4. Each card shows a percentage and a colour:
   - **Green / positive percentage** — the channel is growing in that metric.
   - **Red / negative percentage** — the channel is declining in that metric.
   - **"Insufficient Data"** — the channel doesn't yet have enough history to calculate a comparison. This is normal for recently-added channels.

---

## 20. Reading the Channel About

This section shows the creator's self-written description, scraped directly from their channel page.

1. Open a channel profile.
2. Scroll down past the Growth Velocity section.
3. The **Channel About** section contains the bio or about text the creator wrote for their page.
4. This is useful for understanding the creator's stated content focus, seeing what keywords they use to describe themselves, and finding any contact information they chose to publish.
5. If the section says *No about description available*, the creator's page didn't have a public bio.

---

## 21. Viewing Recent Videos

This section shows the last three videos or posts scraped from the channel.

1. Open a channel profile.
2. Scroll down to the **Recent Videos** section.
3. A table shows up to three entries with:
   - **Title** — click the title to open the original video or post in a new tab.
   - **Views** — how many views that post received.
   - **Comments** — how many comments that post received.
   - **Uploaded Date** — when the post was published.
4. If the section says *No video data available*, the scraper didn't collect individual post data for this channel yet.

---

## 22. Finding Other Channels and Links

This section shows external links and contact information found on the creator's channel page.

1. Open a channel profile.
2. Scroll down to the **Other Channels and Links** section.
3. You may find:
   - Links to the creator's profiles on other platforms (YouTube, Twitter/X, Instagram, etc.).
   - Personal website URLs.
   - Email addresses for direct contact.
4. Click any link to open it in a new tab.
5. If the section says *No contact information found*, the scraper didn't find any external links on their page.

---

## 23. Loading Similar Channels

The "similar channels" feature finds other creators in the database that share characteristics with the channel you're viewing.

1. Open a channel profile.
2. Scroll down to the **Similar Channels** section.
3. Click the **Load Similar Channels** button.
4. The system searches for channels that overlap in topic, audience type, or content keywords.
5. Matching channels appear as cards below the button. Each card shows:
   - The matched channel's name and platform.
   - Key stats (subscribers, avg comments, engagement rate).
   - The basis for the match (e.g., *topic match*, *keyword overlap*).
6. Click any matched channel's name to open that channel's profile.
7. If no results appear after loading, the system didn't find any strong matches in the current database.

---

## 24. Reading the Scrape History

A scrape is the automated process that collects data from a channel's page. This section shows the history of those attempts.

1. Open a channel profile.
2. Scroll down to the **Scrape History** section.
3. A table shows the 10 most recent scrape attempts with:
   - **Timestamp** — how long ago the scrape was attempted (e.g., *2 days ago*).
   - **Status** — the outcome:
     - **success** (green) — data was collected successfully.
     - **blocked** (yellow) — the platform detected automated access and blocked the request.
     - **retry** (yellow) — the scrape failed but will be tried again automatically.
     - **failed** (red) — the scrape failed and will not be retried automatically.
   - **Error** — the specific error message if the scrape failed, or a dash if it succeeded.

---

## 25. Setting Do Not Contact Status

Use this to flag a channel's relationship status so it can be excluded from or prioritized in outreach lists.

1. Open a channel profile.
2. Scroll to the bottom of the page to the **Data Cleanup** section.
3. On the right side, find the **Do Not Contact** panel.
4. The current status badge shows the channel's status (default is *Not Set*).
5. Click one of the buttons to set a status:
   - **Hired and Canceled** (red) — marks this creator as someone who was hired but the deal fell through. The channel should be excluded from future outreach.
   - **Current Partner** (gold) — marks this creator as an active partner.
   - **Reset** — clears the status back to *Not Set*.
6. The badge updates immediately after you click.

---

## 26. Deleting a Channel's History

This removes all historical scrape records and snapshot data for a channel while keeping the channel itself in the database. Use this to reset bad data and allow a fresh collection.

1. Open a channel profile.
2. Scroll to the bottom of the page to the **Data Cleanup** section.
3. On the left side, find the **Delete History (Snapshot)** button.
4. Click it. A confirmation prompt will appear in your browser asking you to confirm.
5. Click **OK** to confirm. The history is deleted and the page refreshes.

> **Note:** The channel stays in the database. Only its historical records are removed. It will be re-scraped on the next scrape run.

---

## 27. Deleting a Channel Completely

This removes a channel and all its data from the database permanently. This cannot be undone.

1. Open a channel profile.
2. Scroll to the bottom of the page to the **Data Cleanup** section.
3. Find the **Delete Completely** button.
4. Click it. A confirmation prompt will appear warning you that this cannot be undone.
5. Click **OK** to confirm. The channel is deleted and you are returned to the Channel Discovery dashboard.

---

## 28. Signing Out

1. Click the **Sign Out** button in the top-right corner of the navigation bar (it shows a door/arrow icon and the text *Sign Out* on wider screens).
2. You are returned to the login page.

---

---

# Admin Section

> The features in this section are only available to accounts with admin privileges. If you do not see the **Admin** link in the navigation bar, your account does not have admin access.

---

## 29. Admin — Triggering a Full Scrape

A "full scrape" collects fresh metrics (subscriber count, average views, average comments, recent videos, etc.) for every active channel in the database.

1. Click **Admin** in the navigation bar.
2. Find the **Manual Task Triggers** section at the top of the page.
3. Click **Trigger Full Scrape**.
4. A task status card appears below the buttons confirming the scrape has been queued.
5. The scrape runs in the background. See [Monitoring Task Progress](#35-admin--monitoring-task-progress) to track it.

> **When to use:** After adding new channels, or when you need up-to-date metrics before building a campaign list.

---

## 30. Admin — Triggering Channel Discovery

Discovery searches the web for new channels that match the topics and keywords configured in the system, and adds any new ones to the database.

1. Click **Admin** in the navigation bar.
2. In the **Manual Task Triggers** section, click **Trigger Discovery**.
3. A task card appears confirming discovery has been queued.
4. New channels found during discovery will appear in the channel list after the run completes.

> **When to use:** When you want to expand the database with new creators in a given topic area.

---

## 31. Admin — Bootstrapping Never-Scraped Channels

Sometimes channels are added to the database (via discovery or manual intake) but have never been scraped for metrics. This trigger queues all of them for their first scrape.

1. Click **Admin** in the navigation bar.
2. In the **Manual Task Triggers** section, click **Bootstrap Never-Scraped Rumble/Substack**.
3. A task card appears confirming the job has been queued.

> **When to use:** After a bulk channel import, or when the channel list has many entries showing no metrics.

---

## 32. Admin — Recalculating Weekly Velocity

Velocity scores measure how fast a channel is growing or declining. This trigger recalculates velocity for all channels in the database.

1. Click **Admin** in the navigation bar.
2. In the **Manual Task Triggers** section, click **Trigger Weekly Velocity**.
3. A task card appears confirming the calculation has been queued.

> **When to use:** If velocity data looks stale or incorrect after a large scrape run.

---

## 33. Admin — Running an Affiliation Batch

The affiliation batch re-scans all channels to check whether they are promoting any competitor brands. It compares channel content against the list of competitors configured in the admin panel.

1. Click **Admin** in the navigation bar.
2. In the **Manual Task Triggers** section, click **Trigger Affiliation Batch**.
3. Optionally, if you want to run affiliation only for specific channels: paste their channel IDs (one per line or comma-separated) into the text box below the trigger buttons before clicking.
4. A task card appears confirming the batch has been queued.

> **When to use:** After adding new competitors to the affiliation list, or when you need fresh affiliation flags before exporting a campaign shortlist.

---

## 34. Admin — AI Classifying Channels

The AI classifier reads each channel's content and assigns it a topic category tag (e.g., Conservative Politics, Health & Wellness). This trigger runs the classifier on channels that haven't been classified yet, or on all channels.

1. Click **Admin** in the navigation bar.
2. In the **Manual Task Triggers** section:
   - Click **AI Classify Channels** to classify only channels that don't have a category tag yet.
   - Click **AI Reclassify All** to re-run the classifier on every channel, overwriting existing tags.
3. A task card appears confirming the job has been queued.

> **When to use:** After adding new category keyword sets, or after a large batch of new channels has been added without categories.

---

## 35. Admin — Monitoring Task Progress

After triggering any task, a status card appears below the trigger buttons. It automatically updates every few seconds.

Each card shows:
- The **task name** (e.g., Full Scrape, Discovery).
- A **status badge**:
  - **Queued** — the job is waiting to start.
  - **Running** — the job is actively being processed.
  - **Success** (green) — the job completed successfully.
  - **Error** (red) — the job failed. The card will show an error message.
  - **Retrying** — the job encountered an issue and is trying again automatically.
- The number of individual worker tasks spawned by the job.
- Each individual task's ID and status, which updates as they complete.

You do not need to stay on the admin page — tasks run in the background even if you navigate away.

---

## 36. Admin — Adding a Single Channel Manually

Use this when you know the exact URL of a channel you want to add to the database.

1. Click **Admin** in the navigation bar.
2. Scroll to the **Channel Intake** section.
3. Click the **Add Single Channel** tab.
4. Paste the channel's URL into the URL field (e.g., `https://rumble.com/c/ChannelName`).
5. Optionally, add any notes about the channel in the Notes field.
6. Click **Add Channel**.
7. A confirmation message appears. The channel is added to the database and will be scraped on the next scrape run.

> **Note:** If the channel already exists in the database, a duplicate warning will appear and the channel will not be added again.

---

## 37. Admin — Bulk Adding Channels by URL

Use this to add many channels at once by pasting a list of URLs.

1. Click **Admin** in the navigation bar.
2. Scroll to the **Channel Intake** section.
3. Click the **Bulk Add URLs** tab.
4. Paste a list of channel URLs into the text area — one URL per line.
5. Click **Bulk Add**.
6. A summary appears showing how many channels were added, how many were duplicates (already in the database), and how many failed.

---

## 38. Admin — Resolving a Creator Name to a URL

Use this when you know a creator's name but don't know their exact channel URL.

1. Click **Admin** in the navigation bar.
2. Scroll to the **Channel Intake** section.
3. Click the **Creator Name Resolver** tab.
4. Type the creator's name into the name field.
5. Select the platform (Rumble or Substack) from the dropdown.
6. Click **Find Channel**.
7. The system searches for matching channel URLs and displays results.
8. Review the results and click **Add** next to the correct channel to add it to the database.

---

## 39. Admin — Checking Worker Health

Workers are the background services that run scrapes, discovery, and other tasks. This section shows whether they are running correctly.

1. Click **Admin** in the navigation bar.
2. Scroll to the **Worker Health** section.
3. Each worker is shown as a row with:
   - A **green dot** (online) or **red dot** (offline) indicating whether the worker is running.
   - The worker's service name.
   - **Online / Offline** status badge.
   - **Active tasks** — how many tasks the worker is currently processing.
   - **Reserved tasks** — tasks queued and waiting in the worker's buffer.
   - **Concurrency** — how many tasks the worker can run simultaneously.
   - **Total done** — how many tasks the worker has completed since it last restarted.
4. This list refreshes automatically every 10 seconds. Click **Refresh** to update it immediately.

> **If a worker shows Offline:** The service may have crashed or been stopped. Contact your system administrator.

---

## 40. Admin — Viewing Worker Logs

Each worker has a log that records what it is doing in real time. Use this to investigate failed tasks or unexpected behaviour.

1. Click **Admin** in the navigation bar.
2. Scroll to the **Worker Health** section.
3. Find the worker you want to inspect.
4. Click **View Logs** on the right side of the worker's row.
5. A dark terminal-style panel expands below the row, showing the last 150 lines of log output.
6. To refresh the logs, click **Refresh logs** at the bottom of the panel.
7. To close the logs, click **Hide Logs**.

---

## 41. Admin — Purging All Tasks (Danger Zone)

> **Warning:** This is a destructive action. It immediately stops all running tasks, wipes the job queue, and clears cached scraper state. Only use this when tasks are stuck and the system needs a clean restart.

1. Click **Admin** in the navigation bar.
2. Scroll to the red **Danger Zone — Purge All Tasks** section.
3. Click **Purge All Tasks & Redis State**.
4. A confirmation box appears describing exactly what will be deleted:
   - All currently running tasks are force-stopped.
   - The job queue is cleared.
   - All cached scraper data in Redis (proxy scores, scrape locks, etc.) is deleted.
   - Worker processes are restarted.
5. Click **Yes, purge everything** to confirm, or **Cancel** to go back.
6. After the purge completes, a green summary box appears showing what was deleted and when.

> **When to use:** When the task queue is stuck, tasks are looping indefinitely, or you need a completely clean slate before starting a new scrape run.

---

## 42. Admin — Adding a Competitor for Affiliation Detection

The affiliation system flags channels that promote competitor brands. Add brands here to tell the system what to look for.

1. Click **Admin** in the navigation bar.
2. Scroll to the **Affiliation Competitors** section.
3. Click **+ Add Competitor**.
4. A new row appears at the bottom of the table with two input fields:
   - **Brand name** — the name of the competitor (e.g., *BrandX*).
   - **Domains** — the web domains associated with this brand, separated by commas (e.g., *brandx.com, shop.brandx.com*).
5. Fill in both fields and click **Add**.
6. The competitor is saved immediately. The next affiliation batch run will use this new entry.

---

## 43. Admin — Editing or Removing a Competitor

1. Click **Admin** in the navigation bar.
2. Scroll to the **Affiliation Competitors** section.
3. Find the competitor you want to change in the table.
4. To **edit**: click **Edit** on that row. The fields become editable. Make your changes and click **Save**.
5. To **delete**: click **Delete** on that row. The competitor is removed immediately.
6. Changes take effect on the next affiliation batch run.

---

## 44. Admin — Adding a Category Keyword Set

Category keywords tell the AI classifier how to tag channels with topic categories. Each category has a name and a list of seed keywords that describe it.

1. Click **Admin** in the navigation bar.
2. Scroll to the **Category Keywords** section.
3. Click **+ Add Category**.
4. A new row appears with two input fields:
   - **Category name** — what you want to call this topic area (e.g., *Personal Finance*).
   - **Keywords** — a comma-separated list of words the AI should look for when deciding if a channel belongs in this category (e.g., *investing, stocks, retirement, budgeting, money*).
5. Fill in both fields and click **Add**.
6. The category is saved. It will be used the next time you run AI Classify Channels.

---

## 45. Admin — Editing or Removing a Category

1. Click **Admin** in the navigation bar.
2. Scroll to the **Category Keywords** section.
3. Find the category you want to change.
4. To **edit**: click **Edit** on that row. Update the category name or keyword list and click **Save**.
5. To **delete**: click **Delete** on that row. The category is removed immediately.
6. Changes apply on the next AI Classify run — existing channel tags are not retroactively updated until a new classify run is triggered.

---

## 46. Admin — Reading the Audit Log

The audit log records every action taken in the admin panel by any admin user.

1. Click **Admin** in the navigation bar.
2. Scroll to the very bottom of the page to the **Recent Admin Audit** section.
3. The table shows the last 20 actions with:
   - **Time (UTC)** — when the action was taken, in Coordinated Universal Time.
   - **Actor** — the email address of the admin who performed the action.
   - **Action** — what was done (e.g., *trigger_scrape*, *add_channel*, *update_competitors*).
   - **Target** — the specific item that was affected (e.g., a channel ID, a brand name).
4. Use this log to track who triggered what and when, and to correlate system behaviour with specific admin actions.
