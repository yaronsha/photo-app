import type { SearchResult } from '../../api/types';
import type { PhotoInfo } from '../../api/types';
import { PhotoLabels } from './PhotoLabels';

interface PhotoSidebarProps {
  photo: SearchResult;
  info: PhotoInfo | null | undefined;
  isLoadingInfo: boolean;
}

function formatDate(str: string | null | undefined): string {
  if (!str) return '';
  try {
    const d = new Date(str);
    if (isNaN(d.getTime())) return str.slice(0, 10);
    return d.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    });
  } catch {
    return str.slice(0, 10);
  }
}

function formatTime(str: string | null | undefined): string {
  if (!str) return '';
  try {
    const d = new Date(str);
    if (isNaN(d.getTime())) return '';
    return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
  } catch {
    return '';
  }
}

export function PhotoSidebar({ photo, info, isLoadingInfo }: PhotoSidebarProps) {
  const merged = info ?? photo;
  const caption = merged.caption;
  const description = info?.description;
  const takenAt = merged.taken_at;
  const locationName = merged.location_name;
  const people = info?.people ?? photo.people ?? [];
  const tags = info?.tags ?? photo.tags ?? [];
  const activities = info?.activities ?? photo.activities ?? [];

  return (
    <aside className="w-full md:w-[320px] bg-surface border-l border-outline-variant flex flex-col overflow-y-auto">
      {/* Asset Header */}
      <div className="p-lg flex items-center gap-md border-b border-outline-variant">
        <div>
          <p className="text-label-md text-on-surface-variant uppercase tracking-wider">
            Asset Information
          </p>
          {caption && (
            <h3 className="text-headline-sm text-primary mt-xs leading-snug">{caption}</h3>
          )}
          {people.length > 0 && (
            <div className="flex flex-wrap gap-xs mt-sm">
              {people.map(p => (
                <span
                  key={p.id}
                  className="px-sm py-xs bg-primary-fixed text-primary text-label-sm rounded-full font-medium"
                >
                  {p.name}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Description & Labels */}
      <div className="p-lg space-y-lg">
        {description && (
          <div className="space-y-sm">
            <h4 className="text-label-md text-on-surface-variant uppercase tracking-wider">
              Description
            </h4>
            <p className="text-body-md text-on-surface leading-relaxed">{description}</p>
          </div>
        )}

        {isLoadingInfo ? (
          <div className="space-y-sm">
            <div className="h-4 w-16 bg-surface-container-high rounded animate-pulse" />
            <div className="flex gap-xs flex-wrap">
              <div className="h-6 w-16 bg-surface-container-high rounded-full animate-pulse" />
              <div className="h-6 w-20 bg-surface-container-high rounded-full animate-pulse" />
            </div>
          </div>
        ) : (
          <PhotoLabels
            tags={tags}
            activities={activities}
            subjectType={merged.subject_type}
            primaryFocus={merged.primary_focus}
            settingType={merged.setting_type}
            indoorOutdoor={merged.indoor_outdoor}
            sharpness={merged.sharpness}
            faceClarityScore={merged.face_clarity_score}
            contentType={merged.content_type}
          />
        )}
      </div>

      {/* EXIF / Details */}
      <div className="p-lg bg-surface-container-low/50 space-y-md border-y border-outline-variant">
        {takenAt && (
          <div className="flex items-center gap-md">
            <span className="material-symbols-outlined text-outline text-[20px]">
              calendar_today
            </span>
            <div>
              <p className="text-label-md font-bold text-on-surface">{formatDate(takenAt)}</p>
              <p className="text-label-sm text-on-surface-variant">{formatTime(takenAt)}</p>
            </div>
          </div>
        )}
        {locationName && (
          <div className="flex items-center gap-md">
            <span className="material-symbols-outlined text-outline text-[20px]">location_on</span>
            <div>
              <p className="text-label-md font-bold text-on-surface">{locationName}</p>
            </div>
          </div>
        )}
      </div>

      {/* Action Bar */}
      <div className="mt-auto p-lg flex flex-col gap-sm">
        <a
          href={`/photo/${photo.id}`}
          download
          className="w-full flex items-center justify-center gap-sm bg-primary text-on-primary py-md rounded-xl text-label-md hover:opacity-90 transition-opacity"
        >
          <span className="material-symbols-outlined text-[18px]">download</span>
          Download High Res
        </a>
        <button
          disabled
          title="Coming soon"
          className="w-full flex items-center justify-center gap-sm border border-outline-variant text-on-surface-variant py-md rounded-xl text-label-md opacity-50 cursor-not-allowed"
        >
          <span className="material-symbols-outlined text-[18px]">edit</span>
          Edit Metadata
        </button>
      </div>
    </aside>
  );
}
