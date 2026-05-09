import { useState, useEffect } from 'react';

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const MIN_YEAR = 1920;

export interface MonthYear {
  year: number;
  month: number;
}

export function cmpMonthYear(a: MonthYear, b: MonthYear): number {
  return a.year !== b.year ? a.year - b.year : a.month - b.month;
}

interface NavButtonProps {
  onClick: () => void;
  disabled?: boolean;
  label: string;
  icon: string;
}

function NavButton({ onClick, disabled, label, icon }: NavButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-surface-container-high text-on-surface-variant disabled:opacity-30 disabled:cursor-not-allowed"
    >
      <span className="material-symbols-outlined text-[20px]">{icon}</span>
    </button>
  );
}

interface MonthYearPickerProps {
  label: string;
  value: MonthYear | null;
  onChange: (value: MonthYear | null) => void;
  min?: MonthYear | null;
  max?: MonthYear | null;
  'data-testid'?: string;
}

type View = 'month' | 'year';

const _now = new Date();
const currentYear = _now.getFullYear();
const currentMonth = _now.getMonth();

function decadeStart(y: number) {
  return Math.floor(y / 10) * 10;
}

export function MonthYearPicker({ label, value, onChange, min, max, 'data-testid': testId }: MonthYearPickerProps) {
  const [view, setView] = useState<View>('month');
  const [pivotYear, setPivotYear] = useState<number>(value?.year ?? currentYear);
  const [pivotDecade, setPivotDecade] = useState<number>(decadeStart(value?.year ?? currentYear));

  useEffect(() => {
    if (value) {
      setPivotYear(value.year);
      setPivotDecade(decadeStart(value.year));
    } else {
      setView('month');
      setPivotYear(currentYear);
      setPivotDecade(decadeStart(currentYear));
    }
  }, [value]);

  const effectiveMin: MonthYear = min ?? { year: MIN_YEAR, month: 0 };
  const effectiveMax: MonthYear = max ?? { year: currentYear, month: currentMonth };

  function isMonthDisabled(year: number, month: number): boolean {
    return (
      cmpMonthYear({ year, month }, effectiveMin) < 0 ||
      cmpMonthYear({ year, month }, effectiveMax) > 0
    );
  }

  function isYearDisabled(year: number): boolean {
    return year < effectiveMin.year || year > effectiveMax.year;
  }

  const selMonth = value?.month ?? null;
  const selYear = value?.year ?? null;

  function selectMonth(month: number) {
    if (!isMonthDisabled(pivotYear, month)) onChange({ year: pivotYear, month });
  }

  function selectYear(year: number) {
    if (isYearDisabled(year)) return;
    setPivotYear(year);
    setPivotDecade(decadeStart(year));
    setView('month');
    if (selMonth !== null && !isMonthDisabled(year, selMonth)) {
      onChange({ year, month: selMonth });
    }
  }

  const minDecade = decadeStart(effectiveMin.year);
  const maxDecade = decadeStart(effectiveMax.year);

  const canPrevYear = pivotYear > effectiveMin.year;
  const canNextYear = pivotYear < effectiveMax.year;
  const canPrevDecade = pivotDecade > minDecade;
  const canNextDecade = pivotDecade < maxDecade;

  return (
    <div className="flex flex-col gap-sm w-[220px]" data-testid={testId}>
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
        {view === 'month' ? (
          <NavButton
            onClick={() => setPivotYear(y => y - 1)}
            disabled={!canPrevYear}
            label="Previous year"
            icon="chevron_left"
          />
        ) : (
          <NavButton
            onClick={() => setView('month')}
            label="Back to months"
            icon="arrow_back"
          />
        )}

        {view === 'month' ? (
          <button
            type="button"
            onClick={() => setView('year')}
            className="text-body-md font-bold text-on-surface hover:text-primary px-sm flex items-center gap-1"
          >
            {pivotYear}
            <span className="material-symbols-outlined text-[16px] text-on-surface-variant">expand_more</span>
          </button>
        ) : (
          <span className="text-body-md font-bold text-on-surface px-sm">
            {pivotDecade}–{pivotDecade + 9}
          </span>
        )}

        {view === 'month' ? (
          <NavButton
            onClick={() => setPivotYear(y => y + 1)}
            disabled={!canNextYear}
            label="Next year"
            icon="chevron_right"
          />
        ) : (
          <div className="flex">
            <NavButton
              onClick={() => setPivotDecade(d => d - 10)}
              disabled={!canPrevDecade}
              label="Previous decade"
              icon="chevron_left"
            />
            <NavButton
              onClick={() => setPivotDecade(d => d + 10)}
              disabled={!canNextDecade}
              label="Next decade"
              icon="chevron_right"
            />
          </div>
        )}
      </div>

      {view === 'month' && (
        <div className="grid grid-cols-3 gap-xs">
          {MONTHS.map((name, i) => {
            const isSel = selMonth === i && selYear === pivotYear;
            const disabled = isMonthDisabled(pivotYear, i);
            return (
              <button
                key={name}
                type="button"
                onClick={() => selectMonth(i)}
                disabled={disabled}
                className={
                  'h-9 rounded-lg text-label-md transition-colors ' +
                  (isSel
                    ? 'bg-primary text-on-primary font-bold'
                    : disabled
                      ? 'text-outline opacity-40 cursor-not-allowed'
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
            const disabled = isYearDisabled(y);
            return (
              <button
                key={y}
                type="button"
                onClick={() => selectYear(y)}
                disabled={disabled}
                className={
                  'h-9 rounded-lg text-label-md transition-colors ' +
                  (isSel
                    ? 'bg-primary text-on-primary font-bold'
                    : disabled
                      ? 'text-outline opacity-30 cursor-not-allowed'
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
    </div>
  );
}
