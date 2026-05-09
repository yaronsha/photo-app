import { Routes, Route } from 'react-router-dom';
import { SideNav } from './layout/SideNav';
import { MobileBottomNav } from './layout/MobileBottomNav';
import { GalleryPage } from './features/gallery/GalleryPage';
import { GamesPage } from './features/games/GamesPage';

export function App() {
  return (
    <div className="bg-background text-on-surface min-h-screen">
      <SideNav />

      <div className="md:ml-[280px] min-h-screen flex flex-col pb-[60px] md:pb-0">
        <Routes>
          <Route path="/" element={<GalleryPage />} />
          <Route path="/games" element={<GamesPage />} />
          {/* Catch-all → gallery */}
          <Route path="*" element={<GalleryPage />} />
        </Routes>
      </div>

      <MobileBottomNav />
    </div>
  );
}
