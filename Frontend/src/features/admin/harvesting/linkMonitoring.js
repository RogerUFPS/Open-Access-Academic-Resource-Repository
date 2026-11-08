import { getPlatformJournals, getPlatforms } from "@/features/admin/harvesting/harvesting";

/**
 * Vistas del módulo de enlaces. El filtro vive en la URL (fuente de verdad);
 * `failure_confirmed` es un parámetro de consulta, nunca un campo de la fila.
 */
export const LINK_VIEWS = [
  { key: "caidos", label: "Caídos", query: { current: "true", failure_confirmed: "true" } },
  { key: "no-disponibles", label: "No disponibles", query: { current: "true", verification_status: "unavailable" } },
  {
    key: "sin-confirmar",
    label: "Fallos sin confirmar",
    query: { current: "true", verification_status: "unavailable", failure_confirmed: "false" },
  },
  { key: "funcionando", label: "Funcionando", query: { current: "true", verification_status: "available" } },
  { key: "sin-verificar", label: "Sin verificar", query: { current: "true", verification_status: "unverified" } },
  { key: "vigentes", label: "Todos vigentes", query: { current: "true" } },
  { key: "historial", label: "Historial", query: { current: "false" } },
];

export const VIEW_PARAM_KEYS = ["current", "failure_confirmed", "verification_status"];
export const EXTRA_PARAM_KEYS = ["platform", "journal_platform", "journal_platform__isnull", "is_active"];

export const CONFIRMED_FAILURES_QUERY = { current: "true", failure_confirmed: "true" };
export const ALERTS_PATH = "/admin/alertas";
export const CONFIRMED_ALERTS_HREF = `${ALERTS_PATH}?current=true&failure_confirmed=true`;

export function pickParams(params, keys) {
  return Object.fromEntries(keys.filter((key) => params[key] !== undefined && params[key] !== "").map((key) => [key, params[key]]));
}

export function matchView(params) {
  const viewParams = pickParams(params, VIEW_PARAM_KEYS);
  return (
    LINK_VIEWS.find((view) => {
      const keys = new Set([...Object.keys(view.query), ...Object.keys(viewParams)]);
      return [...keys].every((key) => view.query[key] === viewParams[key]);
    }) || null
  );
}

export function buildQueryString(params) {
  return new URLSearchParams(params).toString();
}

/**
 * Estado mostrado según `verification_status`. La caída confirmada se
 * determina por la consulta (`confirmed`), no por campos de la fila.
 */
export function linkStatus(row, confirmed) {
  if (row.verification_status === "available") return { label: "Funcionando", state: "success" };
  if (row.verification_status === "unavailable") {
    return confirmed
      ? { label: "Caída confirmada", state: "error" }
      : { label: "No disponible", state: "warning" };
  }
  return { label: "Sin verificar", state: "info" };
}

export const platformIdOf = (row) => (typeof row.platform === "object" ? row.platform?.id : row.platform);
export const relationIdOf = (row) =>
  typeof row.journal_platform === "object" ? row.journal_platform?.id ?? null : row.journal_platform ?? null;

export function httpStatusLabel(row) {
  return row.http_status_code == null ? "Sin respuesta HTTP" : `HTTP ${row.http_status_code}`;
}

/**
 * Resuelve nombres y enlaces de recursos. Las revistas se identifican por
 * `journal_platform` ↔ `platforms[].relation_id`, nunca comparando URLs.
 *
 * `cache` se conserva entre recargas: { platforms?: Promise, journals: Map }.
 */
export async function resolveLinkResources(rows, signal, cache) {
  if (!cache.platforms) {
    cache.platforms = getPlatforms(signal).catch((error) => {
      cache.platforms = null;
      throw error;
    });
  }
  const platformNames = new Map();
  try {
    (await cache.platforms).forEach((platform) => platformNames.set(String(platform.id), platform.name));
  } catch {
    // Sin nombres: se muestran IDs.
  }

  const journalPlatformIds = [
    ...new Set(rows.filter((row) => relationIdOf(row) !== null).map((row) => String(platformIdOf(row)))),
  ];
  await Promise.all(
    journalPlatformIds.map(async (platformId) => {
      if (!cache.journals.has(platformId)) {
        cache.journals.set(
          platformId,
          getPlatformJournals(platformId, signal).catch((error) => {
            cache.journals.delete(platformId);
            throw error;
          })
        );
      }
      try {
        await cache.journals.get(platformId);
      } catch {
        // Se resolverá como relación sin nombre.
      }
    })
  );

  const relations = new Map();
  for (const platformId of journalPlatformIds) {
    let journals = [];
    try {
      journals = (await cache.journals.get(platformId)) || [];
    } catch {
      journals = [];
    }
    journals.forEach((journal) => {
      (journal.platforms || []).forEach((entry) => {
        if (entry.relation_id != null) relations.set(String(entry.relation_id), journal);
      });
    });
  }

  const resources = new Map();
  rows.forEach((row) => {
    const platformId = platformIdOf(row);
    const platformName = platformNames.get(String(platformId)) || `Plataforma #${platformId}`;
    const relationId = relationIdOf(row);
    if (relationId === null) {
      resources.set(row.id, {
        kind: "platform",
        name: platformName,
        context: "Enlace general de la plataforma",
        href: `/admin/bases-de-datos/vista/${platformId}`,
        platformId,
        platformName,
      });
      return;
    }
    const journal = relations.get(String(relationId));
    resources.set(row.id, {
      kind: "journal",
      name: journal ? journal.title : `Revista (relación #${relationId})`,
      context: `Enlace de revista en ${platformName}`,
      href: journal ? `/admin/revistas/vista/${journal.id}` : `/admin/bases-de-datos/vista/${platformId}`,
      platformId,
      platformName,
    });
  });
  return resources;
}

/** Mensajes explícitos para 401/403/400/503 en acciones de verificación. */
export function linkActionError(error) {
  const status = error?.status;
  if (status === 401) return "La sesión expiró. Inicia sesión nuevamente.";
  if (status === 403) return "Tu cuenta no tiene el permiso platforms.platforms.check_link.";
  if (status === 503) return "El servicio de verificación no está disponible en este momento. Inténtalo más tarde.";
  if (status === 400) return `Solicitud rechazada: ${error.message}`;
  return error?.message || "No se pudo completar la verificación.";
}

export function canCheckLinks(user) {
  return Boolean(user?.is_superadmin || user?.effective_permissions?.platforms?.platforms?.check_link);
}

/*
 * Selección de filas con paginación en el servidor.
 *
 * - `ids`: selección explícita; guarda id → plataforma de cada fila marcada,
 *   aunque pertenezca a otra página.
 * - `all`: "todos los resultados filtrados"; guarda solo las exclusiones. Las
 *   plataformas implicadas se calculan recorriendo las páginas del filtro.
 */
export function emptySelection() {
  return { mode: "ids", items: new Map() };
}

export function selectAllFiltered() {
  return { mode: "all", excluded: new Map() };
}

const rowKey = (row) => String(row.id);

export function isRowSelected(selection, row) {
  return selection.mode === "all" ? !selection.excluded.has(rowKey(row)) : selection.items.has(rowKey(row));
}

export function setRowsSelected(selection, rows, checked) {
  const map = new Map(selection.mode === "all" ? selection.excluded : selection.items);
  // En modo `all` marcar una fila significa quitarla de las exclusiones.
  const add = selection.mode === "all" ? !checked : checked;
  rows.forEach((row) => {
    if (add) map.set(rowKey(row), String(platformIdOf(row)));
    else map.delete(rowKey(row));
  });
  return selection.mode === "all" ? { mode: "all", excluded: map } : { mode: "ids", items: map };
}

export function toggleRow(selection, row) {
  return setRowsSelected(selection, [row], !isRowSelected(selection, row));
}

export function selectionCount(selection, total) {
  return selection.mode === "all" ? Math.max(0, total - selection.excluded.size) : selection.items.size;
}

export function isEverythingSelected(selection, total) {
  return total > 0 && selectionCount(selection, total) === total;
}

/** Plataformas de una selección explícita (sin consultar al servidor). */
export function explicitPlatformIds(selection) {
  return selection.mode === "ids" ? [...new Set(selection.items.values())] : [];
}
