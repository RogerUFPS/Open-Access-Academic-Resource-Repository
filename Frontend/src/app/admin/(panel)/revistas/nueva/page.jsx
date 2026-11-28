"use client";

import React, { Suspense, useState, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import JournalForm from "@/features/admin/journals/components/JournalForm";
import { journalService } from "@/features/admin/journals/services/journalService";

function NewJournalPageInner() {
  const searchParams = useSearchParams();
  const journalId = searchParams.get("id");
  const isEdit = Boolean(journalId);
  let publishErrors = null;
  try {
    publishErrors = JSON.parse(searchParams.get("publishErrors") || "null");
  } catch {
    publishErrors = null;
  }

  // Resultado de la carga junto con el id que lo produjo: si el id de la URL
  // cambia, la carga se deriva sin reiniciar estado dentro del efecto.
  const [loaded, setLoaded] = useState({ id: null, data: null, error: null });
  const loading = isEdit && loaded.id !== journalId;
  const journalData = loaded.data;
  const error = loaded.id === journalId ? loaded.error : null;

  useEffect(() => {
    if (!(isEdit && journalId)) return undefined;
    let active = true;
    journalService
      .getJournalById(journalId)
      .then((data) => {
        if (active) setLoaded({ id: journalId, data, error: null });
      })
      .catch((err) => {
        if (active) setLoaded({ id: journalId, data: null, error: err.message });
      });
    return () => {
      active = false;
    };
  }, [isEdit, journalId]);

  if (isEdit) {
    if (loading) {
      return (
        <div className="p-16 text-center text-gray-500">
          <div className="w-8 h-8 border-2 border-[#C8102E] border-t-transparent rounded-full animate-spin mx-auto mb-3"></div>
          <p className="text-xs font-medium">Cargando datos de la revista para edición...</p>
        </div>
      );
    }

    if (error) {
      return (
        <div className="p-8 text-center text-rose-600 bg-white rounded-2xl border border-gray-200">
          <p className="font-semibold text-sm">Error al cargar para edición: {error}</p>
        </div>
      );
    }

    return <JournalForm initialData={journalData} isEdit={true} publishErrors={publishErrors} />;
  }

  return <JournalForm isEdit={false} />;
}

export default function NewJournalPage() {
  return (
    <Suspense
      fallback={
        <div className="p-16 text-center text-gray-500">
          <div className="w-8 h-8 border-2 border-[#C8102E] border-t-transparent rounded-full animate-spin mx-auto mb-3"></div>
          <p className="text-xs font-medium">Cargando formulario de revista...</p>
        </div>
      }
    >
      <NewJournalPageInner />
    </Suspense>
  );
}