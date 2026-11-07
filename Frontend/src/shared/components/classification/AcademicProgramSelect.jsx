"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Check, Lock, Search, X } from "lucide-react";
import { capitalizeWords } from "@/lib/utils";
import { academicProgramService } from "@/shared/services/catalogService";
import { FieldError, fieldAnchorId, fieldErrorId } from "@/shared/components/forms/FormParts";
import OriginBadge from "./OriginBadge";

const SEARCH_DEBOUNCE_MS = 350;

/**
 * Multi-select con búsqueda, chips y contador para programas académicos.
 *
 * - `value`: IDs seleccionados manualmente (editables).
 * - `lockedPrograms`: programas derivados que no se pueden quitar
 *   ([{ id, name, is_manual, is_derived }]).
 * - `knownNames`: { [id]: name } para pintar chips sin pedir de nuevo.
 */
export default function AcademicProgramSelect({
  field = "academic_programs",
  label = "Programas académicos",
  required = false,
  optional = false,
  hint,
  value = [],
  onChange,
  lockedPrograms = [],
  knownNames = {},
  error,
  emptyMessage,
}) {
  const containerRef = useRef(null);
  const inputId = `${field}-search`;
  const listboxId = `${field}-listbox`;
  const hintId = `${field}-hint`;

  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState({ query: null, items: [], error: null });
  const [resolvedNames, setResolvedNames] = useState({});

  const lockedIds = useMemo(() => new Set(lockedPrograms.map((program) => Number(program.id))), [lockedPrograms]);
  const names = useMemo(() => {
    const map = { ...resolvedNames, ...knownNames };
    lockedPrograms.forEach((program) => {
      if (program?.name) map[program.id] = program.name;
    });
    search.items.forEach((program) => {
      map[program.id] = program.name;
    });
    return map;
  }, [resolvedNames, knownNames, lockedPrograms, search.items]);

  // Resolver nombres de IDs seleccionados que aún no conocemos.
  const missingKey = value.filter((id) => !names[id]).join(",");
  useEffect(() => {
    if (!missingKey) return undefined;
    let cancelled = false;
    Promise.all(
      missingKey.split(",").map((id) =>
        academicProgramService.getById(id).then(
          (program) => [id, program?.name || `Programa #${id}`],
          () => [id, `Programa #${id}`]
        )
      )
    ).then((entries) => {
      if (!cancelled) setResolvedNames((current) => ({ ...current, ...Object.fromEntries(entries) }));
    });
    return () => {
      cancelled = true;
    };
  }, [missingKey]);

  // Búsqueda con debounce contra el backend.
  useEffect(() => {
    if (!open) return undefined;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      academicProgramService
        .search(query, { signal: controller.signal })
        .then((items) => setSearch({ query, items, error: null }))
        .catch((err) => {
          if (err?.name === "AbortError") return;
          setSearch({ query, items: [], error: err?.message || "No se pudieron cargar los programas." });
        });
    }, SEARCH_DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [open, query]);

  // Cerrar al hacer clic fuera.
  useEffect(() => {
    if (!open) return undefined;
    const handlePointer = (event) => {
      if (!containerRef.current?.contains(event.target)) setOpen(false);
    };
    document.addEventListener("mousedown", handlePointer);
    return () => document.removeEventListener("mousedown", handlePointer);
  }, [open]);

  const searching = open && search.query !== query;
  const toggle = (id) => {
    const numericId = Number(id);
    if (lockedIds.has(numericId)) return;
    onChange(value.includes(numericId) ? value.filter((item) => item !== numericId) : [...value, numericId]);
  };

  const total = value.length + lockedPrograms.filter((program) => !value.includes(Number(program.id))).length;
  const describedBy = [hint ? hintId : null, error ? fieldErrorId(field) : null].filter(Boolean).join(" ") || undefined;

  return (
    <div
      id={fieldAnchorId(field)}
      ref={containerRef}
      className={`bg-white border rounded-xl p-4 shadow-2xs space-y-2.5 ${error ? "border-rose-300 ring-1 ring-rose-200" : "border-gray-200"}`}
      onKeyDown={(event) => {
        if (event.key === "Escape") setOpen(false);
      }}
    >
      <div className="flex items-center justify-between pb-1 border-b border-gray-100 gap-2">
        <label htmlFor={inputId} className="text-[11px] font-bold text-gray-700 uppercase tracking-wider">
          {label}
          {required && <span className="text-[#C8102E]"> *</span>}
          {optional && <span className="normal-case font-medium text-gray-400"> (opcional)</span>}
        </label>
        <span className="text-[10px] bg-slate-100 text-slate-600 font-semibold px-2 py-0.5 rounded-full">
          {total} seleccionados
        </span>
      </div>

      {hint && (
        <p id={hintId} className="text-[11px] text-gray-500">
          {hint}
        </p>
      )}

      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-gray-400" aria-hidden="true" />
        <input
          id={inputId}
          type="text"
          role="combobox"
          aria-expanded={open}
          aria-controls={listboxId}
          aria-autocomplete="list"
          aria-describedby={describedBy}
          aria-invalid={error ? "true" : undefined}
          autoComplete="off"
          value={query}
          onFocus={() => setOpen(true)}
          onChange={(event) => {
            setQuery(event.target.value);
            setOpen(true);
          }}
          placeholder="Buscar programa..."
          className="w-full h-9 rounded-lg border border-slate-300 bg-slate-50 pl-8 pr-3 text-xs font-medium text-slate-900 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"
        />
        {open && (
          <ul
            id={listboxId}
            role="listbox"
            aria-multiselectable="true"
            aria-busy={searching ? "true" : undefined}
            className="absolute z-30 mt-1 max-h-64 w-full overflow-y-auto rounded-lg border border-gray-200 bg-white p-1 shadow-lg"
          >
            {searching ? (
              <li className="px-3 py-2 text-xs text-gray-500">Buscando programas...</li>
            ) : search.error ? (
              <li className="px-3 py-2 text-xs text-rose-600">{search.error}</li>
            ) : search.items.length === 0 ? (
              <li className="px-3 py-2 text-xs text-gray-500">Sin resultados.</li>
            ) : (
              search.items.map((program) => {
                const locked = lockedIds.has(Number(program.id));
                const selected = locked || value.includes(Number(program.id));
                return (
                  <li
                    key={program.id}
                    role="option"
                    aria-selected={selected}
                    aria-disabled={locked ? "true" : undefined}
                    onMouseDown={(event) => event.preventDefault()}
                    onClick={() => toggle(program.id)}
                    className={`flex items-center justify-between gap-2 rounded-md px-3 py-2 text-xs ${
                      locked ? "cursor-not-allowed text-gray-400" : "cursor-pointer text-gray-800 hover:bg-gray-50"
                    } ${selected && !locked ? "font-semibold bg-rose-50/70" : ""}`}
                  >
                    <span className="truncate">{capitalizeWords(program.name)}</span>
                    {locked ? (
                      <Lock className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                    ) : (
                      <span
                        aria-hidden="true"
                        className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border ${
                          selected ? "border-[#C8102E] bg-[#C8102E] text-white" : "border-gray-300"
                        }`}
                      >
                        {selected && <Check className="h-3 w-3" />}
                      </span>
                    )}
                  </li>
                );
              })
            )}
          </ul>
        )}
      </div>

      {total === 0 ? (
        emptyMessage && <p className="text-xs italic text-gray-400">{emptyMessage}</p>
      ) : (
        <ul className="flex flex-wrap gap-2" aria-label="Programas seleccionados">
          {value.map((id) => (
            <li
              key={`manual-${id}`}
              className="inline-flex items-center gap-1 rounded-lg border border-[#C8102E]/40 bg-rose-50/70 py-1 pl-2.5 pr-1 text-xs font-semibold text-gray-900"
            >
              <span>{names[id] ? capitalizeWords(names[id]) : "Cargando..."}</span>
              <button
                type="button"
                onClick={() => toggle(id)}
                aria-label={`Quitar ${names[id] || `programa ${id}`}`}
                className="rounded p-0.5 text-gray-500 hover:bg-rose-100 hover:text-[#C8102E] cursor-pointer"
              >
                <X className="h-3.5 w-3.5" aria-hidden="true" />
              </button>
            </li>
          ))}
          {lockedPrograms
            .filter((program) => !value.includes(Number(program.id)))
            .map((program) => (
              <li key={`locked-${program.id}`}>
                <span
                  aria-disabled="true"
                  title="Derivado de las revistas asociadas; no se puede quitar"
                  className="inline-flex items-center gap-1.5 rounded-lg border border-gray-200 bg-gray-50 px-2.5 py-1 text-xs font-semibold text-gray-800"
                >
                  <Lock className="h-3 w-3 text-gray-500" aria-hidden="true" />
                  <span>{capitalizeWords(program.name)}</span>
                  <OriginBadge isManual={Boolean(program.is_manual)} isDerived={Boolean(program.is_derived)} />
                </span>
              </li>
            ))}
        </ul>
      )}

      <FieldError field={field} message={error} />
    </div>
  );
}
