-- Add discovery provenance fields for auto-promoted seed expansion channels.

alter table channels
    add column if not exists discovery_source text,
    add column if not exists discovery_confidence double precision,
    add column if not exists discovered_from_channel_id uuid references channels(id) on delete set null,
    add column if not exists discovered_at timestamptz;

create index if not exists idx_channels_discovery_source
    on channels(discovery_source);

create index if not exists idx_channels_discovered_from_channel_id
    on channels(discovered_from_channel_id);
