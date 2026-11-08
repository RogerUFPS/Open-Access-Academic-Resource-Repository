export function clampPage(page, totalPages) {
  const safeTotal = Math.max(1, Number(totalPages) || 1);
  const safePage = Number.isFinite(Number(page)) ? Number(page) : 1;
  return Math.min(Math.max(1, Math.trunc(safePage)), safeTotal);
}

export function sanitizePageValue(value, totalPages) {
  const safeTotal = Math.max(1, Number(totalPages) || 1);
  const trimmed = String(value ?? "").trim();

  if (!/^\d+$/.test(trimmed)) {
    return { valid: false, page: null };
  }

  const parsed = Number.parseInt(trimmed, 10);
  if (!Number.isInteger(parsed) || parsed < 1 || parsed > safeTotal) {
    return { valid: false, page: null };
  }

  return { valid: true, page: parsed };
}

/**
 * Normaliza una respuesta paginada del backend
 * ({ results, total_items, total_pages, page_size, current_page }).
 * Lanza un error si el servidor no devolvió un listado paginado.
 */
export function readPage(response, fallbackPageSize = 10) {
  if (!response || !Array.isArray(response.results)) {
    throw new Error("El servidor no devolvió un listado paginado válido.");
  }
  const pageSize = Number(response.page_size) || fallbackPageSize;
  const totalItems = Number(response.total_items ?? response.count ?? response.results.length) || 0;
  const totalPages = Math.max(1, Number(response.total_pages) || Math.ceil(totalItems / pageSize) || 1);
  const page = clampPage(response.current_page ?? 1, totalPages);
  return { results: response.results, totalItems, totalPages, pageSize, page };
}

/**
 * DRF responde 404 cuando la página pedida ya no existe (por ejemplo, tras
 * eliminar el último registro de la última página).
 */
export function isMissingPage(error, page) {
  return page > 1 && error?.status === 404;
}
