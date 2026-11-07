import { apiClient } from "@/shared/services/apiClient";

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
];

function sanitizePayload(data) {
  if (!data || typeof data !== "object") return data;
  const clean = { ...data };
  FORBIDDEN_FIELDS.forEach((field) => {
    delete clean[field];
  });
  return clean;
}

export const journalService = {
  /**
   * List journals (supports ?search=..., pagination, ordering)
   */
  getJournals: async (params = {}) => {
    return apiClient.get("/api/journals/", params);
  },

  /**
   * List logically deleted journals (GET /api/journals/archived/)
   */
  getArchivedJournals: async () => {
    return apiClient.get("/api/journals/archived/");
  },

  /**
   * Get detail of a specific journal
   */
  getJournalById: async (id) => {
    return apiClient.get(`/api/journals/${id}/`);
  },

  /**
   * Get detail of a specific editorial (From production)
   */
  getEditorialById: async (id) => {
    return apiClient.get(`/api/catalog/editorials/${id}/`);
  },

  /**
   * Create a new journal (POST /api/journals/)
   * Regla de negocio: La creación crea un registro en borrador.
   * Requiere mínimo issn (formato XXXX-XXXX) y title.
   * NUNCA envía campos prohibidos / de solo lectura.
   */
  createJournal: async (data) => {
    const clean = sanitizePayload(data);
    // Asegurar estructura de knowledge_areas como array de IDs
    if (clean.knowledge_areas && Array.isArray(clean.knowledge_areas)) {
      clean.knowledge_areas = clean.knowledge_areas.map((ka) =>
        typeof ka === "object" && ka !== null ? ka.id : Number(ka)
      );
    }
    // Asegurar estructura de platforms
    if (clean.platforms && Array.isArray(clean.platforms)) {
      clean.platforms = clean.platforms.map((p) => ({
        platform: typeof p.platform === "object" && p.platform !== null ? p.platform.id : Number(p.platform),
        journal_url: String(p.journal_url || "").trim(),
        has_full_text: Boolean(p.has_full_text),
      }));
    }
    return apiClient.post("/api/journals/", clean);
  },

  /**
   * Partial update of a journal (PATCH /api/journals/{id}/)
   * Knowledge areas se envía como array simple de IDs manuales: [1, 4, 7].
   * Platforms se envía como [{ platform, journal_url, has_full_text }].
   * Campos prohibidos son removidos.
   */
  patchJournal: async (id, data) => {
    const clean = sanitizePayload(data);

    if (clean.knowledge_areas !== undefined) {
      if (Array.isArray(clean.knowledge_areas)) {
        clean.knowledge_areas = clean.knowledge_areas.map((ka) =>
          typeof ka === "object" && ka !== null ? ka.id : Number(ka)
        );
      }
    }

    if (clean.platforms !== undefined) {
      if (Array.isArray(clean.platforms)) {
        clean.platforms = clean.platforms.map((p) => ({
          platform: typeof p.platform === "object" && p.platform !== null ? p.platform.id : Number(p.platform),
          journal_url: String(p.journal_url || "").trim(),
          has_full_text: Boolean(p.has_full_text),
        }));
      }
    }

    return apiClient.patch(`/api/journals/${id}/`, clean);
  },

  /**
   * Publish journal (POST /api/journals/{id}/publish/)
   * Valida en el backend que la ficha esté completa.
   */
  publishJournal: async (id, licenses = []) => {
    return apiClient.post(`/api/journals/${id}/publish/`, {});
  },

  /**
   * Lifecycle endpoints
   */
  markObsoleteJournal: async (id) => {
    return apiClient.post(`/api/journals/${id}/mark-obsolete/`, {});
  },

  reactivateJournal: async (id) => {
    return apiClient.post(`/api/journals/${id}/reactivate/`, {});
  },

  deactivateJournal: async (id) => {
    return apiClient.post(`/api/journals/${id}/deactivate/`, {});
  },

  /**
   * Delete journal (DELETE /api/journals/{id}/)
   */
  deleteJournal: async (id, deleteExplanation = "") => {
    return apiClient.delete(`/api/journals/${id}/`, {
      delete_explanation: deleteExplanation.trim(),
    });
  },

  /**
   * Restore a logically deleted journal (POST /api/journals/{id}/restore/)
   */
  restoreJournal: async (id) => {
    return apiClient.post(`/api/journals/${id}/restore/`, {});
  },

  /**
   * List licenses (GET /api/journals/licenses/)
   */
  getLicenses: async (params = {}) => {
    try {
      const res = await apiClient.get("/api/journals/licenses/", params);
      if (Array.isArray(res)) return res;
      if (res && Array.isArray(res.results)) return res.results;
      return [];
    } catch (err) {
      console.error("Error fetching licenses:", err);
      throw err;
    }
  },

  /**
   * Create license (POST /api/journals/licenses/)
   */
  createLicense: async (data) => {
    return apiClient.post("/api/journals/licenses/", data);
  },

  /**
   * Partial update of a license (PATCH /api/journals/licenses/{id}/)
   */
  patchLicense: async (id, data) => {
    return apiClient.patch(`/api/journals/licenses/${id}/`, data);
  },

  /**
   * Delete license (DELETE /api/journals/licenses/{id}/)
   */
  deleteLicense: async (id, deleteExplanation) => {
    return apiClient.delete(`/api/journals/licenses/${id}/`, {
      delete_explanation: deleteExplanation,
    });
  },

  /**
   * Published platforms only — journals can only be associated to these.
   * Usa GET /api/platforms/public/ (o fallback a /api/platforms/?status=publicado).
   */
  getPublishedPlatforms: async () => {
    try {
      const res = await apiClient.get("/api/platforms/public/", { page_size: 200 });
      const list = Array.isArray(res) ? res : res?.results || [];
      return list;
    } catch {
      try {
        const fallbackRes = await apiClient.get("/api/platforms/", {
          status: "publicado",
          page_size: 200,
        });
        const list = Array.isArray(fallbackRes) ? fallbackRes : fallbackRes?.results || [];
        return list.filter((p) => String(p.status || "").toUpperCase() === "PUBLICADO");
      } catch {
        return [];
      }
    }
  },

  /**
   * Obtener áreas de conocimiento con filtro contextual:
   * GET /api/catalog/knowledge-areas/?available_for_journal={id}
   */
  getKnowledgeAreasForJournal: async (journalId = null) => {
    const endpoint = journalId
      ? `/api/catalog/knowledge-areas/?available_for_journal=${encodeURIComponent(journalId)}`
      : "/api/catalog/knowledge-areas/";
    return journalService.getCatalogData(endpoint, []);
  },

  /**
   * Helper to load catalog list safely from /api/catalog/{resource}/
   */
  getCatalogData: async (endpoint, fallback = []) => {
    try {
      const res = await apiClient.get(endpoint);
      if (Array.isArray(res)) return res;
      if (res && Array.isArray(res.results)) return res.results;
      return fallback;
    } catch {
      return fallback;
    }
  },

  /**
   * Load catalog options required by the journal form.
   */
  loadFormCatalogs: async (journalId = null) => {
    const [languages, countries, materialTypes, academicPrograms, editorials, publishedPlatforms, knowledgeAreas, licenses] =
      await Promise.all([
        journalService.getCatalogData("/api/catalog/languages/", [
          { id: 1, abbreviation: "ES", name: "Español" },
          { id: 2, abbreviation: "PT", name: "Portugués" },
          { id: 3, abbreviation: "EN", name: "Inglés" },
        ]),
        journalService.getCatalogData("/api/catalog/countries/", [
          { id: 1, abbreviation: "BR", name: "Brasil", emoji_flag: "🇧🇷" },
          { id: 2, abbreviation: "CO", name: "Colombia", emoji_flag: "🇨🇴" },
          { id: 3, abbreviation: "MX", name: "México", emoji_flag: "🇲🇽" },
          { id: 4, abbreviation: "US", name: "Estados Unidos", emoji_flag: "🇺🇸" },
        ]),
        journalService.getCatalogData("/api/catalog/material-types/", [
          { id: 1, name: "Revistas y artículos" },
          { id: 2, name: "Libros y Monografías" },
          { id: 3, name: "Tesis y Disertaciones" },
        ]),
        journalService.getCatalogData("/api/catalog/academic-programs/", [
          { id: 1, name: "Ingeniería de Sistemas" },
          { id: 2, name: "Ingeniería Industrial" },
          { id: 3, name: "Medicina" },
          { id: 4, name: "Todos los programas" },
        ]),
        journalService.getCatalogData("/api/catalog/editorials/").then(async (list) => {
          if (Array.isArray(list) && list.length > 0) return list;
          return journalService.getCatalogData("/api/catalog/editoriales/", []);
        }),
        journalService.getPublishedPlatforms(),
        journalService.getKnowledgeAreasForJournal(journalId),
        journalService.getLicenses(),
      ]);

    return {
      languages,
      countries,
      materialTypes,
      academicPrograms,
      editorials,
      publishedPlatforms,
      knowledgeAreas,
      licenses,
    };
  },
};