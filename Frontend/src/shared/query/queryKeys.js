// Claves de caché por recurso. Invalidar la raíz (`queryKeys.platforms.all`)
// revalida todas las listas de ese recurso, sea cual sea su filtro o página.
export const queryKeys = {
  platforms: {
    all: ["platforms"],
    list: (params) => ["platforms", "list", params],
  },
  journals: {
    all: ["journals"],
    list: (params) => ["journals", "list", params],
  },
  harvests: {
    all: ["harvests"],
    lists: ["harvests", "list"],
    list: (page) => ["harvests", "list", page],
    journals: (harvestId, page) => ["harvests", "journals", harvestId, page],
    schedules: ["harvests", "schedules"],
    sourceCount: ["harvests", "source-count"],
    filterOptions: ["harvests", "filter-options"],
  },
  catalog: {
    all: ["catalog"],
    options: (endpoint, search) => ["catalog", "options", endpoint, search],
    entry: (endpoint, id) => ["catalog", "entry", endpoint, Number(id)],
  },
  accounts: {
    all: ["accounts"],
    viewer: ["accounts", "viewer"],
    users: ["accounts", "users"],
    presets: ["accounts", "presets"],
  },
  agent: {
    all: ["agent"],
    models: ["agent", "models"],
    conversations: ["agent", "conversations"],
    conversationList: (params) => ["agent", "conversations", "list", params],
    conversationDetail: (id, page) => ["agent", "conversations", "detail", id, page],
    analyticsTopics: (params) => ["agent", "analytics", "topics", params],
    analyticsQueries: (params) => ["agent", "analytics", "queries", params],
  },
  indicators: {
    overview: ["indicators", "overview"],
  },
};
