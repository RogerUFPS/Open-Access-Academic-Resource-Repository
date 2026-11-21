"use client";

import { useQuery } from "@tanstack/react-query";
import Button from "@/shared/components/Button";
import FormField from "@/shared/components/FormField";
import Notice from "@/shared/components/Notice";
import { queryKeys } from "@/shared/query/queryKeys";
import { getHarvestCountries, SELECTION_TEXT_MAX_LENGTH, selectionFieldsFor } from "@/features/admin/harvesting/harvesting";

const DOAJ_FIELDS = [
  { field: "title", label: "Título contiene", placeholder: "p. ej. revista de salud" },
  { field: "publisher", label: "Editorial contiene", placeholder: "p. ej. Universidad Nacional" },
  { field: "subject", label: "Tema contiene", placeholder: "p. ej. medicine" },
  { field: "language", label: "Código de idioma (exacto)", placeholder: "p. ej. es" },
];

/** Catálogo Country (todas las páginas, en caché) para el filtro de OpenAlex. */
export function useHarvestCountries(options, enabled = true) {
  const endpoint = options?.country_catalog?.endpoint || "/api/catalog/countries/";
  return useQuery({
    queryKey: queryKeys.harvests.countries(endpoint),
    queryFn: ({ signal }) => getHarvestCountries(endpoint, signal),
    enabled: Boolean(options) && enabled,
    staleTime: 10 * 60 * 1000,
  });
}

/**
 * Controles de selección según el proveedor de la plataforma. Solo muestra los
 * campos que el backend declara en filter-options para ese proveedor.
 */
export default function HarvestSelectionFields({ idPrefix, provider, options, values, onChange, disabled = false }) {
  const fields = selectionFieldsFor(provider, options);
  const showCountry = provider === "openalex" && fields.includes("country_code");
  const countries = useHarvestCountries(options, showCountry);
  const setValue = (field, value) => onChange({ ...values, [field]: value });

  if (!provider) {
    return <Notice>Esta plataforma no tiene un conector con filtros de selección. Se cosechará el recorrido global.</Notice>;
  }
  if (!fields.length) {
    return <Notice>El backend no declara filtros para este proveedor. Se cosechará el recorrido global.</Notice>;
  }

  if (showCountry) {
    const loaded = countries.data || [];
    // Conserva un valor guardado aunque ya no exista en el catálogo.
    const missing = values.country_code && !loaded.some((country) => country.abbreviation.trim().toUpperCase() === values.country_code);
    const countryOptions = [
      { value: "", label: countries.isPending ? "Cargando países…" : "Todos los países" },
      ...(missing ? [{ value: values.country_code, label: `${values.country_code} (no está en el catálogo)` }] : []),
      ...loaded.map((country) => ({
        value: country.abbreviation.trim().toUpperCase(),
        label: `${country.emoji_flag ? `${country.emoji_flag} ` : ""}${country.name} (${country.abbreviation.trim().toUpperCase()})`,
      })),
    ];
    return (
      <div className="flex flex-col gap-3">
        <div className="grid grid-cols-1 gap-4 min-[541px]:grid-cols-2">
          <FormField id={`${idPrefix}-country`} label="País de la revista" options={countryOptions} disabled={disabled || countries.isPending} value={values.country_code} onChange={(event) => setValue("country_code", event.target.value)} />
        </div>
        {countries.isError && <Notice variant="error" live>
          No se pudo cargar el catálogo de países. {countries.error?.message}
          <Button variant="quiet" size="small" disabled={countries.isFetching} onClick={() => countries.refetch()}>Reintentar países</Button>
        </Notice>}
        <p className="text-xs text-[#68707C]">«Todos los países» mantiene el recorrido global de OpenAlex. Al elegir un país solo se recorren las revistas de OpenAlex registradas en ese país.</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-1 gap-4 min-[541px]:grid-cols-2">
        {DOAJ_FIELDS.filter(({ field }) => fields.includes(field)).map(({ field, label, placeholder }) => (
          <FormField key={field} id={`${idPrefix}-${field}`} label={label} maxLength={SELECTION_TEXT_MAX_LENGTH} placeholder={placeholder} disabled={disabled} value={values[field]} onChange={(event) => setValue(field, event.target.value)} />
        ))}
      </div>
      <p className="text-xs text-[#68707C]">DOAJ no busca por estos campos en origen: los filtros se aplican a los metadatos Dublin Core de cada revista mientras se recorre OAI-PMH. Título, editorial y tema buscan texto parcial sin distinguir mayúsculas; el idioma debe coincidir exactamente con el código registrado (p. ej. «es», «en»). Los temas no se traducen: «medicina» no coincide con «medicine». Una revista sin el campo no coincide.</p>
    </div>
  );
}
