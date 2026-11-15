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
};
