import { useState, useCallback, useRef, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  usePeople,
  useSearchInfinite,
  flattenPages,
  useMe,
  useSetPhotoHidden,
} from '../../api/queries';
import { useSearchParamString, useSearchParamArray } from '../../hooks/useSearchParamsState';
import { TopBar } from '../../layout/TopBar';
import { PeopleFilter } from './PeopleFilter';
import { DateRangeChip } from './DateRangeChip';
import { DateRangePopover } from './DateRangePopover';
import { PhotoGrid } from './PhotoGrid';
import { Pagination } from './Pagination';
import { PhotoDetailModal } from '../detail/PhotoDetailModal';

const SUGGESTIONS = [
  'grandma at the beach',
  'birthday party',
  'family vacation',
  'everyone smiling',
  'summer holidays',
  'old photos',
];

export function GalleryPage() {
  const [q, setQ] = useSearchParamString('q');
  const [inputQ, setInputQ] = useState(() => q);

  useEffect(() => {
    setInputQ(q);
  }, [q]);
  const [dateFrom] = useSearchParamString('date_from');
  const [dateTo] = useSearchParamString('date_to');
  const [, setSearchParams] = useSearchParams();
  const [personIds, setPersonIds] = useSearchParamArray('person_id');
  const [peopleMode, setPeopleMode] = useSearchParamString('people_mode', 'any');

  const [showDatePicker, setShowDatePicker] = useState(false);
  const [activePhotoIndex, setActivePhotoIndex] = useState<number | null>(null);

  const { data: people } = usePeople();
  const { data: me } = useMe();
  const isAdmin = !!me?.is_admin;
  const [view, setView] = useSearchParamString('view');
  const hiddenOnly = isAdmin && view === 'hidden';

  const setHidden = useSetPhotoHidden();
  const [toast, setToast] = useState<
    { photoId: string; hidden: boolean } | { error: string } | null
  >(null);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 6000);
    return () => clearTimeout(t);
  }, [toast]);

  const toggleHidden = useCallback(
    (photoId: string, hidden: boolean) => {
      setHidden.mutate(
        { photoId, hidden },
        {
          onSuccess: () => setToast({ photoId, hidden }),
          onError: () =>
            setToast({ error: hidden ? "Couldn't hide photo" : "Couldn't unhide photo" }),
        },
      );
    },
    [setHidden],
  );

  const filters = {
    q,
    dateFrom,
    dateTo,
    personIds,
    peopleMode: (peopleMode === 'all' ? 'all' : 'any') as 'any' | 'all',
    hiddenOnly,
  };

  const {
    data,
    isLoading,
    isFetchingNextPage,
    fetchNextPage,
    hasNextPage,
  } = useSearchInfinite(filters);

  const allPhotos = flattenPages(data?.pages);

  const allPhotosRef = useRef(allPhotos);
  allPhotosRef.current = allPhotos;
  const hasNextPageRef = useRef(hasNextPage);
  hasNextPageRef.current = hasNextPage;
  const fetchNextPageRef = useRef(fetchNextPage);
  fetchNextPageRef.current = fetchNextPage;
  const pendingAdvanceRef = useRef(false);

  function handleSearch() {
    const trimmed = inputQ.trim();
    setQ(trimmed);
  }

  function handleSuggestion(s: string) {
    setInputQ(s);
    setQ(s);
  }

  function handlePersonToggle(id: string) {
    if (personIds.includes(id)) {
      setPersonIds(personIds.filter(p => p !== id));
    } else {
      setPersonIds([...personIds, id]);
    }
  }

  function handleModeToggle() {
    setPeopleMode(peopleMode === 'any' ? 'all' : 'any');
  }

  function handleDateApply(from: string, to: string) {
    setSearchParams(prev => {
      const next = new URLSearchParams(prev);
      if (from) next.set('date_from', from);
      else next.delete('date_from');
      if (to) next.set('date_to', to);
      else next.delete('date_to');
      return next;
    }, { replace: true });
  }

  const openPhoto = useCallback((index: number) => {
    setActivePhotoIndex(index);
  }, []);

  const closePhoto = useCallback(() => {
    setActivePhotoIndex(null);
  }, []);

  const goToPrev = useCallback(() => {
    setActivePhotoIndex(prev => (prev != null && prev > 0 ? prev - 1 : prev));
  }, []);

  const goToNext = useCallback(() => {
    setActivePhotoIndex(prev => {
      if (prev == null) return prev;
      if (prev < allPhotosRef.current.length - 1) return prev + 1;
      if (hasNextPageRef.current && !pendingAdvanceRef.current) {
        pendingAdvanceRef.current = true;
        fetchNextPageRef.current();
      }
      return prev;
    });
  }, []);

  useEffect(() => {
    if (
      pendingAdvanceRef.current &&
      activePhotoIndex != null &&
      allPhotos.length > activePhotoIndex + 1
    ) {
      pendingAdvanceRef.current = false;
      setActivePhotoIndex(prev => (prev != null ? prev + 1 : prev));
    }
  }, [allPhotos.length, activePhotoIndex]);

  const hasFilters = !!(q || dateFrom || dateTo || personIds.length || hiddenOnly);

  return (
    <>
      <TopBar query={inputQ} onQueryChange={setInputQ} onSearch={handleSearch} isPending={inputQ.trim() !== q} />

      <main className="flex-1 px-margin-mobile md:px-margin-desktop py-lg">
        {/* Filters Header */}
        <section className="mb-xl flex flex-col gap-lg">
          <div className="flex flex-col md:flex-row md:items-end justify-between gap-lg">
            {people && people.length > 0 && (
              <PeopleFilter
                people={people}
                selectedIds={personIds}
                mode={filters.peopleMode}
                onToggle={handlePersonToggle}
                onModeToggle={handleModeToggle}
              />
            )}
            <div className="relative">
              <DateRangeChip
                dateFrom={dateFrom}
                dateTo={dateTo}
                onClick={() => setShowDatePicker(v => !v)}
              />
              {showDatePicker && (
                <DateRangePopover
                  dateFrom={dateFrom}
                  dateTo={dateTo}
                  onApply={handleDateApply}
                  onClose={() => setShowDatePicker(false)}
                />
              )}
            </div>
            {isAdmin && (
              <div className="flex flex-col gap-md">
                <h3 className="text-label-md text-on-surface-variant uppercase tracking-wider">
                  Admin
                </h3>
                <button
                  type="button"
                  onClick={() => setView(hiddenOnly ? '' : 'hidden')}
                  aria-pressed={hiddenOnly}
                  className={`flex items-center gap-sm rounded-xl px-md py-sm border transition-colors ${
                    hiddenOnly
                      ? 'bg-primary text-on-primary border-primary'
                      : 'bg-surface-container-low text-on-surface border-outline-variant hover:border-primary'
                  }`}
                >
                  <span className="material-symbols-outlined text-[18px]">visibility_off</span>
                  <span className="text-body-md">Hidden photos</span>
                </button>
              </div>
            )}
          </div>
        </section>

        {/* Content */}
        {!hasFilters ? (
          <EmptyState onSuggestion={handleSuggestion} />
        ) : isLoading ? (
          <PhotoGrid photos={[]} onPhotoClick={openPhoto} isLoading />
        ) : allPhotos.length === 0 ? (
          hiddenOnly ? <NoHidden /> : <NoResults />
        ) : (
          <>
            <div className="mb-md">
              <p className="text-label-md text-on-surface-variant" aria-live="polite">
                {allPhotos.length} photo{allPhotos.length !== 1 ? 's' : ''}
              </p>
            </div>
            <PhotoGrid photos={allPhotos} onPhotoClick={openPhoto} />
            <Pagination
              loadedCount={allPhotos.length}
              hasMore={!!hasNextPage}
              isLoadingMore={isFetchingNextPage}
              onLoadMore={() => fetchNextPage()}
            />
          </>
        )}
      </main>

      {/* Photo detail overlay */}
      {activePhotoIndex != null && allPhotos[activePhotoIndex] && (
        <PhotoDetailModal
          photo={allPhotos[activePhotoIndex]}
          index={activePhotoIndex}
          total={allPhotos.length}
          onClose={closePhoto}
          onPrev={goToPrev}
          onNext={goToNext}
          hasPrev={activePhotoIndex > 0}
          hasNext={activePhotoIndex < allPhotos.length - 1 || !!hasNextPage}
          isLoadingNext={isFetchingNextPage && activePhotoIndex === allPhotos.length - 1}
          isAdmin={isAdmin}
          onToggleHidden={toggleHidden}
          isTogglingHidden={setHidden.isPending}
        />
      )}

      {toast && (
        <div
          role="status"
          className="fixed bottom-[76px] md:bottom-lg left-1/2 -translate-x-1/2 z-[110] flex items-center gap-md bg-inverse-surface text-inverse-on-surface px-lg py-md rounded-xl shadow-lg"
        >
          {'error' in toast ? (
            <span className="text-body-md">{toast.error}</span>
          ) : (
            <>
              <span className="text-body-md">
                {toast.hidden ? 'Photo hidden from everyone except admins' : 'Photo visible again'}
              </span>
              <button
                type="button"
                onClick={() => {
                  const { photoId, hidden } = toast;
                  setToast(null);
                  toggleHidden(photoId, !hidden);
                }}
                className="text-label-md font-bold underline"
              >
                Undo
              </button>
            </>
          )}
        </div>
      )}
    </>
  );
}

function EmptyState({ onSuggestion }: { onSuggestion: (s: string) => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-[80px] gap-lg text-center">
      <span className="material-symbols-outlined text-[64px] text-on-surface-variant">
        photo_library
      </span>
      <div>
        <p className="text-headline-sm text-on-surface font-bold mb-xs">
          Search the family archive
        </p>
        <p className="text-body-md text-on-surface-variant">
          Describe a memory, a person, or a place
        </p>
      </div>
      <div className="flex flex-wrap gap-sm justify-center mt-sm">
        {SUGGESTIONS.map(s => (
          <button
            key={s}
            onClick={() => onSuggestion(s)}
            className="px-md py-sm rounded-full border border-outline-variant text-body-md text-on-surface-variant hover:bg-surface-container-high transition-colors"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}

function NoHidden() {
  return (
    <div className="flex flex-col items-center justify-center py-[80px] gap-lg text-center">
      <span className="material-symbols-outlined text-[64px] text-on-surface-variant">
        visibility
      </span>
      <div>
        <p className="text-headline-sm text-on-surface font-bold mb-xs">No hidden photos</p>
        <p className="text-body-md text-on-surface-variant">
          Photos you hide show up here so you can unhide them
        </p>
      </div>
    </div>
  );
}

function NoResults() {
  return (
    <div className="flex flex-col items-center justify-center py-[80px] gap-lg text-center">
      <span className="material-symbols-outlined text-[64px] text-on-surface-variant">
        search_off
      </span>
      <div>
        <p className="text-headline-sm text-on-surface font-bold mb-xs">No photos found</p>
        <p className="text-body-md text-on-surface-variant">
          Try different words or remove some filters
        </p>
      </div>
    </div>
  );
}
