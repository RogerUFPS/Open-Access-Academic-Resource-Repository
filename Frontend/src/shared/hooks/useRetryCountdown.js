"use client";

import { useCallback, useEffect, useState } from "react";

// Sin Retry-After se bloquea el envío un tiempo prudente igualmente.
const DEFAULT_WAIT_SECONDS = 30;

/**
 * Countdown driven by a 429's `Retry-After`. While `remaining > 0` the form must
 * stay disabled; nothing is retried automatically when it reaches zero.
 */
export default function useRetryCountdown() {
  const [until, setUntil] = useState(0);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!until) return undefined;
    const timer = setInterval(() => {
      const current = Date.now();
      setNow(current);
      if (current >= until) {
        setUntil(0);
        clearInterval(timer);
      }
    }, 1000);
    return () => clearInterval(timer);
  }, [until]);

  /** Starts the countdown when `error` is a 429. Returns true if it was one. */
  const handleRateLimit = useCallback((error) => {
    if (error?.status !== 429) return false;
    const seconds = Number.isFinite(error.retryAfter) && error.retryAfter > 0 ? error.retryAfter : DEFAULT_WAIT_SECONDS;
    const current = Date.now();
    setNow(current);
    setUntil(current + seconds * 1000);
    return true;
  }, []);

  const remaining = until ? Math.max(0, Math.ceil((until - now) / 1000)) : 0;
  return { remaining, limited: remaining > 0, handleRateLimit };
}

export function formatWait(seconds) {
  if (seconds < 60) return `${seconds} s`;
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return rest ? `${minutes} min ${rest} s` : `${minutes} min`;
}
