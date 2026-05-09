import { useRef, useEffect } from 'react';
import { DayPicker } from 'react-day-picker';
import type { DateRange } from 'react-day-picker';
import 'react-day-picker/style.css';

interface DateRangePopoverProps {
  dateFrom: string;
  dateTo: string;
  onApply: (from: string, to: string) => void;
  onClose: () => void;
}

function parseIso(iso: string): Date | undefined {
  if (!iso) return undefined;
  const d = new Date(iso + 'T00:00:00');
  return isNaN(d.getTime()) ? undefined : d;
}

function toIsoDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

export function DateRangePopover({
  dateFrom,
  dateTo,
  onApply,
  onClose,
}: DateRangePopoverProps) {
  const ref = useRef<HTMLDivElement>(null);

  // Click-outside to close
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        onClose();
      }
    }
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [onClose]);

  // Escape to close
  useEffect(() => {
    function handler(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose();
    }
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [onClose]);

  const selected: DateRange = {
    from: parseIso(dateFrom),
    to: parseIso(dateTo),
  };

  function handleSelect(range: DateRange | undefined) {
    const from = range?.from ? toIsoDate(range.from) : '';
    const to = range?.to ? toIsoDate(range.to) : '';
    onApply(from, to);
  }

  function handleClear() {
    onApply('', '');
    onClose();
  }

  return (
    <div
      ref={ref}
      className="absolute z-50 mt-xs bg-surface border border-outline-variant rounded-xl shadow-lg p-md"
      role="dialog"
      aria-label="Date range picker"
    >
      <DayPicker
        mode="range"
        numberOfMonths={2}
        selected={selected}
        onSelect={handleSelect}
        classNames={{
          root: 'text-body-md',
          months: 'flex gap-lg flex-wrap',
          month_caption: 'text-label-md font-bold text-on-surface mb-sm px-md',
          nav: 'flex items-center gap-xs',
          button_previous: 'w-8 h-8 flex items-center justify-center rounded-full hover:bg-surface-container-high text-on-surface-variant',
          button_next: 'w-8 h-8 flex items-center justify-center rounded-full hover:bg-surface-container-high text-on-surface-variant',
          weeks: '',
          week: 'flex',
          weekday: 'w-9 h-9 flex items-center justify-center text-label-sm text-on-surface-variant uppercase',
          day: 'w-9 h-9 flex items-center justify-center',
          day_button: 'w-9 h-9 flex items-center justify-center rounded-full hover:bg-surface-container-high text-body-md transition-colors',
          selected: 'bg-primary-container text-on-primary',
          range_start: '!bg-primary !text-on-primary rounded-full',
          range_end: '!bg-primary !text-on-primary rounded-full',
          range_middle: 'bg-secondary-container text-on-secondary-container rounded-none',
          today: 'font-bold text-primary',
          outside: 'text-outline-variant',
          disabled: 'opacity-40 cursor-not-allowed',
        }}
      />
      <div className="flex justify-end gap-sm mt-sm border-t border-outline-variant pt-sm">
        <button
          onClick={handleClear}
          className="px-md py-xs rounded-xl border border-outline-variant text-on-surface-variant text-label-md hover:bg-surface-container-high transition-colors"
        >
          Clear
        </button>
        <button
          onClick={onClose}
          className="px-md py-xs rounded-xl bg-primary text-on-primary text-label-md hover:opacity-90 transition-opacity"
        >
          Done
        </button>
      </div>
    </div>
  );
}
