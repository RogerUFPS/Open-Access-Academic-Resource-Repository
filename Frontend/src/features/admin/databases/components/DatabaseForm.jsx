"use client";

import React, { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { platformService } from "../services/platformService";
import { capitalizeWords } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useToast } from "@/components/ui/use-toast";
import { useAccountsApi } from "@/shared/components/AccountsProvider";
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
import { buildPlatformChecklist, isChecklistComplete } from "@/shared/utils/publishChecklists";
import { SyntaxSelector } from "./SyntaxSelector";
import { ValidSintaxisModal } from "./ValidSintaxisModal";
import { ArrowLeft, CheckCircle2, Save } from "lucide-react";

const STATUS_LABELS = {
  BORRADOR: "Borrador",
  PUBLICADO: "Publicado",
  OBSOLETO: "Obsoleto",
};

const EMPTY_FORM = {
  name: "",
  public_url: "",
  is_harvestable: false,
  base_api_url: "",
  api_key: "",
  url_image: "",
  requires_registration: false,
  has_access_text: false,
  valid_sintaxis: null,
  institutions: [],
  languages: [],
  countries: [],
  material_types: [],
  academic_programs: [], // opcional
};

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

/**
 * Separa los programas en selección manual editable y programas derivados
 * (bloqueados). Un programa manual y derivado a la vez tampoco se puede quitar.
 */
function splitPrograms(list) {
  const manual = [];
  const locked = [];
  (Array.isArray(list) ? list : []).forEach((item) => {
    if (item == null) return;
    if (typeof item !== "object") {
      const id = Number(item);
      if (!Number.isNaN(id)) manual.push(id);
      return;
    }
    if (item.is_derived) locked.push(item);
    else if (item.is_manual !== false) manual.push(Number(item.id));
  });
  return { manual, locked };
}

function formFromRecord(record) {
  return {
    name: record.name || "",
    public_url: record.public_url || "",
    is_harvestable: Boolean(record.is_harvestable),
    base_api_url: record.base_api_url || "",
    api_key: "", // write-only: el backend nunca la devuelve
    url_image: record.url_image || "",
    requires_registration: Boolean(record.requires_registration),
    has_access_text: Boolean(record.has_access_text),
    valid_sintaxis:
      typeof record.valid_sintaxis === "object" && record.valid_sintaxis !== null
        ? record.valid_sintaxis.id ?? null
        : record.valid_sintaxis ?? null,
    institutions: extractIds(record.institutions),
    languages: extractIds(record.languages),
    countries: extractIds(record.countries),
    material_types: extractIds(record.material_types),
    academic_programs: splitPrograms(record.academic_programs).manual,
  };
}

function formatDate(value) {
  if (!value) return null;
  const [year, month, day] = String(value).slice(0, 10).split("-").map(Number);
  if (!year || !month || !day) return String(value);
  return new Date(year, month - 1, day).toLocaleDateString("es-ES", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

const cardClass = "bg-white border border-gray-200 rounded-xl p-3 shadow-2xs space-y-1";
const labelClass = "text-[11px] font-medium text-gray-500 block";
const inputClass =
  "border-0 p-0 text-xs shadow-none focus-visible:ring-0 h-6 font-semibold text-gray-900 disabled:opacity-40 disabled:cursor-not-allowed";
const selectClass = "w-full text-xs font-semibold text-gray-900 outline-none bg-transparent h-6 cursor-pointer";

export default function DatabaseForm({ initialData = null, isEdit = false, publishErrors = null }) {
  const router = useRouter();
  const accountsApi = useAccountsApi();
  const { toast } = useToast();

  const [catalogs, setCatalogs] = useState({
    sintaxis: [],
    institutions: [],
    languages: [],
    countries: [],
    materialTypes: [],
  });
  const [loadingCatalogs, setLoadingCatalogs] = useState(true);
  const [syntaxError, setSyntaxError] = useState("");
  const [syntaxModal, setSyntaxModal] = useState(null);
  const [syntaxPermissions, setSyntaxPermissions] = useState({ create: false, update: false, delete: false });
  const [pendingImage, setPendingImage] = useState(null);

  // Último estado confirmado por el backend (fuente de verdad tras guardar).
  const [record, setRecord] = useState(initialData);
  const [formData, setFormData] = useState(() => (initialData ? formFromRecord(initialData) : EMPTY_FORM));
  const [clearApiKey, setClearApiKey] = useState(false);
  const [submitting, setSubmitting] = useState(null); // null | "save" | "publish"
  const [fieldErrors, setFieldErrors] = useState(() => toFieldErrors(publishErrors));
  const [formError, setFormError] = useState(() =>
    publishErrors && Object.keys(publishErrors).length > 0
      ? "La plataforma no se pudo publicar. Corrige los campos indicados."
      : null
  );

  useEffect(() => {
    let cancelled = false;
    platformService
      .loadFormCatalogs()
      .then((catData) => {
        if (cancelled) return;
        setCatalogs(catData);
        setSyntaxError(catData.sintaxisError ? "No se pudo cargar el catálogo de sintaxis." : "");
      })
      .catch((err) => {
        console.error("Error loading catalogs:", err);
        if (!cancelled) setSyntaxError("No se pudo cargar el catálogo de sintaxis.");
      })
      .finally(() => {
        if (!cancelled) setLoadingCatalogs(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    accountsApi.me(controller.signal).then((user) => {
      const permissions = user?.effective_permissions?.platforms?.["valid-sintaxis"] || {};
      setSyntaxPermissions({
        create: Boolean(user?.is_superadmin || permissions.create),
        update: Boolean(user?.is_superadmin || permissions.update),
        delete: Boolean(user?.is_superadmin || permissions.delete),
      });
    }).catch(() => setSyntaxPermissions({ create: false, update: false, delete: false }));
    return () => controller.abort();
  }, [accountsApi]);

  // Programas derivados (de revistas) que no se pueden quitar.
  const lockedPrograms = useMemo(() => splitPrograms(record?.academic_programs).locked, [record]);
  const savedProgramIds = useMemo(() => extractIds(record?.academic_programs), [record]);
  const effectiveProgramIds = useMemo(
    () => [...new Set([...formData.academic_programs, ...lockedPrograms.map((program) => Number(program.id))])],
    [formData.academic_programs, lockedPrograms]
  );
  const knownProgramNames = useMemo(
    () => Object.fromEntries((record?.academic_programs || []).filter((p) => p && typeof p === "object").map((p) => [p.id, p.name])),
    [record]
  );
  const derivedAreas = useDerivedKnowledgeAreas({
    programIds: effectiveProgramIds,
    savedProgramIds,
    savedAreas: record ? record.knowledge_areas || [] : undefined,
  });

  const status = String(record?.status || "BORRADOR").toUpperCase();
  const recordId = record?.id ?? null;
  const canBePublished = status === "BORRADOR";

  const checklist = buildPlatformChecklist({
    publicUrl: formData.public_url,
    urlStatus: "pending",
    validSintaxis: formData.valid_sintaxis,
    institutions: formData.institutions,
    countries: formData.countries,
    languages: formData.languages,
    materialTypes: formData.material_types,
    isHarvestable: formData.is_harvestable,
    baseApiUrl: formData.base_api_url,
    hasApiKey: formData.is_harvestable && Boolean(formData.api_key.trim()),
  }).map((item) => ({
    ...item,
    failed: Boolean(fieldErrors[item.key] || (item.key === "api_key" && fieldErrors.base_api_url)),
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

  const showErrors = (message, errors = {}) => {
    setFieldErrors(errors);
    setFormError(message);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const handleSubmit = async (action = "save") => {
    setFormError(null);
    setFieldErrors({});

    const name = formData.name.trim();
    const publicUrl = formData.public_url.trim();
    const baseApiUrl = formData.base_api_url.trim();
    const apiKey = formData.api_key.trim();

    const localErrors = {};
    if (!name) localErrors.name = "El nombre de la base de datos es obligatorio.";
    if (publicUrl && !/^https?:\/\/\S+$/i.test(publicUrl)) {
      localErrors.public_url = "Debe empezar con http:// o https://";
    }
    // La API Key solo se habilita si es cosechable, así que esta regla también
    // cubre "si hay api_key, base_api_url presente".
    if (formData.is_harvestable && !baseApiUrl) {
      localErrors.base_api_url = "Una plataforma cosechable debe tener una URL base de API.";
    }
    if (Object.keys(localErrors).length > 0) {
      showErrors("Revisa los campos marcados antes de guardar.", localErrors);
      return;
    }

    setSubmitting(action);

    // 1. Guardar (POST o PATCH). knowledge_areas nunca se envía.
    const payload = {
      name,
      public_url: publicUrl || null,
      is_harvestable: formData.is_harvestable,
      base_api_url: formData.is_harvestable ? baseApiUrl || null : null,
      requires_registration: formData.requires_registration,
      has_access_text: formData.has_access_text,
      valid_sintaxis: formData.valid_sintaxis ? Number(formData.valid_sintaxis) : null,
      institutions: formData.institutions,
      languages: formData.languages,
      countries: formData.countries,
      material_types: formData.material_types,
      // Incluye los programas manuales que además son derivados (no editables).
      academic_programs: [
        ...new Set([
          ...formData.academic_programs,
          ...lockedPrograms.filter((program) => program.is_manual).map((program) => Number(program.id)),
        ]),
      ],
    };
    // api_key: null si no es cosechable o se pidió borrarla; se omite si no cambió.
    if (!formData.is_harvestable || clearApiKey) payload.api_key = null;
    else if (apiKey) payload.api_key = apiKey;

    let saved;
    try {
      saved = recordId
        ? await platformService.patchPlatform(recordId, payload)
        : await platformService.createPlatform(payload);
    } catch (err) {
      console.error("Form submit error:", err);
      showErrors(err.message || "Error al guardar la plataforma.", toFieldErrors(err.data));
      setSubmitting(null);
      return;
    }

    // 2. La respuesta es la fuente de verdad (academic_programs, knowledge_areas…).
    const savedId = saved?.id ?? recordId;
    if (saved && typeof saved === "object") {
      setRecord(saved);
      setFormData(formFromRecord(saved));
      setClearApiKey(false);
    }

    if (pendingImage && savedId) {
      try {
        const updated = await platformService.uploadPlatformImage(savedId, pendingImage);
        setPendingImage(null);
        setFormData((current) => ({ ...current, url_image: updated?.url_image || "" }));
      } catch (imageError) {
        toast({
          title: "No se pudo subir la imagen",
          description: imageError.message || "La plataforma se guardó, pero no se pudo subir la imagen.",
          variant: "destructive",
        });
      }
    }

    // 3. Verificar URL y publicar.
    if (action === "publish" && savedId) {
      try {
        const link = await platformService.checkLink(savedId);
        const verification = link?.verification_status ?? (link?.is_active ? "available" : "unavailable");
        if (verification !== "available") {
          showErrors("Los cambios se guardaron, pero la plataforma no se publicó.", {
            public_url: "La URL pública no está disponible. Corrígela o vuelve a verificarla antes de publicar.",
          });
          setSubmitting(null);
          return;
        }
        await platformService.publishPlatform(savedId);
      } catch (err) {
        console.warn("Error en la publicación:", err);
        showErrors(
          "Los cambios se guardaron, pero la plataforma no se publicó. Corrige los campos indicados.",
          toFieldErrors(err.data)
        );
        setSubmitting(null);
        return;
      }
      toast({ title: "Plataforma publicada", description: `“${saved?.name || name}” ya es visible en el directorio.` });
      router.push(`/admin/bases-de-datos/${savedId}`);
      return;
    }

    toast({ title: "Cambios guardados" });
    if (isEdit && savedId) router.push(`/admin/bases-de-datos/${savedId}`);
    else router.push("/admin/bases-de-datos");
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
    <>
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
              {recordId ? "Editar plataforma" : "Nueva plataforma"}
            </h1>
            <span
              className={`text-[11px] font-bold px-2.5 py-0.5 rounded-full border ${
                status === "PUBLICADO"
                  ? "bg-emerald-50 text-emerald-800 border-emerald-200"
                  : status === "OBSOLETO"
                  ? "bg-gray-100 text-gray-700 border-gray-200"
                  : "bg-amber-50 text-amber-800 border-amber-200"
              }`}
            >
              {STATUS_LABELS[status] || status}
            </span>
          </div>
          <p className="text-xs text-gray-500 mt-1">
            Borrador → Publicado → Obsoleto. Para publicar, completa los requisitos del panel lateral.
          </p>
        </div>

        <div className="mb-6">
          <FormErrorSummary message={formError} fieldErrors={fieldErrors} />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_18rem] gap-6 items-start">
          <div className="space-y-6 min-w-0">
            {/* 1. Información general */}
            <FormSection id="platform-general" number={1} title="Información general">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div id={fieldAnchorId("name")} className={`${cardClass} md:col-span-2`}>
                  <label htmlFor="name" className={labelClass}>Nombre *</label>
                  <Input
                    id="name"
                    required
                    value={formData.name}
                    onChange={(e) => updateField("name", e.target.value)}
                    aria-invalid={invalid("name")}
                    aria-describedby={describedBy("name")}
                    placeholder="Nombre de la base de datos (Ej. SciELO)"
                    className={inputClass}
                  />
                  <FieldError field="name" message={fieldErrors.name} />
                </div>

                <div id={fieldAnchorId("url_image")} className={`${cardClass} md:row-span-2`}>
                  <span className={labelClass}>Imagen (opcional)</span>
                  <ResourceImageUploader
                    value={formData.url_image}
                    alt={`Imagen de ${formData.name || "la plataforma"}`}
                    resourceId={recordId}
                    uploadImage={platformService.uploadPlatformImage}
                    deleteImage={platformService.deletePlatformImage}
                    onImageChange={(urlImage) => setFormData((current) => ({ ...current, url_image: urlImage || "" }))}
                    onPendingFileChange={setPendingImage}
                  />
                  <FieldError field="url_image" message={fieldErrors.url_image} />
                </div>

                <div id={fieldAnchorId("public_url")} className={`${cardClass} md:col-span-2`}>
                  <label htmlFor="public_url" className={labelClass}>URL pública de acceso</label>
                  <Input
                    id="public_url"
                    type="url"
                    value={formData.public_url}
                    onChange={(e) => updateField("public_url", e.target.value)}
                    aria-invalid={invalid("public_url")}
                    aria-describedby={describedBy("public_url")}
                    placeholder="https://www.scielo.org"
                    className={inputClass}
                  />
                  <p className="text-[10px] text-gray-400">Se verifica automáticamente (check-link) al publicar.</p>
                  <FieldError field="public_url" message={fieldErrors.public_url} />
                </div>
              </div>
            </FormSection>

            {/* 2. Cobertura y acceso */}
            <FormSection id="platform-access" number={2} title="Cobertura y acceso">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div className={cardClass}>
                  <span className={labelClass}>Fecha de registro (solo lectura)</span>
                  <p className="text-xs font-semibold text-gray-700 h-6 flex items-center">
                    {formatDate(record?.start_period) || "Se asigna automáticamente"}
                  </p>
                </div>
                <div className={cardClass}>
                  <span className={labelClass}>Fecha de obsolescencia (solo lectura)</span>
                  <p className="text-xs font-semibold text-gray-700 h-6 flex items-center">
                    {formatDate(record?.finish_period) || "Sin definir"}
                  </p>
                </div>
                <div className={cardClass}>
                  <label htmlFor="requires_registration" className={labelClass}>¿Exige registro previo?</label>
                  <select
                    id="requires_registration"
                    value={formData.requires_registration ? "true" : "false"}
                    onChange={(e) => updateField("requires_registration", e.target.value === "true")}
                    className={selectClass}
                  >
                    <option value="false">No (Acceso libre)</option>
                    <option value="true">Sí (Exige registro)</option>
                  </select>
                </div>
                <div className={cardClass}>
                  <label htmlFor="has_access_text" className={labelClass}>¿Texto completo disponible?</label>
                  <select
                    id="has_access_text"
                    value={formData.has_access_text ? "true" : "false"}
                    onChange={(e) => updateField("has_access_text", e.target.value === "true")}
                    className={selectClass}
                  >
                    <option value="true">Sí (Texto completo)</option>
                    <option value="false">No (Solo resúmenes / citas)</option>
                  </select>
                </div>
              </div>
            </FormSection>

            {/* 3. Cosecha */}
            <FormSection id="platform-harvest" number={3} title="Cosecha">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div id={fieldAnchorId("is_harvestable")} className={cardClass}>
                  <span id="is_harvestable-label" className={labelClass}>Cosechable vía API</span>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={formData.is_harvestable}
                    aria-labelledby="is_harvestable-label"
                    aria-describedby={describedBy("is_harvestable")}
                    onClick={() => {
                      const next = !formData.is_harvestable;
                      setFormData((current) => ({
                        ...current,
                        is_harvestable: next,
                        ...(next ? {} : { base_api_url: "", api_key: "" }),
                      }));
                      setFieldErrors((current) => ({ ...current, is_harvestable: null, base_api_url: null }));
                    }}
                    className="flex items-center gap-2 h-6 text-xs font-semibold text-gray-900 cursor-pointer"
                  >
                    <span
                      aria-hidden="true"
                      className={`relative inline-flex h-4 w-7 rounded-full transition-colors ${
                        formData.is_harvestable ? "bg-[#C8102E]" : "bg-gray-300"
                      }`}
                    >
                      <span
                        className={`absolute top-0.5 h-3 w-3 rounded-full bg-white transition-all ${
                          formData.is_harvestable ? "left-3.5" : "left-0.5"
                        }`}
                      />
                    </span>
                    {formData.is_harvestable ? "Sí (cosechable vía API)" : "No (solo acceso manual)"}
                  </button>
                  <FieldError field="is_harvestable" message={fieldErrors.is_harvestable} />
                </div>

                <div id={fieldAnchorId("base_api_url")} className={`${cardClass} md:col-span-2`}>
                  <label htmlFor="base_api_url" className={labelClass}>
                    URL base API de cosecha{formData.is_harvestable && " *"}
                  </label>
                  <Input
                    id="base_api_url"
                    type="url"
                    disabled={!formData.is_harvestable}
                    value={formData.base_api_url}
                    onChange={(e) => updateField("base_api_url", e.target.value)}
                    aria-invalid={invalid("base_api_url")}
                    aria-describedby={describedBy("base_api_url")}
                    placeholder={formData.is_harvestable ? "https://api.scielo.org/v1/oai (obligatoria)" : "Activar cosecha para habilitar"}
                    className={inputClass}
                  />
                  <FieldError field="base_api_url" message={fieldErrors.base_api_url} />
                </div>

                <div id={fieldAnchorId("api_key")} className={`${cardClass} md:col-span-3`}>
                  <label htmlFor="api_key" className={labelClass}>API Key (opcional)</label>
                  <Input
                    id="api_key"
                    type="password"
                    autoComplete="new-password"
                    value={formData.api_key}
                    onChange={(e) => {
                      setClearApiKey(false);
                      updateField("api_key", e.target.value);
                    }}
                    disabled={clearApiKey || !formData.is_harvestable}
                    aria-invalid={invalid("api_key")}
                    aria-describedby={describedBy("api_key")}
                    placeholder={
                      !formData.is_harvestable
                        ? "Activar cosecha para habilitar"
                        : clearApiKey
                        ? "Clave eliminada (se enviará null al guardar)"
                        : recordId
                        ? "Clave sin configurar / Escriba para cambiar"
                        : "Sin configurar"
                    }
                    className={inputClass}
                  />
                  <FieldError field="api_key" message={fieldErrors.api_key} />
                  {recordId && formData.is_harvestable && (
                    <label className="flex items-center gap-1.5 text-[10px] text-rose-600 cursor-pointer pt-1 font-medium">
                      <input
                        type="checkbox"
                        checked={clearApiKey}
                        onChange={(e) => {
                          setClearApiKey(e.target.checked);
                          if (e.target.checked) setFormData((current) => ({ ...current, api_key: "" }));
                        }}
                        className="rounded border-gray-300 text-rose-600 focus:ring-rose-500"
                      />
                      <span>Eliminar clave (enviará null)</span>
                    </label>
                  )}
                </div>
              </div>
            </FormSection>

            {/* 4. Clasificación del catálogo */}
            <FormSection id="platform-catalog" number={4} title="Clasificación del catálogo">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <CatalogCheckboxGrid
                  field="institutions"
                  label="Institución responsable"
                  items={catalogs.institutions}
                  selected={formData.institutions}
                  onToggle={(id) => toggleInList("institutions", id)}
                  error={fieldErrors.institutions}
                />
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
                <CatalogCheckboxGrid
                  field="material_types"
                  label="Tipo de material"
                  items={catalogs.materialTypes}
                  selected={formData.material_types}
                  onToggle={(id) => toggleInList("material_types", id)}
                  error={fieldErrors.material_types}
                />
              </div>
            </FormSection>

            {/* 5. Clasificación académica (opcional) */}
            <FormSection
              id="platform-academic"
              number={5}
              title="Clasificación académica (opcional)"
              description="Selecciona solo programas académicos. Las áreas del conocimiento las calcula el backend."
            >
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <AcademicProgramSelect
                  optional
                  value={formData.academic_programs}
                  onChange={(ids) => updateField("academic_programs", ids)}
                  lockedPrograms={lockedPrograms}
                  knownNames={knownProgramNames}
                  error={fieldErrors.academic_programs}
                  emptyMessage="Clasificación académica opcional."
                />
                <DerivedKnowledgeAreas
                  areas={derivedAreas.areas}
                  loading={derivedAreas.loading}
                  error={derivedAreas.error}
                  onRetry={derivedAreas.retry}
                  isPreview={derivedAreas.isPreview}
                  emptyMessage="Sin áreas derivadas. Puedes publicar sin clasificación."
                />
              </div>
            </FormSection>

            {/* 6. Sintaxis de búsqueda */}
            <FormSection id="platform-syntax" number={6} title="Sintaxis de búsqueda">
              <div id={fieldAnchorId("valid_sintaxis")} className={cardClass}>
                <label htmlFor="valid_sintaxis" className={labelClass}>Sintaxis de búsqueda admitida</label>
                <SyntaxSelector
                  options={catalogs.sintaxis || []}
                  value={formData.valid_sintaxis}
                  loading={false}
                  error={syntaxError}
                  canCreate={syntaxPermissions.create}
                  canUpdate={syntaxPermissions.update}
                  onChange={(validSintaxis) => updateField("valid_sintaxis", validSintaxis)}
                  onCreate={() => setSyntaxModal({ mode: "create" })}
                  onEdit={() => {
                    const selected = (catalogs.sintaxis || []).find(
                      (syntax) => syntax.id === Number(formData.valid_sintaxis)
                    );
                    if (selected) setSyntaxModal({ mode: "edit", item: selected });
                  }}
                />
                <FieldError field="valid_sintaxis" message={fieldErrors.valid_sintaxis} />
              </div>
            </FormSection>
          </div>

          <aside className="lg:sticky lg:top-4 space-y-3">
            <PublishChecklist
              items={checklist}
              description={
                canBePublished
                  ? "Programas académicos y áreas no son obligatorios para publicar."
                  : `La plataforma está en estado ${STATUS_LABELS[status] || status}; solo un borrador se puede publicar.`
              }
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
            {canBePublished && (
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
            )}
          </div>
        </div>
      </form>

      {syntaxModal && (
        <ValidSintaxisModal
          mode={syntaxModal.mode}
          item={syntaxModal.item}
          canDelete={syntaxPermissions.delete}
          onClose={() => setSyntaxModal(null)}
          onSaved={(saved) => {
            setCatalogs((current) => ({
              ...current,
              sintaxis: current.sintaxis.some((syntax) => syntax.id === saved.id)
                ? current.sintaxis.map((syntax) => (syntax.id === saved.id ? saved : syntax))
                : [...current.sintaxis, saved],
            }));
            updateField("valid_sintaxis", saved.id);
            setSyntaxModal(null);
          }}
          onDeleted={(id) => {
            setCatalogs((current) => ({ ...current, sintaxis: current.sintaxis.filter((syntax) => syntax.id !== id) }));
            setFormData((current) => ({
              ...current,
              valid_sintaxis: current.valid_sintaxis === id ? null : current.valid_sintaxis,
            }));
            setSyntaxModal(null);
          }}
        />
      )}
    </>
  );
}
