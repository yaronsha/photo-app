import { useState, useCallback } from 'react';
import { usePeople, useSearchInfinite, flattenPages } from '../../api/queries';
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
  const [inputQ, setInputQ] = useState('');
  const [q, setQ] = useSearchParamString('q');
  const [dateFrom, setDateFrom] = useSearchParamString('date_from');
  const [dateTo, setDateTo] = useSearchParamString('date_to');
  const [personIds, setPersonIds] = useSearchParamArray('person_id');
  const [peopleMode, setPeopleMode] = useSearchParamString('people_mode', 'any');

  const [showDatePicker, setShowDatePicker] = useState(false);
  const [activePhotoIndex, setActivePhotoIndex] = useState<number | null>(null);

  // Sync input with URL param on initial load
  const [initialized, setInitialized] = useState(false);
  if (!initialized) {
    setInputQ(q);
    setInitialized(true);
  }

  const { data: people } = usePeople();

  const filters = {
    q,
    dateFrom,
    dateTo,
    personIds,
    peopleMode: (peopleMode === 'all' ? 'all' : 'any') as 'any' | 'all',
  };

  const {
    data,
    isLoading,
    isFetchingNextPage,
    fetchNextPage,
    hasNextPage,
  } = useSearchInfinite(filters);

  const allPhotos = flattenPages(data?.pages);

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
    setDateFrom(from);
    setDateTo(to);
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
    setActivePhotoIndex(prev =>
      prev != null && prev < allPhotos.length - 1 ? prev + 1 : prev,
    );
  }, [allPhotos.length]);

  const hasFilters = !!(q || dateFrom || dateTo || personIds.length);

  return (
    <>
      <TopBar query={inputQ} onQueryChange={setInputQ} onSearch={handleSearch} />

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
          </div>
        </section>

        {/* Content */}
        {!hasFilters ? (
          <EmptyState onSuggestion={handleSuggestion} />
        ) : isLoading ? (
          <PhotoGrid photos={[]} onPhotoClick={openPhoto} isLoading />
        ) : allPhotos.length === 0 ? (
          <NoResults />
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
          hasNext={activePhotoIndex < allPhotos.length - 1}
        />
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
