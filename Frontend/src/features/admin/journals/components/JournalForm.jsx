"use client";

import React, { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { journalService } from "../services/journalService";
import { capitalizeWords } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useToast } from "@/components/ui/use-toast";
import { ResourceImageUploader } from "@/shared/components/ResourceImageUploader";
import {
  CatalogCheckboxGrid,
  FieldError,
  FormErrorSummary,
  FormSection,
  PublishChecklist,
  fieldAnchorId,
  fieldErrorId,
} from "@/shared/components/forms/FormParts";
import AcademicProgramSelect from "@/shared/components/classification/AcademicProgramSelect";
import DerivedKnowledgeAreas from "@/shared/components/classification/DerivedKnowledgeAreas";
import useDerivedKnowledgeAreas from "@/shared/components/classification/useDerivedKnowledgeAreas";
import { toFieldErrors } from "@/shared/utils/formErrors";
import { buildJournalChecklist, isChecklistComplete } from "@/shared/utils/publishChecklists";
import { ArrowLeft, CheckCircle2, ExternalLink, Globe, Plus, Save, Trash2 } from "lucide-react";

function extractIds(list) {
  if (!Array.isArray(list)) return [];
  return list
    .map((item) => {
      if (item == null) return null;
      if (typeof item === "object") return item.id ?? null;
      const parsed = Number(item);
      return Number.isNaN(parsed) ? null : parsed;
    })
    .filter((id) => id !== null && id !== undefined && id !== "");
}

function extractSingleId(value) {
  if (value === null || value === undefined || value === "") return "";
  if (typeof value === "object") return value.id ?? "";
  return Number(value);
}

let rowSequence = 0;
function emptyPlatformRow() {
  rowSequence += 1;
  return { _key: `new-${rowSequence}`, platform: "", journal_url: "", has_full_text: true };
}

function formFromRecord(record) {
  return {
    issn: record.issn || "",
    title: record.title || "",
    editorial: extractSingleId(record.editorial),
    publication_date: String(record.publication_date || "").slice(0, 10),
    has_apc: Boolean(record.has_apc),
    url_image: record.url_image || "",
    languages: extractIds(record.languages),
    countries: extractIds(record.countries),
    material_types: extractIds(record.material_types),
    academic_programs: extractIds(record.academic_programs), // obligatorio para publicar
    licenses: extractIds(record.licenses),
    platforms: (record.platforms || []).map((p, index) => ({
      _key: `existing-${p.relation_id ?? p.id ?? index}`,
      platform: typeof p.platform === "object" && p.platform !== null ? p.platform.id : p.platform ?? p.id,
      name: p.name || (typeof p.platform === "object" ? p.platform?.name : ""),
      status: p.status,
      is_public: p.is_public,
      journal_url: p.journal_url || "",
      start_period: String(p.start_period || "").slice(0, 10),
      finish_period: String(p.finish_period || "").slice(0, 10),
      has_full_text: Boolean(p.has_full_text),
    })),
  };
}

function emptyForm() {
  return {
    issn: "",
    title: "",
    editorial: "",
    publication_date: "",
    has_apc: false,
    url_image: "",
    languages: [],
    countries: [],
    material_types: [],
    academic_programs: [],
    platforms: [emptyPlatformRow()],
    licenses: [],
  };
}

function journalStatus(record) {
  if (record?.active) return { label: "Activa", className: "bg-emerald-50 text-emerald-800 border-emerald-200" };
  if (record?.validated_at) return { label: "Desactivada", className: "bg-gray-100 text-gray-700 border-gray-200" };
  return { label: "Borrador", className: "bg-amber-50 text-amber-800 border-amber-200" };
}

const cardClass = "bg-white border border-gray-200 rounded-xl p-3 shadow-2xs space-y-1";
const labelClass = "text-[11px] font-medium text-gray-500 uppercase block";
const inputClass = "border-0 p-0 text-xs shadow-none focus-visible:ring-0 h-6 font-semibold text-gray-900";
const platformFieldClass =
  "w-full h-9 px-3 text-xs font-medium text-slate-900 bg-slate-50 border border-slate-300 rounded-lg shadow-none outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 focus-visible:ring-2 focus-visible:ring-blue-500/20";

export default function JournalForm({ initialData = null, isEdit = false, publishErrors = null }) {
  const router = useRouter();
  const { toast } = useToast();

  const [catalogs, setCatalogs] = useState({
    languages: [],
    countries: [],
    materialTypes: [],
    academicPrograms: [],
    editorials: [],
    publishedPlatforms: [],
    licenses: [],
  });
  const [loadingCatalogs, setLoadingCatalogs] = useState(true);

  // Último estado confirmado por el backend (fuente de verdad tras guardar).
  const [record, setRecord] = useState(initialData);
  const [formData, setFormData] = useState(() => (initialData ? formFromRecord(initialData) : emptyForm()));
  const [submitting, setSubmitting] = useState(null); // null | "save" | "publish"
  const [fieldErrors, setFieldErrors] = useState(() => toFieldErrors(publishErrors));
  const [formError, setFormError] = useState(() =>
    publishErrors && Object.keys(publishErrors).length > 0
      ? "La revista no se pudo publicar. Corrige los campos indicados."
      : null
  );
  const [pendingImage, setPendingImage] = useState(null);

  useEffect(() => {
    let cancelled = false;
    journalService
      .loadFormCatalogs()
      .then((catData) => {
        if (!cancelled) setCatalogs(catData);
      })
      .catch((err) => console.error("Error loading catalogs:", err))
      .finally(() => {
        if (!cancelled) setLoadingCatalogs(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const recordId = record?.id ?? null;
  const status = journalStatus(record);

  const knownProgramNames = useMemo(
    () => Object.fromEntries(catalogs.academicPrograms.map((program) => [program.id, program.name])),
    [catalogs.academicPrograms]
  );
  const savedProgramIds = useMemo(() => extractIds(record?.academic_programs), [record]);
  const derivedAreas = useDerivedKnowledgeAreas({
    programIds: formData.academic_programs,
    savedProgramIds,
    savedAreas: record ? record.knowledge_areas || [] : undefined,
  });

  const publishedIds = useMemo(
    () => new Set(catalogs.publishedPlatforms.map((platform) => String(platform.id))),
    [catalogs.publishedPlatforms]
  );
  const isRowPublished = (row) =>
    publishedIds.has(String(row.platform)) || row.is_public === true || String(row.status || "").toUpperCase() === "PUBLICADO";

  const checklist = buildJournalChecklist({
    issn: formData.issn,
    title: formData.title,
    editorial: formData.editorial,
    publicationDate: formData.publication_date,
    languages: formData.languages,
    countries: formData.countries,
    materialTypes: formData.material_types,
    academicPrograms: formData.academic_programs,
    platforms: formData.platforms.map((row) => ({ platform: row.platform, published: isRowPublished(row) })),
    licenses: formData.licenses,
  }).map((item) => ({
    ...item,
    failed: Boolean(fieldErrors[item.key] || (item.key === "issn" && fieldErrors.title)),
  }));
  const checklistComplete = isChecklistComplete(checklist);

  const updateField = (field, value) => {
    setFormData((current) => ({ ...current, [field]: value }));
    if (fieldErrors[field]) setFieldErrors((current) => ({ ...current, [field]: null }));
  };

  const toggleInList = (field, id) => {
    const numericId = Number(id);
    const current = formData[field] || [];
    updateField(field, current.includes(numericId) ? current.filter((item) => item !== numericId) : [...current, numericId]);
  };

  const updatePlatformRow = (index, patch) => {
    setFormData((current) => {
      const next = [...current.platforms];
      next[index] = { ...next[index], ...patch };
      return { ...current, platforms: next };
    });
    if (fieldErrors.platforms) setFieldErrors((current) => ({ ...current, platforms: null }));
  };

  const addPlatformRow = () =>
    setFormData((current) => ({ ...current, platforms: [...current.platforms, emptyPlatformRow()] }));

  const removePlatformRow = (index) =>
    setFormData((current) => ({ ...current, platforms: current.platforms.filter((_, i) => i !== index) }));

  const showErrors = (message, errors = {}) => {
    setFieldErrors(errors);
    setFormError(message);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const handleSubmit = async (action = "save") => {
    setFormError(null);
    setFieldErrors({});

    const localErrors = {};
    if (!formData.title.trim()) localErrors.title = "El título es requerido.";
    if (!formData.issn.trim()) localErrors.issn = "El ISSN es requerido.";
    const incompleteRow = formData.platforms.findIndex((row) => row.platform && !String(row.journal_url || "").trim());
    if (incompleteRow >= 0) {
      localErrors.platforms = `La URL específica de la revista es requerida en la plataforma #${incompleteRow + 1}.`;
    }
    if (action === "publish" && formData.academic_programs.length === 0) {
      localErrors.academic_programs = "Selecciona al menos un programa para publicar.";
    }
    if (Object.keys(localErrors).length > 0) {
      showErrors("Revisa los campos marcados.", localErrors);
      return;
    }

    setSubmitting(action);

    // 1. Guardar (POST o PATCH). knowledge_areas nunca se envía.
    const payload = {
      issn: formData.issn.trim(),
      title: formData.title.trim(),
      editorial: formData.editorial ? Number(formData.editorial) : null,
      publication_date: formData.publication_date || null,
      url_image: formData.url_image ? formData.url_image.trim() : null,
      has_apc: Boolean(formData.has_apc),
      languages: formData.languages,
      countries: formData.countries,
      material_types: formData.material_types,
      academic_programs: formData.academic_programs, // puede ir vacío en un borrador
      licenses: formData.licenses,
      platforms: formData.platforms
        .filter((row) => row.platform)
        .map((row) => ({
          platform: Number(row.platform),
          journal_url: String(row.journal_url).trim(),
          has_full_text: Boolean(row.has_full_text),
        })),
    };

    let saved;
    try {
      saved = recordId
        ? await journalService.patchJournal(recordId, payload)
        : await journalService.createJournal(payload);
    } catch (err) {
      console.error("Form submit error:", err);
      showErrors(err.message || "Error al guardar la revista.", toFieldErrors(err.data));
      setSubmitting(null);
      return;
    }

    // 2. La respuesta es la fuente de verdad (academic_programs, knowledge_areas…).
    const savedId = saved?.id ?? recordId;
    if (saved && typeof saved === "object") {
      setRecord(saved);
      setFormData(formFromRecord(saved));
    }

    if (pendingImage && savedId) {
      try {
        const updated = await journalService.uploadJournalImage(savedId, pendingImage);
        setPendingImage(null);
        setFormData((current) => ({ ...current, url_image: updated?.url_image || "" }));
      } catch (imageError) {
        toast({
          title: "No se pudo subir la imagen",
          description: imageError.message || "La revista se guardó, pero no se pudo subir la imagen.",
          variant: "destructive",
        });
      }
    }

    // 3. Publicar.
    if (action === "publish" && savedId) {
      try {
        await journalService.publishJournal(savedId);
      } catch (err) {
        console.warn("Error en la publicación:", err);
        showErrors(
          "Los cambios se guardaron, pero la revista no se publicó. Corrige los campos indicados.",
          toFieldErrors(err.data)
        );
        setSubmitting(null);
        return;
      }
      toast({ title: "Revista publicada", description: `“${saved?.title || formData.title}” quedó activa en el repositorio.` });
      router.push(`/admin/revistas/${savedId}`);
      return;
    }

    toast({ title: "Cambios guardados" });
    router.push(savedId ? `/admin/revistas/${savedId}` : "/admin/revistas");
  };

  if (loadingCatalogs) {
    return (
      <div className="p-16 text-center text-gray-500">
        <div className="w-8 h-8 border-2 border-[#C8102E] border-t-transparent rounded-full animate-spin mx-auto mb-3"></div>
        <p className="text-xs font-medium">Cargando catálogos del sistema...</p>
      </div>
    );
  }

  const describedBy = (field) => (fieldErrors[field] ? fieldErrorId(field) : undefined);
  const invalid = (field) => (fieldErrors[field] ? "true" : undefined);

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        handleSubmit("save");
      }}
      className="max-w-6xl mx-auto"
      noValidate
    >
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center gap-3 flex-wrap">
          <button
            type="button"
            onClick={() => router.back()}
            aria-label="Volver"
            className="p-1.5 rounded-lg bg-white border border-gray-200 text-gray-600 hover:bg-gray-50 transition-colors cursor-pointer"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>
          <h1 className="text-2xl font-bold text-gray-900 tracking-tight">
            {recordId || isEdit ? "Editar revista" : "Nueva revista"}
          </h1>
          <span className={`text-[11px] font-bold px-2.5 py-0.5 rounded-full border ${status.className}`}>
            {status.label}
          </span>
        </div>
        <p className="text-xs text-gray-500 mt-1">
          Puedes guardar un borrador incompleto. Para publicar, completa los requisitos del panel lateral.
        </p>
      </div>

      <div className="mb-6">
        <FormErrorSummary message={formError} fieldErrors={fieldErrors} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_18rem] gap-6 items-start">
        <div className="space-y-6 min-w-0">
          {/* 1. Identificación */}
          <FormSection id="journal-identification" number={1} title="Identificación">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div id={fieldAnchorId("issn")} className={cardClass}>
                <label htmlFor="issn" className={labelClass}>ISSN *</label>
                <Input
                  id="issn"
                  required
                  value={formData.issn}
                  onChange={(e) => updateField("issn", e.target.value)}
                  aria-invalid={invalid("issn")}
                  aria-describedby={describedBy("issn")}
                  placeholder="Ej. 1234-5678"
                  className={inputClass}
                />
                <FieldError field="issn" message={fieldErrors.issn} />
              </div>

              <div id={fieldAnchorId("title")} className={cardClass}>
                <label htmlFor="title" className={labelClass}>Título *</label>
                <Input
                  id="title"
                  required
                  value={formData.title}
                  onChange={(e) => updateField("title", e.target.value)}
                  aria-invalid={invalid("title")}
                  aria-describedby={describedBy("title")}
                  placeholder="Nombre de la revista"
                  className={inputClass}
                />
                <FieldError field="title" message={fieldErrors.title} />
              </div>

              <div id={fieldAnchorId("editorial")} className={cardClass}>
                <label htmlFor="editorial" className={labelClass}>Editorial</label>
                <select
                  id="editorial"
                  value={formData.editorial}
                  onChange={(e) => updateField("editorial", e.target.value)}
                  aria-invalid={invalid("editorial")}
                  aria-describedby={describedBy("editorial")}
                  className="w-full text-xs font-semibold text-gray-900 outline-none bg-transparent h-6 cursor-pointer"
                >
                  <option value="">Seleccione una editorial</option>
                  {catalogs.editorials.map((ed) => (
                    <option key={ed.id} value={ed.id}>
                      {capitalizeWords(ed.name || ed.nombre)}
                    </option>
                  ))}
                </select>
                <FieldError field="editorial" message={fieldErrors.editorial} />
              </div>

              <div id={fieldAnchorId("publication_date")} className={cardClass}>
                <label htmlFor="publication_date" className={labelClass}>Fecha de publicación</label>
                <Input
                  id="publication_date"
                  type="date"
                  value={formData.publication_date}
                  onChange={(e) => updateField("publication_date", e.target.value)}
                  aria-invalid={invalid("publication_date")}
                  aria-describedby={describedBy("publication_date")}
                  className="border-0 p-0 text-xs shadow-none focus-visible:ring-0 h-6 text-gray-900 font-medium"
                />
                <FieldError field="publication_date" message={fieldErrors.publication_date} />
              </div>
            </div>
          </FormSection>

          {/* 2. Acceso y licencias */}
          <FormSection id="journal-access" number={2} title="Acceso y licencias">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div id={fieldAnchorId("url_image")} className={cardClass}>
                <span className={labelClass}>Imagen (opcional)</span>
                <ResourceImageUploader
                  value={formData.url_image}
                  alt={`Imagen de ${formData.title || "la revista"}`}
                  resourceId={recordId}
                  uploadImage={journalService.uploadJournalImage}
                  deleteImage={journalService.deleteJournalImage}
                  onImageChange={(urlImage) => setFormData((current) => ({ ...current, url_image: urlImage || "" }))}
                  onPendingFileChange={setPendingImage}
                />
                <FieldError field="url_image" message={fieldErrors.url_image} />
              </div>

              <div id={fieldAnchorId("has_apc")} className={`${cardClass} h-fit`}>
                <label htmlFor="has_apc" className={labelClass}>¿Tiene APC?</label>
                <select
                  id="has_apc"
                  value={formData.has_apc ? "true" : "false"}
                  onChange={(e) => updateField("has_apc", e.target.value === "true")}
                  className="w-full text-xs font-semibold text-gray-900 outline-none bg-transparent h-6 cursor-pointer"
                >
                  <option value="false">No</option>
                  <option value="true">Sí</option>
                </select>
                <FieldError field="has_apc" message={fieldErrors.has_apc} />
              </div>

              <div className="md:col-span-2">
                <CatalogCheckboxGrid
                  field="licenses"
                  label="Licencias"
                  items={catalogs.licenses}
                  selected={formData.licenses}
                  onToggle={(id) => toggleInList("licenses", id)}
                  error={fieldErrors.licenses}
                />
              </div>
            </div>
          </FormSection>

          {/* 3. Clasificación del catálogo */}
          <FormSection id="journal-catalog" number={3} title="Clasificación del catálogo">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <CatalogCheckboxGrid
                field="languages"
                label="Idiomas"
                items={catalogs.languages}
                selected={formData.languages}
                onToggle={(id) => toggleInList("languages", id)}
                renderLabel={(lang) =>
                  lang.abbreviation
                    ? `${lang.abbreviation.toUpperCase()} - ${capitalizeWords(lang.name)}`
                    : capitalizeWords(lang.name)
                }
                error={fieldErrors.languages}
              />
              <CatalogCheckboxGrid
                field="countries"
                label="País"
                items={catalogs.countries}
                selected={formData.countries}
                onToggle={(id) => toggleInList("countries", id)}
                renderLabel={(country) =>
                  country.emoji_flag
                    ? `${country.emoji_flag} ${capitalizeWords(country.name)}`
                    : capitalizeWords(country.name)
                }
                error={fieldErrors.countries}
              />
              <div className="md:col-span-2">
                <CatalogCheckboxGrid
                  field="material_types"
                  label="Tipo de material"
                  items={catalogs.materialTypes}
                  selected={formData.material_types}
                  onToggle={(id) => toggleInList("material_types", id)}
                  error={fieldErrors.material_types}
                />
              </div>
            </div>
          </FormSection>

          {/* 4. Clasificación académica */}
          <FormSection
            id="journal-academic"
            number={4}
            title="Clasificación académica"
            description="Selecciona solo programas académicos. Las áreas del conocimiento las calcula el backend."
          >
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <AcademicProgramSelect
                required
                hint="Obligatorio para publicar. Puedes guardar el borrador sin programas."
                value={formData.academic_programs}
                onChange={(ids) => updateField("academic_programs", ids)}
                knownNames={knownProgramNames}
                error={fieldErrors.academic_programs}
                emptyMessage="Selecciona al menos un programa para publicar."
              />
              <DerivedKnowledgeAreas
                areas={derivedAreas.areas}
                loading={derivedAreas.loading}
                error={derivedAreas.error}
                onRetry={derivedAreas.retry}
                isPreview={derivedAreas.isPreview}
                emptyMessage="Selecciona programas académicos para ver las áreas."
              />
            </div>
          </FormSection>

          {/* 5. Plataformas */}
          <FormSection
            id="journal-platforms"
            number={5}
            title="Plataformas"
            description="Para publicar, al menos una plataforma asociada debe estar publicada."
            aside={
              <Button
                type="button"
                variant="outline"
                onClick={addPlatformRow}
                className="rounded-xl border-[#C8102E] text-[#C8102E] text-xs px-3 py-1.5 font-medium hover:bg-[#C8102E]/5 cursor-pointer gap-1.5"
              >
                <Plus className="w-3.5 h-3.5" aria-hidden="true" />
                Añadir plataforma
              </Button>
            }
          >
            <div id={fieldAnchorId("platforms")}>
              <FieldError field="platforms" message={fieldErrors.platforms} />
            </div>

            {formData.platforms.length === 0 ? (
              <div className="p-6 rounded-xl bg-white border border-slate-200/80 text-center text-xs text-slate-500 space-y-2">
                <p>No hay plataformas vinculadas.</p>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={addPlatformRow}
                  className="text-xs border-[#C8102E] text-[#C8102E] hover:bg-[#C8102E]/5 cursor-pointer"
                >
                  + Vincular primera plataforma
                </Button>
              </div>
            ) : (
              <div className="space-y-4">
                {formData.platforms.map((row, index) => {
                  const selectedPlatform = catalogs.publishedPlatforms.find(
                    (p) => String(p.id) === String(row.platform)
                  );
                  const publicUrl = selectedPlatform?.public_url;
                  const rowPublished = isRowPublished(row);
                  const selectId = `platform-row-${row._key}`;
                  const urlId = `platform-url-${row._key}`;

                  return (
                    <div key={row._key} className="bg-white border-2 border-slate-200 rounded-xl p-5 shadow-xs relative">
                      <div className="flex items-center gap-2 pr-12 mb-4">
                        <span className="text-xs font-bold text-slate-700 uppercase tracking-wide">
                          Plataforma #{index + 1}
                        </span>
                        {row.platform && !rowPublished && (
                          <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-100 text-amber-800">
                            No publicada
                          </span>
                        )}
                      </div>

                      <button
                        type="button"
                        onClick={() => removePlatformRow(index)}
                        className="absolute top-4 right-4 p-1.5 rounded-lg border border-rose-200 text-rose-600 hover:bg-rose-600 hover:text-white hover:border-rose-600 transition-all cursor-pointer"
                        title="Eliminar esta plataforma"
                        aria-label={`Eliminar plataforma #${index + 1}`}
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>

                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div className="space-y-1.5">
                          <label htmlFor={selectId} className="text-xs font-bold text-slate-700 uppercase tracking-wide block">
                            Plataforma
                          </label>
                          <select
                            id={selectId}
                            value={row.platform ?? ""}
                            onChange={(e) =>
                              updatePlatformRow(index, { platform: e.target.value, status: undefined, is_public: undefined })
                            }
                            className={`${platformFieldClass} cursor-pointer`}
                          >
                            <option value="">Seleccione una plataforma publicada</option>
                            {row.platform && !selectedPlatform && (
                              <option value={row.platform}>
                                {capitalizeWords(row.name) || `Plataforma #${row.platform}`} (no publicada)
                              </option>
                            )}
                            {catalogs.publishedPlatforms.map((p) => (
                              <option key={p.id} value={p.id}>
                                {capitalizeWords(p.name)}
                              </option>
                            ))}
                          </select>
                        </div>

                        <div className="space-y-1.5">
                          <label htmlFor={urlId} className="text-xs font-bold text-slate-700 uppercase tracking-wide block">
                            URL de la revista en esta plataforma
                          </label>
                          <Input
                            id={urlId}
                            type="url"
                            value={row.journal_url}
                            onChange={(e) => updatePlatformRow(index, { journal_url: e.target.value })}
                            placeholder="https://plataforma.org/revistas/mi-revista"
                            className={platformFieldClass}
                          />
                        </div>

                        {publicUrl && (
                          <div className="md:col-span-2 p-2.5 rounded-lg bg-blue-50/70 border border-blue-200/80 flex items-center justify-between gap-2 text-xs">
                            <div className="flex items-center gap-2 text-blue-900 truncate">
                              <Globe className="w-3.5 h-3.5 text-blue-600 shrink-0" aria-hidden="true" />
                              <span className="font-semibold text-blue-800 shrink-0">URL pública (plataforma):</span>
                              <span className="text-blue-700 truncate">{publicUrl}</span>
                            </div>
                            <a
                              href={publicUrl}
                              target="_blank"
                              rel="noreferrer"
                              className="text-blue-600 hover:text-blue-800 shrink-0 flex items-center gap-1 font-medium hover:underline cursor-pointer"
                            >
                              <span>Visitar</span>
                              <ExternalLink className="w-3 h-3" aria-hidden="true" />
                            </a>
                          </div>
                        )}

                        {(row.start_period || row.finish_period) && (
                          <div className="md:col-span-2 grid grid-cols-1 sm:grid-cols-2 gap-4">
                            <div className="space-y-1.5">
                              <span className="text-xs font-bold text-slate-700 uppercase tracking-wide block">
                                Fecha de vinculación con la plataforma
                              </span>
                              <p className={`${platformFieldClass} flex items-center bg-slate-100 text-slate-600`}>
                                {row.start_period || "Sin definir"}
                              </p>
                            </div>
                            <div className="space-y-1.5">
                              <span className="text-xs font-bold text-slate-700 uppercase tracking-wide block">
                                Fecha de finalización de la vinculación
                              </span>
                              <p className={`${platformFieldClass} flex items-center bg-slate-100 text-slate-600`}>
                                {row.finish_period || "Indefinida"}
                              </p>
                            </div>
                          </div>
                        )}

                        <div className="space-y-1.5 md:col-span-2">
                          <label
                            htmlFor={`platform-fulltext-${row._key}`}
                            className="text-xs font-bold text-slate-700 uppercase tracking-wide block"
                          >
                            ¿Texto completo?
                          </label>
                          <select
                            id={`platform-fulltext-${row._key}`}
                            value={row.has_full_text ? "true" : "false"}
                            onChange={(e) => updatePlatformRow(index, { has_full_text: e.target.value === "true" })}
                            className={`${platformFieldClass} cursor-pointer`}
                          >
                            <option value="true">Sí</option>
                            <option value="false">No</option>
                          </select>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </FormSection>
        </div>

        <aside className="lg:sticky lg:top-4 space-y-3">
          <PublishChecklist
            items={checklist}
            description="Las áreas del conocimiento no se validan por separado: se derivan de los programas."
          />
        </aside>
      </div>

      {/* Footer de acciones (sticky) */}
      <div className="sticky bottom-0 z-20 mt-6 -mx-2 sm:mx-0 border-t border-gray-200 bg-white/95 backdrop-blur px-3 py-3 sm:rounded-t-xl flex flex-col-reverse sm:flex-row sm:items-center sm:justify-between gap-2">
        <Button
          type="button"
          variant="outline"
          onClick={() => router.back()}
          disabled={Boolean(submitting)}
          className="rounded-xl border-gray-300 text-gray-700 text-xs px-5 py-2 font-medium hover:bg-gray-50 cursor-pointer"
        >
          Cancelar
        </Button>
        <div className="flex flex-col sm:flex-row gap-2">
          <Button
            type="submit"
            variant="outline"
            disabled={Boolean(submitting)}
            className="rounded-xl border-[#C8102E] text-[#C8102E] text-xs px-5 py-2 font-medium hover:bg-[#C8102E]/5 cursor-pointer gap-1.5"
          >
            <Save className="w-3.5 h-3.5" aria-hidden="true" />
            {submitting === "save" ? "Guardando..." : "Guardar"}
          </Button>
          <Button
            type="button"
            onClick={() => handleSubmit("publish")}
            disabled={Boolean(submitting) || !checklistComplete}
            title={checklistComplete ? undefined : "Completa los requisitos de publicación"}
            className="rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs px-5 py-2 font-medium cursor-pointer gap-1.5 disabled:bg-gray-300 disabled:text-gray-600"
          >
            <CheckCircle2 className="w-3.5 h-3.5" aria-hidden="true" />
            {submitting === "publish" ? "Publicando..." : "Publicar"}
          </Button>
        </div>
      </div>
    </form>
  );
}
