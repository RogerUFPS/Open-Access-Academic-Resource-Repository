"use client";

import React, { useState } from "react";
import Link from "next/link";
import { journalService } from "../services/journalService";
import { Button } from "@/components/ui/button";
import { PublishChecklist } from "@/shared/components/forms/FormParts";
import { errorSummary, toFieldErrors } from "@/shared/utils/formErrors";
import { buildJournalChecklist, isChecklistComplete } from "@/shared/utils/publishChecklists";
import { CheckCircle2, X, AlertCircle } from "lucide-react";

function journalChecklist(journal) {
  return buildJournalChecklist({
    issn: journal.issn,
    title: journal.title,
    editorial: journal.editorial,
    publicationDate: journal.publication_date,
    languages: journal.languages,
    countries: journal.countries,
    materialTypes: journal.material_types,
    academicPrograms: journal.academic_programs,
    platforms: (journal.platforms || []).map((entry) => ({
      platform: entry.platform ?? entry.id,
      published: entry.is_public === true || String(entry.status || "").toUpperCase() === "PUBLICADO",
    })),
    licenses: journal.licenses,
  });
}

export default function PublishJournalModal({ journal, isOpen, onClose, onSuccess }) {
  const [publishing, setPublishing] = useState(false);
  const [publicationErrors, setPublicationErrors] = useState({ fields: {}, message: null });

  if (!isOpen || !journal) return null;

  const checklist = journalChecklist(journal);
  const checklistComplete = isChecklistComplete(checklist);
  const summary = errorSummary(publicationErrors.fields);
  const hasErrors = summary.length > 0 || Boolean(publicationErrors.message);

  const handleClose = () => {
    setPublicationErrors({ fields: {}, message: null });
    onClose();
  };

  const handleConfirmPublish = async () => {
    setPublishing(true);
    setPublicationErrors({ fields: {}, message: null });
    try {
      await journalService.publishJournal(journal.id);
      onSuccess?.(`Revista "${journal.title}" publicada exitosamente.`);
      handleClose();
    } catch (err) {
      const fields = toFieldErrors(err.data);
      setPublicationErrors({
        fields,
        message: Object.keys(fields).length ? null : err.message || "No se pudo publicar la revista.",
      });
    } finally {
      setPublishing(false);
    }
  };

  const reviewHref = `/admin/revistas/nueva?id=${journal.id}&publishErrors=${encodeURIComponent(
    JSON.stringify(publicationErrors.fields)
  )}`;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-xs">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="publish-journal-title"
        className="bg-white rounded-2xl max-w-md w-full p-6 shadow-2xl border border-gray-100 max-h-[90vh] overflow-y-auto"
      >
        <div className="flex items-center justify-between pb-4 border-b border-gray-100">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-emerald-100 text-emerald-700 flex items-center justify-center">
              <CheckCircle2 className="w-5 h-5" />
            </div>
            <div>
              <h3 id="publish-journal-title" className="font-bold text-gray-900 text-base">Publicar revista</h3>
              <p className="text-xs text-gray-500 font-medium truncate max-w-xs">{journal.title}</p>
            </div>
          </div>
          <button
            onClick={handleClose}
            disabled={publishing}
            aria-label="Cerrar"
            className="text-gray-400 hover:text-gray-600 p-1.5 rounded-lg hover:bg-gray-100"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <p className="mt-4 text-xs text-gray-600 leading-relaxed">
          La revista será publicada y quedará activa en el repositorio.
        </p>

        <div className="mt-4">
          <PublishChecklist items={checklist} />
        </div>

        {hasErrors && (
          <div role="alert" className="mt-4 p-3 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 text-xs flex items-start gap-2">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <div>
              <p className="font-bold mb-2">Complete estos datos antes de publicar:</p>
              {publicationErrors.message && <p>{publicationErrors.message}</p>}
              <ul className="space-y-1.5">
                {summary.map((item) => (
                  <li key={item.field} className="leading-relaxed">
                    <span className="font-semibold">{item.label}:</span> {item.message}
                  </li>
                ))}
              </ul>
              {summary.length > 0 && (
                <Link href={reviewHref} className="mt-2 inline-block font-semibold text-[#7f1218] underline">
                  Revisar datos de la revista
                </Link>
              )}
            </div>
          </div>
        )}

        <div className="mt-6 flex justify-end gap-3">
          <Button type="button" variant="outline" onClick={handleClose} disabled={publishing}>
            Cancelar
          </Button>
          <Button
            type="button"
            onClick={handleConfirmPublish}
            disabled={publishing || !checklistComplete}
            title={checklistComplete ? undefined : "Completa los requisitos de publicación"}
            className="bg-emerald-600 hover:bg-emerald-700 text-white"
          >
            {publishing ? "Publicando..." : "Publicar"}
          </Button>
        </div>
      </div>
    </div>
  );
}
