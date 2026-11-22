"use client";

import { useQuery } from "@tanstack/react-query";
import { getCatalogEntry, getFilterOptions, getPlatforms } from "@/features/admin/harvesting/harvesting";
import { queryKeys } from "@/shared/query/queryKeys";

export const CATALOG_STALE_TIME = 10 * 60 * 1000;

// La configuración de filtros es estática en el backend: se cachea por más tiempo.
export function useFilterOptions() {
  return useQuery({
    queryKey: queryKeys.harvests.filterOptions,
    queryFn: ({ signal }) => getFilterOptions(signal),
    staleTime: 30 * 60 * 1000,
  });
}

/** Todas las plataformas, ordenadas por nombre. Se invalida junto con `queryKeys.platforms.all`. */
export function useAllPlatforms() {
  return useQuery({
    queryKey: queryKeys.platforms.list({ ordering: "name", all: true }),
    queryFn: ({ signal }) => getPlatforms(signal),
    staleTime: 5 * 60 * 1000,
  });
}

/** Una entrada del catálogo; comparte caché entre el selector y el resumen de filtros. */
export function useCatalogEntry(endpoint, id) {
  return useQuery({
    queryKey: queryKeys.catalog.entry(endpoint, id),
    queryFn: ({ signal }) => getCatalogEntry(endpoint, id, signal),
    enabled: Boolean(endpoint) && id !== "" && id != null,
    staleTime: CATALOG_STALE_TIME,
  });
}

/** Estado de carga y error con el mismo criterio que el resto del panel. */
export function queryStatus(query, fallback = "Error al cargar los datos.") {
  return {
    loading: query.isPending || (query.isError && query.isFetching),
    error: query.isError && !query.isFetching ? query.error?.message || fallback : "",
  };
}
