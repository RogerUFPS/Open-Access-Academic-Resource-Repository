import { notifySessionExpired, shouldSkipSessionExpiredAlert } from "@/shared/utils/sessionExpiration";

const isBrowser = typeof window !== "undefined";
export const ACCOUNT_FORBIDDEN_EVENT = "library:account-forbidden";
const API_BASE_URL = isBrowser
  ? process.env.NEXT_PUBLIC_API_URL
  : process.env.BACKEND_INTERNAL_URL || process.env.NEXT_PUBLIC_API_URL;

/**
 * Read csrftoken from document.cookie (browser-only).
 */
function getCsrfToken() {
  if (!isBrowser) return null;
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : null;
}

/**
 * Helper to build full URL with query parameters.
 * In the browser, uses relative URLs so requests go through the Next.js
 * rewrite proxy (same-origin), which lets cookies flow automatically.
 * On the server, uses the absolute backend URL.
 */
function buildUrl(endpoint, params = {}) {
  const cleanEndpoint = endpoint.startsWith("/") ? endpoint : `/${endpoint}`;
  // Ensure trailing slash for API endpoints if not present
  const endpointWithSlash = cleanEndpoint.includes("?") 
    ? cleanEndpoint 
    : cleanEndpoint.endsWith("/") 
      ? cleanEndpoint 
      : `${cleanEndpoint}/`;

  // In the browser, use relative URL for the Next.js proxy; on the server, use the full URL.
  const base = isBrowser ? "" : API_BASE_URL;
  const url = new URL(`${base}${endpointWithSlash}`, isBrowser ? window.location.origin : undefined);

  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      url.searchParams.append(key, value);
    }
  });

  return url.toString();
}

/**
 * Handle HTTP response and parse JSON or extract errors
 */
async function handleResponse(response, endpoint = "") {
  if (response.status === 204) return null;
  const contentType = response.headers.get("content-type");
  let data = null;

  if (contentType && contentType.includes("application/json")) {
    try {
      data = await response.json();
    } catch {
      data = null;
    }
  } else {
    try {
      const text = await response.text();
      data = { detail: text };
    } catch {
      data = null;
    }
  }

  if (!response.ok) {
    if (response.status === 403 && isBrowser) {
      // The backend answers 403 when the account still has to change its
      // password or complete MFA; the admin layout re-checks /auth/me/.
      window.dispatchEvent(new CustomEvent(ACCOUNT_FORBIDDEN_EVENT, { detail: { endpoint } }));
    }
    let errorMessage = `Error ${response.status}: ${response.statusText}`;
    const extractedMessage = extractApiErrorText(data);
    if (extractedMessage) errorMessage = extractedMessage;

    const authExpired = response.status === 401 && !shouldSkipSessionExpiredAlert(endpoint || response.url || "");
    if (authExpired) {
      notifySessionExpired(errorMessage, { endpoint: endpoint || response.url || "", status: response.status });
    }

    const error = new Error(errorMessage);
    error.status = response.status;
    error.data = data;
    error.authExpired = authExpired;
    throw error;
  }

  return data;
}

export function extractApiErrorText(value, fallback = "") {
  if (typeof value === "string") return value.trim();
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) {
    return value.map((item) => extractApiErrorText(item)).filter(Boolean).join(" ");
  }
  if (!value || typeof value !== "object") return fallback;

  const messages = ["message", "detail", "error", "code"]
    .map((key) => {
      const nested = value[key];
      return key === "code" && nested && typeof nested === "object"
        ? ""
        : extractApiErrorText(nested);
    })
    .filter(Boolean);
  if (messages.length) return [...new Set(messages)].join(" ");

  return Object.entries(value)
    .filter(([key]) => key !== "existing_id")
    .map(([, nested]) => extractApiErrorText(nested))
    .filter(Boolean)
    .join(" ");
}

export function normalizeApiFieldErrors(data, fallback = "Ocurrió un error al guardar.") {
  if (!data || typeof data !== "object" || Array.isArray(data)) return {};

  const ignoredKeys = new Set(["detail", "message", "error", "existing_id"]);
  return Object.fromEntries(
    Object.entries(data)
      .filter(([key]) => !ignoredKeys.has(key))
      .map(([key, value]) => {
        const message = extractApiErrorText(value);
        return [key, message || fallback];
      })
      .filter(([, message]) => Boolean(message))
  );
}

export const apiClient = {
  get: async (endpoint, params = {}, options = {}) => {
    const url = buildUrl(endpoint, params);
    const csrfToken = getCsrfToken();
    const response = await fetch(url, {
      method: "GET",
      headers: {
        "Content-Type": "application/json",
        "Accept": "application/json",
        ...(csrfToken ? { "X-CSRFToken": csrfToken } : {}),
        ...options.headers,
      },
      credentials: "include",
      ...options,
    });
    return handleResponse(response, endpoint);
  },

  post: async (endpoint, body = {}, options = {}) => {
    const url = buildUrl(endpoint);
    const csrfToken = getCsrfToken();
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Accept": "application/json",
        ...(csrfToken ? { "X-CSRFToken": csrfToken } : {}),
        ...options.headers,
      },
      body: JSON.stringify(body),
      credentials: "include",
      ...options,
    });
    return handleResponse(response, endpoint);
  },

  put: async (endpoint, body = {}, options = {}) => {
    const url = buildUrl(endpoint);
    const csrfToken = getCsrfToken();
    const response = await fetch(url, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        "Accept": "application/json",
        ...(csrfToken ? { "X-CSRFToken": csrfToken } : {}),
        ...options.headers,
      },
      body: JSON.stringify(body),
      credentials: "include",
      ...options,
    });
    return handleResponse(response, endpoint);
  },

  patch: async (endpoint, body = {}, options = {}) => {
    const url = buildUrl(endpoint);
    const csrfToken = getCsrfToken();
    const response = await fetch(url, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        "Accept": "application/json",
        ...(csrfToken ? { "X-CSRFToken": csrfToken } : {}),
        ...options.headers,
      },
      body: JSON.stringify(body),
      credentials: "include",
      ...options,
    });
    return handleResponse(response, endpoint);
  },

  delete: async (endpoint, body = null, options = {}) => {
    const url = buildUrl(endpoint);
    const csrfToken = getCsrfToken();
    const fetchOptions = {
      method: "DELETE",
      headers: {
        "Content-Type": "application/json",
        "Accept": "application/json",
        ...(csrfToken ? { "X-CSRFToken": csrfToken } : {}),
        ...options.headers,
      },
      credentials: "include",
      ...options,
    };

    if (body) {
      fetchOptions.body = JSON.stringify(body);
    }

    const response = await fetch(url, fetchOptions);
    return handleResponse(response, endpoint);
  },
};

export async function uploadMultipart(endpoint, fieldName, file) {
  const url = buildUrl(endpoint);
  const csrfToken = getCsrfToken();
  const formData = new FormData();
  formData.append(fieldName, file);
  const response = await fetch(url, {
    method: "POST",
    headers: {
      Accept: "application/json",
      ...(csrfToken ? { "X-CSRFToken": csrfToken } : {}),
    },
    credentials: "include",
    body: formData,
  });
  return handleResponse(response, endpoint);
}

export async function deleteMultipart(endpoint) {
  const url = buildUrl(endpoint);
  const csrfToken = getCsrfToken();
  const response = await fetch(url, {
    method: "DELETE",
    headers: {
      Accept: "application/json",
      ...(csrfToken ? { "X-CSRFToken": csrfToken } : {}),
    },
    credentials: "include",
  });
  return handleResponse(response, endpoint);
}

// Read-only requests use the same-origin proxy. Mutations run through the
// Server Action supplied by AccountsGateway, which owns session and CSRF cookies.
async function accountsRequest(path, { method = "GET", body, signal } = {}, mutateAction) {
  const headers = { Accept: "application/json" };
  if (method !== "GET") {
    const result = await mutateAction(path, method, body);
    if (result.status === 204) return null;
    return handleResponse(new Response(JSON.stringify(result.data), {
      status: result.status, headers: { "Content-Type": "application/json" },
    }), path);
  }
  if (body !== undefined) headers["Content-Type"] = "application/json";
  let response;
  try {
    response = await fetch(`/api/accounts/${path}`, {
      method, headers, credentials: "include", cache: "no-store", signal,
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new Error("No se pudo conectar con el servidor. Revisa tu conexión e intenta nuevamente.");
  }
  if (response.status === 204) return null;
  return handleResponse(response, `/api/accounts/${path}`);
}

export function hasAccountPermission(user, action) {
  return Boolean(user?.is_superadmin || user?.effective_permissions?.accounts?.users?.[action]);
}

/**
 * Next onboarding step for the signed-in account, based only on its own
 * /auth/me/ or login flags: "password", "mfa-enroll", "mfa-challenge" or null.
 */
export function pendingAccountStep(account) {
  if (!account) return null;
  const user = account.user ?? account;
  if (account.must_change_password || user.must_change_password || user.force_password_change) return "password";
  const isSuperadmin = Boolean(account.is_superadmin ?? user.is_superadmin);
  const mfaSatisfied = account.mfa_satisfied ?? user.mfa_satisfied;
  if (isSuperadmin && !mfaSatisfied) {
    const enrollment = account.mfa_enrollment_required ?? user.mfa_enrollment_required;
    return enrollment ? "mfa-enroll" : "mfa-challenge";
  }
  return null;
}

// Reads do not depend on the Server Action reference, which can change when
// Next.js refreshes session cookies. Keep these callbacks stable for effects.
const accountQueries = {
  me: (signal) => accountsRequest("auth/me/", { signal }),
  // Always asks the backend, even where `me` reuses the server-validated user.
  currentUser: (signal) => accountsRequest("auth/me/", { signal }),
  mfaEnrollment: (signal) => accountsRequest("auth/mfa/enroll/", { signal }),
  users: (signal) => accountsRequest("users/", { signal }),
  archivedUsers: (signal) => accountsRequest("users/archived/", { signal }),
  user: (id, signal) => accountsRequest(`users/${encodeURIComponent(id)}/`, { signal }),
  permissions: (signal) => accountsRequest("permissions/", { signal }),
  presets: (signal) => accountsRequest("presets/", { signal }),
  preset: (id, signal) => accountsRequest(`presets/${encodeURIComponent(id)}/`, { signal }),
};

export function createAccountsApi(mutateAction, { me = accountQueries.me } = {}) {
  const mutate = (path, method, body) => accountsRequest(path, { method, body }, mutateAction);
  return {
    ...accountQueries,
    me,
    login: (body) => mutate("auth/login/", "POST", body),
    logout: () => mutate("auth/logout/", "POST", {}),
    changePassword: (body) => mutate("password/change/", "POST", body),
    forgotPassword: (body) => mutate("password/forgot/", "POST", body),
    confirmMfaEnrollment: (code) => mutate("auth/mfa/enroll/confirm/", "POST", { code }),
    mfaChallenge: (code) => mutate("auth/mfa/challenge/", "POST", { code }),
    createSuperadmin: (email) => mutate("superadmin/accounts/", "POST", { email }),
    deactivateSuperadmin: () => mutate("superadmin/deactivate/", "POST", {}),
    invite: (body) => mutate("users/invite/", "POST", body),
    updateUser: (id, body) => mutate(`users/${encodeURIComponent(id)}/`, "PATCH", body),
    deactivate: (id) => mutate(`users/${encodeURIComponent(id)}/`, "DELETE"),
    restoreUser: (id) => mutate(`users/${encodeURIComponent(id)}/restore/`, "POST"),
    createPreset: (body) => mutate("presets/", "POST", body),
    updatePreset: (id, body) => mutate(`presets/${encodeURIComponent(id)}/`, "PATCH", body),
    deletePreset: (id) => mutate(`presets/${encodeURIComponent(id)}/`, "DELETE"),
    savePermissions: (id, permissions) => mutate(`users/${encodeURIComponent(id)}/permissions/`, "PUT", { permissions }),
  };
}
