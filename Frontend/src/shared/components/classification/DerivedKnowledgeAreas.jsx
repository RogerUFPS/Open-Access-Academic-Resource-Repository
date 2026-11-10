"use client";

import { AlertTriangle, Lock, RefreshCw } from "lucide-react";
import { capitalizeWords } from "@/lib/utils";
import OriginBadge from "./OriginBadge";

/**
 * Áreas del conocimiento derivadas: chips bloqueados, sin botón de quitar.
 */
export default function DerivedKnowledgeAreas({
  id = "knowledge_areas",
  areas = [],
  loading = false,
  error = null,
  onRetry,
  emptyMessage = "Aún no hay áreas asociadas.",
  isPreview = false,
}) {
  const labelId = `${id}-label`;
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-4 shadow-2xs space-y-2.5">
      <div className="flex items-center justify-between pb-1 border-b border-gray-100 gap-2">
        <span id={labelId} className="text-[11px] font-bold text-gray-700 uppercase tracking-wider flex items-center gap-1.5">
          <Lock className="w-3 h-3 text-gray-500" aria-hidden="true" />
          Áreas del conocimiento (automáticas)
        </span>
        {!loading && !error && (
          <span className="text-[10px] bg-slate-100 text-slate-600 font-semibold px-2 py-0.5 rounded-full">
            {areas.length} {areas.length === 1 ? "área" : "áreas"}
          </span>
        )}
      </div>

      <p className="text-[11px] text-gray-500">
        Derivada automáticamente de los programas académicos. No se puede editar.
      </p>

      <div aria-labelledby={labelId} aria-busy={loading ? "true" : undefined} aria-live="polite">
        {loading ? (
          <div className="flex flex-wrap gap-2" aria-label="Cargando áreas">
            {[72, 112, 88].map((width) => (
              <span key={width} className="h-6 rounded-lg bg-gray-200 animate-pulse" style={{ width }} />
            ))}
          </div>
        ) : error ? (
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1 rounded-lg border border-rose-200 bg-rose-50 px-2.5 py-1 text-xs font-semibold text-rose-700">
              <AlertTriangle className="w-3.5 h-3.5" aria-hidden="true" />
              No se pudieron calcular las áreas
            </span>
            {onRetry && (
              <button
                type="button"
                onClick={onRetry}
                className="inline-flex items-center gap-1 rounded-lg border border-gray-300 px-2.5 py-1 text-xs font-medium text-gray-700 hover:bg-gray-50 cursor-pointer"
              >
                <RefreshCw className="w-3.5 h-3.5" aria-hidden="true" />
                Reintentar
              </button>
            )}
          </div>
        ) : areas.length === 0 ? (
          <p className="text-xs italic text-gray-400">{emptyMessage}</p>
        ) : (
          <ul className="flex flex-wrap gap-2">
            {areas.map((area) => (
              <li key={area.id}>
                <span
                  aria-disabled="true"
                  title="Derivada automáticamente"
                  className="inline-flex items-center gap-1.5 rounded-lg border border-gray-200 bg-gray-50 px-2.5 py-1 text-xs font-semibold text-gray-800"
                >
                  <Lock className="w-3 h-3 text-gray-500" aria-hidden="true" />
                  <span>{capitalizeWords(area.name)}</span>
                  <OriginBadge isManual={Boolean(area.is_manual)} isDerived={area.is_derived !== false} />
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {isPreview && !loading && !error && areas.length > 0 && (
        <p className="text-[10px] text-gray-400">Vista previa: el backend confirmará las áreas al guardar.</p>
      )}
    </div>
  );
}
