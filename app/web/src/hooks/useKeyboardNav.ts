import { useEffect } from 'react';

interface Options {
  onPrev: () => void;
  onNext: () => void;
  onClose: () => void;
  enabled: boolean;
}

export function useKeyboardNav({ onPrev, onNext, onClose, enabled }: Options) {
  useEffect(() => {
    if (!enabled) return;

    function handler(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose();
      else if (e.key === 'ArrowLeft') onPrev();
      else if (e.key === 'ArrowRight') onNext();
    }

    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [enabled, onPrev, onNext, onClose]);
}
