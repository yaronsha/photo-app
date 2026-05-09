import { useState, useEffect } from 'react';

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

export interface MonthYear {
  year: number;
  month: number;
}

interface MonthYearPickerProps {
  label: string;
  value: MonthYear | null;
  onChange: (value: MonthYear | null) => void;
}

type View = 'month' | 'year' | 'decade';

const currentYear = new Date().getFullYear();

function decadeStart(y: number) {
  return Math.floor(y / 10) * 10;
}

function centuryStart(y: number) {
  return Math.floor(y / 100) * 100;
}

export function MonthYearPicker({ label, value, onChange }: MonthYearPickerProps) {
  const [view, setView] = useState<View>('month');
  const [pivotYear, setPivotYear] = useState<number>(value?.year ?? currentYear);
  const [pivotDecade, setPivotDecade] = useState<number>(decadeStart(value?.year ?? currentYear));
  const [pivotCentury, setPivotCentury] = useState<number>(centuryStart(value?.year ?? currentYear));

  useEffect(() => {
    if (value) {
      setPivotYear(value.year);
      setPivotDecade(decadeStart(value.year));
      setPivotCentury(centuryStart(value.year));
    }
  }, [value]);

  const selMonth = value?.month ?? null;
  const selYear = value?.year ?? null;

  function selectMonth(month: number) {
    onChange({ year: pivotYear, month });
  }

  function selectYear(year: number) {
    setPivotYear(year);
    setPivotDecade(decadeStart(year));
    setView('month');
    if (selMonth !== null) onChange({ year, month: selMonth });
  }

  function selectDecade(decade: number) {
    setPivotDecade(decade);
    setView('year');
  }

  return (
    <div className="flex flex-col gap-sm w-[220px]">
      <div className="flex items-center justify-between text-label-md text-on-surface-variant uppercase tracking-wider px-xs">
        <span>{label}</span>
        {value && (
          <button
            type="button"
            onClick={() => onChange(null)}
            className="text-label-sm text-on-surface-variant hover:text-on-surface px-xs"
          >
            Clear
          </button>
        )}
      </div>

      <div className="flex items-center justify-between bg-surface-container-low rounded-xl border border-outline-variant px-sm py-xs">
        <button
          type="button"
          onClick={() => {
            if (view === 'month') setPivotYear(y => y - 1);
            else if (view === 'year') setPivotDecade(d => d - 10);
            else setPivotCentury(c => c - 100);
          }}
          className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-surface-container-high text-on-surface-variant"
          aria-label="Previous"
        >
          <span className="material-symbols-outlined text-[20px]">chevron_left</span>
        </button>
        <button
          type="button"
          onClick={() => {
            if (view === 'month') setView('year');
            else if (view === 'year') setView('decade');
          }}
          className="text-body-md font-bold text-on-surface hover:text-primary px-sm"
        >
          {view === 'month' && pivotYear}
          {view === 'year' && `${pivotDecade}–${pivotDecade + 9}`}
          {view === 'decade' && `${pivotCentury}–${pivotCentury + 99}`}
        </button>
        <button
          type="button"
          onClick={() => {
            if (view === 'month') setPivotYear(y => y + 1);
            else if (view === 'year') setPivotDecade(d => d + 10);
            else setPivotCentury(c => c + 100);
          }}
          className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-surface-container-high text-on-surface-variant"
          aria-label="Next"
        >
          <span className="material-symbols-outlined text-[20px]">chevron_right</span>
        </button>
      </div>

      {view === 'month' && (
        <div className="grid grid-cols-3 gap-xs">
          {MONTHS.map((name, i) => {
            const isSel = selMonth === i && selYear === pivotYear;
            return (
              <button
                key={name}
                type="button"
                onClick={() => selectMonth(i)}
                className={
                  'h-9 rounded-lg text-label-md transition-colors ' +
                  (isSel
                    ? 'bg-primary text-on-primary font-bold'
                    : 'hover:bg-surface-container-high text-on-surface')
                }
              >
                {name}
              </button>
            );
          })}
        </div>
      )}

      {view === 'year' && (
        <div className="grid grid-cols-3 gap-xs">
          {Array.from({ length: 12 }, (_, i) => pivotDecade - 1 + i).map(y => {
            const inDecade = y >= pivotDecade && y < pivotDecade + 10;
            const isSel = selYear === y;
            return (
              <button
                key={y}
                type="button"
                onClick={() => selectYear(y)}
                className={
                  'h-9 rounded-lg text-label-md transition-colors ' +
                  (isSel
                    ? 'bg-primary text-on-primary font-bold'
                    : inDecade
                      ? 'hover:bg-surface-container-high text-on-surface'
                      : 'hover:bg-surface-container-high text-outline')
                }
              >
                {y}
              </button>
            );
          })}
        </div>
      )}

      {view === 'decade' && (
        <div className="grid grid-cols-3 gap-xs">
          {Array.from({ length: 12 }, (_, i) => pivotCentury - 10 + i * 10).map(d => {
            const inCentury = d >= pivotCentury && d < pivotCentury + 100;
            const isSel = selYear !== null && decadeStart(selYear) === d;
            return (
              <button
                key={d}
                type="button"
                onClick={() => selectDecade(d)}
                className={
                  'h-9 rounded-lg text-label-sm transition-colors ' +
                  (isSel
                    ? 'bg-primary text-on-primary font-bold'
                    : inCentury
                      ? 'hover:bg-surface-container-high text-on-surface'
                      : 'hover:bg-surface-container-high text-outline')
                }
              >
                {d}s
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
