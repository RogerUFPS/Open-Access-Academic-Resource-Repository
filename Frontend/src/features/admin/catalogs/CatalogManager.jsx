"use client";

import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, Pencil, Plus, RotateCcw, Search } from "lucide-react";
import { catalogAdminService, CATALOG_RESOURCES } from "./catalogAdminService";
import { CatalogActionDialog, CatalogEntryDialog } from "./CatalogEntryDialog";
import { useToast } from "@/components/ui/use-toast";
import { extractApiErrorText } from "@/shared/services/apiClient";
import { isMissingPage, readPage } from "@/shared/utils/pagination";

const PAGE_SIZE_OPTIONS = [10, 20, 50];
const PAGE_SIZE_DEFAULT = 20;
const focus = "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#7f1218]";

function requestError(error) {
  if (error?.name === "TypeError") {
    return "No se pudo conectar con el servidor. Revisa tu conexión e inténtalo nuevamente.";
  }
  return extractApiErrorText(error?.data) || error?.message || "No se pudo cargar el catálogo.";
}

function displayDate(value) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : new Intl.DateTimeFormat("es-CO").format(date);
}

export default function CatalogManager({ resource, permissions, active }) {
  const config = CATALOG_RESOURCES[resource];
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [search, setSearch] = useState("");
  const [serverSearch, setServerSearch] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(PAGE_SIZE_DEFAULT);
  const [showArchived, setShowArchived] = useState(false);
  const [dialog, setDialog] = useState(null);

  useEffect(() => {
    const timer = setTimeout(() => {
      setServerSearch(search.trim());
      setPage(1);
    }, 250);
    return () => clearTimeout(timer);
  }, [search]);

  const query = useQuery({
    queryKey: ["admin-catalog", resource, showArchived ? "archived" : "active", serverSearch, page, pageSize],
    queryFn: async () => {
      let requestedPage = page;
      let response;
      while (requestedPage > 0) {
        try {
          response = await catalogAdminService.list(resource, {
            archived: showArchived,
            search: serverSearch,
            ordering: "name",
            page: requestedPage,
            pageSize,
          });
          break;
        } catch (error) {
          if (!isMissingPage(error, requestedPage)) throw error;
          requestedPage -= 1;
        }
      }
      if (!response) throw new Error("No se pudo cargar la página solicitada del catálogo.");
      return {
        ...readPage(response, pageSize),
        next: response.next,
        previous: response.previous,
      };
    },
    enabled: active,
    placeholderData: (previousData) => previousData,
  });

  async function onComplete(message) {
    setPage(1);
    await queryClient.invalidateQueries({
      queryKey: ["admin-catalog", resource],
      refetchType: "all",
    });
    setDialog(null);
    toast({ title: message });
  }

  const rows = query.data?.results ?? [];
  const currentPage = query.data?.page ?? page;
  const totalPages = query.data?.totalPages ?? 1;
  const totalItems = query.data?.totalItems ?? 0;
  const actionsAvailable = permissions.update || permissions.delete || permissions.restore;

  return (
    <section
      id={`catalog-panel-${resource}`}
      role="tabpanel"
      aria-labelledby={`catalog-tab-${resource}`}
      hidden={!active}
      className="mt-6"
    >
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-slate-900">{config.label}</h2>
          <p className="mt-1 text-sm text-slate-600">{config.description}</p>
        </div>
        {permissions.create && (
          <button
            type="button"
            onClick={() => setDialog({ mode: "create" })}
            className={`inline-flex items-center gap-2 rounded-md bg-[#7f1218] px-4 py-2 text-sm font-semibold text-white hover:bg-[#6a0f14] ${focus}`}
          >
            <Plus className="h-4 w-4" aria-hidden="true" />
            Nuevo
          </button>
        )}
      </header>

      <section aria-label={`Filtros de ${config.label}`} className="mt-5 flex flex-wrap items-center gap-3">
        <label className="relative block w-full max-w-sm">
          <span className="sr-only">Buscar {config.label.toLocaleLowerCase("es")}</span>
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" aria-hidden="true" />
          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder={`Buscar ${config.label.toLocaleLowerCase("es")}…`}
            className={`w-full rounded-md border border-slate-300 bg-white py-2 pl-9 pr-3 text-sm ${focus}`}
          />
        </label>
        <button
          type="button"
          aria-pressed={showArchived}
          onClick={() => {
            setShowArchived((current) => !current);
            setPage(1);
          }}
          className={`rounded-full border px-4 py-1.5 text-sm font-medium ${focus} ${
            showArchived
              ? "border-slate-700 bg-slate-800 text-white"
              : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
          }`}
        >
          {showArchived ? "Ver vigentes" : "Ver archivados"}
        </button>
        <label className="flex items-center gap-2 text-sm text-slate-600">
          Mostrar
          <select
            value={pageSize}
            onChange={(event) => {
              setPageSize(Number(event.target.value));
              setPage(1);
            }}
            className={`rounded-md border border-slate-300 bg-white px-2 py-1.5 ${focus}`}
            aria-label="Registros por página"
          >
            {PAGE_SIZE_OPTIONS.map((size) => <option key={size} value={size}>{size}</option>)}
          </select>
          por página
        </label>
      </section>

      {query.isError && (
        <div role="alert" className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-md border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">
          <p>{requestError(query.error)}</p>
          <button type="button" onClick={() => query.refetch()} className={`rounded-md border border-rose-300 bg-white px-3 py-1.5 font-medium hover:bg-rose-100 ${focus}`}>
            Reintentar
          </button>
        </div>
      )}

      <div className="mt-4 overflow-x-auto rounded-lg border border-slate-200 bg-white">
        <table className="w-full min-w-[640px] text-left text-sm">
          <caption className="sr-only">{showArchived ? `${config.label} archivados` : config.label}</caption>
          <thead className="bg-slate-100 text-xs font-semibold text-slate-700">
            <tr>
              {config.fields.map((field) => (
                <th scope="col" key={field.name} className="px-5 py-3.5">{field.label}</th>
              ))}
              {showArchived && <th scope="col" className="px-5 py-3.5">Motivo de eliminación</th>}
              {showArchived && <th scope="col" className="px-5 py-3.5">Archivado</th>}
              {actionsAvailable && <th scope="col" className="px-5 py-3.5 text-right">Acciones</th>}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {query.isPending && (
              <tr>
                <td colSpan={config.fields.length + Number(showArchived) * 2 + Number(actionsAvailable)} className="px-5 py-10 text-center text-slate-600" role="status">
                  Cargando {config.label.toLocaleLowerCase("es")}…
                </td>
              </tr>
            )}
            {!query.isError && rows.map((row) => (
              <tr key={row.id} className="hover:bg-slate-50">
                {config.fields.map((field) => (
                  <td key={field.name} className="px-5 py-4 align-top text-slate-800">
                    {field.name === "emoji_flag"
                      ? <span className="text-xl" aria-label={row.emoji_flag ? `Bandera ${row.emoji_flag}` : "Sin bandera"}>{row.emoji_flag || "—"}</span>
                      : row[field.name] || "—"}
                  </td>
                ))}
                {showArchived && (
                  <>
                    <td className="max-w-sm px-5 py-4 text-slate-600">{row.delete_explanation || "Sin motivo registrado"}</td>
                    <td className="whitespace-nowrap px-5 py-4 text-slate-600">{displayDate(row.deleted_at) || "—"}</td>
                  </>
                )}
                {actionsAvailable && (
                  <td className="whitespace-nowrap px-5 py-4 text-right">
                    {showArchived ? (
                      permissions.restore && (
                        <button
                          type="button"
                          onClick={() => setDialog({ mode: "restore", item: row })}
                          className={`inline-flex items-center gap-1 rounded px-2 py-1 text-sm font-medium text-[#7f1218] hover:bg-rose-50 ${focus}`}
                        >
                          <RotateCcw className="h-4 w-4" aria-hidden="true" />
                          Restaurar
                        </button>
                      )
                    ) : (
                      <span className="inline-flex gap-2">
                        {permissions.update && (
                          <button
                            type="button"
                            onClick={() => setDialog({ mode: "edit", item: row })}
                            aria-label={`Editar ${row.name}`}
                            className={`rounded p-2 text-slate-600 hover:bg-slate-100 hover:text-[#7f1218] ${focus}`}
                          >
                            <Pencil className="h-4 w-4" aria-hidden="true" />
                          </button>
                        )}
                        {permissions.delete && (
                          <button
                            type="button"
                            onClick={() => setDialog({ mode: "archive", item: row })}
                            aria-label={`Archivar ${row.name}`}
                            className={`rounded p-2 text-rose-700 hover:bg-rose-50 ${focus}`}
                          >
                            <Archive className="h-4 w-4" aria-hidden="true" />
                          </button>
                        )}
                      </span>
                    )}
                  </td>
                )}
              </tr>
            ))}
            {!query.isPending && !query.isError && rows.length === 0 && (
              <tr>
                <td colSpan={config.fields.length + Number(showArchived) * 2 + Number(actionsAvailable)} className="px-5 py-10 text-center text-slate-600">
                  {serverSearch
                    ? `No se encontraron ${config.label.toLocaleLowerCase("es")} para esa búsqueda.`
                    : showArchived
                    ? `No hay ${config.label.toLocaleLowerCase("es")} archivados.`
                    : `Aún no hay ${config.label.toLocaleLowerCase("es")} registrados.`}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <footer className="mt-4 flex flex-wrap items-center justify-between gap-3 text-sm text-slate-600">
        <p>{totalItems} {totalItems === 1 ? "registro" : "registros"} · Página {currentPage} de {totalPages}</p>
        <div className="flex gap-2">
          <button
            type="button"
            disabled={!query.data?.previous || query.isFetching}
            onClick={() => setPage(Math.max(1, currentPage - 1))}
            className={`rounded-md border border-slate-300 bg-white px-3 py-1.5 font-medium hover:bg-slate-50 disabled:opacity-50 ${focus}`}
          >
            Anterior
          </button>
          <button
            type="button"
            disabled={!query.data?.next || query.isFetching}
            onClick={() => setPage(currentPage + 1)}
            className={`rounded-md border border-slate-300 bg-white px-3 py-1.5 font-medium hover:bg-slate-50 disabled:opacity-50 ${focus}`}
          >
            Siguiente
          </button>
        </div>
      </footer>

      {dialog?.mode === "create" || dialog?.mode === "edit" ? (
        <CatalogEntryDialog
          resource={resource}
          item={dialog.item}
          onClose={() => setDialog(null)}
          onComplete={onComplete}
        />
      ) : dialog && (
        <CatalogActionDialog
          resource={resource}
          item={dialog.item}
          mode={dialog.mode}
          onClose={() => setDialog(null)}
          onComplete={onComplete}
        />
      )}
    </section>
  );
}
