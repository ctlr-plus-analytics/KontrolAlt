-- Add direct-to-channels discovery workflow metadata.

alter table channels
    add column if not exists discovery_status text not null default 'new',
    add column if not exists discovery_evidence_count integer not null default 0,
    add column if not exists discovery_last_seen_at timestamptz,
    add column if not exists discovery_category text,
    add column if not exists last_discovery_source text,
    add column if not exists last_scrape_error text;

do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conname = 'chk_channels_discovery_status'
    ) then
        alter table channels
            add constraint chk_channels_discovery_status
            check (discovery_status in ('new', 'queued', 'scraped', 'failed', 'dead', 'blocked'));
    end if;
end $$;

create index if not exists idx_channels_discovery_status
    on channels(discovery_status);

create index if not exists idx_channels_discovery_last_seen_at
    on channels(discovery_last_seen_at desc);

