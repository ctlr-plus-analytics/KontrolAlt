"""Supabase client singletons for the backend service.

Two clients are exported:

- ``supabase_admin`` — uses the **service role key** to bypass RLS.
  Used for all server-side writes and admin operations.
- ``supabase_anon`` — uses the **anon key** and respects RLS.
  Used for JWT verification via ``supabase_anon.auth.get_user(token)``.
"""

from supabase import Client, create_client

from core.config import settings

# ---------------------------------------------------------------------------
# Admin client — bypasses Row Level Security
# ---------------------------------------------------------------------------
supabase_admin: Client = create_client(
    settings.supabase_url,
    settings.supabase_service_role_key,
)

# ---------------------------------------------------------------------------
# Anon client — respects Row Level Security (used for auth verification)
# ---------------------------------------------------------------------------
supabase_anon: Client = create_client(
    settings.supabase_url,
    settings.supabase_anon_key,
)
