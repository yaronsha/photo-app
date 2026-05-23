// Supabase client + helpers.
//
// Auth is *opt-in*: if VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY are
// unset (typical local dev or e2e mocks), `supabase` is null and the
// session gate is bypassed — matching the backend's behavior when
// SUPABASE_JWT_SECRET is unset.
import { createClient, type SupabaseClient } from '@supabase/supabase-js';

const url = import.meta.env.VITE_SUPABASE_URL as string | undefined;
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined;

export const supabase: SupabaseClient | null =
  url && anonKey ? createClient(url, anonKey) : null;

export const isAuthEnabled = supabase !== null;
