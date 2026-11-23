"use client";

import { useEffect, useRef, useState } from "react";
import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronDown, Search, X } from "lucide-react";
import { getCatalogOptionsPage } from "@/features/admin/harvesting/harvesting";
import { CATALOG_STALE_TIME, useCatalogEntry } from "@/features/admin/harvesting/queries";
import { queryKeys } from "@/shared/query/queryKeys";

const SEARCH_DEBOUNCE_MS = 300;
/**
 * Selector único con búsqueda sobre un catálogo paginado (`results` / `next`).
 * `value` es el ID seleccionado (número o "") y `onChange` recibe el ID numérico o "".
 */
export default function CatalogSelect({ id, label, endpoint, labelField = "name", valueField = "id", value, onChange, disabled = false, placeholder = "Todos" }) {
  const queryClient = useQueryClient();
  const containerRef = useRef(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const listboxId = `${id}-listbox`;
  const hasValue = value !== "" && value != null;

  // Caché por catálogo y texto buscado: reabrir el selector o repetir una búsqueda no vuelve a pedirla.
  const options = useInfiniteQuery({
    queryKey: queryKeys.catalog.options(endpoint, search),
    queryFn: ({ pageParam, signal }) => getCatalogOptionsPage(endpoint, { search, pageUrl: pageParam }, signal),
    initialPageParam: null,
    getNextPageParam: (lastPage) => lastPage.next || undefined,
    enabled: open && Boolean(endpoint),
    staleTime: CATALOG_STALE_TIME,
  });
  const entry = useCatalogEntry(endpoint, value);

  useEffect(() => {
    const timer = setTimeout(() => setSearch(query.trim()), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [query]);

  useEffect(() => {
    if (!open) return undefined;
    const close = (event) => { if (!containerRef.current?.contains(event.target)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  const seen = new Set();
  const items = (options.data?.pages || []).flatMap((page) => page.results).filter((item) => {
    if (seen.has(item[valueField])) return false;
    seen.add(item[valueField]);
    return true;
  });
  const selectedName = !hasValue ? "" : entry.data?.[labelField] || (entry.isError ? `#${value}${entry.error?.status === 404 ? " (no disponible)" : ""}` : "");
  const listing = {
    items,
    next: options.hasNextPage,
    error: options.isError && !options.isFetching ? options.error?.message || "No se pudieron cargar las opciones." : "",
  };

  function loadMore() {
    if (!options.isFetchingNextPage && options.hasNextPage) options.fetchNextPage();
  }
  const loadingMore = options.isFetchingNextPage;

  function select(item) {
    const itemId = Number(item[valueField]);
    // La opción ya trae su nombre: se siembra la caché para no pedir la entrada.
    queryClient.setQueryData(queryKeys.catalog.entry(endpoint, itemId), item);
    onChange(itemId);
    setOpen(false);
    setQuery("");
  }

  const searching = open && (query.trim() !== search || options.isPending);

  return (
    <div ref={containerRef} className="relative min-w-0" onKeyDown={(event) => { if (event.key === "Escape") setOpen(false); }}>
      <div className={`flex min-h-[68px] min-w-0 flex-col gap-[5px] rounded-lg border bg-white p-3 ${open ? "border-primary" : "border-[#DCE0E5]"} ${disabled ? "opacity-60" : ""}`}>
        <span id={`${id}-label`} className="text-xs leading-[18px] tracking-[0.1px] text-[#68707C]">{label}</span>
        <div className="flex items-center gap-2">
          <button
            type="button"
            id={id}
            disabled={disabled}
            aria-haspopup="listbox"
            aria-expanded={open}
            aria-controls={listboxId}
            aria-labelledby={`${id}-label ${id}`}
            onClick={() => setOpen((current) => !current)}
            className="flex min-w-0 flex-1 items-center justify-between gap-2 text-left text-sm leading-[22px] focus-visible:outline-2 focus-visible:outline-offset-3 focus-visible:outline-primary disabled:cursor-not-allowed"
          >
            <span className={`truncate ${hasValue ? "text-[#171A1F]" : "text-[#68707C]"}`}>{hasValue ? selectedName || "Cargando…" : placeholder}</span>
            <ChevronDown aria-hidden="true" className="size-4 shrink-0 text-[#68707C]" />
          </button>
          {hasValue && !disabled && (
            <button type="button" onClick={() => onChange("")} aria-label={`Quitar filtro de ${label.toLowerCase()}`} className="rounded p-0.5 text-[#68707C] hover:text-[#A90D27] focus-visible:outline-2 focus-visible:outline-primary">
              <X aria-hidden="true" className="size-4" />
            </button>
          )}
        </div>
      </div>
      {open && (
        <div className="absolute inset-x-0 top-full z-20 mt-1 flex max-h-80 flex-col rounded-lg border border-[#DCE0E5] bg-white shadow-lg">
          <label className="flex items-center gap-2 border-b border-[#DCE0E5] px-3 py-2">
            <Search aria-hidden="true" className="size-4 shrink-0 text-[#68707C]" />
            <input
              autoFocus
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Buscar…"
              aria-label={`Buscar ${label.toLowerCase()}`}
              aria-controls={listboxId}
              className="w-full min-w-0 border-0 bg-transparent p-0 text-sm outline-none"
            />
          </label>
          <ul id={listboxId} role="listbox" aria-labelledby={`${id}-label`} className="min-h-0 flex-1 overflow-y-auto py-1">
            {searching && <li className="px-3 py-2 text-[#68707C]" role="presentation">Buscando…</li>}
            {!searching && listing.error && <li className="px-3 py-2 text-[#820A1F]" role="presentation">{listing.error}</li>}
            {!searching && !listing.error && !listing.items.length && <li className="px-3 py-2 text-[#68707C]" role="presentation">Sin resultados.</li>}
            {!searching && listing.items.map((item) => {
              const selected = Number(item[valueField]) === Number(value);
              return (
                <li key={item[valueField]} role="option" aria-selected={selected}>
                  <button type="button" onClick={() => select(item)} className={`flex w-full items-center justify-between gap-2 px-3 py-2 text-left hover:bg-[#F7F8FA] focus-visible:bg-[#F7F8FA] focus-visible:outline-none ${selected ? "font-semibold text-[#A90D27]" : ""}`}>
                    <span className="truncate">{item[labelField]}</span>
                    {selected && <Check aria-hidden="true" className="size-4 shrink-0" />}
                  </button>
                </li>
              );
            })}
            {!searching && listing.next && (
              <li role="presentation" className="px-3 py-1">
                <button type="button" onClick={loadMore} disabled={loadingMore} className="w-full rounded py-1.5 text-sm font-semibold text-[#A90D27] hover:bg-[#F7F8FA] disabled:opacity-60">{loadingMore ? "Cargando…" : "Cargar más"}</button>
              </li>
            )}
          </ul>
        </div>
      )}
    </div>
  );
}
