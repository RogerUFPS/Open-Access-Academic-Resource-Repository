import { extractApiErrorText } from "@/shared/services/apiClient";

export const FIELD_LABELS = {
  name: "Nombre",
  title: "Título",
  issn: "ISSN",
  public_url: "URL pública",
  url: "URL pública",
  url_image: "Imagen",
  is_harvestable: "Cosechable vía API",
  base_api_url: "URL base de API",
  api_key: "API Key",
  start_period: "Fecha de registro",
  finish_period: "Fecha de obsolescencia",
  valid_sintaxis: "Sintaxis de búsqueda",
  institutions: "Instituciones",
  countries: "Países",
  languages: "Idiomas",
  material_types: "Tipos de material",
  academic_programs: "Programas académicos",
  platforms: "Plataformas",
  licenses: "Licencias",
  editorial: "Editorial",
  publication_date: "Fecha de publicación",
  has_apc: "APC",
  status: "Estado",
  detail: "Error",
};

// Las áreas del conocimiento nunca se envían: no se muestran sus errores.
const IGNORED_KEYS = new Set(["knowledge_areas", "message", "error", "existing_id"]);

// Claves del backend que se muestran sobre otro control del formulario.
const FIELD_ALIASES = { url: "public_url" };

/**
 * Convierte la respuesta de error del backend en { campo: mensaje }.
 * Conserva `detail` para el resumen superior.
 */
export function toFieldErrors(data) {
  if (!data || typeof data !== "object" || Array.isArray(data)) return {};
  const result = {};
  Object.entries(data).forEach(([key, value]) => {
    if (IGNORED_KEYS.has(key)) return;
    const message = extractApiErrorText(value);
    if (!message) return;
    const field = FIELD_ALIASES[key] || key;
    result[field] = result[field] ? `${result[field]} ${message}` : message;
  });
  return result;
}

export function errorSummary(fieldErrors = {}) {
  return Object.entries(fieldErrors)
    .filter(([key, message]) => message && !IGNORED_KEYS.has(key))
    .map(([key, message]) => ({
      field: key,
      label: FIELD_LABELS[key] || key,
      message: Array.isArray(message) ? message.join(" ") : String(message),
    }));
}
