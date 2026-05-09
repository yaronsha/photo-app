import { useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';

/**
 * Sync a single URL search param to/from React Router state.
 * Returns [value, setter].
 */
export function useSearchParamString(
  key: string,
  defaultValue = '',
): [string, (v: string) => void] {
  const [searchParams, setSearchParams] = useSearchParams();
  const value = searchParams.get(key) ?? defaultValue;

  const setValue = useCallback(
    (v: string) => {
      setSearchParams(prev => {
        const next = new URLSearchParams(prev);
        if (v) next.set(key, v);
        else next.delete(key);
        return next;
      }, { replace: true });
    },
    [key, setSearchParams],
  );

  return [value, setValue];
}

/**
 * Sync a repeatable URL param (multi-value) to/from state.
 * Returns [values, setter].
 */
export function useSearchParamArray(
  key: string,
): [string[], (v: string[]) => void] {
  const [searchParams, setSearchParams] = useSearchParams();
  const values = searchParams.getAll(key);

  const setValues = useCallback(
    (v: string[]) => {
      setSearchParams(prev => {
        const next = new URLSearchParams(prev);
        next.delete(key);
        v.forEach(item => next.append(key, item));
        return next;
      }, { replace: true });
    },
    [key, setSearchParams],
  );

  return [values, setValues];
}
