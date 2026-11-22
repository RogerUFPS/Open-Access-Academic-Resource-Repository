"use client";

import FormField from "@/shared/components/FormField";
import { TEXT_FILTER_MAX_LENGTH } from "@/features/admin/harvesting/harvesting";
import CatalogSelect from "./CatalogSelect";

const FILTER_LABELS = {
  country: "País",
  publisher: "Editorial",
  language: "Idioma",
  title: "Título contiene",
  subject: "Tema contiene",
};
const FIELD_ORDER = ["country", "publisher", "language", "title", "subject"];

/** Campos de filtro que `filter-options` publica para un proveedor, en orden de presentación. */
export function getProviderFilterFields(filterOptions, provider) {
  const fields = filterOptions?.[provider];
  if (!fields || typeof fields !== "object") return [];
  return Object.keys(fields).sort((a, b) => {
    const left = FIELD_ORDER.indexOf(a);
    const right = FIELD_ORDER.indexOf(b);
    return (left === -1 ? FIELD_ORDER.length : left) - (right === -1 ? FIELD_ORDER.length : right);
  });
}

export default function HarvestFilters({ idPrefix = "harvest-filter", filterOptions, provider, values, onChange, disabled = false }) {
  const definitions = filterOptions?.[provider] || {};
  const fields = getProviderFilterFields(filterOptions, provider);
  if (!fields.length) return null;
  const update = (field, value) => onChange({ ...values, [field]: value });

  return (
    <div className="grid grid-cols-1 gap-4 min-[541px]:grid-cols-2 min-[901px]:grid-cols-3">
      {fields.map((field) => {
        const definition = definitions[field];
        const label = FILTER_LABELS[field] || field;
        if (definition?.catalog_endpoint) {
          return (
            <CatalogSelect
              key={field}
              id={`${idPrefix}-${field}`}
              label={label}
              endpoint={definition.catalog_endpoint}
              labelField={definition.label_field || "name"}
              valueField={definition.value_field || "id"}
              value={values[field] ?? ""}
              onChange={(value) => update(field, value)}
              disabled={disabled}
            />
          );
        }
        return (
          <FormField
            key={field}
            id={`${idPrefix}-${field}`}
            label={label}
            maxLength={definition?.max_length || TEXT_FILTER_MAX_LENGTH}
            placeholder="Cualquiera"
            disabled={disabled}
            value={values[field] ?? ""}
            onChange={(event) => update(field, event.target.value)}
          />
        );
      })}
    </div>
  );
}
