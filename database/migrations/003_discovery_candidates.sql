-- Stage discovered channels before promotion into channels table.

create table if not exists discovery_candidates (
    id uuid primary key default gen_random_uuid(),
    candidate_url text not null,
    platform text not null,
    source text not null,
    source_ref text,
    title text,
    category text,
    confidence double precision not null default 0.0,
    evidence_count integer not null default 1,
    status text not null default 'pending',
    rejection_reason text,
    first_seen_at timestamptz not null default now(),
    last_seen_at timestamptz not null default now(),
    discovered_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint chk_discovery_candidates_platform
        check (platform in ('rumble', 'bitchute')),
    constraint chk_discovery_candidates_status
        check (status in ('pending', 'verified', 'rejected', 'promoted')),
    constraint uq_discovery_candidates_url unique(candidate_url)
);

create index if not exists idx_discovery_candidates_status
    on discovery_candidates(status);

create index if not exists idx_discovery_candidates_platform_status
    on discovery_candidates(platform, status);

create index if not exists idx_discovery_candidates_last_seen_at
    on discovery_candidates(last_seen_at desc);
