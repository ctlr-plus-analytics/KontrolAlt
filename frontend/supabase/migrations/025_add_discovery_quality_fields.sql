ALTER TABLE channels
  ADD COLUMN IF NOT EXISTS discovery_quality_tier        TEXT     DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS discovery_serp_snippet        TEXT     DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS discovery_serp_title          TEXT     DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS discovery_niche_hint          TEXT[]   DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS classification_confidence     FLOAT    DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS classification_needs_review   BOOLEAN  DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS classification_context_score  SMALLINT DEFAULT NULL;
