import { apiClient } from "@/shared/services/apiClient";

const MAX_PAGE_SIZE = 100;

export function extractResults(response) {
  if (Array.isArray(response)) return response;
  if (response && Array.isArray(response.results)) return response.results;
  return [];
}

/**
 * Los catálogos están paginados (PAGE_SIZE=10 por defecto en el backend).
 * Recorre todas las páginas con el tamaño máximo permitido, siguiendo `next`
 * hasta `null`, para que los listados no queden truncados.
 */
export async function fetchAllPages(endpoint, params = {}) {
  const items = [];
  for (let page = 1; ; page += 1) {
    const response = await apiClient.get(endpoint, {
      ...params,
      page,
      page_size: MAX_PAGE_SIZE,
    });
    if (Array.isArray(response)) return response;
    const results = extractResults(response);
    items.push(...results);
    // Sin `next` (o una página vacía) indica el final del listado.
    if (!response?.next || results.length === 0) break;
  }
  return items;
}

const PROGRAMS_ENDPOINT = "/api/catalog/academic-programs/";

// Caché de sesión: evita repetir peticiones al añadir/quitar programas.
const programAreasCache = new Map();
const programCache = new Map();

function rememberProgram(program) {
  if (program && program.id != null) programCache.set(Number(program.id), program);
  return program;
}

export const academicProgramService = {
  /**
   * GET /api/catalog/academic-programs/?search=...&page=...&page_size=...
   * Devuelve una página y si hay más (`next`), para cargar resultados
   * adicionales sin truncar búsquedas amplias.
   */
  searchPage: async (search = "", { signal, page = 1, pageSize = 20 } = {}) => {
    const response = await apiClient.get(
      PROGRAMS_ENDPOINT,
      { search: search.trim(), page, page_size: pageSize, ordering: "name" },
      signal ? { signal } : {}
    );
    return {
      items: extractResults(response).map(rememberProgram),
      hasMore: !Array.isArray(response) && Boolean(response?.next),
    };
  },

  getCached: (id) => programCache.get(Number(id)) || null,

  getById: async (id) => {
    const cached = programCache.get(Number(id));
    if (cached) return cached;
    return rememberProgram(await apiClient.get(`${PROGRAMS_ENDPOINT}${id}/`));
  },

  /**
   * GET /api/catalog/academic-programs/{id}/knowledge-areas/
   */
  getKnowledgeAreas: (id) => {
    const key = Number(id);
    if (!programAreasCache.has(key)) {
      const request = fetchAllPages(`${PROGRAMS_ENDPOINT}${key}/knowledge-areas/`).catch((error) => {
        programAreasCache.delete(key);
        throw error;
      });
      programAreasCache.set(key, request);
    }
    return programAreasCache.get(key);
  },

  /**
   * Vista previa de las áreas derivadas: unión de las áreas de los programas.
   */
  previewKnowledgeAreas: async (programIds = []) => {
    const lists = await Promise.all(
      [...new Set(programIds.map(Number))].map((id) => academicProgramService.getKnowledgeAreas(id))
    );
    const byId = new Map();
    lists.flat().forEach((area) => {
      byId.set(area.id, {
        id: area.id,
        name: area.name,
        is_manual: false,
        is_derived: true,
        editable: false,
      });
    });
    return [...byId.values()].sort((a, b) => String(a.name).localeCompare(String(b.name), "es"));
  },
};
