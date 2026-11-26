"use client";

import { useRef, useState } from "react";
import Button from "@/shared/components/Button";
import FormField from "@/shared/components/FormField";
import Notice from "@/shared/components/Notice";
import { buildSchedule, buildSelectionFilters, formatDate, getHarvestProvider, getHarvestSources, IMMEDIATE_HARVEST_ENABLED, MAX_HARVEST_LIMIT, nextBogotaDate } from "@/features/admin/harvesting/harvesting";
import { queryStatus, useAllPlatforms, useFilterOptions } from "@/features/admin/harvesting/queries";
import HarvestFilters, { getProviderFilterFields } from "./HarvestFilters";
import HarvestSourceOption from "./HarvestSourceOption";
import HarvestScheduleRuns from "./HarvestScheduleRuns";
import { useHarvestingApi } from "./HarvestingProvider";

const frequencies = [
  { value: "once", label: "Única vez" },
  { value: "daily", label: "Diaria" },
  { value: "weekly", label: "Semanal" },
  { value: "monthly", label: "Mensual" },
];
const panelClasses = "flex flex-col gap-3 rounded-xl border border-[#DCE0E5] bg-white p-5";
const headingClasses = "text-[21px] leading-7 font-semibold min-[541px]:text-2xl min-[541px]:leading-8";
const radioClasses = "size-[13px] accent-[#A90D27] focus-visible:outline-2 focus-visible:outline-offset-3 focus-visible:outline-primary";

export default function HarvestForm() {
  const { createSchedule, prepareImmediateSchedule } = useHarvestingApi();
  const [chosenPlatformId, setChosenPlatformId] = useState("");
  const [limit, setLimit] = useState("200");
  const [minutes, setMinutes] = useState("30");
  const [mode, setMode] = useState("scheduled");
  const [startDate, setStartDate] = useState("");
  const [frequency, setFrequency] = useState("weekly");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [created, setCreated] = useState(null);
  const [executionFeedback, setExecutionFeedback] = useState(null);
  const [canRetryPreparation, setCanRetryPreparation] = useState(false);
  const [runsRevision, setRunsRevision] = useState(0);
  const [filterValues, setFilterValues] = useState({});
  const requestPending = useRef(false);

  // Plataformas y filtros vienen de la caché compartida del panel; se revalidan en segundo plano.
  const platformsQuery = useAllPlatforms();
  const filterOptionsQuery = useFilterOptions();
  const { loading, error: sourceError } = queryStatus(platformsQuery, "No se pudieron cargar las plataformas.");
  // Sin filter-options aún se puede cosechar sin filtros adicionales.
  const { loading: filterOptionsLoading, error: filterOptionsError } = queryStatus(filterOptionsQuery, "No se pudieron cargar los filtros disponibles.");
  const filterOptions = filterOptionsQuery.data || null;
  const sources = platformsQuery.data ? getHarvestSources(platformsQuery.data) : [];
  const platformId = sources.some((item) => String(item.id) === chosenPlatformId) ? chosenPlatformId : String(sources[0]?.id || "");
  // La fecha sugerida se calcula en el cliente (no en el render del servidor).
  if (!startDate && platformsQuery.data) setStartDate(nextBogotaDate());

  function retryLoad() {
    if (platformsQuery.isError) platformsQuery.refetch();
    if (filterOptionsQuery.isError) filterOptionsQuery.refetch();
  }

  async function prepare(schedule) {
    if (!IMMEDIATE_HARVEST_ENABLED) return;
    setExecutionFeedback(null);
    setCanRetryPreparation(false);
    try {
      setCreated(await prepareImmediateSchedule(schedule));
      setExecutionFeedback({ variant: "neutral", message: "Programación lista. Pulsa Actualizar ejecuciones para ejecutar las programaciones vencidas y consultar su estado." });
    } catch (error) {
      setExecutionFeedback({ variant: "error", message: `La programación quedó guardada, pero no se pudo ajustar su fecha de inicio. ${error.message}` });
      setCanRetryPreparation(true);
    } finally {
      setRunsRevision((current) => current + 1);
    }
  }

  async function retryPreparation() {
    if (requestPending.current || !created) return;
    requestPending.current = true;
    setSaving(true);
    try {
      await prepare(created);
    } finally {
      requestPending.current = false;
      setSaving(false);
    }
  }

  async function submit(event) {
    event.preventDefault();
    if (requestPending.current || created || loading || sourceError) return;
    if (mode === "now" && !IMMEDIATE_HARVEST_ENABLED) {
      setError("La ejecución inmediata estará disponible en un próximo sprint. Selecciona Programar cosecha.");
      return;
    }
    setError("");
    try {
      const selectionFilters = buildSelectionFilters(filterValues, filterFields);
      const payload = buildSchedule({ platformId, limit, minutes, mode, startDate, frequency, selectionFilters });
      requestPending.current = true;
      setSaving(true);
      const schedule = await createSchedule(payload);
      setCreated(schedule);
      if (mode === "now") await prepare(schedule);
    } catch (error) {
      setError(error.message);
    } finally {
      requestPending.current = false;
      setSaving(false);
    }
  }

  const selectedSource = sources.find((item) => String(item.id) === platformId);
  const provider = getHarvestProvider(selectedSource);
  const filterFields = getProviderFilterFields(filterOptions, provider);

  function selectPlatform(id) {
    // Cada proveedor tiene sus propios filtros: al cambiar de fuente se limpia la selección.
    if (getHarvestProvider(sources.find((item) => String(item.id) === id)) !== provider) setFilterValues({});
    setChosenPlatformId(id);
  }

  return (
    <div className="flex-1 bg-[#F7F8FA] font-sans text-sm leading-[22px] text-[#171A1F]">
      <div className="mx-auto flex w-full max-w-[1088px] flex-col gap-5">
        <h1 className="text-[26px] leading-[34px] font-bold tracking-[-0.3px] min-[541px]:text-[32px] min-[541px]:leading-10">Nueva cosecha de revistas</h1>
        <p className="text-sm leading-[22px] text-[#68707C] min-[541px]:text-base min-[541px]:leading-[26px]">Selecciona una base de datos de origen y configura su cosecha. Podrás consultar los resultados en las ejecuciones.</p>
        <form className="flex flex-col gap-5" onSubmit={submit} onChange={() => setError("")} aria-busy={saving}>
          <fieldset disabled={saving || Boolean(created) || loading || Boolean(sourceError)} className="flex min-w-0 flex-col gap-5">
            <section className={panelClasses} aria-labelledby="source-title">
              <h2 id="source-title" className={headingClasses}>Base de datos a cosechar</h2>
              {loading && <Notice live>Cargando plataformas…</Notice>}
              {sourceError && <Notice variant="error" live>{sourceError}</Notice>}
              {!loading && !sourceError && !sources.length && <Notice>No hay bases de datos habilitadas para cosecha.</Notice>}
              <div className="grid grid-cols-1 gap-3 min-[541px]:grid-cols-2 min-[901px]:grid-cols-4" role="radiogroup" aria-labelledby="source-title">
                {sources.map((item) => <HarvestSourceOption key={item.id} source={item.name} value={String(item.id)} description="Habilitada para cosecha" checked={platformId === String(item.id)} onChange={() => selectPlatform(String(item.id))} />)}
              </div>
              {sources.length > 0 && <p className="text-xs text-[#68707C]">Se muestran únicamente bases de datos habilitadas para cosecha.</p>}
            </section>
            {selectedSource && (filterFields.length > 0 || filterOptionsError || filterOptionsLoading) && <section className={panelClasses} aria-labelledby="filters-title">
              <h2 id="filters-title" className={headingClasses}>Filtros de selección <span className="text-sm font-normal text-[#68707C]">(opcional)</span></h2>
              {filterOptionsLoading && <Notice live>Cargando filtros disponibles…</Notice>}
              {filterOptionsError && <Notice variant="error" live>No se pudieron cargar los filtros disponibles: {filterOptionsError} Puedes programar la cosecha sin filtros o reintentar la carga.</Notice>}
              <HarvestFilters idPrefix="harvest-filter" filterOptions={filterOptions} provider={provider} values={filterValues} onChange={(values) => { setFilterValues(values); setError(""); }} />
              {filterFields.length > 0 && <p className="text-xs text-[#68707C]">
                {provider === "doaj" ? "Filtros de DOAJ." : "Filtros de OpenAlex."} Deja un campo vacío para no filtrar por él. Si eliges varios, cada revista debe cumplirlos todos. Para usar filtros de otro proveedor, crea una programación aparte.
              </p>}
            </section>}
            <section className={panelClasses} aria-labelledby="limits-title">
              <h2 id="limits-title" className={headingClasses}>Límites de ejecución</h2>
              <div className="grid grid-cols-1 gap-4 min-[541px]:grid-cols-2">
                <FormField id="harvest-limit" label="Límite máximo de revistas" type="number" min="1" max={MAX_HARVEST_LIMIT} step="1" value={limit} onChange={(event) => setLimit(event.target.value)} suffix="revistas" />
                <FormField id="harvest-minutes" label="Límite de tiempo" type="number" min="1" max={MAX_HARVEST_LIMIT} step="1" value={minutes} onChange={(event) => setMinutes(event.target.value)} suffix="minutos" />
              </div>
              <p className="text-xs text-[#68707C]">Indica al menos un límite. Si completas ambos, la cosecha se detiene al alcanzar el primero. El límite de revistas cuenta los registros examinados, no garantiza esa cantidad de revistas nuevas.</p>
            </section>
            <section className={panelClasses} aria-labelledby="schedule-title">
              <h2 id="schedule-title" className={headingClasses}>Programación</h2>
              <div className="flex flex-wrap gap-[18px]" role="radiogroup" aria-labelledby="schedule-title">
                <label title={IMMEDIATE_HARVEST_ENABLED ? undefined : "Disponible en un próximo sprint"} className={`flex items-center gap-[5px] ${IMMEDIATE_HARVEST_ENABLED ? "cursor-pointer" : "cursor-not-allowed opacity-60"} ${mode === "now" ? "text-[#A90D27]" : "text-[#68707C]"}`}><input className={radioClasses} type="radio" name="mode" value="now" disabled={!IMMEDIATE_HARVEST_ENABLED} checked={mode === "now"} onChange={() => setMode("now")} />Ejecutar una vez ahora</label>
                <label className={`flex cursor-pointer items-center gap-[5px] ${mode === "scheduled" ? "text-[#A90D27]" : "text-[#68707C]"}`}><input className={radioClasses} type="radio" name="mode" value="scheduled" checked={mode === "scheduled"} onChange={() => setMode("scheduled")} />Programar cosecha</label>
              </div>
              <div className="grid grid-cols-1 gap-4 min-[901px]:grid-cols-3">
                <FormField id="harvest-start" label="Fecha y hora inicial" type="datetime-local" required={mode === "scheduled"} disabled={mode === "now"} value={startDate} onChange={(event) => setStartDate(event.target.value)} />
                <FormField id="harvest-frequency" label="Frecuencia" options={frequencies} disabled={mode === "now"} value={frequency} onChange={(event) => setFrequency(event.target.value)} />
                <FormField id="harvest-timezone" label="Zona horaria" value="America/Bogota" readOnly />
              </div>
            </section>
          </fieldset>
          {(sourceError || filterOptionsError) && !created && <Button variant="quiet" className="self-start" disabled={loading || filterOptionsLoading || saving} onClick={retryLoad}>Reintentar carga</Button>}
          <div className="flex flex-wrap items-center gap-3">
            <Button href="/admin/cosecha" variant="quiet" className="w-full min-w-[140px] min-[541px]:w-auto">{created ? "Ver cosechas" : "Cancelar"}</Button>
            {!created && <Button type="submit" disabled={loading || saving || Boolean(sourceError) || !selectedSource || (mode === "now" && !IMMEDIATE_HARVEST_ENABLED)} className="w-full min-w-[210px] min-[541px]:w-auto">{saving ? "Guardando…" : mode === "scheduled" ? "Programar cosecha" : "Guardar cosecha"}</Button>}
            {created && canRetryPreparation && <Button disabled={saving || !IMMEDIATE_HARVEST_ENABLED} onClick={retryPreparation}>{saving ? "Preparando…" : "Reintentar preparación"}</Button>}
            {created && <Button disabled={saving} onClick={() => { setCreated(null); setExecutionFeedback(null); setCanRetryPreparation(false); setStartDate(nextBogotaDate()); }} className="w-full min-[541px]:w-auto">Crear otra cosecha</Button>}
          </div>
          {error && <Notice variant="error" live>{error}</Notice>}
          {created && <Notice variant="success" live>Programación #{created.id} guardada. Inicio: {formatDate(created.start_date)} (America/Bogota). {created.frequency === "once" ? "Consulta abajo el estado de la ejecución." : "El backend ejecutará la cosecha en la fecha programada."} Guardar la programación no significa que la cosecha haya terminado.</Notice>}
          {created && saving && <Notice live>Preparando la programación…</Notice>}
          {executionFeedback && <Notice variant={executionFeedback.variant} live>{executionFeedback.message}</Notice>}
        </form>
        {created?.frequency === "once" && <HarvestScheduleRuns key={created.id} scheduleId={created.id} revision={runsRevision} busy={saving || canRetryPreparation} />}
      </div>
    </div>
  );
}
