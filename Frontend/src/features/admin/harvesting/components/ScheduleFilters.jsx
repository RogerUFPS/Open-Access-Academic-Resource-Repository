"use client";

import { useRef, useState } from "react";
import Button from "@/shared/components/Button";
import Notice from "@/shared/components/Notice";
import { buildSelectionFilters, getHarvestProvider } from "@/features/admin/harvesting/harvesting";
import { queryStatus, useAllPlatforms, useCatalogEntry, useFilterOptions } from "@/features/admin/harvesting/queries";
import HarvestFilters, { getProviderFilterFields } from "./HarvestFilters";
import { useHarvestingApi } from "./HarvestingProvider";

const SUMMARY_LABELS = { country: "País", publisher: "Editorial", language: "Idioma", title: "Título", subject: "Tema" };
const CATALOG_ENDPOINTS = { country: "/api/catalog/countries/", publisher: "/api/catalog/editorials/", language: "/api/catalog/languages/" };

function CatalogName({ id, endpoint }) {
  const { data, isError } = useCatalogEntry(endpoint, id);
  return data?.name || (isError ? `#${id}` : "…");
}

/** Texto compacto de `selection_filters` con los nombres del catálogo. */
export function ScheduleFiltersSummary({ filters, filterOptions }) {
  const entries = Object.entries(filters || {});
  if (!entries.length) return <span className="text-[#68707C]">Sin filtros</span>;
  const endpointFor = (field) => filterOptions?.openalex?.[field]?.catalog_endpoint || filterOptions?.doaj?.[field]?.catalog_endpoint || CATALOG_ENDPOINTS[field];
  return (
    <ul className="flex flex-col gap-0.5">
      {entries.map(([field, value]) => (
        <li key={field}>
          <span className="text-[#68707C]">{SUMMARY_LABELS[field] || field}:</span>{" "}
          {typeof value === "number" && endpointFor(field) ? <CatalogName id={value} endpoint={endpointFor(field)} /> : `“${value}”`}
        </li>
      ))}
    </ul>
  );
}

/** Edita `selection_filters` de una programación: el objeto enviado reemplaza la selección completa. */
export function ScheduleFiltersEditor({ schedule, onSaved, onCancel }) {
  const { updateScheduleFilters } = useHarvestingApi();
  const filterOptions = useFilterOptions();
  const platforms = useAllPlatforms();
  const [values, setValues] = useState(() => ({ ...(schedule.selection_filters || {}) }));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const pending = useRef(false);

  const scheduledPlatforms = (platforms.data || []).filter((platform) => schedule.platforms.includes(platform.id));
  const providers = [...new Set(scheduledPlatforms.map(getHarvestProvider))];
  const provider = providers.length === 1 ? providers[0] : null;
  const fields = getProviderFilterFields(filterOptions.data, provider);
  const filterStatus = queryStatus(filterOptions, "No se pudieron cargar los filtros disponibles.");
  const platformStatus = queryStatus(platforms, "No se pudieron cargar las plataformas.");
  const loading = filterStatus.loading || platformStatus.loading;
  const loadError = filterStatus.error || platformStatus.error;

  async function submit(event) {
    event.preventDefault();
    if (pending.current || loading || !provider) return;
    setError("");
    try {
      const selectionFilters = buildSelectionFilters(values, fields);
      pending.current = true;
      setSaving(true);
      const updated = await updateScheduleFilters(schedule.id, selectionFilters);
      onSaved(updated);
    } catch (submitError) {
      setError(submitError.message);
    } finally {
      pending.current = false;
      setSaving(false);
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-3 rounded-lg border border-[#DCE0E5] p-4" aria-busy={saving || loading}>
      <p className="font-semibold">Editar filtros de la programación #{schedule.id}</p>
      <p className="text-xs text-[#68707C]">{schedule.platform_names?.join(", ")}. Los cambios aplican a las próximas ejecuciones; las cosechas ya creadas conservan su selección. Deja un campo vacío para no filtrar por él.</p>
      {loading && <Notice live>Cargando filtros disponibles…</Notice>}
      {loadError && <Notice variant="error" live>{loadError}</Notice>}
      {!loading && !loadError && !provider && <Notice>Esta programación combina proveedores distintos; sus filtros no se pueden editar aquí.</Notice>}
      {!loading && !loadError && provider && (fields.length
        ? <HarvestFilters idPrefix={`schedule-${schedule.id}-filter`} filterOptions={filterOptions.data} provider={provider} values={values} onChange={(next) => { setValues(next); setError(""); }} disabled={saving} />
        : <Notice>Este proveedor no admite filtros adicionales.</Notice>)}
      {error && <Notice variant="error" live>{error}</Notice>}
      <div className="flex flex-wrap gap-3">
        <Button type="submit" size="small" disabled={saving || loading || Boolean(loadError) || !provider || !fields.length}>{saving ? "Guardando…" : "Guardar filtros"}</Button>
        <Button variant="quiet" size="small" disabled={saving || loading || !Object.values(values).some((value) => value !== "" && value != null)} onClick={() => setValues({})}>Quitar todos</Button>
        <Button variant="quiet" size="small" disabled={saving} onClick={onCancel}>Cancelar</Button>
      </div>
    </form>
  );
}
