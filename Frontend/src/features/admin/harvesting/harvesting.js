import { notifySessionExpired, shouldSkipSessionExpiredAlert } from "@/shared/utils/sessionExpiration";

export const MAX_HARVEST_LIMIT = 2147483647;
export const IMMEDIATE_HARVEST_ENABLED = false;
export const HARVEST_JOURNALS_PAGE_SIZE = 10;
export const SCHEDULE_HARVESTS_PAGE_SIZE = 10;
export const LINK_ALERTS_PAGE_SIZE = 20;

const FIELD_NAMES = {
  platforms: "Plataformas",
  frequency: "Frecuencia",
  start_date: "Fecha inicial",
  max_quantity: "Límite de registros examinados",
  stop_after_minutes: "Límite de tiempo",
  delete_explanation: "Motivo de desactivación",
  url: "URL",
  non_field_errors: "Validación",
  platform: "Plataforma",
  title: "Título",
  issn: "ISSN",
  reason: "Motivo",
  code: "Código",
  status: "Estado",
  status_code: "Código de estado",
  record: "Registro",
  records: "Registros",
  selection_filters: "Selección de revistas",
  country_code: "País",
  publisher: "Editorial",
  subject: "Tema",
  language: "Idioma",
};

// Harvest workers can return plain text, objects or serialized JSON in error_message.
export function formatHarvestError(value) {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") {
    const message = value.trim();
    try {
      return formatHarvestError(JSON.parse(message));
    } catch {
      return message;
    }
  }
  if (Array.isArray(value)) {
    return value.map(formatHarvestError).filter(Boolean).join("\n");
  }
  if (typeof value === "object") {
    return Object.entries(value).flatMap(([field, detail]) => {
      const message = formatHarvestError(detail);
      if (!message) return [];
      if (["detail", "message", "error", "errors", "error_message"].includes(field)) return [message];
      const label = FIELD_NAMES[field] || field.replace(/([a-z])([A-Z])/g, "$1 $2").replace(/[_-]+/g, " ");
      const heading = label.charAt(0).toUpperCase() + label.slice(1);
      return message.split("\n").map((line) => `${heading}: ${line}`);
    }).join("\n");
  }
  return String(value);
}

export class ApiError extends Error {
  constructor(message, status, payload, retryAfter = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
    this.retryAfter = retryAfter;
  }
}

function errorMessage(payload, status) {
  if (payload?.detail) return String(payload.detail);
  if (payload && typeof payload === "object") {
    const messages = Object.entries(payload).map(([field, value]) =>
      `${FIELD_NAMES[field] || field}: ${Array.isArray(value) ? value.join(" ") : String(value)}`,
    );
    if (messages.length) return messages.join(" · ");
  }
  return `La API respondió con un error (${status}). Intenta nuevamente.`;
}

async function request(path, { method = "GET", body, signal, timeoutMs = 30000, expectJson = true } = {}, mutateAction) {
  // Session cookies belong to Next.js. Reads use its proxy; mutations use the
  // Server Action that forwards the session and obtains the backend CSRF token.
  if (method !== "GET") {
    const { status, data, retryAfter } = await mutateAction(path, method, body);
    if (status < 200 || status >= 300) {
      const message = errorMessage(data, status);
      if (status === 401 && !shouldSkipSessionExpiredAlert(path)) {
        notifySessionExpired(message, { endpoint: path, status });
      }
      throw new ApiError(message, status, data, retryAfter ?? null);
    }
    if (!expectJson) return { status };
    if (data === null) throw new Error("La API devolvió una respuesta que no se pudo leer.");
    return data;
  }
  const timeoutSignal = timeoutMs === null ? null : AbortSignal.timeout(timeoutMs);
  const signals = [signal, timeoutSignal].filter(Boolean);
  try {
    const response = await fetch(path, {
      method,
      headers: body === undefined ? { Accept: "application/json" } : {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      signal: signals.length ? AbortSignal.any(signals) : undefined,
      credentials: "include",
      cache: "no-store",
    });
    if (response.ok && !expectJson) return;
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      const message = errorMessage(payload, response.status);
      if (response.status === 401 && !shouldSkipSessionExpiredAlert(path)) {
        notifySessionExpired(message, { endpoint: path, status: response.status });
      }
      throw new ApiError(message, response.status, payload);
    }
    if (payload === null) throw new Error("La API devolvió una respuesta que no se pudo leer.");
    return payload;
  } catch (error) {
    if (signal?.aborted) throw error;
    if (timeoutSignal?.aborted) throw new Error("La API tardó demasiado en responder. Actualiza la vista antes de repetir una acción para comprobar si se guardó.");
    if (error instanceof TypeError) throw new Error("No se pudo conectar con la API. Revisa tu conexión e intenta nuevamente.");
    throw error;
  }
}

function withQuery(path, query = {}) {
  const params = new URLSearchParams();
  Object.entries(query).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
  });
  const search = params.toString();
  return search ? `${path}?${search}` : path;
}

async function list(path, query = {}, signal) {
  const page = await request(withQuery(path, query), { signal });
  if (!Array.isArray(page.results)) throw new Error("La API no devolvió un listado válido.");
  return page;
}

async function listAll(path, query, signal) {
  const items = [];
  let pageNumber = 1;
  let page;
  do {
    page = await list(path, { ...query, page: pageNumber, page_size: 100 }, signal);
    items.push(...page.results);
    pageNumber += 1;
  } while (page.next && pageNumber <= page.total_pages);
  return items;
}

export function getPlatforms(signal) {
  return listAll("/api/platforms/", { ordering: "name" }, signal);
}

export async function getHarvestSourceCount(signal) {
  const page = await list("/api/platforms/", { is_harvestable: true, page: 1, page_size: 1 }, signal);
  return page.total_items;
}

export function getHarvests(page, signal) {
  return list("/api/harvesting/harvests/", { page, page_size: 10, ordering: "-created_at" }, signal);
}

export function getHarvest(id, signal) {
  return request(`/api/harvesting/harvests/${encodeURIComponent(id)}/`, { signal });
}

export function getHarvestJournals(id, page, signal) {
  return list(`/api/harvesting/harvests/${encodeURIComponent(id)}/journals/`, { page, page_size: HARVEST_JOURNALS_PAGE_SIZE }, signal);
}

/** Una página de ejecuciones de una programación (más recientes primero). */
export function getScheduleHarvests(scheduleId, page, signal) {
  return list("/api/harvesting/harvests/", {
    schedule: scheduleId, ordering: "-created_at", page, page_size: SCHEDULE_HARVESTS_PAGE_SIZE,
  }, signal);
}

export async function getUpcomingSchedules(signal) {
  const [schedules, events] = await Promise.all([
    listAll("/api/harvesting/schedules/", { ordering: "-created_at" }, signal),
    listAll("/api/harvesting/events/", { ordering: "-scheduled_for" }, signal),
  ]);
  const executedOnceSchedules = new Set(events.map((event) => event.schedule));
  return schedules.filter((schedule) => schedule.frequency !== "once" || !executedOnceSchedules.has(schedule.id));
}

/** Una página de verificaciones de enlaces con los filtros del monitor. */
export function getLinkAlertsPage(query = {}, { page = 1, pageSize = 10 } = {}, signal) {
  return list("/api/platforms/link-check-logs/", { ...query, page, page_size: pageSize }, signal);
}

/**
 * Caídas confirmadas entre las filas de una página. `failure_confirmed` es un
 * filtro (no un campo de la fila): para cada fila no disponible se consulta
 * ese filtro acotado a su contexto (plataforma o relación revista–plataforma),
 * que tiene una sola URL vigente.
 */
export async function getConfirmedIdsOnPage(rows, signal) {
  const candidates = rows.filter((row) => row.verification_status === "unavailable");
  const confirmed = await Promise.all(candidates.map(async (row) => {
    const platform = typeof row.platform === "object" ? row.platform?.id : row.platform;
    const relation = typeof row.journal_platform === "object" ? row.journal_platform?.id : row.journal_platform;
    const context = relation == null
      ? { platform, journal_platform__isnull: "true" }
      : { platform, journal_platform: relation };
    const page = await list("/api/platforms/link-check-logs/", {
      ...context, current: "true", failure_confirmed: "true", page: 1, page_size: 1,
    }, signal);
    return page.results.some((item) => item.id === row.id) ? row.id : null;
  }));
  return new Set(confirmed.filter((id) => id !== null));
}

/**
 * Plataformas de "todos los resultados filtrados" (menos las exclusiones).
 * Solo se ejecuta cuando el usuario selecciona todo: recorre las páginas del
 * filtro en el servidor porque la API no ofrece un resumen de selección.
 */
export async function getFilteredPlatformIds(query, excludedIds, signal) {
  const excluded = new Set(excludedIds.map(String));
  const platformIds = new Set();
  let count = 0;
  for (let pageNumber = 1; ; pageNumber += 1) {
    const page = await list("/api/platforms/link-check-logs/", { ...query, page: pageNumber, page_size: 100 }, signal);
    page.results.forEach((row) => {
      if (excluded.has(String(row.id))) return;
      count += 1;
      platformIds.add(String(typeof row.platform === "object" ? row.platform?.id : row.platform));
    });
    if (!page.next || page.results.length === 0) return { count, platformIds: [...platformIds] };
  }
}

/** Revistas vinculadas a una plataforma (incluye `platforms[].relation_id`). */
export function getPlatformJournals(platformId, signal) {
  return listAll("/api/journals/", { platform: platformId }, signal);
}

export function getHarvestSources(platforms) {
  return platforms.filter((platform) => platform.is_harvestable === true);
}

/* ---------- Selección dirigida de revistas (selection_filters) ---------- */

export const SELECTION_TEXT_MAX_LENGTH = 120;
export const EMPTY_SELECTION_VALUES = { country_code: "", title: "", publisher: "", subject: "", language: "" };
const SELECTION_LABELS = { country_code: "País", title: "Título", publisher: "Editorial", subject: "Tema", language: "Idioma" };
const COUNTRY_CODE_PATTERN = /^[A-Za-z]{2}$/;

/** Contrato estático de filtros por proveedor (no consulta APIs externas). */
export function getHarvestFilterOptions(signal) {
  return request("/api/harvesting/schedules/filter-options/", { signal });
}

/**
 * Catálogo Country completo, solo con abreviaturas ISO de dos letras (las
 * únicas válidas para `country_code`). El endpoint lo indica filter-options.
 */
export async function getHarvestCountries(endpoint = "/api/catalog/countries/", signal) {
  // Solo se aceptan rutas relativas de la API: nunca se consulta otro origen.
  const path = typeof endpoint === "string" && /^\/api\/[\w/-]+\/$/.test(endpoint) ? endpoint : "/api/catalog/countries/";
  const countries = await listAll(path, { ordering: "name" }, signal);
  return countries.filter((country) => COUNTRY_CODE_PATTERN.test(String(country.abbreviation ?? "").trim()));
}

/**
 * Proveedor del conector según la configuración de la plataforma (mismo
 * criterio que el backend), nunca según su ID numérico.
 */
export function harvestProvider(platform) {
  if (!platform) return null;
  const name = String(platform.name ?? "").toLowerCase();
  const baseUrl = String(platform.base_api_url ?? "").toLowerCase();
  let path = "";
  try {
    path = baseUrl ? new URL(baseUrl).pathname.replace(/\/+$/, "") : "";
  } catch {
    path = "";
  }
  if (name.includes("doaj") || (baseUrl.includes("doaj.org") && path.endsWith("/oai"))) return "doaj";
  if (name.includes("openalex") || baseUrl.includes("openalex.org")) return "openalex";
  return null;
}

/** Campos admitidos por un proveedor según filter-options. */
export function selectionFieldsFor(provider, options) {
  const fields = provider && options?.[provider];
  return fields && typeof fields === "object" ? Object.keys(fields).filter((field) => field in EMPTY_SELECTION_VALUES) : [];
}

/**
 * selection_filters con solo los campos activos del proveedor. `{}` conserva
 * el recorrido global. La normalización definitiva la hace el backend.
 */
export function buildSelectionFilters(provider, values, options) {
  const selection = {};
  for (const field of selectionFieldsFor(provider, options)) {
    const value = String(values?.[field] ?? "").trim();
    if (!value) continue;
    if (value.length > SELECTION_TEXT_MAX_LENGTH) {
      throw new Error(`${SELECTION_LABELS[field]}: usa como máximo ${SELECTION_TEXT_MAX_LENGTH} caracteres.`);
    }
    if (field === "country_code") {
      if (!COUNTRY_CODE_PATTERN.test(value)) throw new Error("País: selecciona un país del catálogo con código ISO de dos letras.");
      selection.country_code = value.toUpperCase();
    } else {
      selection[field] = value;
    }
  }
  return selection;
}

/** Valores del formulario a partir de una selección guardada. */
export function selectionValuesFrom(filters) {
  const values = { ...EMPTY_SELECTION_VALUES };
  if (filters && typeof filters === "object") {
    Object.keys(values).forEach((field) => {
      if (typeof filters[field] === "string") values[field] = field === "country_code" ? filters[field].toUpperCase() : filters[field];
    });
  }
  return values;
}

/** Texto legible de una selección; `{}` o vacío es el recorrido global. */
export function formatSelectionFilters(filters, countryNames) {
  if (!filters || typeof filters !== "object" || !Object.keys(filters).length) return "Recorrido global";
  return Object.entries(filters).map(([field, value]) => {
    if (!(field in SELECTION_LABELS)) return `${field}: ${String(value)} (filtro retirado)`;
    const shown = field === "country_code" ? countryNames?.get(String(value).toUpperCase()) || String(value).toUpperCase() : String(value);
    return `${SELECTION_LABELS[field]}: ${shown}`;
  }).join(" · ");
}

export function hasRetiredSelectionFilters(filters) {
  return Boolean(filters && typeof filters === "object" && Object.keys(filters).some((field) => !(field in SELECTION_LABELS)));
}

/** Permiso para despachar programaciones vencidas (POST run-due). */
export function canRunDueSchedules(user) {
  return Boolean(user?.is_superadmin || user?.effective_permissions?.harvesting?.schedules?.run_due);
}

/** Permiso para editar programaciones (PATCH). */
export function canUpdateSchedules(user) {
  return Boolean(user?.is_superadmin || user?.effective_permissions?.harvesting?.schedules?.update);
}

function checkPlatformLink(platformId, url, mutateAction) {
  return request(`/api/platforms/${platformId}/check-link/`, {
    method: "POST",
    body: url === undefined ? {} : { url },
  }, mutateAction);
}

// Verifica la URL general y todas las relaciones Journal–Platform vigentes (síncrono, 200).
function checkPlatformLinks(platformId, mutateAction) {
  return request(`/api/platforms/${platformId}/check-links/`, { method: "POST" }, mutateAction);
}

// Encola la verificación global de enlaces vigentes (202: solo confirma el encolado).
function checkAllLinksAsync(mutateAction) {
  return request("/api/platforms/check-links-async/", { method: "POST" }, mutateAction);
}

// Encola reintentos de enlaces vigentes con 1–4 fallos consecutivos (202).
function checkFailedLinksAsync(mutateAction) {
  return request("/api/platforms/check-failed-links/", { method: "POST" }, mutateAction);
}

function createSchedule(payload, mutateAction) {
  return request("/api/harvesting/schedules/", { method: "POST", body: payload }, mutateAction);
}

// PATCH solo con selection_filters: `{}` cambia las ejecuciones futuras al recorrido global.
function updateScheduleSelection(id, selectionFilters, mutateAction) {
  return request(`/api/harvesting/schedules/${id}/`, {
    method: "PATCH",
    body: { selection_filters: selectionFilters },
  }, mutateAction);
}

function deactivateSchedule(id, explanation, mutateAction) {
  return request(`/api/harvesting/schedules/${id}/`, {
    method: "DELETE",
    body: { delete_explanation: explanation.trim() },
    expectJson: false,
  }, mutateAction);
}

export function buildImmediateScheduleUpdate(schedule) {
  if (!schedule?.created_at || !Number.isFinite(Date.parse(schedule.created_at))) {
    throw new Error("La API no devolvió una fecha de creación válida. Actualiza la programación antes de reintentar su inicio.");
  }
  // Use the backend's own timestamp so browser clock drift cannot postpone an immediate run.
  return { start_date: schedule.created_at };
}

function prepareImmediateSchedule(schedule, mutateAction) {
  return request(`/api/harvesting/schedules/${schedule.id}/`, {
    method: "PATCH",
    body: buildImmediateScheduleUpdate(schedule),
  }, mutateAction);
}

function runDueSchedules(mutateAction) {
  // Accept successful responses without a body; execution state comes from GET /harvests/.
  // 202 confirma un despacho; 200 puede indicar que no había nuevas ejecuciones.
  return request("/api/harvesting/schedules/run-due/", { method: "POST", expectJson: false }, mutateAction);
}

/** Mensaje para el resultado de run-due: un despacho no es una cosecha terminada. */
export function runDueFeedback(result) {
  if (result?.status === 202) {
    return { variant: "neutral", message: "Despacho solicitado. Las cosechas se procesan en segundo plano: consulta su estado en las ejecuciones; esto no significa que hayan terminado." };
  }
  return { variant: "neutral", message: "Solicitud procesada. Puede que no hubiera nuevas ejecuciones vencidas; consulta el estado actualizado en las ejecuciones." };
}

/** Mensaje de error de run-due, respetando Retry-After en 425. */
export function runDueErrorMessage(error) {
  if (error?.status === 425) {
    const wait = Number.isFinite(error.retryAfter) && error.retryAfter > 0 ? ` Espera ${error.retryAfter} segundos antes de reintentar.` : " Espera unos segundos antes de reintentar.";
    return `${error.message}${wait}`;
  }
  if (error?.status === 401 || error?.status === 403) {
    return `${error.message} Ejecutar programaciones vencidas requiere el permiso «Ejecutar pendientes» de cosecha.`;
  }
  return error?.message || "No se pudo solicitar la ejecución.";
}

function pauseHarvest(id, mutateAction) {
  return request(`/api/harvesting/harvests/${id}/pause/`, { method: "POST" }, mutateAction);
}

function resumeHarvest(id, mutateAction) {
  return request(`/api/harvesting/harvests/${id}/resume/`, { method: "POST" }, mutateAction);
}

export function createHarvestingApi(mutateAction) {
  return {
    checkPlatformLink: (id, url) => checkPlatformLink(id, url, mutateAction),
    checkPlatformLinks: (id) => checkPlatformLinks(id, mutateAction),
    checkAllLinksAsync: () => checkAllLinksAsync(mutateAction),
    checkFailedLinksAsync: () => checkFailedLinksAsync(mutateAction),
    createSchedule: (payload) => createSchedule(payload, mutateAction),
    updateScheduleSelection: (id, selectionFilters) => updateScheduleSelection(id, selectionFilters, mutateAction),
    deactivateSchedule: (id, explanation) => deactivateSchedule(id, explanation, mutateAction),
    prepareImmediateSchedule: (schedule) => prepareImmediateSchedule(schedule, mutateAction),
    runDueSchedules: () => runDueSchedules(mutateAction),
    pauseHarvest: (id) => pauseHarvest(id, mutateAction),
    resumeHarvest: (id) => resumeHarvest(id, mutateAction),
  };
}

export function buildSchedule({ platformId, limit, minutes, mode, startDate, frequency, selectionFilters = {} }, now = new Date()) {
  const maxQuantity = limit === "" ? null : Number(limit);
  const stopAfterMinutes = minutes === "" ? null : Number(minutes);
  for (const value of [maxQuantity, stopAfterMinutes]) {
    if (value !== null && (!Number.isSafeInteger(value) || value <= 0)) {
      throw new Error("Los límites deben ser números enteros mayores que cero.");
    }
    if (value !== null && value > MAX_HARVEST_LIMIT) {
      throw new Error(`Los límites no pueden superar ${MAX_HARVEST_LIMIT} (máximo permitido por la API).`);
    }
  }
  if (maxQuantity === null && stopAfterMinutes === null) throw new Error("Indica al menos un límite: revistas o tiempo.");
  if (!Number.isSafeInteger(Number(platformId)) || Number(platformId) <= 0) throw new Error("Selecciona una plataforma de origen.");
  const start = mode === "now" ? now : new Date(`${startDate}:00-05:00`);
  if (!Number.isFinite(start.getTime())) throw new Error("Indica una fecha y hora inicial válidas.");
  if (mode !== "now" && start <= now) throw new Error("La fecha inicial debe ser posterior al momento actual (America/Bogota).");
  return {
    platforms: [Number(platformId)],
    frequency: mode === "now" ? "once" : frequency,
    start_date: start.toISOString(),
    max_quantity: maxQuantity,
    stop_after_minutes: stopAfterMinutes,
    selection_filters: selectionFilters,
  };
}

export function nextBogotaDate(now = new Date()) {
  const nextHour = new Date(now.getTime() + 60 * 60 * 1000);
  return new Date(nextHour.getTime() - 5 * 60 * 60 * 1000).toISOString().slice(0, 16);
}

export function formatDate(value) {
  if (!value) return "Sin iniciar";
  return new Intl.DateTimeFormat("es-CO", {
    timeZone: "America/Bogota", day: "2-digit", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  }).format(new Date(value));
}
