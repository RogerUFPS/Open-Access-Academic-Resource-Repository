"use client";

import React, { useState } from "react";
import { journalService } from "../services/journalService";
import { Button } from "@/components/ui/button";
import { CheckCircle2, X, AlertCircle } from "lucide-react";

export default function PublishJournalModal({ journal, isOpen, onClose, onSuccess }) {
  const [publishing, setPublishing] = useState(false);
  const [publicationErrors, setPublicationErrors] = useState([]);

  const fieldLabels = {
    detail: "Publicación",
    title: "Título",
    issn: "ISSN",
    editorial: "Editorial",
    publication_date: "Fecha de publicación",
    languages: "Idiomas",
    countries: "Países",
    knowledge_areas: "Áreas de conocimiento",
    material_types: "Tipos de material",
    academic_programs: "Programas académicos",
    platforms: "Plataformas",
    licenses: "Licencias",
  };

  const normalizeErrors = (payload, fallback) => {
    if (!payload || typeof payload !== "object") {
      return [fallback];
    }
    const entries = Object.entries(payload).filter(([key]) =>
      !["detail", "message", "error"].includes(key)
    );
    if (entries.length > 0) {
      return entries.flatMap(([field, value]) => {
        const messages = Array.isArray(value) ? value : [value];
        return messages.map((message) => ({
          field: fieldLabels[field] || field,
          message: typeof message === "object" ? JSON.stringify(message) : String(message),
        }));
      });
    }
    const general = payload.detail || payload.message || payload.error || fallback;
    return [{ field: "Publicación", message: String(general) }];
  };

  if (!isOpen || !journal) return null;

  const handleConfirmPublish = async () => {
    setPublishing(true);
    setPublicationErrors([]);
    try {
      await journalService.publishJournal(journal.id);
      onSuccess?.(`Revista "${journal.title}" publicada exitosamente.`);
      onClose();
    } catch (err) {
      setPublicationErrors(normalizeErrors(err.data, err.message || "No se pudo publicar la revista."));
    } finally {
      setPublishing(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-xs">
      <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-2xl border border-gray-100">
        <div className="flex items-center justify-between pb-4 border-b border-gray-100">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-emerald-100 text-emerald-700 flex items-center justify-center">
              <CheckCircle2 className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-bold text-gray-900 text-base">Publicar revista</h3>
              <p className="text-xs text-gray-500 font-medium truncate max-w-xs">{journal.title}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            disabled={publishing}
            className="text-gray-400 hover:text-gray-600 p-1.5 rounded-lg hover:bg-gray-100"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <p className="mt-4 text-xs text-gray-600 leading-relaxed">
          La revista será publicada y quedará activa en el repositorio.
        </p>

        {publicationErrors.length > 0 && (
          <div className="mt-4 p-3 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 text-xs flex items-start gap-2">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <div>
              <p className="font-bold mb-2">Complete estos datos antes de publicar:</p>
              <ul className="space-y-1.5">
                {publicationErrors.map((item, index) => (
                  <li key={`${item.field}-${index}`} className="leading-relaxed">
                    <span className="font-semibold">{item.field}:</span> {item.message}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}

        <div className="mt-6 flex justify-end gap-3">
          <Button type="button" variant="outline" onClick={onClose} disabled={publishing}>
            Cancelar
          </Button>
          <Button
            type="button"
            onClick={handleConfirmPublish}
            disabled={publishing}
            className="bg-emerald-600 hover:bg-emerald-700 text-white"
          >
            {publishing ? "Publicando..." : "Publicar"}
          </Button>
        </div>
      </div>
    </div>
  );
}
