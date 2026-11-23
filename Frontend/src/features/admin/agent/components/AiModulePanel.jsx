"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  Cpu,
  Loader2,
  MessageSquareText,
  RefreshCw,
  RotateCcw,
  ShieldAlert,
  Sparkles,
} from "lucide-react";
import AccountFeedback from "@/shared/components/AccountFeedback";
import Badge from "@/shared/components/Badge";
import Button from "@/shared/components/Button";
import MetricCard from "@/shared/components/MetricCard";
import Notice from "@/shared/components/Notice";
import { useAccountsApi } from "@/shared/components/AccountsProvider";
import { mutateAgent } from "@/shared/actions/backendMutations";
import { queryKeys } from "@/shared/query/queryKeys";
import {
  AGENT_MODELS_POLL_ACTIVE_MS,
  AGENT_MODELS_POLL_IDLE_MS,
  createAgentMutations,
  DEFAULT_ANALYTICS_LIMIT,
  getModels,
  getQueryAnalytics,
  getTopicAnalytics,
  hasAgentPermission,
  isModelTransitioning,
  isTargetActivated,
  MAX_ANALYTICS_LIMIT,
  MIN_ANALYTICS_LIMIT,
  normalizeAvailableModels,
  validateAnalyticsRange,
} from "@/features/admin/agent/agentAdminService";

const agentMutations = createAgentMutations(mutateAgent);
const primaryButtonClass = "!border-[#7f1218] !bg-[#7f1218] hover:!bg-[#6a0f14]";
const outlineButtonClass = "!border-[#7f1218] !text-[#7f1218]";

const PHASE_META = {
  ready: { label: "Listo", state: "success", description: "El modelo activo atiende nuevas consultas con normalidad." },
  draining: {
    label: "Drenando turnos",
    state: "warning",
    description: "Se cerraron nuevas admisiones y se espera a que terminen todos los turnos aceptados o en cola.",
  },
  switching: {
    label: "Cambiando modelo",
    state: "info",
    description: "Validando y reactivando el modelo de destino antes de enrutar el tráfico.",
  },
  error: {
    label: "Error en transición",
    state: "error",
    description: "Se conserva el modelo de origen y el controlador reintentará periódicamente.",
  },
};

function formatModelTitle(name) {
  const labels = {
    qwen: "Qwen",
    glm: "GLM",
    llama: "Llama",
  };
  const key = String(name ?? "").toLowerCase();
  return labels[key] || String(name ?? "—");
}

function ModelControlSection({ canUpdateModels }) {
  const queryClient = useQueryClient();
  const [busyAction, setBusyAction] = useState(null);
  const [feedback, setFeedback] = useState(null);

  const modelsQuery = useQuery({
    queryKey: queryKeys.agent.models,
    queryFn: ({ signal }) => getModels(signal),
    refetchInterval: (query) => (
      isModelTransitioning(query.state.data) ? AGENT_MODELS_POLL_ACTIVE_MS : AGENT_MODELS_POLL_IDLE_MS
    ),
    refetchIntervalInBackground: false,
  });

  const data = modelsQuery.data;
  const availableModels = normalizeAvailableModels(data);
  const phase = data?.phase || "ready";
  const phaseMeta = PHASE_META[phase] || { label: phase, state: "info", description: "" };
  const transitioning = isModelTransitioning(data);
  const loading = modelsQuery.isPending || (modelsQuery.isError && modelsQuery.isFetching);

  async function handleSwitch(targetModel) {
    if (!canUpdateModels || busyAction) return;
    setBusyAction(`switch:${targetModel}`);
    setFeedback(null);
    try {
      const result = await agentMutations.switchModel(targetModel);
      if (result.status === 200) {
        setFeedback({
          variant: "success",
          message: `El modelo ${formatModelTitle(targetModel)} ya se encontraba activo.`,
        });
      } else {
        setFeedback({
          variant: "neutral",
          message: `Cambio hacia ${formatModelTitle(targetModel)} iniciado. No se mostrará como activo hasta que termine el drenaje y la fase vuelva a «Listo».`,
        });
      }
      await queryClient.invalidateQueries({ queryKey: queryKeys.agent.models });
    } catch (error) {
      setFeedback({
        variant: "error",
        message: error.message || "No se pudo solicitar el cambio de modelo.",
      });
      await queryClient.invalidateQueries({ queryKey: queryKeys.agent.models });
    } finally {
      setBusyAction(null);
    }
  }

  async function handleCancelSwitch() {
    if (!canUpdateModels || busyAction) return;
    setBusyAction("cancel");
    setFeedback(null);
    try {
      await agentMutations.cancelModelSwitch();
      setFeedback({
        variant: "success",
        message: "Cambio pendiente cancelado. Se conserva o reactiva el modelo de origen.",
      });
      await queryClient.invalidateQueries({ queryKey: queryKeys.agent.models });
    } catch (error) {
      setFeedback({
        variant: "error",
        message:
          error?.status === 409
            ? error.message || "No se puede cancelar porque el cambio de modelo ya está en ejecución."
            : error.message || "No se pudo cancelar el cambio pendiente.",
      });
      await queryClient.invalidateQueries({ queryKey: queryKeys.agent.models });
    } finally {
      setBusyAction(null);
    }
  }

  if (loading) {
    return (
      <div role="status" className="flex items-center gap-2 rounded-xl border border-[#DCE0E5] bg-white p-8 text-sm text-[#68707C]">
        <Loader2 className="h-4 w-4 animate-spin text-[#7f1218]" aria-hidden="true" />
        <span>Cargando estado del controlador de modelos…</span>
      </div>
    );
  }

  if (modelsQuery.isError) {
    return <AccountFeedback error={modelsQuery.error} retry={() => modelsQuery.refetch()} />;
  }

  const canCancel = canUpdateModels && Boolean(data?.pending_model || phase === "draining" || phase === "error");

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-[#1F242E]">Estado del modelo activo</h2>
          <p className="text-sm text-[#6B758A]">
            Consulta y realiza cambios seguros entre modelos configurados sin interrumpir turnos en curso.
          </p>
        </div>
        <Button
          variant="outline"
          size="small"
          className={outlineButtonClass}
          onClick={() => modelsQuery.refetch()}
          disabled={modelsQuery.isFetching}
        >
          <RefreshCw className={`mr-1.5 h-3.5 w-3.5 ${modelsQuery.isFetching ? "animate-spin" : ""}`} aria-hidden="true" />
          Actualizar
        </Button>
      </div>

      {/* Tarjetas de estado del controlador */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard
          value={data?.active_model ? formatModelTitle(data.active_model) : "Sin activo"}
          label="Modelo activo actual"
          delta={phaseMeta.label}
        />
        <MetricCard
          value={data?.pending_model ? formatModelTitle(data.pending_model) : "Ninguno"}
          label="Cambio pendiente"
          delta={
            data?.pending_model
              ? "Aún no está activo; esperando fin de transición"
              : "Sin transición en curso"
          }
        />
        <MetricCard
          value={String(data?.inflight ?? 0)}
          label="Turnos en curso (inflight)"
          delta="Turnos aceptados o en cola"
        />
        <MetricCard
          value={String(data?.generation ?? 0)}
          label="Generación"
          delta={transitioning ? "Actualizando cada 4 s" : "Controlador estable"}
        />
      </div>

      {/* Banner de fase actual */}
      <div className="rounded-xl border border-[#DCE0E5] bg-white p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2.5">
            <span className="text-sm font-semibold text-[#1F242E]">Fase del controlador:</span>
            <Badge state={phaseMeta.state}>{phaseMeta.label}</Badge>
            <span className="text-sm text-[#6B758A]">{phaseMeta.description}</span>
          </div>
          {canCancel && (
            <Button
              variant="outline"
              size="small"
              className={outlineButtonClass}
              disabled={busyAction !== null || phase === "switching"}
              onClick={handleCancelSwitch}
            >
              <RotateCcw className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
              {busyAction === "cancel" ? "Cancelando…" : "Cancelar cambio"}
            </Button>
          )}
        </div>
      </div>

      {data?.last_error && (
        <Notice variant="error" live>
          <div className="flex items-start gap-2.5">
            <ShieldAlert className="mt-1 h-5 w-5 shrink-0" aria-hidden="true" />
            <div className="space-y-1 text-sm">
              <p className="font-semibold">Último error reportado por el controlador</p>
              <p className="whitespace-pre-wrap break-words">{String(data.last_error)}</p>
              <p className="text-xs opacity-90">
                Mientras persista el error se conserva el modelo de origen y el controlador reintenta periódicamente.
              </p>
            </div>
          </div>
        </Notice>
      )}

      {feedback && (
        <Notice variant={feedback.variant} live>
          <p className="text-sm">{feedback.message}</p>
        </Notice>
      )}

      {/* Catálogo de modelos disponibles */}
      <div className="space-y-3">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h3 className="text-base font-bold text-[#1F242E]">Modelos disponibles</h3>
          <p className="text-xs text-[#6B758A]">
            «Configurado» indica configuración disponible en el servidor, no una prueba remota de salud.
          </p>
        </div>

        {availableModels.length === 0 ? (
          <Notice>
            <p className="text-sm text-[#68707C]">No hay modelos reportados por el controlador.</p>
          </Notice>
        ) : (
          <div className="grid gap-4 md:grid-cols-3">
            {availableModels.map((model) => {
              const fullyActive = isTargetActivated(data, model.name);
              const isOriginDuringTransition = data?.active_model === model.name && !fullyActive;
              const isPendingTarget = data?.pending_model === model.name;
              const incompatiblePending = Boolean(
                data?.pending_model && data.pending_model !== model.name,
              );
              const isSwitchingThis = busyAction === `switch:${model.name}`;
              const disabled =
                !canUpdateModels ||
                !model.configured ||
                fullyActive ||
                isPendingTarget ||
                incompatiblePending ||
                phase === "switching" ||
                busyAction !== null;

              return (
                <article
                  key={model.name}
                  className={`flex flex-col justify-between rounded-xl border bg-white p-5 transition ${
                    fullyActive
                      ? "border-[#17643A]/40 ring-1 ring-[#17643A]/20"
                      : isPendingTarget
                        ? "border-[#174C92]/40 ring-1 ring-[#174C92]/20"
                        : "border-[#DCE0E5]"
                  }`}
                >
                  <div className="space-y-3">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <h4 className="text-lg font-bold text-[#1F242E]">{formatModelTitle(model.name)}</h4>
                        <p className="font-mono text-xs text-[#6B758A]">{model.name}</p>
                      </div>
                      <Badge state={model.configured ? "success" : "error"}>
                        {model.configured ? "Configurado" : "No configurado"}
                      </Badge>
                    </div>

                    <div className="flex flex-wrap gap-2">
                      {fullyActive && (
                        <Badge state="success">
                          <CheckCircle2 className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
                          Activo
                        </Badge>
                      )}
                      {isOriginDuringTransition && (
                        <Badge state="warning">Origen actual (drenando)</Badge>
                      )}
                      {isPendingTarget && (
                        <Badge state="info">
                          <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                          Destino pendiente
                        </Badge>
                      )}
                    </div>

                    <p className="text-xs leading-5 text-[#6B758A]">
                      {!model.configured
                        ? "Este modelo no tiene configuración activa en el servidor."
                        : fullyActive
                          ? "Atendiendo actualmente las consultas del asistente público."
                          : isPendingTarget
                            ? "Cambio en curso: pasará a activo únicamente cuando el controlador complete el drenaje y vuelva a fase «Listo»."
                            : isOriginDuringTransition
                              ? "Seguirá respondiendo los turnos aceptados hasta completar el cambio seguro."
                              : "Disponible para programar un cambio seguro sin interrumpir turnos actuales."}
                    </p>
                  </div>

                  {canUpdateModels && (
                    <div className="mt-5 pt-3 border-t border-[#EEF0F3]">
                      <Button
                        size="small"
                        variant={fullyActive ? "quiet" : "primary"}
                        className={fullyActive ? "w-full" : `w-full ${primaryButtonClass}`}
                        disabled={disabled}
                        onClick={() => handleSwitch(model.name)}
                      >
                        {isSwitchingThis
                          ? "Solicitando cambio…"
                          : fullyActive
                            ? "Modelo activo"
                            : isPendingTarget
                              ? "Cambio pendiente…"
                              : "Cambiar a este modelo"}
                      </Button>
                    </div>
                  )}
                </article>
              );
            })}
          </div>
        )}
      </div>

      {/* Nota operativa */}
      <div className="rounded-xl border border-[#DCE0E5] bg-[#F7F8FA] p-4 text-xs leading-5 text-[#4B5563]">
        <p className="font-semibold text-[#1F242E]">Cómo funciona el cambio seguro de modelo</p>
        <p className="mt-1">
          Al solicitar un cambio, el controlador cierra nuevas admisiones, finaliza todos los turnos aceptados
          (incluidos los en cola) sin interrumpirlos, confirma el drenaje remoto y valida o reactiva el destino antes
          de cambiar la ruta. El proveedor apaga por inactividad el modelo de origen.
        </p>
      </div>
    </div>
  );
}

function AgentAnalyticsSection() {
  const [kind, setKind] = useState("program");
  const [sinceInput, setSinceInput] = useState("");
  const [untilInput, setUntilInput] = useState("");
  const [limitInput, setLimitInput] = useState(String(DEFAULT_ANALYTICS_LIMIT));
  const [appliedFilters, setAppliedFilters] = useState({
    since: "",
    until: "",
    limit: DEFAULT_ANALYTICS_LIMIT,
  });
  const [filterError, setFilterError] = useState("");
  const [querySearch, setQuerySearch] = useState("");

  const topicParams = {
    kind,
    limit: appliedFilters.limit,
    since: appliedFilters.since,
    until: appliedFilters.until,
  };

  const queryParams = {
    since: appliedFilters.since,
    until: appliedFilters.until,
  };

  const topicsQuery = useQuery({
    queryKey: queryKeys.agent.analyticsTopics(topicParams),
    queryFn: ({ signal }) => getTopicAnalytics(topicParams, signal),
  });

  const queriesQuery = useQuery({
    queryKey: queryKeys.agent.analyticsQueries(queryParams),
    queryFn: ({ signal }) => getQueryAnalytics(queryParams, signal),
  });

  function applyFilters(event) {
    event.preventDefault();
    const check = validateAnalyticsRange({
      since: sinceInput,
      until: untilInput,
      limit: limitInput,
    });
    if (!check.valid) {
      setFilterError(check.error);
      return;
    }
    setFilterError("");
    setAppliedFilters({
      since: check.since,
      until: check.until,
      limit: check.limit,
    });
  }

  function clearFilters() {
    setSinceInput("");
    setUntilInput("");
    setLimitInput(String(DEFAULT_ANALYTICS_LIMIT));
    setFilterError("");
    setAppliedFilters({
      since: "",
      until: "",
      limit: DEFAULT_ANALYTICS_LIMIT,
    });
  }

  const topics = topicsQuery.data?.results ?? [];
  const maxTopicQueries = topics.reduce((max, item) => Math.max(max, Number(item.queries) || 0), 1);

  const frequentQueries = queriesQuery.data?.results ?? [];
  const searchTerm = querySearch.trim().toLocaleLowerCase("es");
  const filteredQueries = searchTerm
    ? frequentQueries.filter((item) =>
      String(item.prompt || item.prompt_key || "").toLocaleLowerCase("es").includes(searchTerm),
    )
    : frequentQueries;

  return (
    <div className="space-y-6">
      {/* Filtros compartidos */}
      <form
        onSubmit={applyFilters}
        className="rounded-xl border border-[#DCE0E5] bg-white p-4 space-y-4"
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-lg font-bold text-[#1F242E]">Filtros de analítica</h2>
            <p className="text-xs text-[#6B758A]">
              Fechas opcionales inclusivas. Las métricas cuentan consultas y chats anónimos, no personas únicas.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="quiet" size="small" onClick={clearFilters}>
              Limpiar
            </Button>
            <Button type="submit" size="small" className={primaryButtonClass}>
              Aplicar filtros
            </Button>
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="space-y-1">
            <label htmlFor="analytics-kind" className="block text-xs font-semibold text-[#4B5563]">
              Agrupación de ranking
            </label>
            <select
              id="analytics-kind"
              value={kind}
              onChange={(event) => setKind(event.target.value)}
              className="h-10 w-full rounded-lg border border-[#CCD4E0] bg-white px-3 text-sm text-[#1F242E] focus-visible:outline-2 focus-visible:outline-[#7f1218]"
            >
              <option value="program">Programas académicos</option>
              <option value="area">Áreas de conocimiento</option>
            </select>
          </div>

          <div className="space-y-1">
            <label htmlFor="analytics-since" className="block text-xs font-semibold text-[#4B5563]">
              Desde (inclusiva)
            </label>
            <input
              id="analytics-since"
              type="date"
              value={sinceInput}
              onChange={(event) => setSinceInput(event.target.value)}
              className="h-10 w-full rounded-lg border border-[#CCD4E0] bg-white px-3 text-sm text-[#1F242E] focus-visible:outline-2 focus-visible:outline-[#7f1218]"
            />
          </div>

          <div className="space-y-1">
            <label htmlFor="analytics-until" className="block text-xs font-semibold text-[#4B5563]">
              Hasta (inclusiva)
            </label>
            <input
              id="analytics-until"
              type="date"
              value={untilInput}
              onChange={(event) => setUntilInput(event.target.value)}
              className="h-10 w-full rounded-lg border border-[#CCD4E0] bg-white px-3 text-sm text-[#1F242E] focus-visible:outline-2 focus-visible:outline-[#7f1218]"
            />
          </div>

          <div className="space-y-1">
            <label htmlFor="analytics-limit" className="block text-xs font-semibold text-[#4B5563]">
              Límite de temas ({MIN_ANALYTICS_LIMIT}–{MAX_ANALYTICS_LIMIT})
            </label>
            <input
              id="analytics-limit"
              type="number"
              min={MIN_ANALYTICS_LIMIT}
              max={MAX_ANALYTICS_LIMIT}
              value={limitInput}
              onChange={(event) => setLimitInput(event.target.value)}
              className="h-10 w-full rounded-lg border border-[#CCD4E0] bg-white px-3 text-sm text-[#1F242E] focus-visible:outline-2 focus-visible:outline-[#7f1218]"
            />
          </div>
        </div>

        {filterError && (
          <p role="alert" className="text-xs font-medium text-[#820A1F]">
            {filterError}
          </p>
        )}
      </form>

      {/* Ranking de temas */}
      <section className="rounded-xl border border-[#DCE0E5] bg-white p-5 space-y-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 className="flex items-center gap-2 text-base font-bold text-[#1F242E]">
              <BarChart3 className="h-4 w-4 text-[#7f1218]" aria-hidden="true" />
              Ranking de {kind === "area" ? "áreas de conocimiento" : "programas académicos"}
            </h3>
            <p className="mt-1 text-xs leading-5 text-[#6B758A]">
              Ranking denso: iguales frecuencias comparten posición (1, 1, 2…). Un tema se cuenta una vez por turno;
              las áreas pueden derivarse del programa consultado. «Conversaciones» cuenta chats anónimos, no personas.
            </p>
          </div>
          <Button
            variant="quiet"
            size="small"
            onClick={() => topicsQuery.refetch()}
            disabled={topicsQuery.isFetching}
          >
            <RefreshCw className={`mr-1.5 h-3.5 w-3.5 ${topicsQuery.isFetching ? "animate-spin" : ""}`} aria-hidden="true" />
            Actualizar
          </Button>
        </div>

        {topicsQuery.isPending ? (
          <div role="status" className="flex items-center gap-2 py-6 text-sm text-[#68707C]">
            <Loader2 className="h-4 w-4 animate-spin text-[#7f1218]" aria-hidden="true" />
            <span>Cargando ranking de temas…</span>
          </div>
        ) : topicsQuery.isError ? (
          <AccountFeedback error={topicsQuery.error} retry={() => topicsQuery.refetch()} />
        ) : topics.length === 0 ? (
          <p className="rounded-lg bg-[#F7F8FA] p-6 text-center text-sm text-[#68707C]">
            No hay registros de temas para el filtro seleccionado.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] border-collapse text-sm">
              <thead>
                <tr className="bg-[#EEF0F3] text-left text-xs uppercase tracking-wider text-[#68707C]">
                  <th scope="col" className="px-3 py-2.5 font-semibold w-24">Tier</th>
                  <th scope="col" className="px-3 py-2.5 font-semibold">
                    {kind === "area" ? "Área de conocimiento" : "Programa académico"}
                  </th>
                  <th scope="col" className="px-3 py-2.5 font-semibold w-48">Consultas</th>
                  <th scope="col" className="px-3 py-2.5 font-semibold w-36 text-right">Conversaciones</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#EEF0F3]">
                {topics.map((item, idx) => {
                  const queriesCount = Number(item.queries) || 0;
                  const ratio = Math.max(4, Math.round((queriesCount / maxTopicQueries) * 100));
                  return (
                    <tr key={`${item.catalog_id ?? item.name}-${idx}`} className="hover:bg-[#F9FAFB]">
                      <td className="px-3 py-3">
                        <Badge state={item.tier === 1 ? "warning" : "info"}>
                          Tier #{item.tier}
                        </Badge>
                      </td>
                      <td className="px-3 py-3">
                        <p className="font-medium text-[#1F242E]">{item.name}</p>
                        {item.catalog_id != null && (
                          <p className="font-mono text-[11px] text-[#6B758A]">ID catálogo: {item.catalog_id}</p>
                        )}
                      </td>
                      <td className="px-3 py-3">
                        <div className="space-y-1">
                          <span className="font-semibold text-[#1F242E]">{queriesCount}</span>
                          <div className="h-2 w-full overflow-hidden rounded-full bg-[#EEF0F3]">
                            <div
                              className="h-full rounded-full bg-[#7f1218]"
                              style={{ width: `${ratio}%` }}
                            />
                          </div>
                        </div>
                      </td>
                      <td className="px-3 py-3 text-right font-medium text-[#4B5563]">
                        {item.conversations}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Consultas frecuentes */}
      <section className="rounded-xl border border-[#DCE0E5] bg-white p-5 space-y-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 className="flex items-center gap-2 text-base font-bold text-[#1F242E]">
              <MessageSquareText className="h-4 w-4 text-[#7f1218]" aria-hidden="true" />
              Consultas frecuentes
            </h3>
            <p className="mt-1 text-xs leading-5 text-[#6B758A]">
              Hasta 100 textos normalizados por mayúsculas y espacios (no agrupa paráfrasis semánticas). No existe
              analítica de usuarios únicos.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <label htmlFor="frequent-queries-filter" className="sr-only">
              Filtrar consultas frecuentes
            </label>
            <input
              id="frequent-queries-filter"
              type="search"
              value={querySearch}
              onChange={(event) => setQuerySearch(event.target.value)}
              placeholder="Filtrar en resultados…"
              className="h-8 rounded-lg border border-[#CCD4E0] bg-white px-3 text-xs text-[#1F242E] focus-visible:outline-2 focus-visible:outline-[#7f1218]"
            />
            <Button
              variant="quiet"
              size="small"
              onClick={() => queriesQuery.refetch()}
              disabled={queriesQuery.isFetching}
            >
              <RefreshCw className={`mr-1.5 h-3.5 w-3.5 ${queriesQuery.isFetching ? "animate-spin" : ""}`} aria-hidden="true" />
              Actualizar
            </Button>
          </div>
        </div>

        {queriesQuery.isPending ? (
          <div role="status" className="flex items-center gap-2 py-6 text-sm text-[#68707C]">
            <Loader2 className="h-4 w-4 animate-spin text-[#7f1218]" aria-hidden="true" />
            <span>Cargando consultas frecuentes…</span>
          </div>
        ) : queriesQuery.isError ? (
          <AccountFeedback error={queriesQuery.error} retry={() => queriesQuery.refetch()} />
        ) : filteredQueries.length === 0 ? (
          <p className="rounded-lg bg-[#F7F8FA] p-6 text-center text-sm text-[#68707C]">
            {frequentQueries.length === 0
              ? "Todavía no hay consultas frecuentes registradas para el periodo seleccionado."
              : "Ninguna consulta coincide con el texto ingresado."}
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] border-collapse text-sm">
              <thead>
                <tr className="bg-[#EEF0F3] text-left text-xs uppercase tracking-wider text-[#68707C]">
                  <th scope="col" className="px-3 py-2.5 font-semibold w-14">#</th>
                  <th scope="col" className="px-3 py-2.5 font-semibold">Consulta normalizada</th>
                  <th scope="col" className="px-3 py-2.5 font-semibold w-28 text-right">Consultas</th>
                  <th scope="col" className="px-3 py-2.5 font-semibold w-36 text-right">Conversaciones</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#EEF0F3]">
                {filteredQueries.map((item, idx) => (
                  <tr key={`${item.prompt_key ?? item.prompt}-${idx}`} className="hover:bg-[#F9FAFB]">
                    <td className="px-3 py-3 text-xs text-[#6B758A]">{idx + 1}</td>
                    <td className="px-3 py-3">
                      <p className="whitespace-pre-wrap break-words font-medium text-[#1F242E]">
                        {item.prompt || item.prompt_key}
                      </p>
                    </td>
                    <td className="px-3 py-3 text-right font-semibold text-[#1F242E]">{item.queries}</td>
                    <td className="px-3 py-3 text-right text-[#4B5563]">{item.conversations}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

export default function AiModulePanel({ initialTab = "modelos" }) {
  const accountsApi = useAccountsApi();
  const [selectedTab, setSelectedTab] = useState(initialTab === "analitica" ? "analitica" : "modelos");

  const viewerQuery = useQuery({
    queryKey: queryKeys.accounts.viewer,
    queryFn: ({ signal }) => accountsApi.me(signal),
  });

  const viewer = viewerQuery.data ?? null;
  const canViewModels = hasAgentPermission(viewer, "models", "view");
  const canUpdateModels = hasAgentPermission(viewer, "models", "update");
  const canViewAnalytics = hasAgentPermission(viewer, "analytics", "view");
  const canViewConversations = hasAgentPermission(viewer, "conversations", "view");

  const activeTab =
    selectedTab === "modelos" && !canViewModels && canViewAnalytics
      ? "analitica"
      : selectedTab === "analitica" && !canViewAnalytics && canViewModels
        ? "modelos"
        : selectedTab;

  return (
    <section className="space-y-5 text-[#1F242E]">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-[30px] leading-[41px] font-bold">Módulo de IA</h1>
          <p className="mt-2 text-[15px] text-[#6B758A]">
            Administra el modelo activo del asistente de búsqueda y consulta la analítica anónima de uso.
          </p>
        </div>
        {canViewConversations && (
          <Button variant="outline" className={outlineButtonClass} href="/admin/chats">
            Ver conversaciones
          </Button>
        )}
      </header>

      {viewerQuery.isPending ? (
        <div role="status" className="flex items-center gap-2 rounded-xl border border-[#DCE0E5] bg-white p-8 text-sm text-[#68707C]">
          <Loader2 className="h-4 w-4 animate-spin text-[#7f1218]" aria-hidden="true" />
          <span>Verificando permisos del módulo de IA…</span>
        </div>
      ) : viewerQuery.isError ? (
        <AccountFeedback error={viewerQuery.error} retry={() => viewerQuery.refetch()} />
      ) : !canViewModels && !canViewAnalytics ? (
        <Notice variant="error">
          <div className="flex items-start gap-2.5 text-sm">
            <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" aria-hidden="true" />
            <p>
              Tu cuenta no tiene permisos para consultar el estado de modelos ni la analítica del asistente
              (<code>agent.models.view</code> o <code>agent.analytics.view</code>).
            </p>
          </div>
        </Notice>
      ) : (
        <>
          {/* Pestañas de navegación del módulo */}
          <div className="flex flex-wrap gap-2 border-b border-[#DCE0E5]" role="tablist" aria-label="Secciones del módulo de IA">
            {canViewModels && (
              <button
                type="button"
                role="tab"
                aria-selected={activeTab === "modelos"}
                onClick={() => setSelectedTab("modelos")}
                className={`inline-flex items-center gap-2 border-b-2 px-4 py-2.5 text-sm font-semibold transition ${
                  activeTab === "modelos"
                    ? "border-[#7f1218] text-[#7f1218]"
                    : "border-transparent text-[#6B758A] hover:text-[#1F242E]"
                }`}
              >
                <Cpu className="h-4 w-4" aria-hidden="true" />
                Modelos de IA
              </button>
            )}
            {canViewAnalytics && (
              <button
                type="button"
                role="tab"
                aria-selected={activeTab === "analitica"}
                onClick={() => setSelectedTab("analitica")}
                className={`inline-flex items-center gap-2 border-b-2 px-4 py-2.5 text-sm font-semibold transition ${
                  activeTab === "analitica"
                    ? "border-[#7f1218] text-[#7f1218]"
                    : "border-transparent text-[#6B758A] hover:text-[#1F242E]"
                }`}
              >
                <Sparkles className="h-4 w-4" aria-hidden="true" />
                Analítica del asistente
              </button>
            )}
          </div>

          {activeTab === "modelos" && canViewModels && (
            <ModelControlSection canUpdateModels={canUpdateModels} />
          )}
          {activeTab === "analitica" && canViewAnalytics && (
            <AgentAnalyticsSection />
          )}
        </>
      )}
    </section>
  );
}
