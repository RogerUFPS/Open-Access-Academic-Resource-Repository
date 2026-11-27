"use client";

// Estado de verificación de un enlace tal como lo devuelve el Backend
// (verification_status): null = sin URL registrada.
const STATES = {
  available: { label: "Disponible", className: "bg-emerald-50 text-emerald-800 border-emerald-200" },
  unavailable: { label: "No disponible", className: "bg-rose-50 text-rose-700 border-rose-200" },
  unverified: { label: "Sin verificar", className: "bg-amber-50 text-amber-800 border-amber-200" },
  missing: { label: "Sin URL", className: "bg-gray-100 text-gray-600 border-gray-200" },
};

export function LinkStatusBadge({ status, label }) {
  const state = STATES[status ?? "missing"] || STATES.unverified;
  return (
    <span
      className={`inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full border ${state.className}`}
    >
      {label && <span className="font-medium opacity-80">{label}:</span>}
      {state.label}
    </span>
  );
}

/** Una asociación revista–plataforma cuenta para publicar (dato del Backend). */
export function ServingBadge({ serving }) {
  return serving ? (
    <span className="inline-flex text-[10px] font-bold px-2 py-0.5 rounded-full border bg-emerald-600 text-white border-emerald-600">
      Cuenta para publicar
    </span>
  ) : (
    <span className="inline-flex text-[10px] font-bold px-2 py-0.5 rounded-full border bg-white text-gray-500 border-gray-300">
      No cuenta para publicar
    </span>
  );
}
