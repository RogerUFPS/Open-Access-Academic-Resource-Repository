// Auditoría archivada en AuditCompressor, siempre a través del Backend
// (Backend/docs/ARCHIVO_AUDITORIA.md). La API Key nunca llega al navegador.
import { apiClient } from "@/shared/services/apiClient";

export const ARCHIVE_SOURCES = {
  auditlog: {
    label: "Auditoría general",
    endpoint: "/api/audit/archived-logs/",
    permission: "archived-logs",
  },
  superadmin_events: {
    label: "Eventos de superadmin",
    endpoint: "/api/audit/archived-superadmin-events/",
    permission: "archived-superadmin-events",
  },
};

/** Página de registros archivados en [start_date, end_date) (fechas YYYY-MM-DD). */
export function getArchivedPage(source, { startDate, endDate, page = 1, pageSize = 10 }, options = {}) {
  return apiClient.get(
    ARCHIVE_SOURCES[source].endpoint,
    { start_date: startDate, end_date: endDate, page, page_size: pageSize },
    options
  );
}

/** Semestres ya comprimidos con registros que esperan decisión. */
export function getAnomalies(options = {}) {
  return apiClient.get("/api/audit/archive-anomalies/", {}, options);
}

export function getAnomalyRecords(source, snapshotId, { page = 1, pageSize = 10 } = {}, options = {}) {
  return apiClient.get(
    `/api/audit/archive-anomalies/${source}/${snapshotId}/records/`,
    { page, page_size: pageSize },
    options
  );
}

/** action: "compress" | "delete"; expectedRows: cantidad revisada (409 si cambió). */
export function resolveAnomaly({ source, snapshotId, action, expectedRows }) {
  return apiClient.post("/api/audit/archive-anomalies/resolve/", {
    source,
    snapshot_id: snapshotId,
    action,
    expected_rows: expectedRows,
  });
}

/** Mensaje para los errores propios del archivo (ARCHIVO_AUDITORIA.md §6). */
export function archiveErrorMessage(error) {
  if (error?.status === 503) return "La auditoría archivada no está disponible en este momento. Intenta más tarde.";
  if (error?.status === 502) {
    return "Un archivo del período no superó la verificación de integridad. Avisa al administrador del sistema.";
  }
  if (error?.status === 409) return "La anomalía cambió desde que la revisaste. Se recargó la lista.";
  if (error?.status === 403) return "No tienes permiso para esta acción.";
  return error?.message || "No se pudo completar la operación.";
}

/* ───────────── Semestres (hora de Colombia, [inicio, fin)) ───────────── */

const pad = (n) => String(n).padStart(2, "0");
const isoDate = (year, month, day) => `${year}-${pad(month)}-${pad(day)}`;

/** Semestre {label, startDate, endDate} que contiene la fecha local dada. */
export function semesterOf(year, month) {
  return month <= 6
    ? { label: `${year}-I`, startDate: isoDate(year, 1, 1), endDate: isoDate(year, 7, 1) }
    : { label: `${year}-II`, startDate: isoDate(year, 7, 1), endDate: isoDate(year + 1, 1, 1) };
}

/** Los `count` semestres anteriores al actual, del más reciente al más antiguo. */
export function pastSemesters(count = 8, today = new Date()) {
  const result = [];
  let year = today.getFullYear();
  let firstHalf = today.getMonth() < 6;
  for (let i = 0; i < count; i += 1) {
    if (firstHalf) {
      year -= 1;
      firstHalf = false;
    } else {
      firstHalf = true;
    }
    result.push(semesterOf(year, firstHalf ? 1 : 7));
  }
  return result;
}

/** Etiqueta del semestre de un snapshot a partir de su inicio (ISO UTC). */
export function semesterLabelFromStart(startIso) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Bogota",
    year: "numeric",
    month: "numeric",
  }).formatToParts(new Date(startIso));
  const year = Number(parts.find((part) => part.type === "year")?.value);
  const month = Number(parts.find((part) => part.type === "month")?.value);
  return semesterOf(year, month).label;
}

/** Suma un día a una fecha YYYY-MM-DD (el fin del rango es exclusivo). */
export function nextDay(date) {
  const value = new Date(`${date}T00:00:00Z`);
  value.setUTCDate(value.getUTCDate() + 1);
  return value.toISOString().slice(0, 10);
}
