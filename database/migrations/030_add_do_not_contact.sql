ALTER TABLE channels
    ADD COLUMN IF NOT EXISTS do_not_contact text DEFAULT NULL;

ALTER TABLE channels
    DROP CONSTRAINT IF EXISTS channels_do_not_contact_check;

ALTER TABLE channels
    ADD CONSTRAINT channels_do_not_contact_check
    CHECK (
        do_not_contact IS NULL
        OR do_not_contact IN ('Hired and Canceled', 'Current Partner')
    );
