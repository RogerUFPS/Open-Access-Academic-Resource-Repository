import { apiClient, deleteMultipart, uploadMultipart } from "@/shared/services/apiClient";
import { extractResults, fetchAllPages } from "@/shared/services/catalogService";

const LINK_CHECK_LOGS_ENDPOINT = "/api/platforms/link-check-logs/";

const FORBIDDEN_FIELDS = [
  "status",
  "start_period",
  "finish_period",
  "validated_by",
  "validated_at",
  "created_by",
  "created_at",
  "updated_by",
  "updated_at",
  "deleted_by",
  "deleted_at",
  "encrypted_api_key",
  // Solo lectura: el backend deriva las áreas de los programas académicos.
  "knowledge_areas",
];

function sanitizePayload(data) {
  if (!data || typeof data !== "object") return data;
  const clean = { ...data };
  FORBIDDEN_FIELDS.forEach((field) => {
    delete clean[field];
  });
  return clean;
}

export const platformService = {
  /**
   * List active platforms (with optional search, filters, ordering, pagination)
   */
  getPlatforms: async (params = {}) => {
    return apiClient.get("/api/platforms/", params);
  },

  /**
   * Endpoint Público: GET /api/platforms/public/ (solo trae las plataformas publicadas)
   */
  getPublicPlatforms: async (params = {}) => {
    return apiClient.get("/api/platforms/public/", params);
  },

  /**
   * List archived/deleted platforms
   */
  getArchivedPlatforms: async (params = {}) => {
    return apiClient.get("/api/platforms/archived/", params);
  },

  /**
   * Get detail of a specific platform
   */
  getPlatformById: async (id) => {
    return apiClient.get(`/api/platforms/${id}/`);
  },

  /**
   * Create a new platform (POST /api/platforms/)
   * Regla de negocio: La creación crea un registro en borrador y conserva
   * los campos administrativos admitidos por el formulario.
   */
  createPlatform: async (data) => {
    const payload = {
      name: data?.name ? String(data.name).trim() : "",
      public_url: data?.public_url ? String(data.public_url).trim() : "",
    };
    const editableFields = [
      "is_harvestable",
      "base_api_url",
      "api_key",
      "url_image",
      "requires_registration",
      "has_access_text",
      "valid_sintaxis",
      "institutions",
      "languages",
      "countries",
      "material_types",
      "academic_programs",
    ];
    editableFields.forEach((field) => {
      if (data?.[field] !== undefined) payload[field] = data[field];
    });
    return apiClient.post("/api/platforms/", payload);
  },

  /**
   * Full update of a platform (PUT /api/platforms/{id}/)
   */
  updatePlatform: async (id, data) => {
    const cleanPayload = sanitizePayload(data);
    return apiClient.put(`/api/platforms/${id}/`, cleanPayload);
  },

  /**
   * Partial update of a platform (PATCH /api/platforms/{id}/)
   * Respeta: base_api_url y api_key solo se envían si is_harvestable es true.
   * Campos de auditoría/estado prohibidos son removidos.
   */
  patchPlatform: async (id, data) => {
    const cleanPayload = sanitizePayload(data);
    if (!cleanPayload.is_harvestable) {
      delete cleanPayload.base_api_url;
      delete cleanPayload.api_key;
    }
    return apiClient.patch(`/api/platforms/${id}/`, cleanPayload);
  },

  /**
   * Delete platform (DELETE /api/platforms/{id}/)
   */
  deletePlatform: async (id, deleteExplanation = "") => {
    return apiClient.delete(`/api/platforms/${id}/`, {
      delete_explanation: deleteExplanation.trim(),
    });
  },

  /**
   * Restore platform (POST /api/platforms/{id}/restore/)
   */
  restorePlatform: async (id) => {
    return apiClient.post(`/api/platforms/${id}/restore/`, {});
  },

  /**
   * Status transitions
   */
  publishPlatform: async (id) => {
    return apiClient.post(`/api/platforms/${id}/publish/`, {});
  },

  markObsoletePlatform: async (id) => {
    return apiClient.post(`/api/platforms/${id}/mark-obsolete/`, {});
  },

  reactivatePlatform: async (id) => {
    return apiClient.post(`/api/platforms/${id}/reactivate/`, {});
  },

  /**
   * Check / Register public URL (POST /api/platforms/{id}/check-link/)
   * If url is provided and non-empty, send { url }. If empty or null, send empty body {}.
   */
  checkLink: async (id, url = null) => {
    const cleanUrl = typeof url === "string" ? url.trim() : null;
    const body = cleanUrl ? { url: cleanUrl } : {};
    return apiClient.post(`/api/platforms/${id}/check-link/`, body);
  },

  /**
   * Get valid syntax options (GET /api/platforms/valid-sintaxis/)
   */
  // Recorre todas las páginas: el selector no debe truncarse a las primeras 100.
  getValidSintaxis: async () => fetchAllPages("/api/platforms/valid-sintaxis/"),

  getValidSintaxisList: async () => fetchAllPages("/api/platforms/valid-sintaxis/"),
  getValidSintaxisById: async (id) =>
    apiClient.get(`/api/platforms/valid-sintaxis/${id}/`),
  createValidSintaxis: async (data) => apiClient.post("/api/platforms/valid-sintaxis/", data),
  updateValidSintaxis: async (id, data) => apiClient.patch(`/api/platforms/valid-sintaxis/${id}/`, data),
  deleteValidSintaxis: async (id, deleteExplanation = "") => apiClient.delete(
    `/api/platforms/valid-sintaxis/${id}/`,
    deleteExplanation ? { delete_explanation: deleteExplanation } : null
  ),
  findSimilarSintaxis: async (data) => apiClient.post("/api/platforms/valid-sintaxis/similar/", data),
  uploadPlatformImage: async (id, file) =>
    uploadMultipart(`/api/platforms/${id}/image/`, "image", file),
  deletePlatformImage: async (id) =>
    deleteMultipart(`/api/platforms/${id}/image/`),

  /**
   * Estado vigente de la URL general de una plataforma:
   * GET /api/platforms/link-check-logs/?platform={id}&current=true&journal_platform__isnull=true
   * Devuelve el LinkCheckLog vigente o null si aún no hay registro.
   */
  getCurrentPlatformLinkLog: async (id) => {
    const response = await apiClient.get(LINK_CHECK_LOGS_ENDPOINT, {
      platform: id,
      current: "true",
      journal_platform__isnull: "true",
      page_size: 1,
    });
    return extractResults(response)[0] || null;
  },

  /**
   * Historial completo (vigente y sustituido) de la URL general de una
   * plataforma, recorriendo todas las páginas. Excluye los enlaces de revistas.
   */
  getPlatformLinkHistory: async (id) =>
    fetchAllPages(LINK_CHECK_LOGS_ENDPOINT, { platform: id, journal_platform__isnull: "true" }),

  /**
   * Helper to load catalog list safely from /api/catalog/{resource}/
   */
  getCatalogData: async (endpoint, fallback = []) => {
    try {
      return await fetchAllPages(endpoint);
    } catch {
      return fallback;
    }
  },

  /**
   * Load catalog options from /api/catalog/ endpoints
   */
  loadFormCatalogs: async () => {
    const sintaxisResult = await platformService.getValidSintaxis().then(
      (sintaxis) => ({ sintaxis: Array.isArray(sintaxis) ? sintaxis : sintaxis.results || [] }),
      (error) => ({ sintaxis: [], sintaxisError: error })
    );
    const [sintaxis, institutions, languages, countries, materialTypes] = await Promise.all([
      Promise.resolve(sintaxisResult.sintaxis),
      platformService.getCatalogData("/api/catalog/institutions/", [
        { id: 1, name: "SciELO Network" },
        { id: 2, name: "Universidad Francisco de Paula Santander" },
      ]),
      platformService.getCatalogData("/api/catalog/languages/", [
        { id: 1, abbreviation: "ES", name: "Español" },
        { id: 2, abbreviation: "PT", name: "Portugués" },
        { id: 3, abbreviation: "EN", name: "Inglés" },
      ]),
      platformService.getCatalogData("/api/catalog/countries/", [
        { id: 1, abbreviation: "BR", name: "Brasil", emoji_flag: "🇧🇷" },
        { id: 2, abbreviation: "CO", name: "Colombia", emoji_flag: "🇨🇴" },
        { id: 3, abbreviation: "MX", name: "México", emoji_flag: "🇲🇽" },
        { id: 4, abbreviation: "US", name: "Estados Unidos", emoji_flag: "🇺🇸" },
      ]),
      platformService.getCatalogData("/api/catalog/material-types/", [
        { id: 1, name: "Revistas y artículos" },
        { id: 2, name: "Libros y Monografías" },
        { id: 3, name: "Tesis y Disertaciones" },
      ]),
    ]);

    return {
      sintaxis: Array.isArray(sintaxis) ? sintaxis : sintaxis.results || [],
      sintaxisError: sintaxisResult.sintaxisError || null,
      institutions,
      languages,
      countries,
      materialTypes,
    };
  },
};
