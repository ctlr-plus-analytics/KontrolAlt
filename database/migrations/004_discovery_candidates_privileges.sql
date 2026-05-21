-- Fix permissions so scraper worker (service_role) can stage discovery candidates.

grant usage on schema public to service_role;

grant select, insert, update, delete
on table public.discovery_candidates
to service_role;

-- Keep app-user behavior aligned with project convention (no delete).
grant select, insert, update
on table public.discovery_candidates
to authenticated;
