interface TopBarProps {
  query: string;
  onQueryChange: (v: string) => void;
  onSearch: () => void;
}

export function TopBar({ query, onQueryChange, onSearch }: TopBarProps) {
  return (
    <header className="flex justify-between items-center px-margin-mobile md:px-margin-desktop py-md w-full sticky top-0 bg-surface z-40 border-b border-outline-variant">
      <div className="flex items-center gap-lg flex-1">
        <form
          className="relative w-full max-w-xl"
          role="search"
          onSubmit={e => {
            e.preventDefault();
            onSearch();
          }}
        >
          <span className="material-symbols-outlined absolute left-md top-1/2 -translate-y-1/2 text-on-surface-variant pointer-events-none">
            search
          </span>
          <input
            type="search"
            value={query}
            onChange={e => onQueryChange(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') onSearch(); }}
            placeholder="Search your archive"
            aria-label="Search photos"
            className="w-full bg-surface-container-low border border-outline-variant focus:border-primary focus:ring-1 focus:ring-primary rounded-xl py-sm pl-[48px] pr-md text-body-md transition-all outline-none"
          />
        </form>
      </div>
      <div className="flex items-center gap-md ml-lg">
        <button
          className="w-10 h-10 flex items-center justify-center text-on-surface-variant hover:bg-surface-container-low transition-colors rounded-full"
          aria-label="Notifications"
        >
          <span className="material-symbols-outlined">notifications</span>
        </button>
      </div>
    </header>
  );
}
