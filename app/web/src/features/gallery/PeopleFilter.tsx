import type { Person } from '../../api/types';

interface PeopleFilterProps {
  people: Person[];
  selectedIds: string[];
  mode: 'any' | 'all';
  onToggle: (id: string) => void;
  onModeToggle: () => void;
}

function getInitials(name: string): string {
  const parts = name.trim().split(/\s+/);
  return parts[0]?.[0]?.toUpperCase() ?? '?';
}

function getFirstName(name: string): string {
  return name.trim().split(/\s+/)[0] ?? name;
}

export function PeopleFilter({
  people,
  selectedIds,
  mode,
  onToggle,
  onModeToggle,
}: PeopleFilterProps) {
  if (!people.length) return null;

  return (
    <div className="flex-1">
      <div className="flex items-center gap-md mb-md">
        <h3 className="text-label-md text-on-surface-variant uppercase tracking-wider">People</h3>
        {selectedIds.length > 0 && (
          <button
            onClick={onModeToggle}
            className={`px-sm py-xs rounded-full text-label-sm transition-colors ${
              mode === 'all'
                ? 'bg-primary text-on-primary'
                : 'bg-surface-container-high text-on-surface-variant'
            }`}
            aria-label={`People filter mode: ${mode}`}
          >
            {mode === 'any' ? 'Any' : 'All'}
          </button>
        )}
      </div>
      <div className="flex items-center gap-md overflow-x-auto no-scrollbar pb-xs">
        {people.map(person => {
          const isSelected = selectedIds.includes(person.id);
          return (
            <button
              key={person.id}
              onClick={() => onToggle(person.id)}
              aria-pressed={isSelected}
              className="flex flex-col items-center gap-xs cursor-pointer group flex-shrink-0"
            >
              <div
                className={`w-14 h-14 rounded-full p-0.5 border-2 relative transition-all ${
                  isSelected
                    ? 'border-primary'
                    : 'border-transparent group-hover:border-outline-variant'
                }`}
              >
                <div
                  className={`w-full h-full rounded-full flex items-center justify-center font-bold text-headline-sm ${
                    isSelected
                      ? 'bg-primary-fixed text-primary'
                      : 'bg-surface-container-high text-on-surface-variant'
                  }`}
                >
                  {getInitials(person.name)}
                </div>
                {isSelected && (
                  <div className="absolute -top-1 -right-1 w-5 h-5 bg-primary text-on-primary rounded-full flex items-center justify-center shadow-sm">
                    <span className="material-symbols-outlined text-[14px]">check</span>
                  </div>
                )}
              </div>
              <span
                className={`text-label-md ${
                  isSelected ? 'text-primary font-bold' : 'text-on-surface-variant'
                }`}
              >
                {getFirstName(person.name)}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
