"use client";

import { useState } from "react";
import Link from "next/link";
import { AlertTriangle, Check, Copy, ExternalLink, Info, Search, XCircle } from "lucide-react";

const STATE_META = {
  ok: {
    label: "Recomendaciones listas",
    tone: "ok",
  },
  informacion_insuficiente: {
    label: "Se necesita más información",
    tone: "warning",
  },
  fuera_de_tema: {
    label: "Consulta fuera de alcance",
    tone: "neutral",
  },
  error_sistema: {
    label: "Error del sistema",
    tone: "error",
  },
};

function labelForProgram(program) {
  if (typeof program === "string") return program;
  if (program && typeof program === "object") {
    return program.name || program.nombre || program.label || String(program.id ?? "");
  }
  return String(program ?? "");
}

function labelForUnappliedFilter(item) {
  if (typeof item === "string") return item;
  if (item && typeof item === "object") {
    if (item.filtro && item.motivo) return `${item.filtro}: ${item.motivo}`;
    return item.mensaje || item.detail || item.name || JSON.stringify(item);
  }
  return String(item ?? "");
}

function SearchStrategyCard({ item, openPlatformInNewTab = false }) {
  const [copied, setCopied] = useState(false);

  const platformName = item?.plataforma ? String(item.plataforma) : "Plataforma académica";
  const platformId = item?.plataforma_id;
  const queryText = item?.cadena ? String(item.cadena) : "";
  const justification = item?.justificacion ? String(item.justificacion) : "";

  async function handleCopy() {
    if (!queryText) return;
    try {
      await navigator.clipboard.writeText(queryText);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  }

  return (
    <article className="rounded-lg border border-[#e7dfd9] bg-[#fcfaf8] p-3.5 text-sm text-[#1f1a1a]">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <Search className="h-4 w-4 shrink-0 text-[#a3141c]" aria-hidden="true" />
          <h4 className="font-semibold text-[#1f1a1a]">{platformName}</h4>
        </div>
        {platformId != null && String(platformId).trim() !== "" && (
          <Link
            href={`/bases-de-datos/${encodeURIComponent(String(platformId))}`}
            target={openPlatformInNewTab ? "_blank" : undefined}
            rel={openPlatformInNewTab ? "noopener noreferrer" : undefined}
            className="inline-flex items-center gap-1 rounded-sm text-xs font-semibold text-[#a3141c] underline decoration-[#c9a45c] underline-offset-4 hover:text-[#8a1018] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#a3141c]"
          >
            Ver recurso
            <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
          </Link>
        )}
      </div>

      {queryText && (
        <div className="mt-2.5">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-[#5c5252]">
              Cadena de búsqueda
            </span>
            <button
              type="button"
              onClick={handleCopy}
              className="inline-flex items-center gap-1.5 rounded-md border border-[#dcd3cc] bg-white px-2.5 py-1 text-xs font-semibold text-[#1f1a1a] transition hover:border-[#a3141c] hover:text-[#a3141c] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#a3141c]"
            >
              {copied ? (
                <>
                  <Check className="h-3.5 w-3.5 text-[#17643A]" aria-hidden="true" />
                  <span>Copiada</span>
                </>
              ) : (
                <>
                  <Copy className="h-3.5 w-3.5" aria-hidden="true" />
                  <span>Copiar</span>
                </>
              )}
            </button>
          </div>
          <pre className="mt-1.5 overflow-x-auto whitespace-pre-wrap break-words rounded-md border border-[#e7dfd9] bg-white px-3 py-2 font-mono text-xs leading-5 text-[#1f1a1a]">
            {queryText}
          </pre>
        </div>
      )}

      {justification && (
        <div className="mt-2.5 rounded-md bg-white/80 px-3 py-2 text-xs leading-5 text-[#4a4343]">
          <span className="font-semibold text-[#1f1a1a]">Justificación: </span>
          <span className="whitespace-pre-wrap break-words">{justification}</span>
        </div>
      )}
    </article>
  );
}

/**
 * Renderiza `turn.response` siempre como texto escapado (nunca HTML sin procesar).
 * Soporta los estados: ok, informacion_insuficiente, fuera_de_tema y error_sistema.
 */
export default function ChatResponseView({
  response,
  turnStatus = "completed",
  openPlatformInNewTab = false,
  showStateBadge = false,
}) {
  if (!response || typeof response !== "object") {
    if (turnStatus === "failed") {
      return (
        <div className="flex items-start gap-2.5 rounded-lg border border-[#f5c2c7] bg-[#fff5f5] p-3 text-sm text-[#820A1F]">
          <XCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <p className="whitespace-pre-wrap break-words">
            No fue posible completar la respuesta por un error del sistema. Intenta nuevamente más tarde.
          </p>
        </div>
      );
    }
    return (
      <p className="text-sm text-[#5c5252]">
        Sin contenido estructurado en la respuesta.
      </p>
    );
  }

  const estado = typeof response.estado === "string" ? response.estado : turnStatus === "failed" ? "error_sistema" : "ok";
  const mensaje = typeof response.mensaje === "string" && response.mensaje.trim() ? response.mensaje.trim() : null;
  const programas = Array.isArray(response.programas_seleccionados)
    ? response.programas_seleccionados.map(labelForProgram).filter(Boolean)
    : [];
  const busquedas = Array.isArray(response.busquedas) ? response.busquedas : [];
  const filtrosNoAplicados = Array.isArray(response.filtros_no_aplicados)
    ? response.filtros_no_aplicados.map(labelForUnappliedFilter).filter(Boolean)
    : [];

  const meta = STATE_META[estado] ?? { label: estado, tone: "neutral" };

  return (
    <div className="space-y-3">
      {showStateBadge && (
        <div className="flex flex-wrap items-center gap-2">
          <span
            className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${
              meta.tone === "ok"
                ? "bg-[#DDF5E7] text-[#17643A]"
                : meta.tone === "warning"
                  ? "bg-[#FFF0C7] text-[#7A4B00]"
                  : meta.tone === "error"
                    ? "bg-[#FFE1E3] text-[#820A1F]"
                    : "bg-[#EEF0F3] text-[#4B5563]"
            }`}
          >
            {meta.label}
          </span>
        </div>
      )}

      {estado === "error_sistema" && (
        <div className="flex items-start gap-2.5 rounded-lg border border-[#f5c2c7] bg-[#fff5f5] p-3 text-sm text-[#820A1F]">
          <XCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <p className="whitespace-pre-wrap break-words">
            {mensaje || "Ocurrió un error interno al procesar tu consulta. Intenta nuevamente más tarde."}
          </p>
        </div>
      )}

      {estado === "informacion_insuficiente" && (
        <div className="flex items-start gap-2.5 rounded-lg border border-[#f3d9a4] bg-[#fffaf0] p-3 text-sm text-[#6b4400]">
          <Info className="mt-0.5 h-4 w-4 shrink-0 text-[#a16207]" aria-hidden="true" />
          <div className="space-y-1">
            <p className="font-semibold">Necesito un poco más de contexto</p>
            <p className="whitespace-pre-wrap break-words">
              {mensaje || "Indica el programa académico, tema específico o idioma que buscas para generar estrategias de búsqueda."}
            </p>
          </div>
        </div>
      )}

      {estado === "fuera_de_tema" && (
        <div className="flex items-start gap-2.5 rounded-lg border border-[#dce0e5] bg-[#f7f8fa] p-3 text-sm text-[#374151]">
          <Info className="mt-0.5 h-4 w-4 shrink-0 text-[#68707C]" aria-hidden="true" />
          <div className="space-y-1">
            <p className="font-semibold text-[#1f1a1a]">Fuera del alcance del asistente</p>
            <p className="whitespace-pre-wrap break-words">
              {mensaje || "Este asistente está enfocado en orientar búsquedas académicas en las bases de datos y revistas de la biblioteca."}
            </p>
          </div>
        </div>
      )}

      {/* En estado ok, mensaje=null es normal y no representa un error. */}
      {estado !== "error_sistema" && estado !== "informacion_insuficiente" && estado !== "fuera_de_tema" && mensaje && (
        <p className="whitespace-pre-wrap break-words text-sm leading-6 text-[#1f1a1a]">{mensaje}</p>
      )}

      {programas.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-[#5c5252]">
            Programas seleccionados
          </p>
          <div className="flex flex-wrap gap-1.5">
            {programas.map((program, idx) => (
              <span
                key={`${program}-${idx}`}
                className="inline-flex items-center rounded-full border border-[#e7dfd9] bg-[#faf7f4] px-2.5 py-1 text-xs font-medium text-[#7f1218]"
              >
                {program}
              </span>
            ))}
          </div>
        </div>
      )}

      {busquedas.length > 0 && (
        <div className="space-y-2.5">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-[#5c5252]">
            Estrategias de búsqueda recomendadas ({busquedas.length})
          </p>
          <div className="space-y-2.5">
            {busquedas.map((item, idx) => (
              <SearchStrategyCard
                key={`${item?.plataforma_id ?? item?.plataforma ?? "search"}-${idx}`}
                item={item}
                openPlatformInNewTab={openPlatformInNewTab}
              />
            ))}
          </div>
        </div>
      )}

      {estado === "ok" && !mensaje && busquedas.length === 0 && programas.length === 0 && (
        <p className="text-sm text-[#5c5252]">
          No se generaron cadenas de búsqueda para esta consulta. Puedes precisar el tema o el programa académico.
        </p>
      )}

      {filtrosNoAplicados.length > 0 && (
        <div
          role="note"
          className="rounded-lg border border-[#f3d9a4] bg-[#fffbeb] p-3 text-xs leading-5 text-[#7A4B00]"
        >
          <div className="flex items-center gap-1.5 font-semibold">
            <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden="true" />
            <span>Filtros no aplicados</span>
          </div>
          <ul className="mt-1.5 list-disc space-y-1 pl-5">
            {filtrosNoAplicados.map((filterText, idx) => (
              <li key={`${idx}-${filterText}`} className="whitespace-pre-wrap break-words">
                {filterText}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
