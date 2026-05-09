interface DateRangeChipProps {
  dateFrom: string;
  dateTo: string;
  onClick: () => void;
}

function formatMonthYear(iso: string): string {
  if (!iso) return '';
  try {
    const [year, month] = iso.split('-');
    const d = new Date(Number(year), Number(month) - 1, 1);
    return d.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
  } catch {
    return iso;
  }
}

export function DateRangeChip({ dateFrom, dateTo, onClick }: DateRangeChipProps) {
  return (
    <div className="flex flex-col gap-md">
      <h3 className="text-label-md text-on-surface-variant uppercase tracking-wider">
        Date Range
      </h3>
      <button
        type="button"
        onClick={onClick}
        className="flex items-center gap-sm bg-surface-container-low rounded-xl px-md py-sm border border-outline-variant hover:border-primary transition-colors text-left"
        aria-label="Open date range picker"
      >
        <div className="flex flex-col">
          <span className="text-label-sm text-outline">From</span>
          <span className="text-body-md text-on-surface">
            {dateFrom ? formatMonthYear(dateFrom) : '—'}
          </span>
        </div>
        <span className="material-symbols-outlined text-outline">arrow_forward</span>
        <div className="flex flex-col">
          <span className="text-label-sm text-outline">To</span>
          <span className="text-body-md text-on-surface">
            {dateTo ? formatMonthYear(dateTo) : '—'}
          </span>
        </div>
        <span className="ml-md text-primary material-symbols-outlined">calendar_month</span>
      </button>
    </div>
  );
}
