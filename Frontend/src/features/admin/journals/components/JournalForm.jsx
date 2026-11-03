"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { journalService } from "../services/journalService";
import { capitalizeWords } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  ArrowLeft,
  AlertCircle,
  Check,
  Plus,
  Trash2,
  Globe,
  ExternalLink,
  Tag,
  Save,
  Lock,
} from "lucide-react";

function extractIds(list) {
  if (!list || !Array.isArray(list) || list.length === 0) return [];
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

function emptyPlatformRow() {
  return {
    _key: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    platform: "",
    journal_url: "",
    has_full_text: true,
  };
}

// Validación ISSN formato XXXX-XXXX (e.g. 1234-5678 o 1234-567X)
const ISSN_REGEX = /^\d{4}-\d{3}[\dX]$/i;

export default function JournalForm({ initialData = null, isEdit = false }) {
  const router = useRouter();

  const [catalogs, setCatalogs] = useState({
    languages: [],
    countries: [],
    materialTypes: [],
    academicPrograms: [],
    editorials: [],
    publishedPlatforms: [],
    availableKnowledgeAreas: [],
  });
  const [loadingCatalogs, setLoadingCatalogs] = useState(isEdit);

  // Form State
  const [formData, setFormData] = useState({
    title: "",
    issn: "",
    publication_date: "",
    url_image: "",
    has_apc: false,
    languages: [],
    countries: [],
    material_types: [],
    academic_programs: [],
    editorial: "",
    platforms: [],
  });

  // Knowledge Areas state with provenance: { id, name, is_manual, is_derived, editable }
  const [knowledgeAreas, setKnowledgeAreas] = useState([]);
  const [selectedAreaToAdd, setSelectedAreaToAdd] = useState("");

  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState(null);
  const [fieldErrors, setFieldErrors] = useState({});

  useEffect(() => {
    async function loadData() {
      if (!isEdit) {
        setLoadingCatalogs(false);
        return;
      }
      setLoadingCatalogs(true);
      try {
        const catData = await journalService.loadFormCatalogs(initialData?.id);
        setCatalogs({
          ...catData,
          availableKnowledgeAreas: catData.knowledgeAreas || [],
        });

        if (initialData) {
          setFormData({
            title: initialData.title || "",
            issn: initialData.issn || "",
            publication_date: String(initialData.publication_date || "").slice(0, 10),
            url_image: initialData.url_image || "",
            has_apc: Boolean(initialData.has_apc),
            languages: extractIds(initialData.languages),
            countries: extractIds(initialData.countries),
            material_types: extractIds(initialData.material_types),
            academic_programs: extractIds(initialData.academic_programs),
            editorial: extractSingleId(initialData.editorial),
            platforms: (initialData.platforms || []).map((p, index) => ({
              _key: `existing-${p.id ?? index}`,
              platform:
                typeof p.platform === "object" && p.platform !== null ? p.platform.id : p.platform,
              journal_url: p.journal_url || "",
              has_full_text: Boolean(p.has_full_text),
            })),
          });

          // Normalizar knowledge_areas recibidas de la lectura
          const areas = Array.isArray(initialData.knowledge_areas)
            ? initialData.knowledge_areas.map((ka) => {
                if (typeof ka === "object" && ka !== null) {
                  return {
                    id: ka.id,
                    name: ka.name || `Área #${ka.id}`,
                    is_manual: Boolean(ka.is_manual),
                    is_derived: Boolean(ka.is_derived),
                    editable: Boolean(ka.editable),
                  };
                }
                return {
                  id: Number(ka),
                  name: `Área #${ka}`,
                  is_manual: true,
                  is_derived: false,
                  editable: true,
                };
              })
            : [];
          setKnowledgeAreas(areas);
        }
      } catch (err) {
        console.error("Error loading catalogs:", err);
      } finally {
        setLoadingCatalogs(false);
      }
    }
    loadData();
  }, [initialData, isEdit]);

  // Manejo de entrada con autoformato para ISSN XXXX-XXXX
  const handleIssnChange = (value) => {
    let clean = value.toUpperCase().replace(/[^0-9X-]/g, "");
    if (!clean.includes("-") && clean.length > 4) {
      clean = `${clean.slice(0, 4)}-${clean.slice(4, 8)}`;
    }
    setFormData((prev) => ({ ...prev, issn: clean }));
    if (fieldErrors.issn) {
      setFieldErrors((prev) => ({ ...prev, issn: null }));
    }
  };

  const handleMultiSelectToggle = (field, id) => {
    setFormData((prev) => {
      const current = prev[field] || [];
      const numId = Number(id);
      if (current.includes(numId)) {
        return { ...prev, [field]: current.filter((item) => item !== numId) };
      }
      return { ...prev, [field]: [...current, numId] };
    });
  };

  const updatePlatformRow = (index, patch) => {
    setFormData((prev) => {
      const next = [...prev.platforms];
      next[index] = { ...next[index], ...patch };
      return { ...prev, platforms: next };
    });
    if (fieldErrors.platforms) {
      setFieldErrors((prev) => ({ ...prev, platforms: null }));
    }
  };

  const addPlatformRow = () => {
    setFormData((prev) => ({
      ...prev,
      platforms: [...prev.platforms, emptyPlatformRow()],
    }));
  };

  const removePlatformRow = (index) => {
    setFormData((prev) => ({
      ...prev,
      platforms: prev.platforms.filter((_, i) => i !== index),
    }));
  };

  // Agregar área de conocimiento desde catálogo
  const handleAddKnowledgeArea = () => {
    if (!selectedAreaToAdd) return;
    const areaId = Number(selectedAreaToAdd);
    if (knowledgeAreas.some((ka) => ka.id === areaId)) {
      setSelectedAreaToAdd("");
      return;
    }
    const found = catalogs.availableKnowledgeAreas.find((a) => a.id === areaId);
    const newArea = {
      id: areaId,
      name: found ? found.name : `Área #${areaId}`,
      is_manual: true,
      is_derived: false,
      editable: true,
    };
    setKnowledgeAreas((prev) => [...prev, newArea]);
    setSelectedAreaToAdd("");
  };

  // Remover área de conocimiento: Regla de UI: Solo permitida si editable === true
  const handleRemoveKnowledgeArea = (areaId) => {
    setKnowledgeAreas((prev) =>
      prev.filter((ka) => {
        if (ka.id !== areaId) return true;
        // Solo eliminar si editable es true
        return !ka.editable;
      })
    );
  };

  const handleSubmit = async (e) => {
    if (e) e.preventDefault();
    setFormError(null);
    setFieldErrors({});

    const cleanTitle = formData.title.trim();
    const cleanIssn = formData.issn.trim();

    if (!cleanTitle) {
      setFormError("El título de la revista es obligatorio.");
      setFieldErrors({ title: "El título es requerido." });
      return;
    }

    if (!cleanIssn) {
      setFormError("El ISSN de la revista es obligatorio.");
      setFieldErrors({ issn: "El ISSN es requerido." });
      return;
    }

    if (!ISSN_REGEX.test(cleanIssn)) {
      setFormError("El ISSN debe tener el formato internacional XXXX-XXXX (ej. 1234-5678).");
      setFieldErrors({ issn: "Formato inválido. Debe ser XXXX-XXXX." });
      return;
    }

    setSubmitting(true);

    try {
      if (!isEdit) {
        // Regla de Creación: Enviar mínimo issn y title. Se crea en estado borrador.
        const createPayload = {
          title: cleanTitle,
          issn: cleanIssn,
        };

        if (formData.publication_date) {
          createPayload.publication_date = formData.publication_date;
        }
        if (formData.editorial) {
          createPayload.editorial = Number(formData.editorial);
        }

        const savedJournal = await journalService.createJournal(createPayload);
        const redirectId = savedJournal?.id;
        if (redirectId) {
          router.push(`/admin/revistas/${redirectId}`);
        } else {
          router.push("/admin/revistas");
        }
        return;
      }

      // Modo Edición (PATCH):
      // Áreas de conocimiento: Enviar como array simple de IDs manuales
      const manualAreaIds = knowledgeAreas
        .filter((ka) => ka.editable === true)
        .map((ka) => Number(ka.id))
        .filter(Number.isFinite);

      // Validar cada plataforma vinculada en edición si existen
      for (let i = 0; i < formData.platforms.length; i++) {
        const row = formData.platforms[i];
        if (!row.platform) {
          setFormError(`La plataforma en la fila #${i + 1} es obligatoria.`);
          setFieldErrors({ platforms: `Seleccione una plataforma en la fila ${i + 1}.` });
          setSubmitting(false);
          return;
        }
        if (!row.journal_url || !row.journal_url.trim()) {
          setFormError(`La URL de la revista en la plataforma #${i + 1} es obligatoria.`);
          setFieldErrors({
            platforms: `La URL específica de la revista es requerida en la fila ${i + 1}.`,
          });
          setSubmitting(false);
          return;
        }
      }

      const patchPayload = {
        title: cleanTitle,
        issn: cleanIssn,
        publication_date: formData.publication_date || null,
        url_image: formData.url_image ? formData.url_image.trim() : null,
        has_apc: Boolean(formData.has_apc),
        languages: formData.languages,
        countries: formData.countries,
        material_types: formData.material_types,
        academic_programs: formData.academic_programs,
        editorial: formData.editorial ? Number(formData.editorial) : null,
        knowledge_areas: manualAreaIds,
        platforms: formData.platforms.map((row) => ({
          platform: Number(row.platform),
          journal_url: row.journal_url.trim(),
          has_full_text: Boolean(row.has_full_text),
        })),
      };

      await journalService.patchJournal(initialData.id, patchPayload);
      router.push(`/admin/revistas/${initialData.id}`);
    } catch (err) {
      console.error("Form submit error:", err);
      if (err.data && typeof err.data === "object") {
        setFieldErrors(err.data);
      }
      setFormError(err.message || "Error al guardar la revista.");
    } finally {
      setSubmitting(false);
    }
  };

  if (loadingCatalogs) {
    return (
      <div className="p-16 text-center text-gray-500">
        <div className="w-8 h-8 border-2 border-[#7f1218] border-t-transparent rounded-full animate-spin mx-auto mb-3"></div>
        <p className="text-xs font-medium">Cargando catálogos del sistema...</p>
      </div>
    );
  }

  // Vista de CREACIÓN mínima en estado Borrador
  if (!isEdit) {
    return (
      <form onSubmit={handleSubmit} className="space-y-6 max-w-2xl mx-auto">
        <div>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => router.back()}
              className="p-1.5 rounded-lg bg-white border border-gray-200 text-gray-600 hover:bg-gray-50 transition-colors cursor-pointer"
            >
              <ArrowLeft className="w-4 h-4" />
            </button>
            <h1 className="text-2xl font-bold text-gray-900 tracking-tight">
              Crear nueva revista
            </h1>
          </div>
          <p className="text-xs font-medium text-[#7f1218] mt-1">
            Estado inicial: <span className="font-bold">Borrador</span> · Crear NO significa publicar.
          </p>
        </div>

        {formError && (
          <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-xs font-medium flex items-start gap-3 shadow-2xs">
            <AlertCircle className="w-5 h-5 text-rose-600 shrink-0 mt-0.5" />
            <div>
              <p className="font-bold text-sm">Atención en el formulario</p>
              <p className="mt-0.5 leading-relaxed">{formError}</p>
            </div>
          </div>
        )}

        <div className="bg-white border border-gray-200 rounded-2xl p-6 shadow-xs space-y-5">
          <div className="space-y-1">
            <h2 className="text-sm font-bold text-gray-900">Datos mínimos obligatorios</h2>
            <p className="text-xs text-gray-500">
              Registra el ISSN y el título de la revista para crear su ficha inicial en borrador. Podrás vincular plataformas, áreas y clasificaciones posteriormente antes de publicarla.
            </p>
          </div>

          {/* Título */}
          <div className="space-y-1.5">
            <Label htmlFor="title" className="text-xs font-semibold text-gray-700">
              Título de la revista *
            </Label>
            <Input
              id="title"
              required
              value={formData.title}
              onChange={(e) => {
                setFormData({ ...formData, title: e.target.value });
                if (fieldErrors.title) setFieldErrors((prev) => ({ ...prev, title: null }));
              }}
              placeholder="Ej. Revista Respuestas, Eco Matemático..."
              className="rounded-xl border-gray-200 text-sm h-11 focus:border-[#7f1218] focus:ring-1 focus:ring-[#7f1218]"
            />
            {fieldErrors.title && (
              <p className="text-xs text-rose-600 font-medium">
                {Array.isArray(fieldErrors.title) ? fieldErrors.title.join(", ") : fieldErrors.title}
              </p>
            )}
          </div>

          {/* ISSN */}
          <div className="space-y-1.5">
            <Label htmlFor="issn" className="text-xs font-semibold text-gray-700">
              ISSN (Formato XXXX-XXXX) *
            </Label>
            <Input
              id="issn"
              required
              maxLength={9}
              value={formData.issn}
              onChange={(e) => handleIssnChange(e.target.value)}
              placeholder="0122-820X"
              className="rounded-xl border-gray-200 text-sm h-11 font-mono focus:border-[#7f1218] focus:ring-1 focus:ring-[#7f1218]"
            />
            {fieldErrors.issn && (
              <p className="text-xs text-rose-600 font-medium">
                {Array.isArray(fieldErrors.issn) ? fieldErrors.issn.join(", ") : fieldErrors.issn}
              </p>
            )}
            <p className="text-[11px] text-gray-400">
              Debe cumplir con el estándar internacional de 8 caracteres alfanuméricos separados por un guión.
            </p>
          </div>

          <div className="flex items-center justify-end gap-3 pt-4 border-t border-gray-100">
            <Button
              type="button"
              variant="outline"
              onClick={() => router.back()}
              disabled={submitting}
              className="rounded-xl border-gray-300 text-gray-700 text-xs px-5 py-2 font-medium hover:bg-gray-50 cursor-pointer"
            >
              Cancelar
            </Button>
            <Button
              type="submit"
              disabled={submitting}
              className="rounded-xl bg-[#7f1218] hover:bg-[#6a0f14] text-white text-xs px-5 py-2 font-medium cursor-pointer flex items-center gap-1.5"
            >
              <Save className="w-4 h-4" />
              <span>{submitting ? "Creando..." : "Crear borrador de revista"}</span>
            </Button>
          </div>
        </div>
      </form>
    );
  }

  // Vista de EDICIÓN completa
  return (
    <form onSubmit={handleSubmit} className="space-y-6 max-w-5xl mx-auto">
      {/* Header */}
      <div>
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => router.back()}
            className="p-1.5 rounded-lg bg-white border border-gray-200 text-gray-600 hover:bg-gray-50 transition-colors cursor-pointer"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>
          <h1 className="text-2xl font-bold text-gray-900 tracking-tight">
            Editar revista
          </h1>
        </div>
        <p className="text-xs font-medium text-[#7f1218] mt-1">
          {initialData?.active ? "Estado: Publicada (Activa)" : "Estado: Borrador (Pendiente de publicación)"}
        </p>
      </div>

      {/* Error Banner */}
      {formError && (
        <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-xs font-medium flex items-start gap-3 shadow-2xs">
          <AlertCircle className="w-5 h-5 text-rose-600 shrink-0 mt-0.5" />
          <div>
            <p className="font-bold text-sm">Atención en el formulario</p>
            <p className="mt-0.5 leading-relaxed">{formError}</p>
          </div>
        </div>
      )}

      {/* SECCIÓN 1: Identificación */}
      <div className="space-y-3">
        <h2 className="text-sm font-bold text-gray-900">Identificación de la revista</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div className="bg-white border border-gray-200 rounded-xl p-3 shadow-2xs space-y-1 md:col-span-2">
            <Label htmlFor="title" className="text-[11px] font-medium text-gray-500 block">
              Título *
            </Label>
            <Input
              id="title"
              required
              value={formData.title}
              onChange={(e) => {
                setFormData({ ...formData, title: e.target.value });
                if (fieldErrors.title) setFieldErrors((prev) => ({ ...prev, title: null }));
              }}
              placeholder="Nombre oficial de la revista"
              className="border-0 p-0 text-xs shadow-none focus-visible:ring-0 h-6 font-semibold text-gray-900"
            />
          </div>

          <div className="bg-white border border-gray-200 rounded-xl p-3 shadow-2xs space-y-1">
            <Label htmlFor="issn" className="text-[11px] font-medium text-gray-500 block">
              ISSN (XXXX-XXXX) *
            </Label>
            <Input
              id="issn"
              required
              maxLength={9}
              value={formData.issn}
              onChange={(e) => handleIssnChange(e.target.value)}
              placeholder="0122-820X"
              className="border-0 p-0 text-xs shadow-none focus-visible:ring-0 h-6 font-mono font-semibold text-gray-900"
            />
          </div>

          <div className="bg-white border border-gray-200 rounded-xl p-3 shadow-2xs space-y-1">
            <Label htmlFor="publication_date" className="text-[11px] font-medium text-gray-500 block">
              Fecha de inicio / publicación
            </Label>
            <Input
              id="publication_date"
              type="date"
              value={formData.publication_date}
              onChange={(e) => {
                setFormData({ ...formData, publication_date: e.target.value });
                if (fieldErrors.publication_date)
                  setFieldErrors((prev) => ({ ...prev, publication_date: null }));
              }}
              className="border-0 p-0 text-xs shadow-none focus-visible:ring-0 h-6 text-gray-800"
            />
          </div>

          <div className="bg-white border border-gray-200 rounded-xl p-3 shadow-2xs space-y-1">
            <Label htmlFor="editorial" className="text-[11px] font-medium text-gray-500 block">
              Editorial
            </Label>
            <select
              id="editorial"
              value={formData.editorial}
              onChange={(e) => {
                setFormData({ ...formData, editorial: e.target.value });
                if (fieldErrors.editorial) setFieldErrors((prev) => ({ ...prev, editorial: null }));
              }}
              className="w-full text-xs font-semibold text-gray-900 outline-none bg-transparent h-6 cursor-pointer"
            >
              <option value="">Seleccione una editorial...</option>
              {catalogs.editorials.map((ed) => (
                <option key={ed.id} value={ed.id}>
                  {capitalizeWords(ed.name || ed.nombre)}
                </option>
              ))}
            </select>
          </div>

          <div className="bg-white border border-gray-200 rounded-xl p-3 shadow-2xs space-y-1">
            <Label htmlFor="has_apc" className="text-[11px] font-medium text-gray-500 block">
              ¿Aplica cargos APC?
            </Label>
            <select
              id="has_apc"
              value={formData.has_apc ? "true" : "false"}
              onChange={(e) => setFormData({ ...formData, has_apc: e.target.value === "true" })}
              className="w-full text-xs font-semibold text-gray-900 outline-none bg-transparent h-6 cursor-pointer"
            >
              <option value="false">No (Sin cargos de publicación)</option>
              <option value="true">Sí (Aplica APC)</option>
            </select>
          </div>

          <div className="bg-white border border-gray-200 rounded-xl p-3 shadow-2xs space-y-1 md:col-span-3">
            <Label htmlFor="url_image" className="text-[11px] font-medium text-gray-500 block">
              URL de imagen de portada (opcional)
            </Label>
            <Input
              id="url_image"
              type="url"
              value={formData.url_image}
              onChange={(e) => setFormData({ ...formData, url_image: e.target.value })}
              placeholder="https://.../portada.jpg"
              className="border-0 p-0 text-xs shadow-none focus-visible:ring-0 h-6 text-gray-800"
            />
          </div>
        </div>
      </div>

      {/* SECCIÓN 2: Áreas de Conocimiento [SÚPER IMPORTANTE] */}
      <div className="space-y-3 pt-2">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-sm font-bold text-gray-900 flex items-center gap-2">
              <Tag className="w-4 h-4 text-[#7f1218]" />
              Áreas de Conocimiento
            </h2>
            <p className="text-[11px] text-gray-500">
              Las áreas manuales son editables por el curador; las áreas derivadas son heredadas del indexado y no pueden eliminarse individualmente.
            </p>
          </div>
          <span className="text-[11px] bg-slate-100 text-slate-700 font-semibold px-2.5 py-1 rounded-full">
            {knowledgeAreas.length} asignadas
          </span>
        </div>

        {/* Lista de áreas asignadas */}
        <div className="bg-white border border-gray-200 rounded-2xl p-4 shadow-2xs space-y-3">
          {knowledgeAreas.length === 0 ? (
            <div className="py-6 text-center text-gray-400 text-xs">
              No hay áreas de conocimiento asociadas a esta revista.
            </div>
          ) : (
            <div className="flex flex-wrap gap-2">
              {knowledgeAreas.map((area) => {
                const isBoth = area.is_manual && area.is_derived;
                return (
                  <div
                    key={area.id}
                    className="flex items-center gap-2 px-3 py-1.5 rounded-xl border border-gray-200 bg-slate-50 text-xs"
                  >
                    <span className="font-semibold text-gray-900">{capitalizeWords(area.name)}</span>
                    
                    {/* Tags visuales: Manual / Derivada / Ambas */}
                    {isBoth ? (
                      <span className="bg-purple-100 text-purple-800 text-[10px] font-bold px-2 py-0.5 rounded-md">
                        Manual · Derivada
                      </span>
                    ) : area.is_manual ? (
                      <span className="bg-emerald-100 text-emerald-800 text-[10px] font-bold px-2 py-0.5 rounded-md">
                        Manual
                      </span>
                    ) : (
                      <span className="bg-blue-100 text-blue-800 text-[10px] font-bold px-2 py-0.5 rounded-md">
                        Derivada
                      </span>
                    )}

                    {/* Regla de UI: Solo se permite eliminar si editable === true */}
                    {area.editable ? (
                      <button
                        type="button"
                        title="Eliminar área de conocimiento manual"
                        onClick={() => handleRemoveKnowledgeArea(area.id)}
                        className="text-gray-400 hover:text-rose-600 p-0.5 transition-colors cursor-pointer"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    ) : (
                      <span title="Área derivada: no se puede eliminar manualmente" className="text-gray-400 cursor-not-allowed">
                        <Lock className="w-3 h-3 text-slate-400" />
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {/* Selector contextual de áreas de conocimiento disponibles */}
          <div className="flex items-center gap-2 pt-2 border-t border-gray-100">
            <select
              value={selectedAreaToAdd}
              onChange={(e) => setSelectedAreaToAdd(e.target.value)}
              className="text-xs border border-gray-200 rounded-xl px-3 py-2 bg-white text-gray-800 outline-none flex-1 focus:border-[#7f1218]"
            >
              <option value="">Seleccione un área del catálogo disponible para asociar...</option>
              {catalogs.availableKnowledgeAreas
                .filter((catArea) => !knowledgeAreas.some((ka) => ka.id === catArea.id))
                .map((catArea) => (
                  <option key={catArea.id} value={catArea.id}>
                    {capitalizeWords(catArea.name || catArea.nombre)}
                  </option>
                ))}
            </select>
            <Button
              type="button"
              disabled={!selectedAreaToAdd}
              onClick={handleAddKnowledgeArea}
              className="rounded-xl bg-[#7f1218] hover:bg-[#6a0f14] text-white text-xs px-3 py-2 cursor-pointer flex items-center gap-1"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>Asociar área</span>
            </Button>
          </div>
        </div>
      </div>

      {/* SECCIÓN 3: Relación Journal-Platform */}
      <div className="space-y-3 pt-2">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-sm font-bold text-gray-900 flex items-center gap-2">
              <Globe className="w-4 h-4 text-[#7f1218]" />
              Indexación en Plataformas / Bases de Datos
            </h2>
            <p className="text-[11px] text-gray-500">
              Vincule las plataformas donde esta revista está indexada. Cada vínculo cuenta con su propia URL contextual de revista.
            </p>
          </div>
          <Button
            type="button"
            variant="outline"
            onClick={addPlatformRow}
            className="rounded-xl border-[#7f1218] text-[#7f1218] text-xs px-3 py-1.5 font-medium hover:bg-[#7f1218]/5 cursor-pointer gap-1.5"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Vincular plataforma</span>
          </Button>
        </div>

        <div className="space-y-3">
          {formData.platforms.length === 0 ? (
            <div className="bg-white border border-gray-200 rounded-2xl p-6 text-center text-xs text-gray-400">
              Sin plataformas vinculadas actualmente.
            </div>
          ) : (
            formData.platforms.map((row, index) => (
              <div
                key={row._key || index}
                className="bg-white border border-gray-200 rounded-2xl p-4 shadow-2xs space-y-3"
              >
                <div className="flex items-center justify-between pb-2 border-b border-gray-100">
                  <span className="text-xs font-bold text-gray-700">Plataforma #{index + 1}</span>
                  <button
                    type="button"
                    onClick={() => removePlatformRow(index)}
                    className="text-xs text-rose-600 hover:text-rose-800 font-medium flex items-center gap-1 cursor-pointer"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                    <span>Quitar vínculo</span>
                  </button>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  <div className="space-y-1">
                    <Label className="text-[11px] font-medium text-gray-500 block">
                      Plataforma *
                    </Label>
                    <select
                      value={row.platform}
                      onChange={(e) => updatePlatformRow(index, { platform: e.target.value })}
                      className="w-full text-xs font-semibold text-gray-900 border border-gray-200 rounded-xl px-2.5 h-9 bg-white cursor-pointer outline-none focus:border-[#7f1218]"
                    >
                      <option value="">Seleccione plataforma...</option>
                      {catalogs.publishedPlatforms.map((plat) => (
                        <option key={plat.id} value={plat.id}>
                          {capitalizeWords(plat.name)}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div className="space-y-1 md:col-span-2">
                    <Label className="text-[11px] font-medium text-gray-500 block">
                      URL de la revista en esta plataforma (journal_url) *
                    </Label>
                    <Input
                      type="url"
                      value={row.journal_url}
                      onChange={(e) => updatePlatformRow(index, { journal_url: e.target.value })}
                      placeholder="https://scielo.org/journal/..."
                      className="rounded-xl border-gray-200 text-xs h-9 focus:border-[#7f1218] focus:ring-1 focus:ring-[#7f1218]"
                    />
                  </div>

                  <div className="space-y-1">
                    <Label className="text-[11px] font-medium text-gray-500 block">
                      ¿Acceso a texto completo?
                    </Label>
                    <select
                      value={row.has_full_text ? "true" : "false"}
                      onChange={(e) => updatePlatformRow(index, { has_full_text: e.target.value === "true" })}
                      className="w-full text-xs font-semibold text-gray-900 border border-gray-200 rounded-xl px-2.5 h-9 bg-white cursor-pointer outline-none focus:border-[#7f1218]"
                    >
                      <option value="true">Sí (Texto completo)</option>
                      <option value="false">No (Solo resúmenes / citas)</option>
                    </select>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* SECCIÓN 4: Cobertura & Clasificación */}
      <div className="space-y-3 pt-2">
        <h2 className="text-sm font-bold text-gray-900">Cobertura y Clasificación adicional</h2>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Idiomas */}
          <div className="bg-white border border-gray-200 rounded-xl p-4 shadow-2xs space-y-2.5">
            <div className="flex items-center justify-between pb-1 border-b border-gray-100">
              <Label className="text-[11px] font-bold text-gray-700 uppercase tracking-wider block">
                Idiomas de publicación
              </Label>
              <span className="text-[10px] bg-slate-100 text-slate-600 font-semibold px-2 py-0.5 rounded-full">
                {formData.languages.length} seleccionados
              </span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-48 overflow-y-auto pr-1">
              {catalogs.languages.map((lang) => {
                const isSelected = formData.languages.includes(lang.id);
                return (
                  <div
                    key={lang.id}
                    onClick={() => handleMultiSelectToggle("languages", lang.id)}
                    className={`flex items-center justify-between p-2.5 rounded-lg text-xs cursor-pointer border transition-all ${
                      isSelected
                        ? "bg-[#7f1218]/5 border-[#7f1218] text-gray-900 font-semibold shadow-2xs"
                        : "bg-white border-gray-200 text-gray-700 hover:bg-gray-50"
                    }`}
                  >
                    <span className="truncate pr-1">{capitalizeWords(lang.name || lang.nombre)}</span>
                    <div className={`w-4 h-4 rounded flex items-center justify-center border transition-all shrink-0 ${isSelected ? "bg-[#7f1218] border-[#7f1218] text-white" : "border-gray-300 bg-white"}`}>
                      {isSelected && <Check className="w-3 h-3" />}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Países */}
          <div className="bg-white border border-gray-200 rounded-xl p-4 shadow-2xs space-y-2.5">
            <div className="flex items-center justify-between pb-1 border-b border-gray-100">
              <Label className="text-[11px] font-bold text-gray-700 uppercase tracking-wider block">
                Países
              </Label>
              <span className="text-[10px] bg-slate-100 text-slate-600 font-semibold px-2 py-0.5 rounded-full">
                {formData.countries.length} seleccionados
              </span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-48 overflow-y-auto pr-1">
              {catalogs.countries.map((country) => {
                const isSelected = formData.countries.includes(country.id);
                return (
                  <div
                    key={country.id}
                    onClick={() => handleMultiSelectToggle("countries", country.id)}
                    className={`flex items-center justify-between p-2.5 rounded-lg text-xs cursor-pointer border transition-all ${
                      isSelected
                        ? "bg-[#7f1218]/5 border-[#7f1218] text-gray-900 font-semibold shadow-2xs"
                        : "bg-white border-gray-200 text-gray-700 hover:bg-gray-50"
                    }`}
                  >
                    <span className="truncate pr-1 flex items-center gap-1.5">
                      {country.emoji_flag && <span>{country.emoji_flag}</span>}
                      <span>{capitalizeWords(country.name || country.nombre)}</span>
                    </span>
                    <div className={`w-4 h-4 rounded flex items-center justify-center border transition-all shrink-0 ${isSelected ? "bg-[#7f1218] border-[#7f1218] text-white" : "border-gray-300 bg-white"}`}>
                      {isSelected && <Check className="w-3 h-3" />}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Tipos de material */}
          <div className="bg-white border border-gray-200 rounded-xl p-4 shadow-2xs space-y-2.5">
            <div className="flex items-center justify-between pb-1 border-b border-gray-100">
              <Label className="text-[11px] font-bold text-gray-700 uppercase tracking-wider block">
                Tipos de material
              </Label>
              <span className="text-[10px] bg-slate-100 text-slate-600 font-semibold px-2 py-0.5 rounded-full">
                {formData.material_types.length} seleccionados
              </span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-48 overflow-y-auto pr-1">
              {catalogs.materialTypes.map((mat) => {
                const isSelected = formData.material_types.includes(mat.id);
                return (
                  <div
                    key={mat.id}
                    onClick={() => handleMultiSelectToggle("material_types", mat.id)}
                    className={`flex items-center justify-between p-2.5 rounded-lg text-xs cursor-pointer border transition-all ${
                      isSelected
                        ? "bg-[#7f1218]/5 border-[#7f1218] text-gray-900 font-semibold shadow-2xs"
                        : "bg-white border-gray-200 text-gray-700 hover:bg-gray-50"
                    }`}
                  >
                    <span className="truncate pr-1">{capitalizeWords(mat.name || mat.nombre)}</span>
                    <div className={`w-4 h-4 rounded flex items-center justify-center border transition-all shrink-0 ${isSelected ? "bg-[#7f1218] border-[#7f1218] text-white" : "border-gray-300 bg-white"}`}>
                      {isSelected && <Check className="w-3 h-3" />}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Programas Académicos */}
          <div className="bg-white border border-gray-200 rounded-xl p-4 shadow-2xs space-y-2.5">
            <div className="flex items-center justify-between pb-1 border-b border-gray-100">
              <Label className="text-[11px] font-bold text-gray-700 uppercase tracking-wider block">
                Programas académicos
              </Label>
              <span className="text-[10px] bg-slate-100 text-slate-600 font-semibold px-2 py-0.5 rounded-full">
                {formData.academic_programs.length} seleccionados
              </span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-48 overflow-y-auto pr-1">
              {catalogs.academicPrograms.map((prog) => {
                const isSelected = formData.academic_programs.includes(prog.id);
                return (
                  <div
                    key={prog.id}
                    onClick={() => handleMultiSelectToggle("academic_programs", prog.id)}
                    className={`flex items-center justify-between p-2.5 rounded-lg text-xs cursor-pointer border transition-all ${
                      isSelected
                        ? "bg-[#7f1218]/5 border-[#7f1218] text-gray-900 font-semibold shadow-2xs"
                        : "bg-white border-gray-200 text-gray-700 hover:bg-gray-50"
                    }`}
                  >
                    <span className="truncate pr-1">{capitalizeWords(prog.name || prog.nombre)}</span>
                    <div className={`w-4 h-4 rounded flex items-center justify-center border transition-all shrink-0 ${isSelected ? "bg-[#7f1218] border-[#7f1218] text-white" : "border-gray-300 bg-white"}`}>
                      {isSelected && <Check className="w-3 h-3" />}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {/* Botones de Acción */}
      <div className="flex items-center gap-3 flex-wrap pt-4 border-t border-gray-100">
        <Button
          type="button"
          variant="outline"
          onClick={() => router.back()}
          disabled={submitting}
          className="rounded-xl border-gray-300 text-gray-700 text-xs px-5 py-2 font-medium hover:bg-gray-50 cursor-pointer"
        >
          Cancelar
        </Button>

        <Button
          type="submit"
          disabled={submitting}
          className="rounded-xl bg-[#7f1218] hover:bg-[#6a0f14] text-white text-xs px-5 py-2 font-medium cursor-pointer flex items-center gap-1.5"
        >
          <Save className="w-4 h-4" />
          <span>{submitting ? "Guardando..." : "Guardar cambios"}</span>
        </Button>
      </div>
    </form>
  );
}
