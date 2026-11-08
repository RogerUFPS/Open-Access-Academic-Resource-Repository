"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { AlertTriangle, Bell, X } from "lucide-react";
import { formatDate, getLinkAlertsPage } from "@/features/admin/harvesting/harvesting";
import {
  CONFIRMED_ALERTS_HREF,
  CONFIRMED_FAILURES_QUERY,
  httpStatusLabel,
  resolveLinkResources,
} from "@/features/admin/harvesting/linkMonitoring";

const PREVIEW_SIZE = 5;

/**
 * Menú lateral de notificaciones. No hay API de notificaciones ni de leído:
 * al abrirse consulta las caídas confirmadas vigentes y muestra el total
 * según `total_items`.
 */
export default function LinkAlertsMenu({ open, onClose }) {
  const panelRef = useRef(null);
  const cache = useRef({ platforms: null, journals: new Map() });
  const [openCount, setOpenCount] = useState(0);
  const [state, setState] = useState({ key: -1, total: 0, rows: [], resources: new Map(), error: null });

  // Cada apertura cuenta como una nueva consulta.
  const [wasOpen, setWasOpen] = useState(open);
  if (open !== wasOpen) {
    setWasOpen(open);
    if (open) setOpenCount((value) => value + 1);
  }

  useEffect(() => {
    if (!open) return undefined;
    const controller = new AbortController();
    const key = openCount;
    getLinkAlertsPage(CONFIRMED_FAILURES_QUERY, { pageSize: PREVIEW_SIZE }, controller.signal)
      .then(async (page) => {
        const rows = page.results || [];
        const resources = await resolveLinkResources(rows, controller.signal, cache.current);
        if (!controller.signal.aborted) {
          setState({ key, total: page.total_items ?? rows.length, rows, resources, error: null });
        }
      })
      .catch((error) => {
        if (!controller.signal.aborted) setState({ key, total: 0, rows: [], resources: new Map(), error });
      });
    return () => controller.abort();
  }, [open, openCount]);

  useEffect(() => {
    if (!open) return undefined;
    panelRef.current?.focus();
    const onKey = (event) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  const loading = state.key !== openCount;

  return (
    <div className="fixed inset-0 z-[60]">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} aria-hidden="true" />
      <aside
        ref={panelRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-labelledby="link-alerts-menu-title"
        className="absolute inset-y-0 right-0 flex w-full max-w-sm flex-col bg-white shadow-2xl outline-none"
      >
        <header className="flex items-center justify-between border-b border-gray-200 px-5 py-4">
          <h2 id="link-alerts-menu-title" className="flex items-center gap-2 text-base font-bold text-gray-900">
            <Bell className="h-4 w-4 text-[#7f1218]" aria-hidden="true" />
            Alertas de enlaces
          </h2>
          <button type="button" onClick={onClose} aria-label="Cerrar alertas" className="rounded-lg p-1.5 text-gray-500 hover:bg-gray-100">
            <X className="h-4 w-4" />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto px-5 py-4" aria-busy={loading} aria-live="polite">
          {loading ? (
            <div className="space-y-3" role="status" aria-label="Cargando alertas">
              {[0, 1, 2].map((item) => <div key={item} className="h-16 animate-pulse rounded-lg bg-gray-100" />)}
            </div>
          ) : state.error ? (
            <p role="alert" className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
              {state.error.status === 403
                ? "Tu cuenta no tiene permiso para consultar las verificaciones de enlaces."
                : state.error.message || "No se pudieron cargar las alertas."}
            </p>
          ) : state.total === 0 ? (
            <p className="rounded-lg bg-emerald-50 p-3 text-sm text-emerald-800">No hay caídas confirmadas vigentes.</p>
          ) : (
            <>
              <p className="mb-3 text-sm font-semibold text-rose-800">
                {state.total} {state.total === 1 ? "caída confirmada vigente" : "caídas confirmadas vigentes"}
              </p>
              <ul className="space-y-2">
                {state.rows.map((row) => {
                  const resource = state.resources.get(row.id);
                  return (
                    <li key={row.id} className="rounded-lg border border-rose-100 bg-rose-50/60 p-3 text-xs">
                      <p className="flex items-center gap-1.5 font-semibold text-gray-900">
                        <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-rose-600" aria-hidden="true" />
                        <span className="truncate">{resource?.name || `Plataforma #${row.platform}`}</span>
                      </p>
                      <p className="mt-0.5 text-gray-600">{resource?.context}</p>
                      <p className="mt-0.5 break-all text-gray-500">{row.url}</p>
                      <p className="mt-0.5 text-gray-500">
                        {httpStatusLabel(row)} · {row.fail_count} fallos · {formatDate(row.last_check)}
                      </p>
                    </li>
                  );
                })}
              </ul>
              {state.total > state.rows.length && (
                <p className="mt-3 text-xs text-gray-500">y {state.total - state.rows.length} más…</p>
              )}
            </>
          )}
        </div>

        <footer className="border-t border-gray-200 px-5 py-4">
          <Link
            href={CONFIRMED_ALERTS_HREF}
            onClick={onClose}
            className="inline-flex w-full items-center justify-center rounded-lg bg-[#7f1218] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[#6a0f14]"
          >
            Mostrar detalle
          </Link>
        </footer>
      </aside>
    </div>
  );
}
