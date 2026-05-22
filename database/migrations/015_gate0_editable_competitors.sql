-- Store admin-editable Gate 0 competitor definitions.

ALTER TABLE system_settings
    ADD COLUMN IF NOT EXISTS gate0_competitors jsonb NOT NULL DEFAULT
    '[
        {"brand": "Noble Gold", "domains": ["noblegold.com"]},
        {"brand": "Birch Gold", "domains": ["birchgold.com"]},
        {"brand": "Patriot Gold", "domains": ["patriotgold.com"]},
        {"brand": "Kirk Elliot", "domains": ["kirkelliot.com"]}
    ]'::jsonb;

UPDATE system_settings
SET gate0_competitors =
    '[
        {"brand": "Noble Gold", "domains": ["noblegold.com"]},
        {"brand": "Birch Gold", "domains": ["birchgold.com"]},
        {"brand": "Patriot Gold", "domains": ["patriotgold.com"]},
        {"brand": "Kirk Elliot", "domains": ["kirkelliot.com"]}
    ]'::jsonb
WHERE gate0_competitors IS NULL OR gate0_competitors = '[]'::jsonb;
