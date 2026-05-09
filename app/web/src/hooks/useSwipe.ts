import { useRef, useCallback } from 'react';

const THRESHOLD = 50;

export function useSwipe(onSwipeLeft: () => void, onSwipeRight: () => void) {
  const touchX0 = useRef(0);

  const onTouchStart = useCallback((e: React.TouchEvent) => {
    touchX0.current = e.touches[0].clientX;
  }, []);

  const onTouchEnd = useCallback(
    (e: React.TouchEvent) => {
      const dx = e.changedTouches[0].clientX - touchX0.current;
      if (Math.abs(dx) > THRESHOLD) {
        if (dx > 0) onSwipeRight();
        else onSwipeLeft();
      }
    },
    [onSwipeLeft, onSwipeRight],
  );

  return { onTouchStart, onTouchEnd };
}
