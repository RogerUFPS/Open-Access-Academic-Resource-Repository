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
 * `platforms`: [{ platform, published, hasUrl, serving }]
 *  - published: la plataforma está publicada.
 *  - hasUrl: la asociación tiene URL de la revista.
 *  - serving: dato del Backend (is_serving): plataforma publicada y ambas URLs
 *    verificadas y disponibles. Solo se conoce en asociaciones guardadas.
 *
 * Publicar exige al menos una asociación que sirva. Como los enlaces se
 * verifican al publicar, el requisito local es tener una plataforma publicada
 * con URL de la revista; el hint informa del estado de verificación.
 */
export function buildJournalChecklist({
  issn,
  title,
  editorial,
  urlImage,
  publicationDate,
  languages,
  countries,
  materialTypes,
  academicPrograms,
  platforms,
  licenses,
}) {
  const linked = (platforms || []).filter((row) => filled(row?.platform));
  const candidates = linked.filter((row) => row.published && row.hasUrl !== false);
  const serving = linked.filter((row) => row.serving).length;
  let platformsHint;
  if (linked.length === 0) platformsHint = "Asocia al menos una plataforma.";
  else if (!linked.some((row) => row.published)) platformsHint = "Ninguna de las plataformas asociadas está publicada.";
  else if (candidates.length === 0) platformsHint = "Registra la URL de la revista en una plataforma publicada.";
  else if (serving > 0) platformsHint = `${serving} asociación(es) con enlaces verificados y disponibles.`;
  else platformsHint = "Los enlaces se verificarán al publicar: al menos uno debe responder.";
  return [
    { key: "issn", label: "ISSN y título", done: filled(issn) && filled(title) },
    { key: "editorial", label: "Editorial", done: filled(editorial) },
    { key: "url_image", label: "Imagen de la revista", done: filled(urlImage) },
    { key: "publication_date", label: "Fecha de publicación", done: filled(publicationDate) },
    { key: "languages", label: "Al menos un idioma", done: count(languages) > 0 },
    { key: "countries", label: "Al menos un país", done: count(countries) > 0 },
    { key: "material_types", label: "Al menos un tipo de material", done: count(materialTypes) > 0 },
    { key: "academic_programs", label: "Al menos un programa académico", done: count(academicPrograms) > 0 },
    {
      key: "platforms",
      label: "Al menos una plataforma publicada con enlaces disponibles",
      done: candidates.length > 0,
      hint: platformsHint,
    },
    { key: "licenses", label: "Al menos una licencia", done: count(licenses) > 0 },
  ];
}

export const isChecklistComplete = (items) => items.every((item) => item.done);
