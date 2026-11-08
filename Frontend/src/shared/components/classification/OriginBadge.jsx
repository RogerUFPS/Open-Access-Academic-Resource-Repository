import { Lock, PencilLine } from "lucide-react";

/**
 * Badge de procedencia según los flags del backend (sección 3.3).
 * Usa texto e icono para no depender solo del color.
 */
export default function OriginBadge({ isManual = false, isDerived = false }) {
  return (
    <span className="inline-flex items-center gap-1">
      {isManual && (
        <span className="inline-flex items-center gap-0.5 rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-bold text-emerald-800">
          <PencilLine className="h-2.5 w-2.5" aria-hidden="true" />
          Manual
        </span>
      )}
      {isDerived && (
        <span className="inline-flex items-center gap-0.5 rounded bg-blue-100 px-1.5 py-0.5 text-[10px] font-bold text-blue-800">
          <Lock className="h-2.5 w-2.5" aria-hidden="true" />
          Automática
        </span>
      )}
    </span>
  );
}

/** Interpreta un elemento del backend ({id, name, is_manual, is_derived}) o un ID simple. */
export function originOf(item) {
  if (item && typeof item === "object") {
    return { isManual: Boolean(item.is_manual), isDerived: Boolean(item.is_derived) };
  }
  return { isManual: true, isDerived: false };
}
