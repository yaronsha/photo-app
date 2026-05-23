import { useEffect, useState } from 'react';
import { Routes, Route } from 'react-router-dom';
import { SideNav } from './layout/SideNav';
import { MobileBottomNav } from './layout/MobileBottomNav';
import { GalleryPage } from './features/gallery/GalleryPage';
import { GamesPage } from './features/games/GamesPage';
import { LoginPage } from './features/auth/LoginPage';
import { AccessDenied } from './features/auth/AccessDenied';
import { useSession, toAuthUser } from './lib/session';
import { isAuthEnabled } from './lib/supabase';
import { fetchMe } from './api/client';

type Authz = 'na' | 'checking' | 'allowed' | 'denied';

/** Verify the signed-in account is authorized (server-side allowlist) before
 *  rendering the app. `/api/me` returns 200 when allowed, 403 when the email
 *  is not in ALLOWED_EMAILS. Transient failures (network/5xx) don't lock a
 *  legit user out — only an explicit 403 denies. */
function useAuthorization(token: string | undefined): Authz {
  const [state, setState] = useState<Authz>('na');
  useEffect(() => {
    if (!isAuthEnabled || !token) {
      setState('na');
      return;
    }
    let active = true;
    setState('checking');
    fetchMe()
      .then(() => active && setState('allowed'))
      .catch((e: Error & { status?: number }) =>
        active && setState(e.status === 403 ? 'denied' : 'allowed')
      );
    return () => {
      active = false;
    };
  }, [token]);
  return state;
}

function FullScreenMessage({ text }: { text: string }) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-background text-on-surface">
      <p className="opacity-60">{text}</p>
    </div>
  );
}

export function App() {
  const { session, loading } = useSession();
  const authz = useAuthorization(session?.access_token);

  if (isAuthEnabled && loading) {
    return <FullScreenMessage text="Loading…" />;
  }

  if (isAuthEnabled && !session) {
    return <LoginPage />;
  }

  const user = toAuthUser(session);

  if (isAuthEnabled && authz === 'checking') {
    return <FullScreenMessage text="Loading…" />;
  }

  if (isAuthEnabled && authz === 'denied') {
    return <AccessDenied email={user?.email} />;
  }

  return (
    <div className="bg-background text-on-surface min-h-screen">
      <SideNav user={user} />

      <div className="md:ml-[280px] min-h-screen flex flex-col pb-[60px] md:pb-0">
        <Routes>
          <Route path="/" element={<GalleryPage />} />
          <Route path="/games" element={<GamesPage />} />
          {/* Catch-all → gallery */}
          <Route path="*" element={<GalleryPage />} />
        </Routes>
      </div>

      <MobileBottomNav user={user} />
    </div>
  );
}
