BEGIN;

-- Purge dependent data linked to BitChute channels.
WITH bitchute_channel_ids AS (
    SELECT id
    FROM channels
    WHERE platform = 'bitchute'
)
DELETE FROM lookalike_matches
WHERE matched_channel_id IN (SELECT id FROM bitchute_channel_ids);

WITH bitchute_channel_ids AS (
    SELECT id
    FROM channels
    WHERE platform = 'bitchute'
)
DELETE FROM gate0_results
WHERE channel_id IN (SELECT id FROM bitchute_channel_ids);

WITH bitchute_channel_ids AS (
    SELECT id
    FROM channels
    WHERE platform = 'bitchute'
)
DELETE FROM scrape_logs
WHERE channel_id IN (SELECT id FROM bitchute_channel_ids);

WITH bitchute_channel_ids AS (
    SELECT id
    FROM channels
    WHERE platform = 'bitchute'
)
DELETE FROM channel_snapshots
WHERE channel_id IN (SELECT id FROM bitchute_channel_ids);

DELETE FROM channels
WHERE platform = 'bitchute';

-- Normalize scrape platform settings to current supported set.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name = 'admin_operational_settings'
    ) THEN
        UPDATE admin_operational_settings
        SET scrape_platform_priority = ARRAY['rumble', 'substack']::text[]
        WHERE scrape_platform_priority IS NULL
           OR 'bitchute' = ANY(scrape_platform_priority);

        ALTER TABLE admin_operational_settings
            ALTER COLUMN scrape_platform_priority
            SET DEFAULT ARRAY['rumble', 'substack']::text[];
    END IF;
END $$;

-- Drop legacy constraints that still permit BitChute.
DO $$
DECLARE
    con_name text;
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name = 'admin_operational_settings'
    ) THEN
        RETURN;
    END IF;

    FOR con_name IN
        SELECT con.conname
        FROM pg_constraint con
        JOIN pg_class rel ON rel.oid = con.conrelid
        JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
        WHERE rel.relname = 'channels'
          AND nsp.nspname = 'public'
          AND con.contype = 'c'
          AND pg_get_constraintdef(con.oid) ILIKE '%platform%'
          AND pg_get_constraintdef(con.oid) ILIKE '%bitchute%'
    LOOP
        EXECUTE format('ALTER TABLE channels DROP CONSTRAINT %I', con_name);
    END LOOP;
END $$;

DO $$
DECLARE
    con_name text;
BEGIN
    FOR con_name IN
        SELECT con.conname
        FROM pg_constraint con
        JOIN pg_class rel ON rel.oid = con.conrelid
        JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
        WHERE rel.relname = 'admin_operational_settings'
          AND nsp.nspname = 'public'
          AND con.contype = 'c'
          AND pg_get_constraintdef(con.oid) ILIKE '%scrape_platform_priority%'
          AND pg_get_constraintdef(con.oid) ILIKE '%bitchute%'
    LOOP
        EXECUTE format('ALTER TABLE admin_operational_settings DROP CONSTRAINT %I', con_name);
    END LOOP;
END $$;

-- Recreate strict constraints.
ALTER TABLE channels
    DROP CONSTRAINT IF EXISTS channels_platform_check;

ALTER TABLE channels
    ADD CONSTRAINT channels_platform_check
    CHECK (platform IN ('rumble', 'substack'));

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name = 'admin_operational_settings'
    ) THEN
        ALTER TABLE admin_operational_settings
            DROP CONSTRAINT IF EXISTS admin_operational_settings_scrape_platform_priority_check;
        ALTER TABLE admin_operational_settings
            ADD CONSTRAINT admin_operational_settings_scrape_platform_priority_check
            CHECK (
                array_length(scrape_platform_priority, 1) >= 1
                AND scrape_platform_priority <@ ARRAY['rumble', 'substack']::text[]
            );
    END IF;
END $$;

COMMIT;
