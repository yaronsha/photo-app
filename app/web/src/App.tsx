import { Routes, Route } from 'react-router-dom';
import { SideNav } from './layout/SideNav';
import { MobileBottomNav } from './layout/MobileBottomNav';
import { GalleryPage } from './features/gallery/GalleryPage';
import { GamesPage } from './features/games/GamesPage';
import { LoginPage } from './features/auth/LoginPage';
import { useSession, toAuthUser } from './lib/session';
import { isAuthEnabled } from './lib/supabase';

export function App() {
  const { session, loading } = useSession();

  if (isAuthEnabled && loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background text-on-surface">
        <p className="opacity-60">Loading…</p>
      </div>
    );
  }

  if (isAuthEnabled && !session) {
    return <LoginPage />;
  }

  const user = toAuthUser(session);

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
