-- 005_admin_control_plane.sql
-- Admin runtime settings + audit log for control-plane actions.

CREATE TABLE IF NOT EXISTS system_settings (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    singleton_key text NOT NULL UNIQUE DEFAULT 'global',
    daily_scrape_utc_time time NOT NULL DEFAULT '02:00:00',
    gate0_enabled boolean NOT NULL DEFAULT true,
    discovery_enabled boolean NOT NULL DEFAULT true,
    lookalike_enabled boolean NOT NULL DEFAULT true,
    scrape_platform_priority text[] NOT NULL DEFAULT ARRAY['rumble', 'bitchute']::text[],
    version bigint NOT NULL DEFAULT 1,
    updated_by uuid,
    updated_by_email text,
    updated_at timestamptz NOT NULL DEFAULT now(),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT singleton_ck CHECK (singleton_key = 'global'),
    CONSTRAINT platform_priority_ck CHECK (
        array_length(scrape_platform_priority, 1) >= 1
        AND scrape_platform_priority <@ ARRAY['rumble', 'bitchute']::text[]
    )
);

INSERT INTO system_settings (singleton_key)
VALUES ('global')
ON CONFLICT (singleton_key) DO NOTHING;

CREATE TABLE IF NOT EXISTS admin_actions_audit (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_user_id uuid NOT NULL,
    actor_email text,
    action text NOT NULL,
    target text NOT NULL,
    old_value jsonb,
    new_value jsonb,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_admin_actions_audit_created_at
    ON admin_actions_audit (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_admin_actions_audit_actor_user_id
    ON admin_actions_audit (actor_user_id);

GRANT SELECT ON system_settings TO authenticated;
GRANT SELECT ON admin_actions_audit TO authenticated;
GRANT ALL ON system_settings TO service_role;
GRANT ALL ON admin_actions_audit TO service_role;

ALTER TABLE system_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE admin_actions_audit ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Authenticated users can read system_settings"
    ON system_settings FOR SELECT TO authenticated USING (true);
CREATE POLICY "Authenticated users can read admin_actions_audit"
    ON admin_actions_audit FOR SELECT TO authenticated USING (true);

CREATE POLICY "Service role can manage system_settings"
    ON system_settings FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "Service role can manage admin_actions_audit"
    ON admin_actions_audit FOR ALL TO service_role USING (true) WITH CHECK (true);
