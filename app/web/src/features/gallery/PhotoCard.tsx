import type { SearchResult } from '../../api/types';

interface PhotoCardProps {
  photo: SearchResult;
  index: number;
  onClick: (index: number) => void;
}

function getBadge(photo: SearchResult): { text: string; red: boolean } | null {
  if (photo.sharpness === 'very_blurry') return { text: 'blurry', red: true };
  if (photo.sharpness === 'slightly_blurry') return { text: '~blurry', red: false };
  if (photo.content_type === 'document') return { text: 'doc', red: false };
  if (photo.content_type === 'other') return { text: 'other', red: false };
  return null;
}

export function PhotoCard({ photo, index, onClick }: PhotoCardProps) {
  const badge = getBadge(photo);

  return (
    <div
      className="aspect-square relative overflow-hidden bg-surface-container-high cursor-pointer group"
      role="listitem"
      tabIndex={0}
      aria-label={photo.caption ?? 'Family photo'}
      onClick={() => onClick(index)}
      onKeyDown={e => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onClick(index);
        }
      }}
    >
      <img
        className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
        src={photo.thumb_url}
        alt={photo.caption ?? ''}
        loading="lazy"
        decoding="async"
      />
      {badge && (
        <span
          className={`absolute top-xs right-xs text-label-sm px-xs py-[2px] rounded text-white ${
            badge.red ? 'bg-error' : 'bg-outline'
          }`}
        >
          {badge.text}
        </span>
      )}
    </div>
  );
}
