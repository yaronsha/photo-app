import { useEffect, useState } from 'react';
import type { Session } from '@supabase/supabase-js';
import { supabase, isAuthEnabled } from './supabase';

export interface SessionState {
  session: Session | null;
  loading: boolean;
}

/** Display identity for the signed-in user, pulled from Google's claims. */
export interface AuthUser {
  email?: string;
  name?: string;
  avatarUrl?: string;
}

export function toAuthUser(session: Session | null): AuthUser | null {
  if (!session?.user) return null;
  const m = (session.user.user_metadata ?? {}) as Record<string, string>;
  return {
    email: session.user.email ?? m.email,
    name: m.full_name ?? m.name,
    avatarUrl: m.avatar_url ?? m.picture,
  };
}

// `<img src="/thumb/..">` / `<img src="/photo/..">` can't send an
// Authorization header, so we mirror the access token into a non-HttpOnly
// `sb_jwt` cookie that the browser attaches automatically. The backend's
// require_auth already accepts this cookie. The token also lives in
// localStorage (supabase-js puts it there), so the cookie exposes nothing new.
function writeAuthCookie(session: Session | null): void {
  if (typeof document === 'undefined') return;
  const secure = location.protocol === 'https:' ? '; Secure' : '';
  if (session?.access_token) {
    const maxAge = Math.max(0, (session.expires_at ?? 0) - Math.floor(Date.now() / 1000));
    document.cookie =
      `sb_jwt=${session.access_token}; Path=/; SameSite=Lax; Max-Age=${maxAge}${secure}`;
  } else {
    document.cookie = `sb_jwt=; Path=/; SameSite=Lax; Max-Age=0${secure}`;
  }
}

export function useSession(): SessionState {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState<boolean>(isAuthEnabled);

  useEffect(() => {
    if (!supabase) return;

    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      writeAuthCookie(data.session);
      setLoading(false);
    });

    // Fires on SIGNED_IN, TOKEN_REFRESHED, SIGNED_OUT — keeps the cookie in
    // lockstep with the access token as supabase-js refreshes it (~hourly).
    const { data: sub } = supabase.auth.onAuthStateChange((_event, next) => {
      setSession(next);
      writeAuthCookie(next);
    });
    return () => sub.subscription.unsubscribe();
  }, []);

  return { session, loading };
}

export async function signOut(): Promise<void> {
  if (!supabase) return;
  writeAuthCookie(null);
  await supabase.auth.signOut();
}
