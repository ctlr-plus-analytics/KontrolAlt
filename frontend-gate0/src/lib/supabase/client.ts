/**
 * Supabase browser client — for use in Client Components.
 */
import { createBrowserClient } from "@supabase/ssr";
import { getSupabasePublicEnv } from "@/lib/supabase/env";

export function createClient() {
  const { url, anonKey } = getSupabasePublicEnv();
  return createBrowserClient(
    url,
    anonKey,
  );
}
