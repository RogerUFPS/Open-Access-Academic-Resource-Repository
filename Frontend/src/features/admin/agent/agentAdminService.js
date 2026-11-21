import {
  ACCOUNT_FORBIDDEN_EVENT,
  apiClient,
  extractApiErrorText,
  RECENT_AUTH_REQUIRED_CODE,
  RECENT_AUTH_REQUIRED_EVENT,
} from "@/shared/services/apiClient";
import { readPage } from "@/shared/utils/pagination";
import { notifySessionExpired, shouldSkipSessionExpiredAlert } from "@/shared/utils/sessionExpiration";

export const AGENT_MODELS_POLL_ACTIVE_MS = 4000;
export const AGENT_MODELS_POLL_IDLE_MS = 15000;
export const CONVERSATIONS_PAGE_SIZE = 20;
export const CONVERSATION_TURNS_PAGE_SIZE = 20;
export const DEFAULT_ANALYTICS_LIMIT = 20;
export const MIN_ANALYTICS_LIMIT = 1;
export const MAX_ANALYTICS_LIMIT = 100;

export function hasAgentPermission(user, resource, action) {
  return Boolean(user?.is_superadmin || user?.effective_permissions?.agent?.[resource]?.[action]);
}

export function isModelTransitioning(modelsState) {
  if (!modelsState) return false;
  return Boolean(
    modelsState.pending_model ||
      modelsState.phase === "draining" ||
      modelsState.phase === "switching" ||
      modelsState.phase === "error",
  );
}

/**
 * Un modelo destino sólo se considera efectivamente activo cuando
 * active_model coincide, pending_model es null y phase es "ready".
 */
export function isTargetActivated(modelsState, targetModel) {
  return Boolean(
    targetModel &&
      modelsState?.active_model === targetModel &&
      modelsState?.pending_model === null &&
      modelsState?.phase === "ready",
  );
}

export function normalizeAvailableModels(modelsState) {
  const raw = modelsState?.available_models;
  if (Array.isArray(raw)) {
    return raw
      .filter((item) => item && typeof item === "object" && item.name)
      .map((item) => ({
        name: String(item.name),
        configured: Boolean(item.configured),
      }));
  }
  if (raw && typeof raw === "object") {
    return Object.entries(raw).map(([name, value]) => ({
      name,
      configured: typeof value === "boolean" ? value : Boolean(value?.configured),
    }));
  }
  return [];
}

function buildMutationError(path, { status, data, retryAfter }) {
  const isBrowser = typeof window !== "undefined";
  const recentAuthRequired = status === 403 && data?.code === RECENT_AUTH_REQUIRED_CODE;
  if (recentAuthRequired && isBrowser) {
    window.dispatchEvent(new CustomEvent(RECENT_AUTH_REQUIRED_EVENT, { detail: { endpoint: path } }));
  } else if (status === 403 && isBrowser) {
    window.dispatchEvent(new CustomEvent(ACCOUNT_FORBIDDEN_EVENT, { detail: { endpoint: path } }));
  }

  let message = extractApiErrorText(data) || `Error ${status} al ejecutar la acción del módulo de IA.`;
  if (status === 409 && !extractApiErrorText(data)) {
    message = "La operación no puede completarse en el estado actual del controlador de modelos.";
  }

  const authExpired = status === 401 && !shouldSkipSessionExpiredAlert(path);
  if (authExpired) {
    notifySessionExpired(message, { endpoint: path, status });
  }

  const error = new Error(message);
  error.status = status;
  error.data = data;
  error.code = typeof data?.code === "string" ? data.code : null;
  error.authExpired = authExpired;
  error.recentAuthRequired = recentAuthRequired;
  if (retryAfter !== null && retryAfter !== undefined) {
    error.retryAfter = retryAfter;
  }
  return error;
}

export function createAgentMutations(mutateAction) {
  async function runMutation(path, body) {
    const result = await mutateAction(path, "POST", body);
    if (!result || typeof result.status !== "number") {
      throw new Error("No se recibió una respuesta válida del servidor.");
    }
    if (result.status < 200 || result.status >= 300) {
      throw buildMutationError(path, result);
    }
    return { status: result.status, data: result.data };
  }

  return {
    switchModel: (model) => {
      const normalized = String(model ?? "").trim();
      if (!normalized) {
        return Promise.reject(new Error("Selecciona un modelo válido para realizar el cambio."));
      }
      return runMutation("/api/agent/models/switch/", { model: normalized });
    },
    // POST cancel sin cuerpo: cancela o reactiva el origen cuando sea seguro.
    cancelModelSwitch: () => runMutation("/api/agent/models/cancel/", undefined),
  };
}

export async function getModels(signal) {
  return apiClient.get("/api/agent/models/", {}, { signal, cache: "no-store" });
}

export async function getConversations(
  { page = 1, pageSize = CONVERSATIONS_PAGE_SIZE, unclear = "all" } = {},
  signal,
) {
  const params = {
    page,
    page_size: pageSize,
  };
  if (unclear === "true" || unclear === true) {
    params.unclear = "true";
  } else if (unclear === "false" || unclear === false) {
    params.unclear = "false";
  }
  const response = await apiClient.get("/api/agent/conversations/", params, { signal, cache: "no-store" });
  return readPage(response, pageSize);
}

export function normalizeConversationDetail(response, fallbackId, fallbackPageSize = CONVERSATION_TURNS_PAGE_SIZE) {
  if (!response || typeof response !== "object") {
    throw new Error("El servidor no devolvió un detalle de conversación válido.");
  }

  const turnsSource = Array.isArray(response.results)
    ? response
    : response.turns && Array.isArray(response.turns.results)
      ? response.turns
      : null;

  if (!turnsSource) {
    throw new Error("El servidor no devolvió los turnos paginados de la conversación.");
  }

  const turnsPage = readPage(turnsSource, fallbackPageSize);
  const metaSource = response.conversation && typeof response.conversation === "object"
    ? response.conversation
    : response;

  const conversation = {
    id: metaSource.id ?? fallbackId,
    created_at: metaSource.created_at ?? null,
    updated_at: metaSource.updated_at ?? null,
    has_unclear: typeof metaSource.has_unclear === "boolean"
      ? metaSource.has_unclear
      : turnsPage.results.some((turn) => Boolean(turn?.unclear)),
    turn_count: metaSource.turn_count ?? turnsPage.totalItems,
  };

  return {
    conversation,
    turns: turnsPage,
  };
}

export async function getConversationDetail(
  id,
  { page = 1, pageSize = CONVERSATION_TURNS_PAGE_SIZE } = {},
  signal,
) {
  const response = await apiClient.get(
    `/api/agent/conversations/${encodeURIComponent(id)}/`,
    { page, page_size: pageSize },
    { signal, cache: "no-store" },
  );
  return normalizeConversationDetail(response, id, pageSize);
}

export function validateAnalyticsRange({ since = "", until = "", limit = DEFAULT_ANALYTICS_LIMIT } = {}) {
  const parsedLimit = limit === "" || limit === null || limit === undefined ? DEFAULT_ANALYTICS_LIMIT : Number(limit);
  if (!Number.isInteger(parsedLimit) || parsedLimit < MIN_ANALYTICS_LIMIT || parsedLimit > MAX_ANALYTICS_LIMIT) {
    return {
      valid: false,
      error: `El límite debe ser un número entero entre ${MIN_ANALYTICS_LIMIT} y ${MAX_ANALYTICS_LIMIT}.`,
    };
  }
  const cleanSince = String(since ?? "").trim();
  const cleanUntil = String(until ?? "").trim();
  if (cleanSince && cleanUntil && cleanSince > cleanUntil) {
    return {
      valid: false,
      error: "La fecha inicial (desde) no puede ser posterior a la fecha final (hasta).",
    };
  }
  return { valid: true, limit: parsedLimit, since: cleanSince, until: cleanUntil, error: "" };
}

export async function getTopicAnalytics(
  { kind = "program", limit = DEFAULT_ANALYTICS_LIMIT, since = "", until = "" } = {},
  signal,
) {
  const safeKind = kind === "area" ? "area" : "program";
  const range = validateAnalyticsRange({ since, until, limit });
  if (!range.valid) {
    throw new Error(range.error);
  }
  const params = {
    kind: safeKind,
    limit: range.limit,
    ...(range.since ? { since: range.since } : {}),
    ...(range.until ? { until: range.until } : {}),
  };
  const response = await apiClient.get("/api/agent/analytics/topics/", params, { signal, cache: "no-store" });
  const results = Array.isArray(response?.results) ? response.results : Array.isArray(response) ? response : [];
  return {
    kind: response?.kind ?? safeKind,
    results,
  };
}

export async function getQueryAnalytics({ since = "", until = "", limit = "" } = {}, signal) {
  const params = {};
  if (since) params.since = since;
  if (until) params.until = until;
  if (limit !== "" && limit !== null && limit !== undefined) {
    const parsed = Number(limit);
    if (Number.isInteger(parsed) && parsed >= MIN_ANALYTICS_LIMIT && parsed <= MAX_ANALYTICS_LIMIT) {
      params.limit = parsed;
    }
  }
  const response = await apiClient.get("/api/agent/analytics/queries/", params, { signal, cache: "no-store" });
  const results = Array.isArray(response?.results) ? response.results : Array.isArray(response) ? response : [];
  return { results };
}

export function formatBogotaDateTime(value) {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return new Intl.DateTimeFormat("es-CO", {
    timeZone: "America/Bogota",
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(parsed);
}

export function formatTurnDuration(createdAt, finishedAt) {
  if (!createdAt || !finishedAt) return null;
  const start = Date.parse(createdAt);
  const end = Date.parse(finishedAt);
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return null;
  const seconds = Math.round((end - start) / 1000);
  if (seconds < 60) return `${seconds} s`;
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return rest ? `${minutes} min ${rest} s` : `${minutes} min`;
}
