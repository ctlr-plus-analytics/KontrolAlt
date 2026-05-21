-- ============================================================
-- Kontrol_Alt — Initial Database Schema
-- Run this migration against your Supabase PostgreSQL instance.
-- ============================================================

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================
-- 1. channels
-- ============================================================
CREATE TABLE channels (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    platform        text NOT NULL CHECK (platform IN ('rumble', 'bitchute')),
    channel_url     text NOT NULL UNIQUE,
    name            text NOT NULL,
    description     text NOT NULL DEFAULT '',
    subscriber_count integer,
    avg_views       integer,
    avg_comments    integer,
    comment_tier    text CHECK (comment_tier IN ('active', 'sweet_spot', 'whale') OR comment_tier IS NULL),
    posts_per_week  numeric(5, 2),
    last_active_date date,
    contact_info    text[] DEFAULT '{}',
    niche_tags      text[] DEFAULT '{}',
    video_titles    text[] NOT NULL DEFAULT '{}',
    is_active       boolean NOT NULL DEFAULT true,
    is_55_plus      boolean DEFAULT false,
    gate0_status    text NOT NULL DEFAULT 'unchecked' CHECK (gate0_status IN ('clean', 'dirty', 'pending', 'unchecked')),
    gate0_checked_at timestamptz,
    secondary_urls  text[] DEFAULT '{}',
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_channels_is_active ON channels(is_active);

-- ============================================================
-- 2. channel_snapshots
-- ============================================================
CREATE TABLE channel_snapshots (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_id       uuid NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    scraped_at       timestamptz NOT NULL DEFAULT now(),
    subscriber_count integer,
    avg_views        integer,
    avg_comments     integer,
    created_at       timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_channel_snapshots_channel_id ON channel_snapshots(channel_id);
CREATE INDEX idx_channel_snapshots_scraped_at ON channel_snapshots(scraped_at);

-- ============================================================
-- 3. velocity_scores
-- ============================================================
CREATE TABLE velocity_scores (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_id            uuid NOT NULL UNIQUE REFERENCES channels(id) ON DELETE CASCADE,
    computed_at           timestamptz NOT NULL DEFAULT now(),
    view_velocity_30d     numeric(10, 4),
    view_velocity_90d     numeric(10, 4),
    comment_velocity_30d  numeric(10, 4),
    comment_velocity_90d  numeric(10, 4),
    created_at            timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_velocity_scores_channel_id ON velocity_scores(channel_id);

-- ============================================================
-- 4. gate0_results
-- ============================================================
CREATE TABLE gate0_results (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_id      uuid NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    checked_at      timestamptz NOT NULL DEFAULT now(),
    search_query    text NOT NULL,
    result_status   text NOT NULL DEFAULT 'clean' CHECK (result_status IN ('clean', 'dirty')),
    flagged_brand   text,
    source_url      text,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_gate0_results_channel_id ON gate0_results(channel_id);

-- ============================================================
-- 5. scrape_logs
-- ============================================================
CREATE TABLE scrape_logs (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_id      uuid NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    attempted_at    timestamptz NOT NULL DEFAULT now(),
    status          text NOT NULL CHECK (status IN ('success', 'blocked', 'retry', 'failed')),
    error_message   text,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_scrape_logs_channel_id ON scrape_logs(channel_id);

-- ============================================================
-- 6. seed_creators
-- ============================================================
CREATE TABLE seed_creators (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid NOT NULL,
    name        text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, name)
);

-- ============================================================
-- 7. lookalike_matches
-- ============================================================
CREATE TABLE lookalike_matches (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    seed_id             uuid NOT NULL REFERENCES seed_creators(id) ON DELETE CASCADE,
    matched_channel_id  uuid NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    match_type          text NOT NULL CHECK (match_type IN ('guest_appearance', 'niche_overlap')),
    match_detail        text,
    found_at            timestamptz NOT NULL DEFAULT now(),
    created_at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (seed_id, matched_channel_id, match_type)
);

CREATE INDEX idx_lookalike_matches_seed_id ON lookalike_matches(seed_id);
CREATE INDEX idx_lookalike_matches_matched_channel_id ON lookalike_matches(matched_channel_id);

-- ============================================================
-- Row Level Security
-- ============================================================

ALTER TABLE channels ENABLE ROW LEVEL SECURITY;
ALTER TABLE channel_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE velocity_scores ENABLE ROW LEVEL SECURITY;
ALTER TABLE gate0_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE scrape_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE seed_creators ENABLE ROW LEVEL SECURITY;
ALTER TABLE lookalike_matches ENABLE ROW LEVEL SECURITY;

-- Authenticated users can SELECT, INSERT, UPDATE (no DELETE)
CREATE POLICY "Authenticated users can read channels"
    ON channels FOR SELECT TO authenticated USING (true);
CREATE POLICY "Authenticated users can insert channels"
    ON channels FOR INSERT TO authenticated WITH CHECK (true);
CREATE POLICY "Authenticated users can update channels"
    ON channels FOR UPDATE TO authenticated USING (true) WITH CHECK (true);

CREATE POLICY "Authenticated users can read channel_snapshots"
    ON channel_snapshots FOR SELECT TO authenticated USING (true);
CREATE POLICY "Authenticated users can insert channel_snapshots"
    ON channel_snapshots FOR INSERT TO authenticated WITH CHECK (true);
CREATE POLICY "Authenticated users can update channel_snapshots"
    ON channel_snapshots FOR UPDATE TO authenticated USING (true) WITH CHECK (true);

CREATE POLICY "Authenticated users can read velocity_scores"
    ON velocity_scores FOR SELECT TO authenticated USING (true);
CREATE POLICY "Authenticated users can insert velocity_scores"
    ON velocity_scores FOR INSERT TO authenticated WITH CHECK (true);
CREATE POLICY "Authenticated users can update velocity_scores"
    ON velocity_scores FOR UPDATE TO authenticated USING (true) WITH CHECK (true);

CREATE POLICY "Authenticated users can read gate0_results"
    ON gate0_results FOR SELECT TO authenticated USING (true);
CREATE POLICY "Authenticated users can insert gate0_results"
    ON gate0_results FOR INSERT TO authenticated WITH CHECK (true);
CREATE POLICY "Authenticated users can update gate0_results"
    ON gate0_results FOR UPDATE TO authenticated USING (true) WITH CHECK (true);

CREATE POLICY "Authenticated users can read scrape_logs"
    ON scrape_logs FOR SELECT TO authenticated USING (true);
CREATE POLICY "Authenticated users can insert scrape_logs"
    ON scrape_logs FOR INSERT TO authenticated WITH CHECK (true);
CREATE POLICY "Authenticated users can update scrape_logs"
    ON scrape_logs FOR UPDATE TO authenticated USING (true) WITH CHECK (true);

CREATE POLICY "Authenticated users can read seed_creators"
    ON seed_creators FOR SELECT TO authenticated USING (true);
CREATE POLICY "Authenticated users can insert seed_creators"
    ON seed_creators FOR INSERT TO authenticated WITH CHECK (true);
CREATE POLICY "Authenticated users can update seed_creators"
    ON seed_creators FOR UPDATE TO authenticated USING (true) WITH CHECK (true);

CREATE POLICY "Authenticated users can read lookalike_matches"
    ON lookalike_matches FOR SELECT TO authenticated USING (true);
CREATE POLICY "Authenticated users can insert lookalike_matches"
    ON lookalike_matches FOR INSERT TO authenticated WITH CHECK (true);
CREATE POLICY "Authenticated users can update lookalike_matches"
    ON lookalike_matches FOR UPDATE TO authenticated USING (true) WITH CHECK (true);

-- Service role can DELETE (applied via supabase service role key)
CREATE POLICY "Service role can delete channels"
    ON channels FOR DELETE TO service_role USING (true);
CREATE POLICY "Service role can delete channel_snapshots"
    ON channel_snapshots FOR DELETE TO service_role USING (true);
CREATE POLICY "Service role can delete velocity_scores"
    ON velocity_scores FOR DELETE TO service_role USING (true);
CREATE POLICY "Service role can delete gate0_results"
    ON gate0_results FOR DELETE TO service_role USING (true);
CREATE POLICY "Service role can delete scrape_logs"
    ON scrape_logs FOR DELETE TO service_role USING (true);
CREATE POLICY "Service role can delete seed_creators"
    ON seed_creators FOR DELETE TO service_role USING (true);
CREATE POLICY "Service role can delete lookalike_matches"
    ON lookalike_matches FOR DELETE TO service_role USING (true);

-- ============================================================
-- 8. channel_discovery (View)
-- ============================================================
CREATE OR REPLACE VIEW channel_discovery AS
SELECT
    c.id,
    c.platform,
    c.channel_url,
    c.name,
    c.description,
    c.subscriber_count,
    c.avg_views,
    c.avg_comments,
    c.comment_tier,
    c.posts_per_week,
    c.last_active_date,
    c.contact_info,
    c.niche_tags,
    c.video_titles,
    c.is_active,
    c.is_55_plus,
    c.gate0_status,
    c.gate0_checked_at,
    c.secondary_urls,
    c.created_at,
    c.updated_at,
    vs.id AS velocity_id,
    vs.computed_at AS velocity_computed_at,
    vs.view_velocity_30d,
    vs.view_velocity_90d,
    vs.comment_velocity_30d,
    vs.comment_velocity_90d,
    gr.id AS gate0_result_id,
    gr.checked_at AS gate0_result_checked_at,
    gr.search_query AS gate0_search_query,
    gr.result_status AS gate0_result_status,
    gr.flagged_brand AS gate0_flagged_brand,
    gr.source_url AS gate0_source_url
FROM channels c
LEFT JOIN velocity_scores vs ON vs.channel_id = c.id
LEFT JOIN LATERAL (
    SELECT *
    FROM gate0_results
    WHERE gate0_results.channel_id = c.id
    ORDER BY checked_at DESC
    LIMIT 1
) gr ON true;

-- ============================================================
-- Postgres Privileges (GRANTs)
-- Ensures Supabase API roles have base access before RLS applies
-- ============================================================
GRANT ALL ON ALL TABLES IN SCHEMA public TO anon;
GRANT ALL ON ALL TABLES IN SCHEMA public TO authenticated;
GRANT ALL ON ALL TABLES IN SCHEMA public TO service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO anon;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO authenticated;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO service_role;
