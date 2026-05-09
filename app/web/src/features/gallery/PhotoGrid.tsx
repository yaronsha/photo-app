import type { SearchResult } from '../../api/types';
import { PhotoCard } from './PhotoCard';

interface PhotoGridProps {
  photos: SearchResult[];
  onPhotoClick: (index: number) => void;
  isLoading?: boolean;
}

function SkeletonCard() {
  return (
    <div className="aspect-square bg-surface-container-high animate-pulse" aria-hidden="true" />
  );
}

export function PhotoGrid({ photos, onPhotoClick, isLoading }: PhotoGridProps) {
  if (isLoading && photos.length === 0) {
    return (
      <section
        className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-sm"
        aria-label="Loading photos"
      >
        {Array.from({ length: 10 }).map((_, i) => (
          <SkeletonCard key={i} />
        ))}
      </section>
    );
  }

  return (
    <section
      className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-sm"
      role="list"
      aria-label="Photo results"
    >
      {photos.map((photo, i) => (
        <PhotoCard key={photo.id} photo={photo} index={i} onClick={onPhotoClick} />
      ))}
    </section>
  );
}
