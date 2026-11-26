import { parseRetryAfter } from "@/shared/services/apiClient";

export const PUBLIC_CHAT_BASE = "/api/agent/chat/conversations/";
export const CHAT_STORAGE_KEY = "ufps_agent_chat_session_v1";
export const PROMPT_MIN_LENGTH = 3;
export const PROMPT_MAX_LENGTH = 4000;
export const POLL_INITIAL_MS = 2000;
export const POLL_MAX_MS = 10000;
export const HISTORY_PAGE_SIZE = 20;

const POLL_BACKOFF_SCHEDULE_MS = [2000, 3000, 4500, 6500, 8500, 10000];
const MAX_HISTORY_PAGES = 200;

export class PublicChatError extends Error {
  constructor(message, { status = null, code = null, retryAfter = null, data = null } = {}) {
    super(message);
    this.name = "PublicChatError";
    this.status = status;
    this.code = code;
    this.retryAfter = retryAfter;
    this.data = data;
  }
}

export function generateClientMessageId() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  if (typeof crypto !== "undefined" && typeof crypto.getRandomValues === "function") {
    const bytes = new Uint8Array(16);
    crypto.getRandomValues(bytes);
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  }
  throw new Error("El navegador no soporta generación segura de identificadores UUID.");
}

export function validatePrompt(rawPrompt) {
  const prompt = String(rawPrompt ?? "").trim();
  if (prompt.length < PROMPT_MIN_LENGTH) {
    return {
      valid: false,
      prompt,
      error: `Escribe al menos ${PROMPT_MIN_LENGTH} caracteres para describir lo que buscas.`,
    };
  }
  if (prompt.length > PROMPT_MAX_LENGTH) {
    return {
      valid: false,
      prompt,
      error: `La consulta no puede superar los ${PROMPT_MAX_LENGTH} caracteres.`,
    };
  }
  return { valid: true, prompt, error: "" };
}

export function isTurnPending(turn) {
  return turn?.status === "queued" || turn?.status === "running";
}

export function computeNextPollDelayMs(attempt = 0, retryAfterSeconds = null) {
  if (Number.isFinite(retryAfterSeconds) && retryAfterSeconds > 0) {
    return Math.max(1000, Math.round(retryAfterSeconds * 1000));
  }
  const index = Math.min(Math.max(0, Math.trunc(attempt)), POLL_BACKOFF_SCHEDULE_MS.length - 1);
  return Math.min(POLL_MAX_MS, Math.max(POLL_INITIAL_MS, POLL_BACKOFF_SCHEDULE_MS[index]));
}

export function loadChatSession(storage = typeof window !== "undefined" ? window.sessionStorage : null) {
  if (!storage) return null;
  try {
    const raw = storage.getItem(CHAT_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || !parsed.id || !parsed.access_token) {
      return null;
    }
    return {
      id: String(parsed.id),
      access_token: String(parsed.access_token),
      pendingTurnId: parsed.pendingTurnId ? String(parsed.pendingTurnId) : null,
      updatedAt: parsed.updatedAt || null,
    };
  } catch {
    return null;
  }
}

export function saveChatSession(session, storage = typeof window !== "undefined" ? window.sessionStorage : null) {
  if (!storage || !session?.id || !session?.access_token) return;
  try {
    storage.setItem(
      CHAT_STORAGE_KEY,
      JSON.stringify({
        id: String(session.id),
        access_token: String(session.access_token),
        pendingTurnId: session.pendingTurnId ? String(session.pendingTurnId) : null,
        updatedAt: new Date().toISOString(),
      }),
    );
  } catch {
    // Private browsing or storage quota limits should not break the active chat in memory.
  }
}

export function clearChatSession(storage = typeof window !== "undefined" ? window.sessionStorage : null) {
  if (!storage) return;
  try {
    storage.removeItem(CHAT_STORAGE_KEY);
  } catch {
    // Ignore storage removal errors.
  }
}

function extractErrorCode(data) {
  if (!data || typeof data !== "object") return null;
  const candidate = data.code ?? data.error_code ?? data.error;
  return typeof candidate === "string" && candidate.trim() ? candidate.trim() : null;
}

function extractErrorDetail(data) {
  if (!data) return "";
  if (typeof data === "string") return data.trim();
  if (typeof data !== "object") return "";
  for (const key of ["detail", "message", "error"]) {
    if (typeof data[key] === "string" && data[key].trim()) {
      return data[key].trim();
    }
  }
  const fieldParts = Object.entries(data)
    .filter(([key]) => !["code", "error_code"].includes(key))
    .map(([, val]) => (Array.isArray(val) ? val.filter((item) => typeof item === "string").join(" ") : typeof val === "string" ? val : ""))
    .filter(Boolean);
  return fieldParts.join(" ");
}

export function describeChatError(error) {
  if (!error) return "Ocurrió un error al consultar el asistente.";
  const status = error.status;
  const code = error.code;

  if (status === 400) {
    const detail = extractErrorDetail(error.data);
    return detail || `Revisa tu consulta: debe tener entre ${PROMPT_MIN_LENGTH} y ${PROMPT_MAX_LENGTH} caracteres.`;
  }
  if (status === 404) {
    return "Esta conversación ya no está disponible o expiró. Inicia una nueva conversación para continuar.";
  }
  if (status === 409 || code === "conversation_busy") {
    return "Ya hay una pregunta en proceso en este chat. Espera a que termine antes de enviar otra.";
  }
  if (status === 429 || code === "agent_busy") {
    return "El asistente está atendiendo otras consultas en este momento. Espera unos segundos para reintentar sin perder tu mensaje.";
  }
  if (status === 503) {
    if (code === "model_switch_pending") {
      return "El asistente está cambiando de modelo de IA en este momento. Espera unos instantes e intenta nuevamente.";
    }
    if (code === "agent_unavailable") {
      return "El asistente no está disponible temporalmente porque no hay un modelo configurado. Intenta más tarde.";
    }
    return "El servicio del asistente no está disponible temporalmente. Intenta nuevamente en unos instantes.";
  }
  if (status === null || status === undefined) {
    return error.message || "No se pudo conectar con el asistente. Verifica tu conexión e intenta nuevamente.";
  }
  return extractErrorDetail(error.data) || error.message || `El asistente respondió con un error (${status}).`;
}

async function parseJsonSafe(response) {
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    try {
      return await response.json();
    } catch {
      return null;
    }
  }
  return null;
}

async function handlePublicChatResponse(response) {
  const retryAfter = parseRetryAfter(response.headers.get("retry-after"));
  const data = await parseJsonSafe(response);

  if (!response.ok) {
    const code = extractErrorCode(data);
    const error = new PublicChatError("", {
      status: response.status,
      code,
      retryAfter,
      data,
    });
    error.message = describeChatError(error);
    throw error;
  }

  return { data, status: response.status, retryAfter };
}

async function publicChatFetch(url, options, fetchImpl = fetch) {
  let response;
  try {
    response = await fetchImpl(url, {
      ...options,
      credentials: "omit",
      cache: "no-store",
    });
  } catch (error) {
    if (error?.name === "AbortError") throw error;
    throw new PublicChatError(
      "No se pudo conectar con el asistente. Tu consulta se conserva para que puedas reintentar.",
      { status: null, code: "network_error" },
    );
  }
  return handlePublicChatResponse(response);
}

export async function createConversation(signal, fetchImpl = fetch) {
  const { data } = await publicChatFetch(
    PUBLIC_CHAT_BASE,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: "{}",
      signal,
    },
    fetchImpl,
  );
  if (!data?.id || !data?.access_token) {
    throw new PublicChatError("El servidor no entregó una conversación válida.", { status: 502 });
  }
  return data;
}

export async function submitMessage(
  { conversationId, accessToken, prompt, clientMessageId, signal },
  fetchImpl = fetch,
) {
  const url = `${PUBLIC_CHAT_BASE}${encodeURIComponent(conversationId)}/messages/`;
  const { data, status, retryAfter } = await publicChatFetch(
    url,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        "X-Chat-Token": accessToken,
      },
      body: JSON.stringify({
        prompt,
        client_message_id: clientMessageId,
      }),
      signal,
    },
    fetchImpl,
  );
  return { turn: data, status, retryAfter };
}

export async function getTurn(
  { conversationId, accessToken, turnId, signal },
  fetchImpl = fetch,
) {
  const url = `${PUBLIC_CHAT_BASE}${encodeURIComponent(conversationId)}/messages/${encodeURIComponent(turnId)}/`;
  const { data, status, retryAfter } = await publicChatFetch(
    url,
    {
      method: "GET",
      headers: {
        Accept: "application/json",
        "X-Chat-Token": accessToken,
      },
      signal,
    },
    fetchImpl,
  );
  return { turn: data, status, retryAfter };
}

export async function getMessagesPage(
  { conversationId, accessToken, page = 1, pageSize = HISTORY_PAGE_SIZE, signal },
  fetchImpl = fetch,
) {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  const url = `${PUBLIC_CHAT_BASE}${encodeURIComponent(conversationId)}/messages/?${params.toString()}`;
  const { data } = await publicChatFetch(
    url,
    {
      method: "GET",
      headers: {
        Accept: "application/json",
        "X-Chat-Token": accessToken,
      },
      signal,
    },
    fetchImpl,
  );
  if (!data || !Array.isArray(data.results)) {
    throw new PublicChatError("El historial del chat devolvió un formato inválido.", { status: 502 });
  }
  return data;
}

export function sortTurns(turns) {
  return [...turns].sort((a, b) => {
    const seqA = Number(a?.sequence);
    const seqB = Number(b?.sequence);
    if (Number.isFinite(seqA) && Number.isFinite(seqB) && seqA !== seqB) {
      return seqA - seqB;
    }
    const timeA = Date.parse(a?.created_at || "") || 0;
    const timeB = Date.parse(b?.created_at || "") || 0;
    return timeA - timeB;
  });
}

export function mergeTurn(turns, nextTurn) {
  if (!nextTurn) return turns;
  const list = Array.isArray(turns) ? turns : [];
  const index = list.findIndex(
    (item) =>
      (nextTurn.id != null && item.id === nextTurn.id) ||
      (nextTurn.client_message_id && item.client_message_id === nextTurn.client_message_id),
  );
  if (index === -1) {
    return sortTurns([...list, nextTurn]);
  }
  const updated = [...list];
  updated[index] = { ...updated[index], ...nextTurn };
  return sortTurns(updated);
}

export async function getAllMessages(
  { conversationId, accessToken, pageSize = HISTORY_PAGE_SIZE, signal },
  fetchImpl = fetch,
) {
  const byId = new Map();
  let page = 1;
  let totalPages = 1;

  while (page <= MAX_HISTORY_PAGES) {
    const payload = await getMessagesPage(
      { conversationId, accessToken, page, pageSize, signal },
      fetchImpl,
    );
    for (const turn of payload.results) {
      const key = turn?.id ?? turn?.client_message_id ?? `${page}-${byId.size}`;
      byId.set(key, turn);
    }
    totalPages = Math.max(1, Number(payload.total_pages) || 1);
    if (!payload.next || page >= totalPages || payload.results.length === 0) {
      break;
    }
    page += 1;
  }

  return sortTurns(Array.from(byId.values()));
}
