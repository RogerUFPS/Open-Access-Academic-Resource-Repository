"use client";

import { useState } from "react";
import { Check, PencilLine, Plus } from "lucide-react";
import { capitalizeWords } from "@/lib/utils";
import { platformService } from "../services/platformService";
import { ValidSintaxisEditor } from "./ValidSintaxisEditor";

function SyntaxSummary({ syntax }) {
  const booleans = Array.isArray(syntax.booleans) ? syntax.booleans : [];
  const fields = syntax.fields && typeof syntax.fields === "object" ? Object.entries(syntax.fields) : [];
  return (
    <div className="mt-1.5 flex flex-wrap gap-1 text-[10px]">
      {booleans.length > 0 ? (
        booleans.map((operator) => (
          <span key={operator} className="rounded bg-slate-200 px-1.5 py-0.5 font-semibold text-slate-700">{operator}</span>
        ))
      ) : (
        <span className="text-slate-400">Sin operadores</span>
      )}
      {syntax.parenthesis && <span className="rounded bg-blue-100 px-1.5 py-0.5 font-semibold text-blue-800">( )</span>}
      {fields.map(([key, prefix]) => (
        <span key={key} className="rounded border border-slate-200 bg-white px-1.5 py-0.5 text-slate-600">
          {key}{prefix ? `: ${prefix}` : ""}
        </span>
      ))}
    </div>
  );
}

/**
 * Sintaxis de búsqueda directamente en la página (sin desplegable ni modal):
 * - Se elige tocando una tarjeta.
 * - "Crear nueva sintaxis" abre el editor en línea y la selecciona al guardar.
 * - "Editar sintaxis existente" modifica la sintaxis compartida: el cambio se
 *   refleja en todas las plataformas que la usan.
 */
export function ValidSintaxisPanel({
  options,
  value,
  loadError,
  canCreate,
  canUpdate,
  canDelete,
  onChange,
  onOptionsChange,
  describedBy,
}) {
  const [editor, setEditor] = useState(null); // null | { mode, item, usageCount }
  const [notice, setNotice] = useState("");
  const selected = options.find((syntax) => syntax.id === Number(value)) || null;

  const openCreate = () => {
    setNotice("");
    setEditor({ mode: "create", item: null, usageCount: null });
  };

  const openEdit = () => {
    if (!selected) return;
    setNotice("");
    setEditor({ mode: "edit", item: selected, usageCount: null });
    platformService
      .getPlatforms({ valid_sintaxis: selected.id, page_size: 1 })
      .then((page) => {
        const total = page?.total_items ?? (Array.isArray(page) ? page.length : null);
        setEditor((current) => (current?.mode === "edit" && current.item?.id === selected.id ? { ...current, usageCount: total } : current));
      })
      .catch(() => {});
  };

  const upsert = (saved) =>
    onOptionsChange((current) =>
      current.some((syntax) => syntax.id === saved.id)
        ? current.map((syntax) => (syntax.id === saved.id ? saved : syntax))
        : [...current, saved]
    );

  const handleSaved = (saved, mode) => {
    upsert(saved);
    onChange(saved.id);
    if (mode === "edit") {
      const count = editor?.usageCount;
      setNotice(
        `Sintaxis “${saved.name}” actualizada${count != null ? ` en ${count} ${count === 1 ? "plataforma" : "plataformas"}` : " en todas las plataformas que la usan"}.`
      );
    } else {
      setNotice(`Sintaxis “${saved.name}” creada y seleccionada. Se asignará al guardar la plataforma.`);
    }
    setEditor(null);
  };

  const handleUseExisting = async (id) => {
    try {
      const existing = await platformService.getValidSintaxisById(id);
      upsert(existing);
      onChange(existing.id);
      setNotice(`Se seleccionó la sintaxis existente “${existing.name}”.`);
      setEditor(null);
    } catch (err) {
      setNotice(err.message || "No se pudo cargar la sintaxis existente.");
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span id="valid_sintaxis-label" className="text-[11px] font-medium text-gray-500">
          Selecciona la sintaxis de búsqueda que admite la plataforma
        </span>
        {!editor && (
          <div className="flex flex-wrap gap-2">
            {canCreate && (
              <button
                type="button"
                onClick={openCreate}
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold hover:bg-slate-50"
              >
                <Plus className="h-3.5 w-3.5" aria-hidden="true" />
                Crear nueva sintaxis
              </button>
            )}
            {canUpdate && (
              <button
                type="button"
                onClick={openEdit}
                disabled={!selected}
                title={selected ? "Los cambios se aplican a todas las plataformas que usan esta sintaxis" : "Selecciona una sintaxis para editarla"}
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <PencilLine className="h-3.5 w-3.5" aria-hidden="true" />
                Editar sintaxis existente
              </button>
            )}
          </div>
        )}
      </div>

      {notice && <p role="status" className="rounded-lg bg-emerald-50 p-2.5 text-xs text-emerald-800">{notice}</p>}

      {editor ? (
        <ValidSintaxisEditor
          key={`${editor.mode}-${editor.item?.id ?? "new"}`}
          mode={editor.mode}
          item={editor.item}
          usageCount={editor.usageCount}
          canDelete={canDelete}
          onCancel={() => setEditor(null)}
          onSaved={handleSaved}
          onUseExisting={handleUseExisting}
          onDeleted={(id) => {
            onOptionsChange((current) => current.filter((syntax) => syntax.id !== id));
            if (Number(value) === id) onChange(null);
            setNotice("Sintaxis eliminada.");
            setEditor(null);
          }}
        />
      ) : loadError ? (
        <p className="text-xs text-rose-600">{loadError}</p>
      ) : options.length === 0 ? (
        <p className="text-xs text-slate-500">No hay sintaxis configuradas.{canCreate ? " Crea una nueva." : ""}</p>
      ) : (
        <div
          role="radiogroup"
          aria-labelledby="valid_sintaxis-label"
          aria-describedby={describedBy}
          className="grid max-h-80 grid-cols-1 gap-2 overflow-y-auto pr-1 sm:grid-cols-2"
        >
          {options.map((syntax) => {
            const isSelected = syntax.id === Number(value);
            return (
              <button
                key={syntax.id}
                type="button"
                role="radio"
                aria-checked={isSelected}
                onClick={() => onChange(isSelected ? null : syntax.id)}
                className={`rounded-lg border p-3 text-left transition-all ${
                  isSelected
                    ? "border-[#C8102E] bg-rose-50/70 shadow-2xs"
                    : "border-gray-200 bg-white hover:border-gray-300 hover:bg-gray-50"
                }`}
              >
                <span className="flex items-center justify-between gap-2">
                  <span className="truncate text-xs font-semibold text-gray-900">{capitalizeWords(syntax.name)}</span>
                  <span
                    aria-hidden="true"
                    className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full border ${
                      isSelected ? "border-[#C8102E] bg-[#C8102E] text-white" : "border-gray-300 bg-white"
                    }`}
                  >
                    {isSelected && <Check className="h-3 w-3" />}
                  </span>
                </span>
                <SyntaxSummary syntax={syntax} />
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
