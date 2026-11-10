const count = (value) => (Array.isArray(value) ? value.length : 0);
const filled = (value) => (typeof value === "string" ? value.trim().length > 0 : value != null && value !== "");

/**
 * Requisitos de publicación de una plataforma (sección 3.4).
 * Los programas académicos y las áreas no forman parte del checklist.
 *
 * `urlStatus`:
 *  - "available"   → URL registrada y verificada.
 *  - "unavailable" → la última verificación falló.
 *  - otro valor    → URL registrada sin verificar.
 */
export function buildPlatformChecklist({
  publicUrl,
  urlStatus,
  validSintaxis,
  institutions,
  countries,
  languages,
  materialTypes,
  isHarvestable,
  baseApiUrl,
  hasApiKey,
}) {
  const hasUrl = filled(publicUrl);
  const urlVerified = hasUrl && urlStatus === "available";
  let urlHint;
  if (!hasUrl) urlHint = "Registra la URL pública.";
  else if (urlStatus === "unavailable") urlHint = "La última verificación falló. Verifica la URL antes de publicar.";
  else if (urlStatus !== "available") urlHint = "Verifica la URL pública antes de publicar.";

  const items = [
    { key: "public_url", label: "URL pública registrada y verificada", done: urlVerified, hint: urlHint },
    { key: "valid_sintaxis", label: "Sintaxis de búsqueda seleccionada", done: filled(validSintaxis) },
    { key: "institutions", label: "Al menos una institución", done: count(institutions) > 0 },
    { key: "countries", label: "Al menos un país", done: count(countries) > 0 },
    { key: "languages", label: "Al menos un idioma", done: count(languages) > 0 },
    { key: "material_types", label: "Al menos un tipo de material", done: count(materialTypes) > 0 },
  ];
  if (isHarvestable) {
    items.push({ key: "base_api_url", label: "URL base de API (plataforma cosechable)", done: filled(baseApiUrl) });
  }
  if (hasApiKey) {
    items.push({ key: "api_key", label: "URL base de API (API Key configurada)", done: filled(baseApiUrl) });
  }
  return items;
}

/**
 * Requisitos de publicación de una revista (sección 3.5).
 * Las áreas del conocimiento no se validan por separado.
 *
 * `platforms`: [{ platform, published }]
 */
export function buildJournalChecklist({
  issn,
  title,
  editorial,
  publicationDate,
  languages,
  countries,
  materialTypes,
  academicPrograms,
  platforms,
  licenses,
}) {
  const linked = (platforms || []).filter((row) => filled(row?.platform));
  return [
    { key: "issn", label: "ISSN y título", done: filled(issn) && filled(title) },
    { key: "editorial", label: "Editorial", done: filled(editorial) },
    { key: "publication_date", label: "Fecha de publicación", done: filled(publicationDate) },
    { key: "languages", label: "Al menos un idioma", done: count(languages) > 0 },
    { key: "countries", label: "Al menos un país", done: count(countries) > 0 },
    { key: "material_types", label: "Al menos un tipo de material", done: count(materialTypes) > 0 },
    { key: "academic_programs", label: "Al menos un programa académico", done: count(academicPrograms) > 0 },
    {
      key: "platforms",
      label: "Al menos una plataforma asociada y publicada",
      done: linked.some((row) => row.published),
      hint: linked.length > 0 && !linked.some((row) => row.published)
        ? "Ninguna de las plataformas asociadas está publicada."
        : undefined,
    },
    { key: "licenses", label: "Al menos una licencia", done: count(licenses) > 0 },
  ];
}

export const isChecklistComplete = (items) => items.every((item) => item.done);
