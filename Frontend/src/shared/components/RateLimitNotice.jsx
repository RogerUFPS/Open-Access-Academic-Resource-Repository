import { formatWait } from "@/shared/hooks/useRetryCountdown";

/** Generic 429 message: it never reveals whether the account exists. */
export default function RateLimitNotice({ remaining }) {
  if (!remaining) return null;
  return <div role="status" aria-live="polite" className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
    Demasiados intentos. Podrás intentarlo de nuevo en <span className="font-semibold tabular-nums">{formatWait(remaining)}</span>.
  </div>;
}
