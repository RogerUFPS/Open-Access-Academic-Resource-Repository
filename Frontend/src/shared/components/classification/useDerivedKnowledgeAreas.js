"use client";

import { useEffect, useMemo, useState } from "react";
import { academicProgramService } from "@/shared/services/catalogService";

const toKey = (ids = []) =>
  [...new Set(ids.map(Number).filter((id) => Number.isFinite(id)))].sort((a, b) => a - b).join(",");

/**
 * Áreas derivadas para mostrar en el formulario.
 *
 * - Mientras la selección coincide con la guardada, usa `knowledge_areas`
 *   de la respuesta del backend (fuente de verdad).
 * - Si cambia, calcula una vista previa a partir de
 *   GET /api/catalog/academic-programs/{id}/knowledge-areas/.
 */
export default function useDerivedKnowledgeAreas({ programIds, savedProgramIds, savedAreas }) {
  const key = toKey(programIds);
  const savedKey = toKey(savedProgramIds);
  const useSaved = Array.isArray(savedAreas) && key === savedKey;
  const [attempt, setAttempt] = useState(0);
  const requestKey = `${key}#${attempt}`;
  const [result, setResult] = useState({ requestKey: null, areas: [], error: null });

  useEffect(() => {
    if (useSaved || !key) return undefined;
    let cancelled = false;
    academicProgramService
      .previewKnowledgeAreas(key.split(",").map(Number))
      .then((areas) => {
        if (!cancelled) setResult({ requestKey, areas, error: null });
      })
      .catch((error) => {
        if (!cancelled) {
          setResult({ requestKey, areas: [], error: error?.message || "No se pudieron cargar las áreas." });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [key, requestKey, useSaved]);

  return useMemo(() => {
    const retry = () => setAttempt((value) => value + 1);
    if (useSaved) return { areas: savedAreas, loading: false, error: null, isPreview: false, retry };
    if (!key) return { areas: [], loading: false, error: null, isPreview: true, retry };
    if (result.requestKey !== requestKey) return { areas: [], loading: true, error: null, isPreview: true, retry };
    return { areas: result.areas, loading: false, error: result.error, isPreview: true, retry };
  }, [useSaved, savedAreas, key, requestKey, result]);
}
