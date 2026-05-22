-- Track scrape completion state separately from frontend visibility.

alter table channels
    add column if not exists has_been_scraped boolean not null default false;

-- Backfill from historical snapshots so existing channels keep accurate state.
update channels c
set has_been_scraped = true
where exists (
    select 1
    from channel_snapshots s
    where s.channel_id = c.id
);

create index if not exists idx_channels_has_been_scraped
    on channels(has_been_scraped);
