"use client";

import { useCallback, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "@/shared/query/queryKeys";
import AdminTable from "@/shared/components/AdminTable";
import Button from "@/shared/components/Button";
import FormField from "@/shared/components/FormField";
import MetricCard from "@/shared/components/MetricCard";
import Notice from "@/shared/components/Notice";
import { buildSelectionFilters, canRunDueSchedules, canUpdateSchedules, formatDate, formatSelectionFilters, getHarvestFilterOptions, getHarvests, getHarvestSourceCount, getPlatforms, getUpcomingSchedules, harvestHistoryOf, harvestProvider, hasRetiredSelectionFilters, runDueErrorMessage, runDueFeedback, runDueKey, selectionValuesFrom, shouldReuseRunDueKey } from "@/features/admin/harvesting/harvesting";
import { useAccountsApi } from "@/shared/components/AccountsProvider";
import HarvestExecutions from "./HarvestExecutions";
import HarvestSelectionFields, { useHarvestCountries } from "./HarvestSelectionFields";
import { useHarvestingApi } from "./HarvestingProvider";
import { clampPage, sanitizePageValue } from "@/shared/utils/pagination";

const FREQUENCIES = { once: "Única", daily: "Diaria", weekly: "Semanal", monthly: "Mensual" };
const SCHEDULE_PAGE_SIZE = 10;

const scheduleColumns = (countryNames) => [
  { key: "platforms", label: "FUENTES", width: "18%", render: (row) => row.platform_names?.join(", ") || row.platforms.map((id) => `Plataforma ${id}`).join(", ") },
  { key: "selection", label: "SELECCIÓN", width: "20%", render: (row) => (
    <div>
      <span className="[overflow-wrap:anywhere]">{formatSelectionFilters(row.selection_filters, countryNames)}</span>
      {hasRetiredSelectionFilters(row.selection_filters) && <span className="mt-1 block text-xs leading-[18px] text-[#820A1F]">Contiene filtros retirados: sus ejecuciones fallarán hasta editar la selección.</span>}
    </div>
  ) },
  { key: "frequency", label: "FRECUENCIA", width: "11%", render: (row) => FREQUENCIES[row.frequency] || row.frequency },
  { key: "start_date", label: "FECHA INICIAL", width: "16%", muted: true, render: (row) => formatDate(row.start_date) },
  { key: "limits", label: "LÍMITES POR FUENTE", width: "17%", render: (row) => [
    row.max_quantity == null ? null : `${row.max_quantity} registros examinados`,
    row.stop_after_minutes == null ? null : `${row.stop_after_minutes} minutos`,
  ].filter(Boolean).join(" · ") },
];

// Datos en caché: al volver a la pestaña se muestra lo último visto y se
// revalida en segundo plano. El sondeo se pausa con la pestaña oculta.
function useHarvestData(queryKey, loadData, refetchInterval = false) {
  const query = useQuery({
    queryKey,
    queryFn: ({ signal }) => loadData(signal),
    refetchInterval: typeof refetchInterval === "function"
      ? (current) => refetchInterval(current.state.data)
      : refetchInterval,
  });
  // Solo hay aviso de carga cuando no existe nada en caché para esta clave.
  const loading = query.isPending || (query.isError && query.isFetching);
  const error = query.isError && !query.isFetching ? query.error?.message || "Error al cargar los datos." : "";
  const { refetch } = query;
  const refresh = useCallback(() => { refetch(); }, [refetch]);
  return { data: query.data, loading, error, refresh };
}

export default function HarvestDashboard() {
  const queryClient = useQueryClient();
  const { deactivateSchedule, runDueSchedules, updateScheduleSelection } = useHarvestingApi();
  const accountsApi = useAccountsApi();
  const [page, setPage] = useState(1);
  const [pageInput, setPageInput] = useState("1");
  const [schedulePage, setSchedulePage] = useState(1);
  const [schedulePageInput, setSchedulePageInput] = useState("1");
  const [executing, setExecuting] = useState(false);
  const [executionFeedback, setExecutionFeedback] = useState(null);
  const [selectedSchedule, setSelectedSchedule] = useState(null);
  const [explanation, setExplanation] = useState("");
  const [deactivating, setDeactivating] = useState(false);
  const [scheduleFeedback, setScheduleFeedback] = useState(null);
  const [editingSchedule, setEditingSchedule] = useState(null);
  const [editValues, setEditValues] = useState(null);
  const [editSaving, setEditSaving] = useState(false);
  const [editError, setEditError] = useState("");
  // Recorrido (plataforma + filter_key del servidor) cuyo historial se muestra.
  const [history, setHistory] = useState(null);
  const requestPending = useRef(false);
  const runDueKeyRef = useRef(null);

  const viewer = useQuery({ queryKey: queryKeys.accounts.viewer, queryFn: ({ signal }) => accountsApi.me(signal) });
  const canRunDue = canRunDueSchedules(viewer.data);
  const canEditSelection = canUpdateSchedules(viewer.data);
  const filterOptions = useQuery({
    queryKey: queryKeys.harvests.filterOptions,
    queryFn: ({ signal }) => getHarvestFilterOptions(signal),
    staleTime: 10 * 60 * 1000,
  });
  // Las plataformas solo se consultan al editar: el proveedor sale de su configuración.
  const platforms = useQuery({
    queryKey: queryKeys.harvests.platforms,
    queryFn: ({ signal }) => getPlatforms(signal),
    enabled: Boolean(editingSchedule),
    staleTime: 5 * 60 * 1000,
  });

  const historyKey = history && { platform: history.platform, filterKey: history.filterKey };
  const harvests = useHarvestData(queryKeys.harvests.list(page, historyKey), (signal) => getHarvests(page, signal, historyKey), (data) => (
    executing || data?.results.some((row) => ["pending", "running", "pausing"].includes(row.state)) ? 5000 : 30000
  ));
  const upcomingSchedules = useHarvestData(queryKeys.harvests.schedules, getUpcomingSchedules, 30000);
  const sources = useHarvestData(queryKeys.harvests.sourceCount, getHarvestSourceCount);
  const usesCountries = [...(harvests.data?.results || []), ...(upcomingSchedules.data || [])].some((row) => row.selection_filters?.country_code);
  const countries = useHarvestCountries(filterOptions.data, usesCountries);
  const countryNames = new Map((countries.data || []).map((country) => [country.abbreviation.trim().toUpperCase(), country.name]));

  // Tras una acción se revalidan todas las páginas de ejecuciones en caché.
  const refreshHarvests = () => queryClient.invalidateQueries({ queryKey: queryKeys.harvests.lists });

  // Si la lista de programaciones se acorta, la página vuelve a la última válida.
  const scheduleCount = upcomingSchedules.data?.length || 0;
  const schedulePages = Math.max(1, Math.ceil(scheduleCount / SCHEDULE_PAGE_SIZE));
  if (upcomingSchedules.data && schedulePage > schedulePages) {
    setSchedulePage(schedulePages);
    setSchedulePageInput(String(schedulePages));
  }

  async function executeDue() {
    if (requestPending.current || harvests.loading || upcomingSchedules.loading || !canRunDue) return;
    requestPending.current = true;
    setExecuting(true);
    setExecutionFeedback(null);
    try {
      runDueKeyRef.current = runDueKey(runDueKeyRef.current);
      setExecutionFeedback(runDueFeedback(await runDueSchedules(runDueKeyRef.current)));
      runDueKeyRef.current = null;
    } catch (error) {
      if (!shouldReuseRunDueKey(error)) runDueKeyRef.current = null;
      setExecutionFeedback({ variant: "error", message: runDueErrorMessage(error) });
    } finally {
      requestPending.current = false;
      setExecuting(false);
      // The result may be uncertain after a timeout; always read the current state.
      setPage(1);
      setPageInput("1");
      refreshHarvests();
      upcomingSchedules.refresh();
    }
  }

  async function deactivate(event) {
    event.preventDefault();
    if (requestPending.current || upcomingSchedules.loading || !selectedSchedule || !explanation.trim()) return;
    requestPending.current = true;
    setDeactivating(true);
    setScheduleFeedback(null);
    try {
      await deactivateSchedule(selectedSchedule.id, explanation);
      setScheduleFeedback({ variant: "success", message: `Programación #${selectedSchedule.id} desactivada.` });
      setSelectedSchedule(null);
      setExplanation("");
    } catch (error) {
      setScheduleFeedback({ variant: "error", message: error.message });
    } finally {
      requestPending.current = false;
      setDeactivating(false);
      upcomingSchedules.refresh();
    }
  }

  // Proveedores de la programación editada; la selección debe ser compatible con todos.
  const editProviders = editingSchedule && platforms.data
    ? [...new Set(editingSchedule.platforms.map((id) => harvestProvider(platforms.data.find((platform) => platform.id === id))))]
    : [];
  const editProvider = editProviders.length === 1 ? editProviders[0] : null;

  function openEdit(row) {
    setSelectedSchedule(null);
    setEditingSchedule(row);
    setEditValues(selectionValuesFrom(row.selection_filters));
    setEditError("");
    setScheduleFeedback(null);
  }

  function closeEdit() {
    setEditingSchedule(null);
    setEditValues(null);
    setEditError("");
  }

  async function saveSelection(event, globalOnly = false) {
    event?.preventDefault();
    if (requestPending.current || !editingSchedule || !filterOptions.data || !platforms.data) return;
    setEditError("");
    let selection;
    try {
      selection = globalOnly ? {} : buildSelectionFilters(editProvider, editValues, filterOptions.data);
    } catch (error) {
      setEditError(error.message);
      return;
    }
    requestPending.current = true;
    setEditSaving(true);
    try {
      const updated = await updateScheduleSelection(editingSchedule.id, selection);
      setScheduleFeedback({ variant: "success", message: `Selección de la programación #${editingSchedule.id} actualizada: ${formatSelectionFilters(updated?.selection_filters ?? selection, countryNames)}. Aplica a ejecuciones futuras; las ejecuciones existentes conservan su selección.` });
      closeEdit();
    } catch (error) {
      setEditError(error.message);
    } finally {
      requestPending.current = false;
      setEditSaving(false);
      upcomingSchedules.refresh();
    }
  }

  const scheduleBusy = upcomingSchedules.loading || Boolean(upcomingSchedules.error) || executing || deactivating || editSaving;
  const columns = [...scheduleColumns(countryNames), {
    key: "actions", label: "ACCIONES", width: "18%", render: (row) => (
      <div className="flex flex-wrap gap-2">
        {canEditSelection && <Button variant="quiet" size="small" disabled={scheduleBusy} aria-label={`Editar selección de la programación #${row.id}`} onClick={() => openEdit(row)}>Editar selección</Button>}
        <Button variant="quiet" size="small" disabled={scheduleBusy} aria-label={`Desactivar programación #${row.id}`} onClick={() => {
          closeEdit();
          setSelectedSchedule(row);
          setExplanation("");
          setScheduleFeedback(null);
        }}>Desactivar</Button>
      </div>
    ),
  }];

  function showHistory(next) {
    setHistory(next);
    setPage(1);
    setPageInput("1");
  }

  function changePage(nextPage, schedules = false) {
    if (schedules) {
      const safePage = clampPage(nextPage, schedulePages);
      setSchedulePage(safePage);
      setSchedulePageInput(String(safePage));
      return;
    }
    const safePage = clampPage(nextPage, Math.max(1, harvests.data?.total_pages ?? 1));
    setPage(safePage);
    setPageInput(String(safePage));
  }

  function submitPageNumber() {
    const result = sanitizePageValue(pageInput, Math.max(1, harvests.data?.total_pages ?? 1));
    if (!result.valid) {
      setPageInput(String(clampPage(page, Math.max(1, harvests.data?.total_pages ?? 1))));
      return;
    }
    const nextPage = result.page;
    if (nextPage !== page) setPage(nextPage);
    setPageInput(String(nextPage));
  }

  function submitSchedulePageNumber() {
    const result = sanitizePageValue(schedulePageInput, schedulePages);
    if (!result.valid) {
      setSchedulePageInput(String(clampPage(schedulePage, schedulePages)));
      return;
    }
    const nextPage = result.page;
    if (nextPage !== schedulePage) setSchedulePage(nextPage);
    setSchedulePageInput(String(nextPage));
  }

  const runs = harvests.data?.results || [];
  const schedules = upcomingSchedules.data?.slice((schedulePage - 1) * SCHEDULE_PAGE_SIZE, schedulePage * SCHEDULE_PAGE_SIZE) || [];
  const totals = runs.reduce((sum, row) => ({
    added: sum.added + row.records_added, updated: sum.updated + row.records_updated, failed: sum.failed + row.records_failed,
  }), { added: 0, updated: 0, failed: 0 });
  const showHarvests = Boolean(harvests.data);

  return (
    <div className="flex-1 bg-[#F7F8FA] font-sans text-sm leading-[22px] text-[#171A1F]">
      <div className="mx-auto flex w-full max-w-[1088px] flex-col gap-5">
        <div className="flex min-h-12 flex-col items-start justify-between gap-5 min-[901px]:flex-row min-[901px]:items-center">
          <h1 className="text-[26px] leading-[34px] font-bold tracking-[-0.3px] min-[541px]:text-[32px] min-[541px]:leading-10">Cosecha y actualización automática</h1>
          <Button href="/admin/revistas?estado=pendiente" variant="quiet" className="w-[220px] shrink-0">Ver revistas pendientes</Button>
        </div>
        <p className="text-sm leading-[22px] text-[#68707C] min-[541px]:text-base min-[541px]:leading-[26px]">Supervisa conectores, ejecuciones y registros modificados.</p>
        <div className="grid grid-cols-2 gap-3 min-[541px]:gap-4 min-[901px]:grid-cols-4">
          <MetricCard value={sources.data ?? "—"} label="Fuentes habilitadas para cosecha" />
          <MetricCard value={showHarvests ? totals.added + totals.updated + totals.failed : "—"} label="Registros contabilizados" />
          <MetricCard value={showHarvests ? totals.updated : "—"} label="Actualizados" />
          <MetricCard value={showHarvests ? totals.failed : "—"} label="Registros fallidos" />
        </div>
        <p className="text-xs text-[#68707C]">Los indicadores de registros corresponden a las ejecuciones de esta página. Fechas en America/Bogota. Ejecuciones actualizadas cada 30 segundos; cada 5 segundos durante ejecuciones activas. Programaciones actualizadas cada 30 segundos.</p>
        {sources.error && <Notice variant="error" live>
          Fuentes habilitadas para cosecha: {sources.error}
          <Button variant="quiet" size="small" disabled={sources.loading} onClick={sources.refresh}>Reintentar fuentes</Button>
        </Notice>}
        <section className="flex min-h-[330px] flex-col gap-3.5 rounded-xl border border-[#DCE0E5] bg-white p-5" aria-labelledby="runs-title" aria-busy={harvests.loading}>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 id="runs-title" className="text-[21px] leading-7 font-semibold min-[541px]:text-2xl min-[541px]:leading-8">Ejecuciones recientes</h2>
            <Button variant="quiet" size="small" disabled={harvests.loading} onClick={harvests.refresh}>Actualizar</Button>
          </div>
          {history && <div className="flex flex-wrap items-center gap-3 rounded-lg bg-[#EEF0F3] px-3 py-2 text-sm">
            <span>Historial del recorrido: <strong>{history.platformName}</strong> · {history.label}{history.filterKey ? "" : " (sin filtros)"}</span>
            <Button variant="quiet" size="small" onClick={() => showHistory(null)}>Ver todas las ejecuciones</Button>
          </div>}
          {harvests.loading && <Notice live>Cargando ejecuciones…</Notice>}
          {harvests.error && <Notice variant="error" live>{harvests.error}</Notice>}
          {showHarvests && <HarvestExecutions rows={runs} onRefresh={refreshHarvests} busy={harvests.loading || Boolean(harvests.error)} countryNames={countryNames} onShowHistory={(row) => {
            const next = harvestHistoryOf(row);
            if (next) showHistory({ ...next, platformName: row.platform_name, label: formatSelectionFilters(row.selection_filters, countryNames) });
          }} />}
          {showHarvests && harvests.data.total_pages > 1 && <div className="flex flex-wrap items-center gap-3">
            <Button variant="quiet" size="small" disabled={harvests.loading || page <= 1} onClick={() => changePage(page - 1)}>Anterior</Button>
            <label className="flex items-center gap-2 text-sm text-[#68707C]">
              <span>Página</span>
              <input
                aria-label="Número de página actual"
                type="number"
                min={1}
                max={harvests.data.total_pages}
                value={pageInput}
                onChange={(event) => setPageInput(event.target.value)}
                onBlur={() => setPageInput(String(clampPage(page, Math.max(1, harvests.data?.total_pages ?? 1))))}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    submitPageNumber();
                  }
                }}
                className="w-14 rounded-md border border-[#DCE0E5] bg-white px-2 py-1 text-center text-sm font-semibold text-[#171A1F] outline-none focus:border-[#A90D27]"
              />
              <span>de {harvests.data.total_pages} · {harvests.data.total_items} ejecuciones</span>
            </label>
            <Button variant="quiet" size="small" disabled={harvests.loading || page >= harvests.data.total_pages} onClick={() => changePage(page + 1)}>Siguiente</Button>
          </div>}
          <Button href="/admin/cosecha/nueva" className="mt-auto w-[220px] self-start">Nueva cosecha</Button>
        </section>
        <section className="flex flex-col gap-3.5 rounded-xl border border-[#DCE0E5] bg-white p-5" aria-labelledby="schedules-title" aria-busy={upcomingSchedules.loading}>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 id="schedules-title" className="text-[21px] leading-7 font-semibold min-[541px]:text-2xl min-[541px]:leading-8">Programaciones</h2>
            <Button size="small" disabled={!canRunDue || harvests.loading || upcomingSchedules.loading || executing || deactivating || editSaving} title={canRunDue ? undefined : "Requiere el permiso «Ejecutar pendientes» de cosecha"} onClick={executeDue}>{executing ? "Ejecutando…" : "Ejecutar programaciones vencidas"}</Button>
          </div>
          <p className="text-xs text-[#68707C]">Se muestran las programaciones únicas que todavía no se han lanzado y las recurrentes para sus próximas ejecuciones.</p>
          <p className="text-xs text-[#68707C]">Guardar una programación no la ejecuta. «Ejecutar programaciones vencidas» despacha ahora todas las programaciones activas cuya fecha ya venció, incluidas las de otras páginas; las futuras conservan su fecha. El despacho encola el trabajo y no significa que la cosecha haya terminado.</p>
          {viewer.data && !canRunDue && <p className="text-xs text-[#68707C]">Tu cuenta no tiene el permiso «Ejecutar pendientes» de cosecha: las programaciones se ejecutarán en su fecha mediante el programador del servidor.</p>}
          {executionFeedback && <Notice variant={executionFeedback.variant} live>{executionFeedback.message}</Notice>}
          {upcomingSchedules.loading && <Notice live>Cargando programaciones…</Notice>}
          {upcomingSchedules.error && <Notice variant="error" live>{upcomingSchedules.error}</Notice>}
          {scheduleFeedback && <Notice variant={scheduleFeedback.variant} live>{scheduleFeedback.message}</Notice>}
          {upcomingSchedules.data && (schedules.length ? <AdminTable caption="Programaciones de cosecha pendientes y recurrentes" columns={columns} rows={schedules} /> : <Notice>No hay programaciones pendientes de cosecha.</Notice>)}
          {editingSchedule && editValues && <form onSubmit={saveSelection} onChange={() => setEditError("")} className="flex flex-col gap-3 rounded-lg border border-[#DCE0E5] p-4" aria-busy={editSaving || platforms.isPending || filterOptions.isPending}>
            <p className="font-semibold">Editar selección de la programación #{editingSchedule.id}</p>
            <p className="text-xs text-[#68707C]">{editingSchedule.platform_names?.join(", ")}. Selección actual: {formatSelectionFilters(editingSchedule.selection_filters, countryNames)}. El cambio aplica a ejecuciones futuras; las ejecuciones existentes (incluidas las pausadas) conservan su selección. Si hay una cosecha activa de esta plataforma, resuélvela primero: solo puede haber una cosecha activa por plataforma.</p>
            {hasRetiredSelectionFilters(editingSchedule.selection_filters) && <Notice variant="error">Esta programación tiene filtros retirados (acceso abierto o pertenencia a DOAJ). Guarda una selección válida o usa el recorrido global para que sus ejecuciones vuelvan a funcionar.</Notice>}
            {(platforms.isPending || filterOptions.isPending) && <Notice live>Cargando filtros disponibles…</Notice>}
            {platforms.isError && <Notice variant="error" live>{platforms.error?.message} <Button variant="quiet" size="small" onClick={() => platforms.refetch()}>Reintentar</Button></Notice>}
            {filterOptions.isError && <Notice variant="error" live>{filterOptions.error?.message} <Button variant="quiet" size="small" onClick={() => filterOptions.refetch()}>Reintentar</Button></Notice>}
            {platforms.data && filterOptions.data && (editProviders.length > 1
              ? <Notice>La programación incluye plataformas de proveedores distintos: solo admite el recorrido global. Para filtrar, crea programaciones separadas por proveedor.</Notice>
              : <HarvestSelectionFields key={editingSchedule.id} idPrefix={`schedule-${editingSchedule.id}-selection`} provider={editProvider} options={filterOptions.data} values={editValues} onChange={setEditValues} disabled={editSaving} />)}
            {editError && <Notice variant="error" live>{editError}</Notice>}
            <div className="flex flex-wrap gap-3">
              {editProvider && editProviders.length === 1 && <Button type="submit" size="small" disabled={editSaving || !platforms.data || !filterOptions.data}>{editSaving ? "Guardando…" : "Guardar selección"}</Button>}
              <Button variant="quiet" size="small" disabled={editSaving || !platforms.data || !filterOptions.data} onClick={() => saveSelection(null, true)}>Usar recorrido global</Button>
              <Button variant="quiet" size="small" disabled={editSaving} onClick={closeEdit}>Cancelar</Button>
            </div>
          </form>}
          {selectedSchedule && <form onSubmit={deactivate} className="flex flex-col gap-3 rounded-lg border border-[#DCE0E5] p-4" aria-busy={deactivating}>
            <p className="font-semibold">Desactivar programación #{selectedSchedule.id}</p>
            <p className="text-xs text-[#68707C]">{selectedSchedule.platform_names?.join(", ")}. Esta programación dejará de generar nuevas ejecuciones. El motivo permite archivarla si tiene registros asociados.</p>
            <FormField id="schedule-deactivation-reason" label="Motivo de desactivación" required autoFocus disabled={deactivating} value={explanation} onChange={(event) => setExplanation(event.target.value)} />
            <div className="flex flex-wrap gap-3">
              <Button type="submit" size="small" disabled={deactivating || executing || upcomingSchedules.loading || !explanation.trim()}>{deactivating ? "Desactivando…" : "Confirmar desactivación"}</Button>
              <Button variant="quiet" size="small" disabled={deactivating} onClick={() => { setSelectedSchedule(null); setExplanation(""); }}>Cancelar</Button>
            </div>
          </form>}
          {upcomingSchedules.data && schedulePages > 1 && <div className="flex flex-wrap items-center gap-3">
            <Button variant="quiet" size="small" disabled={upcomingSchedules.loading || schedulePage <= 1} onClick={() => changePage(schedulePage - 1, true)}>Anterior</Button>
            <label className="flex items-center gap-2 text-sm text-[#68707C]">
              <span>Página</span>
              <input
                aria-label="Número de página de programaciones"
                type="number"
                min={1}
                max={schedulePages}
                value={schedulePageInput}
                onChange={(event) => setSchedulePageInput(event.target.value)}
                onBlur={() => setSchedulePageInput(String(clampPage(schedulePage, schedulePages)))}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    submitSchedulePageNumber();
                  }
                }}
                className="w-14 rounded-md border border-[#DCE0E5] bg-white px-2 py-1 text-center text-sm font-semibold text-[#171A1F] outline-none focus:border-[#A90D27]"
              />
              <span>de {schedulePages} · {scheduleCount} programaciones</span>
            </label>
            <Button variant="quiet" size="small" disabled={upcomingSchedules.loading || schedulePage >= schedulePages} onClick={() => changePage(schedulePage + 1, true)}>Siguiente</Button>
          </div>}
        </section>
      </div>
    </div>
  );
}
