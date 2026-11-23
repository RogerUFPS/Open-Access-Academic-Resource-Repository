"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowLeft, Clock, Cpu, Loader2, RefreshCw, ShieldCheck } from "lucide-react";
import AccountFeedback from "@/shared/components/AccountFeedback";
import Badge from "@/shared/components/Badge";
import Button from "@/shared/components/Button";
import ChatResponseView from "@/shared/components/ChatResponseView";
import Notice from "@/shared/components/Notice";
import { useAccountsApi } from "@/shared/components/AccountsProvider";
import { queryKeys } from "@/shared/query/queryKeys";
import { clampPage, isMissingPage, sanitizePageValue } from "@/shared/utils/pagination";
import {
  CONVERSATION_TURNS_PAGE_SIZE,
  formatBogotaDateTime,
  formatTurnDuration,
  getConversationDetail,
  hasAgentPermission,
} from "@/features/admin/agent/agentAdminService";

const TURN_STATUS_META = {
  completed: { label: "Completado", state: "success" },
  failed: { label: "Fallido", state: "error" },
  running: { label: "En ejecución", state: "info" },
  queued: { label: "En cola", state: "warning" },
};

export default function ConversationDetail({ conversationId }) {
  const accountsApi = useAccountsApi();
  const [page, setPage] = useState(1);
  const [pageInput, setPageInput] = useState("1");

  const viewerQuery = useQuery({
    queryKey: queryKeys.accounts.viewer,
    queryFn: ({ signal }) => accountsApi.me(signal),
  });

  const viewer = viewerQuery.data ?? null;
  const canView = hasAgentPermission(viewer, "conversations", "view");

  const detailQuery = useQuery({
    queryKey: queryKeys.agent.conversationDetail(conversationId, page),
    queryFn: ({ signal }) =>
      getConversationDetail(conversationId, { page, pageSize: CONVERSATION_TURNS_PAGE_SIZE }, signal),
    enabled: Boolean(canView && conversationId),
  });

  if (isMissingPage(detailQuery.error, page)) {
    setPage(1);
    setPageInput("1");
  }

  const conversation = detailQuery.data?.conversation;
  const turnsPage = detailQuery.data?.turns ?? {
    results: [],
    totalItems: 0,
    totalPages: 1,
    pageSize: CONVERSATION_TURNS_PAGE_SIZE,
    page: 1,
  };

  function changePage(nextPage) {
    const safe = clampPage(nextPage, turnsPage.totalPages);
    setPage(safe);
    setPageInput(String(safe));
  }

  function submitPageJump(event) {
    event.preventDefault();
    const parsed = sanitizePageValue(pageInput, turnsPage.totalPages);
    if (!parsed.valid) {
      setPageInput(String(clampPage(page, turnsPage.totalPages)));
      return;
    }
    setPage(parsed.page);
    setPageInput(String(parsed.page));
  }

  return (
    <section className="space-y-5 text-[#1F242E]">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-2">
          <Button href="/admin/chats" variant="quiet" size="small">
            <ArrowLeft className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
            Volver a conversaciones
          </Button>
          <div>
            <h1 className="text-[28px] leading-[36px] font-bold">Detalle de conversación</h1>
            <p className="mt-1 font-mono text-xs text-[#6B758A]">ID: {conversationId}</p>
          </div>
        </div>
        {canView && (
          <Button
            variant="quiet"
            onClick={() => detailQuery.refetch()}
            disabled={detailQuery.isFetching}
          >
            <RefreshCw className={`mr-1.5 h-4 w-4 ${detailQuery.isFetching ? "animate-spin" : ""}`} aria-hidden="true" />
            Actualizar
          </Button>
        )}
      </header>

      {viewerQuery.isPending ? (
        <div role="status" className="flex items-center gap-2 rounded-xl border border-[#DCE0E5] bg-white p-8 text-sm text-[#68707C]">
          <Loader2 className="h-4 w-4 animate-spin text-[#7f1218]" aria-hidden="true" />
          <span>Verificando permisos…</span>
        </div>
      ) : viewerQuery.isError ? (
        <AccountFeedback error={viewerQuery.error} retry={() => viewerQuery.refetch()} />
      ) : !canView ? (
        <Notice variant="error">
          <div className="flex items-start gap-2.5 text-sm">
            <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" aria-hidden="true" />
            <p>
              Tu cuenta no tiene permiso para inspeccionar conversaciones del asistente
              (<code>agent.conversations.view</code>).
            </p>
          </div>
        </Notice>
      ) : detailQuery.isPending ? (
        <div role="status" className="flex items-center gap-2 rounded-xl border border-[#DCE0E5] bg-white p-8 text-sm text-[#68707C]">
          <Loader2 className="h-4 w-4 animate-spin text-[#7f1218]" aria-hidden="true" />
          <span>Cargando turnos de la conversación…</span>
        </div>
      ) : detailQuery.isError ? (
        <AccountFeedback error={detailQuery.error} retry={() => detailQuery.refetch()} />
      ) : (
        <>
          {/* Resumen técnico */}
          <div className="rounded-xl border border-[#DCE0E5] bg-white p-4 space-y-3">
            <div className="flex flex-wrap items-center gap-3 text-sm">
              {conversation?.has_unclear ? (
                <Badge state="warning">Con respuesta poco clara</Badge>
              ) : (
                <Badge state="success">Clara</Badge>
              )}
              <span className="text-[#4B5563]">
                <strong className="text-[#1F242E]">{conversation?.turn_count ?? turnsPage.totalItems}</strong> turnos
              </span>
              {conversation?.created_at && (
                <span className="text-xs text-[#6B758A]">
                  Creada: {formatBogotaDateTime(conversation.created_at)}
                </span>
              )}
              {conversation?.updated_at && (
                <span className="text-xs text-[#6B758A]">
                  Actualizada: {formatBogotaDateTime(conversation.updated_at)}
                </span>
              )}
            </div>
            <div className="flex items-start gap-2 rounded-lg bg-[#F7F8FA] px-3 py-2 text-xs text-[#4B5563]">
              <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-[#7f1218]" aria-hidden="true" />
              <p>
                Auditoría técnica anónima: cada turno incluye el modelo empleado (<code>model_name</code>). No se
                almacena nombre, cuenta, dirección IP ni identidad del autor.
              </p>
            </div>
          </div>

          {/* Lista paginada de turnos */}
          {turnsPage.results.length === 0 ? (
            <div className="rounded-xl border border-[#DCE0E5] bg-white p-8 text-center text-sm text-[#68707C]">
              Esta conversación aún no tiene turnos registrados.
            </div>
          ) : (
            <div className="space-y-4">
              {turnsPage.results.map((turn, idx) => {
                const statusMeta = TURN_STATUS_META[turn.status] || {
                  label: String(turn.status || "Desconocido"),
                  state: "info",
                };
                const duration = formatTurnDuration(turn.created_at, turn.finished_at);

                return (
                  <article
                    key={turn.id ?? turn.client_message_id ?? `turn-${idx}`}
                    className="rounded-xl border border-[#DCE0E5] bg-white p-5 space-y-4"
                  >
                    <header className="flex flex-wrap items-center justify-between gap-2 border-b border-[#EEF0F3] pb-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="rounded-md bg-[#EEF0F3] px-2.5 py-1 font-mono text-xs font-bold text-[#1F242E]">
                          Turno #{turn.sequence ?? idx + 1}
                        </span>
                        <Badge state={statusMeta.state}>{statusMeta.label}</Badge>
                        {turn.unclear && <Badge state="warning">Poco clara</Badge>}
                        {turn.model_name && (
                          <span className="inline-flex items-center gap-1 rounded-full border border-[#DCE0E5] bg-[#F7F8FA] px-2.5 py-1 font-mono text-xs text-[#374151]">
                            <Cpu className="h-3.5 w-3.5 text-[#7f1218]" aria-hidden="true" />
                            {turn.model_name}
                          </span>
                        )}
                      </div>
                      <div className="flex flex-wrap items-center gap-3 text-xs text-[#6B758A]">
                        <span>Inicio: {formatBogotaDateTime(turn.created_at)}</span>
                        {turn.finished_at && <span>Fin: {formatBogotaDateTime(turn.finished_at)}</span>}
                        {duration && (
                          <span className="inline-flex items-center gap-1 font-medium text-[#1F242E]">
                            <Clock className="h-3.5 w-3.5 text-[#6B758A]" aria-hidden="true" />
                            {duration}
                          </span>
                        )}
                      </div>
                    </header>

                    {/* Prompt del usuario (texto escapado) */}
                    <div className="space-y-1.5">
                      <p className="text-[11px] font-bold uppercase tracking-wider text-[#6B758A]">
                        Consulta del usuario
                      </p>
                      <div className="rounded-lg border border-[#E5E7EB] bg-[#F7F8FA] px-3.5 py-3 text-sm leading-6 text-[#1F242E]">
                        <p className="whitespace-pre-wrap break-words">{turn.prompt}</p>
                      </div>
                    </div>

                    {/* Respuesta estructurada (texto escapado) */}
                    <div className="space-y-1.5">
                      <p className="text-[11px] font-bold uppercase tracking-wider text-[#6B758A]">
                        Respuesta del asistente
                      </p>
                      <div className="rounded-lg border border-[#E5E7EB] bg-white p-3.5">
                        {turn.status === "queued" || turn.status === "running" ? (
                          <p className="text-sm text-[#6B758A]">
                            Este turno aún está en procesamiento ({statusMeta.label.toLowerCase()}).
                          </p>
                        ) : (
                          <ChatResponseView
                            response={turn.response}
                            turnStatus={turn.status}
                            openPlatformInNewTab
                            showStateBadge
                          />
                        )}
                      </div>
                    </div>
                  </article>
                );
              })}
            </div>
          )}

          {/* Paginación de turnos */}
          {turnsPage.totalPages > 1 && (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[#DCE0E5] bg-white px-4 py-3 text-xs text-[#6B758A]">
              <span>
                Página <strong className="text-[#1F242E]">{turnsPage.page}</strong> de{" "}
                <strong className="text-[#1F242E]">{turnsPage.totalPages}</strong> ({turnsPage.totalItems} turnos)
              </span>
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  size="small"
                  variant="quiet"
                  disabled={turnsPage.page <= 1}
                  onClick={() => changePage(turnsPage.page - 1)}
                >
                  Anterior
                </Button>
                <form onSubmit={submitPageJump} className="flex items-center gap-1.5">
                  <label htmlFor="turns-page-input" className="sr-only">
                    Ir a la página de turnos
                  </label>
                  <input
                    id="turns-page-input"
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
                  disabled={turnsPage.page >= turnsPage.totalPages}
                  onClick={() => changePage(turnsPage.page + 1)}
                >
                  Siguiente
                </Button>
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}
