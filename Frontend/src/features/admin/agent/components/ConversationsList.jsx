"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, BarChart3, Eye, Loader2, RefreshCw, ShieldCheck } from "lucide-react";
import AccountFeedback from "@/shared/components/AccountFeedback";
import AdminTable from "@/shared/components/AdminTable";
import Badge from "@/shared/components/Badge";
import Button from "@/shared/components/Button";
import Notice from "@/shared/components/Notice";
import { useAccountsApi } from "@/shared/components/AccountsProvider";
import { queryKeys } from "@/shared/query/queryKeys";
import { clampPage, isMissingPage, sanitizePageValue } from "@/shared/utils/pagination";
import {
  CONVERSATIONS_PAGE_SIZE,
  formatBogotaDateTime,
  getConversations,
  hasAgentPermission,
} from "@/features/admin/agent/agentAdminService";

const outlineButtonClass = "!border-[#7f1218] !text-[#7f1218]";

const UNCLEAR_FILTERS = [
  { value: "all", label: "Todas" },
  { value: "true", label: "Con respuesta poco clara" },
  { value: "false", label: "Sin respuestas poco claras" },
];

export default function ConversationsList() {
  const accountsApi = useAccountsApi();
  const [unclearFilter, setUnclearFilter] = useState("all");
  const [page, setPage] = useState(1);
  const [pageInput, setPageInput] = useState("1");

  const viewerQuery = useQuery({
    queryKey: queryKeys.accounts.viewer,
    queryFn: ({ signal }) => accountsApi.me(signal),
  });

  const viewer = viewerQuery.data ?? null;
  const canView = hasAgentPermission(viewer, "conversations", "view");
  const canViewAnalytics = hasAgentPermission(viewer, "analytics", "view");

  const queryParams = {
    page,
    pageSize: CONVERSATIONS_PAGE_SIZE,
    unclear: unclearFilter,
  };

  const conversationsQuery = useQuery({
    queryKey: queryKeys.agent.conversationList(queryParams),
    queryFn: ({ signal }) => getConversations(queryParams, signal),
    enabled: canView,
  });

  // Si la página ya no existe (404), volver a página 1.
  if (isMissingPage(conversationsQuery.error, page)) {
    setPage(1);
    setPageInput("1");
  }

  const pageData = conversationsQuery.data ?? {
    results: [],
    totalItems: 0,
    totalPages: 1,
    pageSize: CONVERSATIONS_PAGE_SIZE,
    page: 1,
  };

  function changeFilter(nextValue) {
    setUnclearFilter(nextValue);
    setPage(1);
    setPageInput("1");
  }

  function changePage(nextPage) {
    const safe = clampPage(nextPage, pageData.totalPages);
    setPage(safe);
    setPageInput(String(safe));
  }

  function submitPageJump(event) {
    event.preventDefault();
    const parsed = sanitizePageValue(pageInput, pageData.totalPages);
    if (!parsed.valid) {
      setPageInput(String(clampPage(page, pageData.totalPages)));
      return;
    }
    setPage(parsed.page);
    setPageInput(String(parsed.page));
  }

  const columns = [
    {
      key: "id",
      label: "CONVERSACIÓN",
      width: "26%",
      render: (row) => (
        <span className="block truncate font-mono text-xs font-medium text-[#1F242E]" title={String(row.id)}>
          {String(row.id)}
        </span>
      ),
    },
    {
      key: "turn_count",
      label: "TURNOS",
      width: "10%",
      render: (row) => <span className="font-semibold text-[#1F242E]">{row.turn_count ?? 0}</span>,
    },
    {
      key: "has_unclear",
      label: "CLASIFICACIÓN",
      width: "20%",
      render: (row) =>
        row.has_unclear ? (
          <Badge state="warning">Con respuesta poco clara</Badge>
        ) : (
          <Badge state="success">Clara</Badge>
        ),
    },
    {
      key: "created_at",
      label: "CREADA",
      width: "16%",
      muted: true,
      render: (row) => <span className="text-xs">{formatBogotaDateTime(row.created_at)}</span>,
    },
    {
      key: "updated_at",
      label: "ÚLTIMA ACTIVIDAD",
      width: "16%",
      muted: true,
      render: (row) => <span className="text-xs">{formatBogotaDateTime(row.updated_at)}</span>,
    },
    {
      key: "actions",
      label: "ACCIONES",
      width: "12%",
      render: (row) => (
        <Button
          size="small"
          variant="outline"
          className={outlineButtonClass}
          href={`/admin/chats/${encodeURIComponent(String(row.id))}`}
        >
          <Eye className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
          Detalle
        </Button>
      ),
    },
  ];

  return (
    <section className="space-y-4 text-[#1F242E]">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-[30px] leading-[41px] font-bold">Conversaciones del asistente</h1>
          <p className="mt-2 text-[15px] text-[#6B758A]">
            Auditoría técnica de chats anónimos y seguimiento de conversaciones con respuestas poco claras.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {canViewAnalytics && (
            <Button variant="outline" className={outlineButtonClass} href="/admin/modulo-ia?tab=analitica">
              <BarChart3 className="mr-1.5 h-4 w-4" aria-hidden="true" />
              Ver analítica
            </Button>
          )}
          {canView && (
            <Button
              variant="quiet"
              onClick={() => conversationsQuery.refetch()}
              disabled={conversationsQuery.isFetching}
            >
              <RefreshCw className={`mr-1.5 h-4 w-4 ${conversationsQuery.isFetching ? "animate-spin" : ""}`} aria-hidden="true" />
              Actualizar
            </Button>
          )}
        </div>
      </header>

      {viewerQuery.isPending ? (
        <div role="status" className="flex items-center gap-2 rounded-xl border border-[#DCE0E5] bg-white p-8 text-sm text-[#68707C]">
          <Loader2 className="h-4 w-4 animate-spin text-[#7f1218]" aria-hidden="true" />
          <span>Verificando permisos de conversaciones…</span>
        </div>
      ) : viewerQuery.isError ? (
        <AccountFeedback error={viewerQuery.error} retry={() => viewerQuery.refetch()} />
      ) : !canView ? (
        <Notice variant="error">
          <div className="flex items-start gap-2.5 text-sm">
            <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" aria-hidden="true" />
            <p>
              Tu cuenta no tiene permiso para consultar conversaciones del asistente
              (<code>agent.conversations.view</code>).
            </p>
          </div>
        </Notice>
      ) : (
        <>
          {/* Filtros y aclaración metodológica */}
          <div className="rounded-xl border border-[#DCE0E5] bg-white p-4 space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Filtrar conversaciones">
                {UNCLEAR_FILTERS.map((option) => {
                  const active = unclearFilter === option.value;
                  return (
                    <button
                      key={option.value}
                      type="button"
                      aria-pressed={active}
                      onClick={() => changeFilter(option.value)}
                      className={`rounded-lg border px-3.5 py-2 text-xs font-semibold transition ${
                        active
                          ? "border-[#7f1218] bg-[#7f1218] text-white"
                          : "border-[#CCD4E0] bg-white text-[#4B5563] hover:border-[#7f1218] hover:text-[#7f1218]"
                      }`}
                    >
                      {option.label}
                    </button>
                  );
                })}
              </div>
              <p className="text-xs font-medium text-[#6B758A]">
                Total en vista: <span className="font-bold text-[#1F242E]">{pageData.totalItems}</span>
              </p>
            </div>

            <div className="flex items-start gap-2 rounded-lg bg-[#F7F8FA] px-3 py-2.5 text-xs leading-5 text-[#4B5563]">
              <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-[#7f1218]" aria-hidden="true" />
              <p>
                Una conversación queda marcada como «poco clara» si algún turno tuvo una respuesta no <code>ok</code>,
                un error o filtros no aplicados (el indicador permanece aunque después haya respuestas correctas; es
                una clasificación conservadora, no una evaluación humana). Los chats son anónimos: no se guarda nombre,
                cuenta, dirección IP ni identidad de autor.
              </p>
            </div>
          </div>

          {conversationsQuery.isPending ? (
            <div role="status" className="flex items-center gap-2 rounded-xl border border-[#DCE0E5] bg-white p-8 text-sm text-[#68707C]">
              <Loader2 className="h-4 w-4 animate-spin text-[#7f1218]" aria-hidden="true" />
              <span>Cargando conversaciones…</span>
            </div>
          ) : conversationsQuery.isError ? (
            <AccountFeedback error={conversationsQuery.error} retry={() => conversationsQuery.refetch()} />
          ) : pageData.results.length === 0 ? (
            <div className="rounded-xl border border-[#DCE0E5] bg-white p-10 text-center text-sm text-[#68707C]">
              No hay conversaciones registradas para el filtro seleccionado.
            </div>
          ) : (
            <div className="overflow-hidden rounded-xl border border-[#DCE0E5] bg-white">
              <AdminTable
                caption="Listado de conversaciones anónimas del asistente"
                columns={columns}
                rows={pageData.results}
              />

              {/* Paginación */}
              <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[#EEF0F3] px-4 py-3 text-xs text-[#6B758A]">
                <span>
                  Página <strong className="text-[#1F242E]">{pageData.page}</strong> de{" "}
                  <strong className="text-[#1F242E]">{pageData.totalPages}</strong> ({pageData.totalItems} chats)
                </span>
                <div className="flex flex-wrap items-center gap-2">
                  <Button
                    size="small"
                    variant="quiet"
                    disabled={pageData.page <= 1}
                    onClick={() => changePage(pageData.page - 1)}
                  >
                    Anterior
                  </Button>
                  <form onSubmit={submitPageJump} className="flex items-center gap-1.5">
                    <label htmlFor="chats-page-input" className="sr-only">
                      Ir a la página
                    </label>
                    <input
                      id="chats-page-input"
                      type="text"
                      inputMode="numeric"
                      value={pageInput}
                      onChange={(event) => setPageInput(event.target.value)}
                      className="h-8 w-14 rounded-md border border-[#CCD4E0] px-2 text-center text-xs text-[#1F242E]"
                    />
                    <Button type="submit" size="small" variant="quiet">
                      Ir
                    </Button>
                  </form>
                  <Button
                    size="small"
                    variant="quiet"
                    disabled={pageData.page >= pageData.totalPages}
                    onClick={() => changePage(pageData.page + 1)}
                  >
                    Siguiente
                  </Button>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}
