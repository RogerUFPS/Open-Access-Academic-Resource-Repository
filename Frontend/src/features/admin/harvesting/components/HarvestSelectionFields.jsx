"use client";

import { useEffect, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import Button from "@/shared/components/Button";
import FormField from "@/shared/components/FormField";
import Notice from "@/shared/components/Notice";
import { queryKeys } from "@/shared/query/queryKeys";
import { catalogLabel, getHarvestCountries, getHarvestLanguages, searchHarvestEditorials, SELECTION_TEXT_MAX_LENGTH, selectionFieldsFor } from "@/features/admin/harvesting/harvesting";

const DOAJ_TEXT_FIELDS = {
  title: { label: "Título contiene", placeholder: "p. ej. revista de salud" },
  subject: { label: "Tema contiene", placeholder: "p. ej. medicine" },
};

/** Valor que se estabiliza tras `delay` ms sin cambios (búsqueda remota). */
function useDebouncedValue(value, delay = 300) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

/**
 * Editorial: texto libre (el filtro es «contiene») con sugerencias del
 * catálogo Editorial buscadas en el servidor mientras se escribe.
 */
function PublisherField({ id, value, onChange, disabled }) {
  const term = useDebouncedValue(value.trim());
  const editorials = useQuery({
    queryKey: queryKeys.harvests.editorials(term),
    queryFn: ({ signal }) => searchHarvestEditorials(term, signal),
    placeholderData: keepPreviousData,
    staleTime: 60 * 1000,
  });
  const listId = `${id}-options`;
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <FormField id={id} label="Editorial contiene" list={listId} autoComplete="off" maxLength={SELECTION_TEXT_MAX_LENGTH} placeholder="Escribe para buscar en el catálogo" disabled={disabled} value={value} onChange={(event) => onChange(event.target.value)} />
      <datalist id={listId}>
        {(editorials.data || []).map((editorial) => <option key={editorial.id} value={editorial.name.trim()} />)}
      </datalist>
      {editorials.isError
        ? <span className="text-xs text-[#820A1F]">No se pudieron cargar sugerencias de editoriales; puedes escribir el nombre igualmente.</span>
        : <span className="text-xs text-[#68707C]">Sugerencias del catálogo de editoriales. También se admite parte del nombre.</span>}
    </div>
  );
}

/** Idioma: catálogo Language; su abreviatura es el código que DOAJ registra en dc:language. */
function LanguageField({ id, value, onChange, disabled }) {
  const languages = useQuery({
    queryKey: queryKeys.harvests.languages,
    queryFn: ({ signal }) => getHarvestLanguages(signal),
    staleTime: 10 * 60 * 1000,
  });
  if (languages.isError) {
    return (
      <div className="flex min-w-0 flex-col gap-1">
        <FormField id={id} label="Código de idioma (exacto)" maxLength={SELECTION_TEXT_MAX_LENGTH} placeholder="p. ej. es" disabled={disabled} value={value} onChange={(event) => onChange(event.target.value)} />
        <span className="text-xs text-[#820A1F]">No se pudo cargar el catálogo de idiomas; escribe el código. <button type="button" className="underline" onClick={() => languages.refetch()}>Reintentar</button></span>
      </div>
    );
  }
  const loaded = languages.data || [];
  const missing = value && !loaded.some((language) => language.abbreviation.trim().toLowerCase() === value.toLowerCase());
  const options = [
    { value: "", label: languages.isPending ? "Cargando idiomas…" : "Todos los idiomas" },
    ...(missing ? [{ value, label: `${value} (no está en el catálogo)` }] : []),
    ...loaded.map((language) => {
      const code = language.abbreviation.trim().toLowerCase();
      return { value: code, label: `${catalogLabel(language.name)} (${code})` };
    }),
  ];
  return <FormField id={id} label="Idioma" options={options} disabled={disabled || languages.isPending} value={value.toLowerCase()} onChange={(event) => onChange(event.target.value)} />;
}

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
        label: `${country.emoji_flag ? `${country.emoji_flag} ` : ""}${catalogLabel(country.name)} (${country.abbreviation.trim().toUpperCase()})`,
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
      <div className="grid grid-cols-1 items-start gap-4 min-[541px]:grid-cols-2">
        {fields.map((field) => {
          const id = `${idPrefix}-${field}`;
          if (field === "publisher") return <PublisherField key={field} id={id} value={values.publisher} onChange={(value) => setValue("publisher", value)} disabled={disabled} />;
          if (field === "language") return <LanguageField key={field} id={id} value={values.language} onChange={(value) => setValue("language", value)} disabled={disabled} />;
          const config = DOAJ_TEXT_FIELDS[field];
          if (!config) return null;
          return <FormField key={field} id={id} label={config.label} maxLength={SELECTION_TEXT_MAX_LENGTH} placeholder={config.placeholder} disabled={disabled} value={values[field]} onChange={(event) => setValue(field, event.target.value)} />;
        })}
      </div>
      <p className="text-xs text-[#68707C]">DOAJ no busca por estos campos en origen: los filtros se aplican a los metadatos Dublin Core de cada revista mientras se recorre OAI-PMH. Título, editorial y tema buscan texto parcial sin distinguir mayúsculas; el idioma debe coincidir exactamente con el código registrado. Los temas están en inglés y no se traducen: «medicina» no coincide con «medicine». Una revista sin el campo no coincide.</p>
    </div>
  );
}
