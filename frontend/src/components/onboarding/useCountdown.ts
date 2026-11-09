// src/components/onboarding/useCountdown.ts
// Seconds left until a deadline, ticking once a second. Used for "Resend in 0:42"
// and for waiting out a rate limit.
import { useCallback, useEffect, useState } from 'react';

export function useCountdown(initialSeconds = 0) {
  const [endsAt, setEndsAt] = useState(() => (initialSeconds > 0 ? Date.now() + initialSeconds * 1000 : 0));
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (endsAt <= Date.now()) return;
    const id = setInterval(() => {
      const t = Date.now();
      setNow(t);
      if (t >= endsAt) clearInterval(id);
    }, 1000);
    return () => clearInterval(id);
  }, [endsAt]);

  const start = useCallback((seconds: number) => {
    const t = Date.now();
    setNow(t);
    setEndsAt(seconds > 0 ? t + seconds * 1000 : 0);
  }, []);

  const secondsLeft = Math.max(0, Math.ceil((endsAt - now) / 1000));
  return { secondsLeft, start, active: secondsLeft > 0 };
}
