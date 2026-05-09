interface PaginationProps {
  loadedCount: number;
  hasMore: boolean;
  isLoadingMore: boolean;
  onLoadMore: () => void;
}

export function Pagination({
  loadedCount,
  hasMore,
  isLoadingMore,
  onLoadMore,
}: PaginationProps) {
  if (loadedCount === 0) return null;

  return (
    <footer className="mt-xl flex items-center justify-between border-t border-outline-variant pt-lg">
      <div className="hidden md:block">
        <p className="text-label-md text-on-surface-variant">
          {loadedCount} photo{loadedCount !== 1 ? 's' : ''} loaded
          {hasMore ? ' — more available' : ''}
        </p>
      </div>

      <div className="flex items-center gap-xs">
        {hasMore && (
          <button
            onClick={onLoadMore}
            disabled={isLoadingMore}
            className="px-lg py-sm rounded-xl bg-primary text-on-primary text-label-md hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            {isLoadingMore ? 'Loading…' : 'Load more'}
          </button>
        )}
      </div>

      <div className="hidden md:block">
        {!hasMore && loadedCount > 0 && (
          <p className="text-label-md text-on-surface-variant">All results loaded</p>
        )}
      </div>
    </footer>
  );
}
