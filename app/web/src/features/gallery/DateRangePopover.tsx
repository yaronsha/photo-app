import { useRef, useEffect } from 'react';
import { MonthYearPicker, type MonthYear } from './MonthYearPicker';

interface DateRangePopoverProps {
  dateFrom: string;
  dateTo: string;
  onApply: (from: string, to: string) => void;
  onClose: () => void;
}

function parseIso(iso: string): MonthYear | null {
  if (!iso) return null;
  const m = /^(\d{4})-(\d{2})/.exec(iso);
  if (!m) return null;
  return { year: Number(m[1]), month: Number(m[2]) - 1 };
}

function fromIso(my: MonthYear | null): string {
  if (!my) return '';
  const mm = String(my.month + 1).padStart(2, '0');
  return `${my.year}-${mm}-01`;
}

function toIsoEnd(my: MonthYear | null): string {
  if (!my) return '';
  const lastDay = new Date(my.year, my.month + 1, 0).getDate();
  const mm = String(my.month + 1).padStart(2, '0');
  const dd = String(lastDay).padStart(2, '0');
  return `${my.year}-${mm}-${dd}`;
}

export function DateRangePopover({
  dateFrom,
  dateTo,
  onApply,
  onClose,
}: DateRangePopoverProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    }
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [onClose]);

  useEffect(() => {
    function handler(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose();
    }
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [onClose]);

  const fromValue = parseIso(dateFrom);
  const toValue = parseIso(dateTo);

  function handleFromChange(v: MonthYear | null) {
    onApply(fromIso(v), dateTo);
  }

  function handleToChange(v: MonthYear | null) {
    onApply(dateFrom, toIsoEnd(v));
  }

  function handleClearAll() {
    onApply('', '');
  }

  return (
    <div
      ref={ref}
      className="absolute right-0 z-50 mt-xs bg-surface border border-outline-variant rounded-xl shadow-lg p-md flex flex-col gap-md"
      role="dialog"
      aria-label="Date range picker"
    >
      <div className="flex gap-lg">
        <MonthYearPicker label="From" value={fromValue} onChange={handleFromChange} max={toValue} />
        <MonthYearPicker label="To" value={toValue} onChange={handleToChange} min={fromValue} />
      </div>
      <div className="flex justify-between items-center border-t border-outline-variant pt-sm">
        <button
          type="button"
          onClick={handleClearAll}
          className="px-md py-xs rounded-xl text-label-md text-on-surface-variant hover:bg-surface-container-high transition-colors"
        >
          Clear all
        </button>
        <button
          type="button"
          onClick={onClose}
          className="px-md py-xs rounded-xl bg-primary text-on-primary text-label-md hover:opacity-90 transition-opacity"
        >
          Done
        </button>
      </div>
    </div>
  );
}
