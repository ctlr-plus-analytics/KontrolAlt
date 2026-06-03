-- Migration 031: Gate 0 three-tier confidence system
-- Adds needs_review status, confidence score, and evidence_signals to Gate 0 tables.

-- 1. Widen gate0_status check constraint on channels
DO $$
BEGIN
    ALTER TABLE channels DROP CONSTRAINT IF EXISTS channels_gate0_status_check;
    ALTER TABLE channels
        ADD CONSTRAINT channels_gate0_status_check
        CHECK (gate0_status IN ('unchecked', 'pending', 'clean', 'needs_review', 'dirty'));
EXCEPTION WHEN OTHERS THEN
    NULL;
END $$;

-- 2. Widen result_status check constraint on gate0_results
DO $$
BEGIN
    ALTER TABLE gate0_results DROP CONSTRAINT IF EXISTS gate0_results_result_status_check;
    ALTER TABLE gate0_results
        ADD CONSTRAINT gate0_results_result_status_check
        CHECK (result_status IN ('clean', 'needs_review', 'dirty'));
EXCEPTION WHEN OTHERS THEN
    NULL;
END $$;

-- 3. Add confidence and evidence columns to gate0_results
ALTER TABLE gate0_results
    ADD COLUMN IF NOT EXISTS confidence FLOAT,
    ADD COLUMN IF NOT EXISTS evidence_signals JSONB;
