"use client";

// Piezas compartidas por las pestañas de Bitácora (reciente, archivada y anomalías).
import { useEffect, useRef } from "react";

/* ───────────── Fechas ───────────── */
export const MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
export const pad = (n) => String(n).padStart(2, "0");

export function fmtDate(iso, withSeconds = false) {
  const d = new Date(iso);
  if (isNaN(d)) return iso ?? "";
  const base = `${pad(d.getDate())} ${MESES[d.getMonth()]} ${d.getFullYear()} · ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  return withSeconds ? `${base}:${pad(d.getSeconds())}` : base;
}


/* ───────────── Estilos ───────────── */
export const focus =
  "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#7f1218]";
export const control = `w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm ${focus}`;
export const primary = `rounded-md bg-[#7f1218] px-4 py-2 text-sm font-semibold text-white hover:bg-[#6a0f14] disabled:opacity-50 ${focus}`;
export const secondary = `rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50 ${focus}`;


/* ───────────── Componentes ───────────── */
export function Modal({ title, subtitle, onClose, children }) {
  const ref = useRef(null);

  useEffect(() => {
    ref.current?.querySelector("button")?.focus();
  }, []);

  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-slate-900/40" onClick={onClose} aria-hidden />
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title"
        className="relative flex h-full w-full max-w-xl flex-col bg-white shadow-xl"
      >
        <div className="flex items-start justify-between gap-4 border-b border-slate-200 px-6 py-5">
          <div className="min-w-0">
            <h2 id="modal-title" className="text-lg font-bold">{title}</h2>
            {subtitle && <p className="mt-1 break-words text-sm text-slate-600">{subtitle}</p>}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Cerrar"
            className={`rounded-md px-2 py-1 text-xl leading-none text-slate-600 hover:bg-slate-100 ${focus}`}
          >
            ×
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function Field({ name, children }) {
  return (
    <div className="grid gap-1 sm:grid-cols-[150px_1fr] sm:gap-4">
      <dt className="text-sm text-slate-600">{name}</dt>
      <dd className="min-w-0 break-words text-sm">{children}</dd>
    </div>
  );
}

