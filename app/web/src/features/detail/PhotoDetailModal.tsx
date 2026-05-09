import { useState, useEffect, useCallback } from 'react';
import type { SearchResult } from '../../api/types';
import { usePhotoInfo } from '../../api/queries';
import { useKeyboardNav } from '../../hooks/useKeyboardNav';
import { useSwipe } from '../../hooks/useSwipe';
import { PhotoSidebar } from './PhotoSidebar';

interface PhotoDetailModalProps {
  photo: SearchResult;
  index: number;
  total: number;
  onClose: () => void;
  onPrev: () => void;
  onNext: () => void;
  hasPrev: boolean;
  hasNext: boolean;
}

export function PhotoDetailModal({
  photo,
  index,
  total,
  onClose,
  onPrev,
  onNext,
  hasPrev,
  hasNext,
}: PhotoDetailModalProps) {
  const [imgLoaded, setImgLoaded] = useState(false);

  const { data: info, isLoading: isLoadingInfo } = usePhotoInfo(photo.id);

  // Reset image state when photo changes
  useEffect(() => {
    setImgLoaded(false);
  }, [photo.id]);

  // Lock body scroll
  useEffect(() => {
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = '';
    };
  }, []);

  const handlePrev = useCallback(() => {
    if (hasPrev) onPrev();
  }, [hasPrev, onPrev]);

  const handleNext = useCallback(() => {
    if (hasNext) onNext();
  }, [hasNext, onNext]);

  useKeyboardNav({
    enabled: true,
    onPrev: handlePrev,
    onNext: handleNext,
    onClose,
  });

  const { onTouchStart, onTouchEnd } = useSwipe(handleNext, handlePrev);

  return (
    <div
      className="fixed inset-0 z-[100] flex flex-col bg-black"
      role="dialog"
      aria-modal="true"
      aria-label="Photo viewer"
      onTouchStart={onTouchStart}
      onTouchEnd={onTouchEnd}
    >
      {/* Top nav bar */}
      <nav className="bg-surface border-b border-outline-variant flex justify-between items-center px-margin-desktop py-md flex-shrink-0">
        <div className="flex items-center gap-xl">
          <span className="text-headline-md font-bold text-primary">Gallery Pro</span>
        </div>
        <div className="flex items-center gap-md">
          {total > 1 && (
            <span className="text-label-md text-on-surface-variant" aria-live="polite">
              {index + 1} of {total}
            </span>
          )}
          <button
            onClick={onClose}
            className="p-sm hover:bg-surface-container-low transition-colors rounded-full flex items-center justify-center"
            aria-label="Close photo viewer"
          >
            <span className="material-symbols-outlined text-on-surface-variant">close</span>
          </button>
        </div>
      </nav>

      {/* Main area */}
      <main className="flex flex-col md:flex-row flex-1 overflow-hidden">
        {/* Photo viewer */}
        <div className="relative flex-1 bg-black flex items-center justify-center group overflow-hidden">
          {/* Prev button */}
          {hasPrev && (
            <button
              onClick={handlePrev}
              className="absolute left-md z-10 p-md rounded-full bg-black/20 hover:bg-black/50 text-white transition-all backdrop-blur-md"
              aria-label="Previous photo"
            >
              <span className="material-symbols-outlined text-[32px]">chevron_left</span>
            </button>
          )}

          {/* Spinner */}
          {!imgLoaded && (
            <div className="absolute inset-0 flex items-center justify-center" aria-hidden="true">
              <div className="w-10 h-10 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            </div>
          )}

          {/* Full-res image */}
          <img
            key={photo.id}
            src={`/photo/${photo.id}`}
            alt={photo.caption ?? ''}
            className={`max-w-full max-h-full object-contain shadow-2xl transition-opacity duration-300 ${
              imgLoaded ? 'opacity-100' : 'opacity-0'
            }`}
            onLoad={() => setImgLoaded(true)}
            onError={() => setImgLoaded(true)}
          />

          {/* Next button */}
          {hasNext && (
            <button
              onClick={handleNext}
              className="absolute right-md z-10 p-md rounded-full bg-black/20 hover:bg-black/50 text-white transition-all backdrop-blur-md"
              aria-label="Next photo"
            >
              <span className="material-symbols-outlined text-[32px]">chevron_right</span>
            </button>
          )}
        </div>

        {/* Sidebar */}
        <PhotoSidebar photo={photo} info={info} isLoadingInfo={isLoadingInfo} />
      </main>
    </div>
  );
}
