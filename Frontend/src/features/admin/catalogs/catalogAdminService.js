import { apiClient } from "@/shared/services/apiClient";

export const CATALOG_RESOURCES = {
  institutions: {
    label: "Instituciones",
    singular: "institución",
    description: "Administra las instituciones disponibles para las plataformas.",
    endpoint: "/api/catalog/institutions/",
    fields: [{ name: "name", label: "Nombre" }],
  },
  languages: {
    label: "Idiomas",
    singular: "idioma",
    description: "Administra los idiomas disponibles en el repositorio.",
    endpoint: "/api/catalog/languages/",
    fields: [
      { name: "name", label: "Nombre" },
      { name: "abbreviation", label: "Abreviatura" },
    ],
  },
  countries: {
    label: "Países",
    singular: "país",
    description: "Administra los países y sus banderas.",
    endpoint: "/api/catalog/countries/",
    fields: [
      { name: "name", label: "Nombre" },
      { name: "abbreviation", label: "Abreviatura" },
      { name: "emoji_flag", label: "Bandera (emoji)" },
    ],
  },
};

function endpointFor(resource) {
  const config = CATALOG_RESOURCES[resource];
  if (!config) throw new Error(`Catálogo desconocido: ${resource}`);
  return config.endpoint;
}

export const catalogAdminService = {
  list: (resource, { archived = false, search = "", ordering = "name", page = 1, pageSize = 20 } = {}) => {
    const endpoint = endpointFor(resource);
    return apiClient.get(`${endpoint}${archived ? "archived/" : ""}`, {
      search: search.trim(),
      ordering,
      page: String(page),
      page_size: String(pageSize),
    });
  },

  get: (resource, id) => apiClient.get(`${endpointFor(resource)}${encodeURIComponent(id)}/`),

  create: (resource, payload) => apiClient.post(endpointFor(resource), payload),

  update: (resource, id, payload) =>
    apiClient.patch(`${endpointFor(resource)}${encodeURIComponent(id)}/`, payload),

  archive: (resource, id, deleteExplanation) =>
    apiClient.delete(`${endpointFor(resource)}${encodeURIComponent(id)}/`, {
      delete_explanation: deleteExplanation,
    }),

  restore: (resource, id) =>
    apiClient.post(`${endpointFor(resource)}${encodeURIComponent(id)}/restore/`, {}),
};
