"use client";

import { capitalizeWords } from "@/lib/utils";

export function SyntaxSelector({
  options,
  value,
  loading,
  error,
  canCreate,
  canUpdate,
  onChange,
  onCreate,
  onEdit,
}) {
  const selected = value === null || value === undefined ? "" : String(value);

  return (
    <div className="space-y-2">
      <select
        id="valid_sintaxis"
        value={selected}
        onChange={(event) => onChange(event.target.value ? Number(event.target.value) : null)}
        disabled={loading || Boolean(error)}
        className="h-8 w-full cursor-pointer bg-transparent text-xs font-semibold text-gray-900 outline-none"
      >
        <option value="">Seleccione una sintaxis</option>
        {options.map((syntax) => (
          <option key={syntax.id} value={syntax.id}>
            {capitalizeWords(syntax.name)}
          </option>
        ))}
      </select>
      {loading && <p className="text-xs text-slate-500">Cargando sintaxis…</p>}
      {!loading && error && <p className="text-xs text-rose-600">No se pudo cargar el catálogo de sintaxis.</p>}
      {!loading && !error && options.length === 0 && (
        <p className="text-xs text-slate-500">No hay sintaxis configuradas.</p>
      )}
      <div className="flex flex-wrap gap-2">
        {canCreate && (
          <button type="button" onClick={onCreate} className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-semibold hover:bg-slate-50">
            Crear nueva sintaxis
          </button>
        )}
        {canUpdate && (
          <button type="button" onClick={onEdit} disabled={!value} className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-semibold disabled:cursor-not-allowed disabled:opacity-50 hover:bg-slate-50">
            Editar la seleccionada
          </button>
        )}
      </div>
    </div>
  );
}
