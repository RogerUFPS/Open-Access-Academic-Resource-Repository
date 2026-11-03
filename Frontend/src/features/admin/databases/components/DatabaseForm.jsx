"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { platformService } from "../services/platformService";
import { capitalizeWords } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { 
  ArrowLeft, 
  AlertCircle, 
  Check,
  Save,
  Globe
} from "lucide-react";

export default function DatabaseForm({ initialData = null, isEdit = false }) {
  const router = useRouter();

  // Catalogs state (only needed for full edit)
  const [catalogs, setCatalogs] = useState({
    sintaxis: [],
    institutions: [],
    languages: [],
    countries: [],
    materialTypes: [],
    academicPrograms: [],
  });
  const [loadingCatalogs, setLoadingCatalogs] = useState(isEdit);

  // Form State
  const [formData, setFormData] = useState({
    name: "",
    public_url: "",
    is_harvestable: false,
    base_api_url: "",
    api_key: "",
    url_image: "",
    requires_registration: false,
    has_access_text: true,
    valid_sintaxis: "",
    institutions: [],
    languages: [],
    countries: [],
    material_types: [],
    academic_programs: [],
  });

  const [clearApiKey, setClearApiKey] = useState(false);
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
        const catData = await platformService.loadFormCatalogs();
        setCatalogs(catData);

        if (initialData) {
          setFormData({
            name: initialData.name || "",
            public_url: initialData.public_url || initialData.url || (initialData.link_logs && initialData.link_logs[0]?.url) || "",
            is_harvestable: Boolean(initialData.is_harvestable),
            base_api_url: initialData.base_api_url || "",
            api_key: "", // Write-only, never returned by backend
            url_image: initialData.url_image || "",
            requires_registration: Boolean(initialData.requires_registration),
            has_access_text: Boolean(initialData.has_access_text),
            valid_sintaxis: initialData.valid_sintaxis?.id || initialData.valid_sintaxis || (catData.sintaxis[0]?.id || 1),
            institutions: extractIds(initialData.institutions),
            languages: extractIds(initialData.languages),
            countries: extractIds(initialData.countries),
            material_types: extractIds(initialData.material_types),
            academic_programs: extractIds(initialData.academic_programs),
          });
        }
      } catch (err) {
        console.error("Error loading catalogs:", err);
      } finally {
        setLoadingCatalogs(false);
      }
    }
    loadData();
  }, [initialData, isEdit]);

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

  const handleMultiSelectToggle = (field, id) => {
    setFormData((prev) => {
      const current = prev[field] || [];
      const numId = Number(id);
      if (current.includes(numId)) {
        return { ...prev, [field]: current.filter((item) => item !== numId) };
      } else {
        return { ...prev, [field]: [...current, numId] };
      }
    });
  };

  const handleSubmit = async (e) => {
    if (e) e.preventDefault();
    setFormError(null);
    setFieldErrors({});

    const cleanName = formData.name.trim();
    const cleanPublicUrl = formData.public_url.trim();

    if (!cleanName) {
      setFormError("El nombre de la plataforma es obligatorio.");
      setFieldErrors({ name: "El nombre es requerido." });
      return;
    }

    if (!cleanPublicUrl) {
      setFormError("La URL pública de acceso es obligatoria.");
      setFieldErrors({ public_url: "La URL pública es requerida." });
      return;
    }

    setSubmitting(true);

    try {
      if (!isEdit) {
        // Regla de Creación: Enviar solo name y public_url. Crea en estado borrador.
        const savedPlatform = await platformService.createPlatform({
          name: cleanName,
          public_url: cleanPublicUrl,
        });

        const redirectId = savedPlatform?.id;
        if (redirectId) {
          router.push(`/admin/bases-de-datos/${redirectId}`);
        } else {
          router.push("/admin/bases-de-datos");
        }
        return;
      }

      // Modo Edición (PATCH):
      const hasBaseApiUrl = Boolean(formData.base_api_url && formData.base_api_url.trim());
      const hasApiKeyInput = Boolean(formData.api_key && formData.api_key.trim());

      if (formData.is_harvestable && !hasBaseApiUrl) {
        setFormError("Si la base de datos es cosechable, la URL Base de API es obligatoria.");
        setFieldErrors({ base_api_url: "Obligatoria cuando 'Cosechable vía API' está activado." });
        setSubmitting(false);
        return;
      }

      const patchPayload = {
        name: cleanName,
        public_url: cleanPublicUrl,
        is_harvestable: formData.is_harvestable,
        url_image: formData.url_image ? formData.url_image.trim() : null,
        requires_registration: formData.requires_registration,
        has_access_text: formData.has_access_text,
        valid_sintaxis: formData.valid_sintaxis ? Number(formData.valid_sintaxis) : null,
        institutions: formData.institutions,
        languages: formData.languages,
        countries: formData.countries,
        material_types: formData.material_types,
        academic_programs: formData.academic_programs,
      };

      if (formData.is_harvestable) {
        patchPayload.base_api_url = formData.base_api_url.trim();
        if (clearApiKey) {
          patchPayload.api_key = null;
        } else if (hasApiKeyInput) {
          patchPayload.api_key = formData.api_key.trim();
        }
      } else {
        patchPayload.base_api_url = null;
        patchPayload.api_key = null;
      }

      await platformService.patchPlatform(initialData.id, patchPayload);
      router.push(`/admin/bases-de-datos/${initialData.id}`);
    } catch (err) {
      console.error("Form submit error:", err);
      if (err.data && typeof err.data === "object") {
        setFieldErrors(err.data);
      }
      setFormError(err.message || "Error al procesar la plataforma.");
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

  // Vista simplificada para CREACIÓN mínima en borrador
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
              Crear nueva plataforma
            </h1>
          </div>
          <p className="text-xs font-medium text-[#7f1218] mt-1">
            Estado inicial: <span className="font-bold">Borrador</span> · Crear NO publica el recurso.
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
            <h2 className="text-sm font-bold text-gray-900">Datos mínimos de creación</h2>
            <p className="text-xs text-gray-500">
              Registra el nombre y la URL pública para crear la ficha en borrador. Posteriormente podrás completar la clasificación, verificar la URL y publicar la plataforma.
            </p>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="name" className="text-xs font-semibold text-gray-700">
              Nombre de la plataforma / base de datos *
            </Label>
            <Input
              id="name"
              required
              value={formData.name}
              onChange={(e) => {
                setFormData({ ...formData, name: e.target.value });
                if (fieldErrors.name) setFieldErrors((prev) => ({ ...prev, name: null }));
              }}
              placeholder="Ej. SciELO, IEEE Xplore, Dialnet..."
              className="rounded-xl border-gray-200 text-sm h-11 focus:border-[#7f1218] focus:ring-1 focus:ring-[#7f1218]"
            />
            {fieldErrors.name && (
              <p className="text-xs text-rose-600 font-medium">
                {Array.isArray(fieldErrors.name) ? fieldErrors.name.join(", ") : fieldErrors.name}
              </p>
            )}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="public_url" className="text-xs font-semibold text-gray-700">
              URL Pública de Acceso *
            </Label>
            <Input
              id="public_url"
              type="url"
              required
              value={formData.public_url}
              onChange={(e) => {
                setFormData({ ...formData, public_url: e.target.value });
                if (fieldErrors.public_url) setFieldErrors((prev) => ({ ...prev, public_url: null }));
              }}
              placeholder="https://www.scielo.org"
              className="rounded-xl border-gray-200 text-sm h-11 focus:border-[#7f1218] focus:ring-1 focus:ring-[#7f1218]"
            />
            {fieldErrors.public_url && (
              <p className="text-xs text-rose-600 font-medium">
                {Array.isArray(fieldErrors.public_url) ? fieldErrors.public_url.join(", ") : fieldErrors.public_url}
              </p>
            )}
            <p className="text-[11px] text-gray-400">
              La URL se registrará con estado &quot;Sin verificar&quot;. Podrás ejecutar la prueba de disponibilidad desde la ficha del recurso.
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
              <span>{submitting ? "Creando..." : "Crear borrador"}</span>
            </Button>
          </div>
        </div>
      </form>
    );
  }

  // Vista completa de EDICIÓN
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
            Editar plataforma
          </h1>
        </div>
        <p className="text-xs font-medium text-[#7f1218] mt-1">
          Estado actual: {initialData?.status || "Borrador"}
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
        <h2 className="text-sm font-bold text-gray-900">Identificación</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div className="bg-white border border-gray-200 rounded-xl p-3 shadow-2xs space-y-1 md:col-span-2">
            <Label htmlFor="name" className="text-[11px] font-medium text-gray-500 block">
              Nombre *
            </Label>
            <Input
              id="name"
              required
              value={formData.name}
              onChange={(e) => {
                setFormData({ ...formData, name: e.target.value });
                if (fieldErrors.name) setFieldErrors((prev) => ({ ...prev, name: null }));
              }}
              placeholder="Nombre de la base de datos"
              className="border-0 p-0 text-xs shadow-none focus-visible:ring-0 h-6 font-semibold text-gray-900"
            />
          </div>

          <div className="bg-white border border-gray-200 rounded-xl p-3 shadow-2xs space-y-1">
            <Label htmlFor="url_image" className="text-[11px] font-medium text-gray-500 block">
              URL de imagen
            </Label>
            <Input
              id="url_image"
              type="url"
              value={formData.url_image}
              onChange={(e) => setFormData({ ...formData, url_image: e.target.value })}
              placeholder="https://.../logo.png"
              className="border-0 p-0 text-xs shadow-none focus-visible:ring-0 h-6 text-gray-800"
            />
          </div>

          <div className="bg-white border border-gray-200 rounded-xl p-3 shadow-2xs space-y-1 md:col-span-3">
            <Label htmlFor="public_url" className="text-[11px] font-medium text-gray-500 block">
              URL Pública de Acceso *
            </Label>
            <Input
              id="public_url"
              type="url"
              required
              value={formData.public_url}
              onChange={(e) => {
                setFormData({ ...formData, public_url: e.target.value });
                if (fieldErrors.public_url) setFieldErrors((prev) => ({ ...prev, public_url: null }));
              }}
              placeholder="https://www.scielo.org"
              className="border-0 p-0 text-xs shadow-none focus-visible:ring-0 h-6 text-gray-900 font-semibold"
            />
          </div>

          {/* Cosecha */}
          <div className="bg-white border border-gray-200 rounded-xl p-3 shadow-2xs space-y-1">
            <Label htmlFor="is_harvestable" className="text-[11px] font-medium text-gray-500 block">
              Cosechable vía API
            </Label>
            <select
              id="is_harvestable"
              value={formData.is_harvestable ? "true" : "false"}
              onChange={(e) => {
                const val = e.target.value === "true";
                setFormData((prev) => ({
                  ...prev,
                  is_harvestable: val,
                  ...(val === false ? { base_api_url: "", api_key: "" } : {}),
                }));
              }}
              className="w-full text-xs font-semibold text-gray-900 outline-none bg-transparent h-6 cursor-pointer"
            >
              <option value="false">No (Solo acceso manual)</option>
              <option value="true">Sí (Cosechable vía API)</option>
            </select>
          </div>

          <div className="bg-white border border-gray-200 rounded-xl p-3 shadow-2xs space-y-1 md:col-span-2">
            <Label htmlFor="base_api_url" className="text-[11px] font-medium text-gray-500 block">
              URL Base API de cosecha {formData.is_harvestable ? "*" : "(deshabilitado)"}
            </Label>
            <Input
              id="base_api_url"
              type="url"
              required={formData.is_harvestable}
              disabled={!formData.is_harvestable}
              value={formData.base_api_url}
              onChange={(e) => {
                setFormData({ ...formData, base_api_url: e.target.value });
                if (fieldErrors.base_api_url) setFieldErrors((prev) => ({ ...prev, base_api_url: null }));
              }}
              placeholder={formData.is_harvestable ? "https://api.scielo.org/v1/oai" : "Activar cosecha para habilitar"}
              className="border-0 p-0 text-xs shadow-none focus-visible:ring-0 h-6 text-gray-800 disabled:opacity-40"
            />
          </div>

          <div className="bg-white border border-gray-200 rounded-xl p-3 shadow-2xs space-y-1">
            <Label htmlFor="api_key" className="text-[11px] font-medium text-gray-500 block">
              API Key (escritura)
            </Label>
            <Input
              id="api_key"
              type="password"
              value={formData.api_key}
              onChange={(e) => {
                setClearApiKey(false);
                setFormData({ ...formData, api_key: e.target.value });
              }}
              disabled={clearApiKey || !formData.is_harvestable}
              placeholder={
                !formData.is_harvestable
                  ? "Activar cosecha para habilitar"
                  : clearApiKey
                  ? "Clave eliminada"
                  : "Escriba para cambiar clave existente"
              }
              className="border-0 p-0 text-xs shadow-none focus-visible:ring-0 h-6 text-gray-800 disabled:opacity-40"
            />
            {formData.is_harvestable && (
              <label className="flex items-center gap-1.5 text-[10px] text-gray-600 cursor-pointer pt-1 font-medium">
                <input
                  type="checkbox"
                  checked={clearApiKey}
                  onChange={(e) => {
                    setClearApiKey(e.target.checked);
                    if (e.target.checked) setFormData((prev) => ({ ...prev, api_key: "" }));
                  }}
                  className="rounded border-gray-300 text-[#7f1218] focus:ring-[#7f1218]"
                />
                <span>Eliminar clave existente</span>
              </label>
            )}
          </div>
        </div>
      </div>

      {/* SECCIÓN 2: Cobertura & Clasificación */}
      <div className="space-y-3 pt-2">
        <h2 className="text-sm font-bold text-gray-900">Cobertura y Clasificación</h2>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Institución responsable */}
          <div className="bg-white border border-gray-200 rounded-xl p-4 shadow-2xs space-y-2.5">
            <div className="flex items-center justify-between pb-1 border-b border-gray-100">
              <Label className="text-[11px] font-bold text-gray-700 uppercase tracking-wider block">
                Institución responsable
              </Label>
              <span className="text-[10px] bg-slate-100 text-slate-600 font-semibold px-2 py-0.5 rounded-full">
                {formData.institutions.length} seleccionados
              </span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-52 overflow-y-auto pr-1">
              {catalogs.institutions.map((inst) => {
                const isSelected = formData.institutions.includes(inst.id);
                return (
                  <div
                    key={inst.id}
                    onClick={() => handleMultiSelectToggle("institutions", inst.id)}
                    className={`flex items-center justify-between p-2.5 rounded-lg text-xs cursor-pointer border transition-all ${
                      isSelected
                        ? "bg-[#7f1218]/5 border-[#7f1218] text-gray-900 font-semibold shadow-2xs"
                        : "bg-white border-gray-200 text-gray-700 hover:bg-gray-50"
                    }`}
                  >
                    <span className="truncate pr-1">{inst.name}</span>
                    <div className={`w-4 h-4 rounded flex items-center justify-center border transition-all shrink-0 ${isSelected ? "bg-[#7f1218] border-[#7f1218] text-white" : "border-gray-300 bg-white"}`}>
                      {isSelected && <Check className="w-3 h-3" />}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Idiomas */}
          <div className="bg-white border border-gray-200 rounded-xl p-4 shadow-2xs space-y-2.5">
            <div className="flex items-center justify-between pb-1 border-b border-gray-100">
              <Label className="text-[11px] font-bold text-gray-700 uppercase tracking-wider block">
                Idiomas
              </Label>
              <span className="text-[10px] bg-slate-100 text-slate-600 font-semibold px-2 py-0.5 rounded-full">
                {formData.languages.length} seleccionados
              </span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-52 overflow-y-auto pr-1">
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
                    <span className="truncate pr-1">{lang.name}</span>
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
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-52 overflow-y-auto pr-1">
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
                      <span>{country.name}</span>
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
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-52 overflow-y-auto pr-1">
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
                    <span className="truncate pr-1">{mat.name}</span>
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

      {/* SECCIÓN 3: Acceso y búsqueda */}
      <div className="space-y-3 pt-2">
        <h2 className="text-sm font-bold text-gray-900">Acceso y búsqueda</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div className="bg-white border border-gray-200 rounded-xl p-3 shadow-2xs space-y-1">
            <Label htmlFor="requires_registration" className="text-[11px] font-medium text-gray-500 block">
              ¿Exige registro previo?
            </Label>
            <select
              id="requires_registration"
              value={formData.requires_registration ? "true" : "false"}
              onChange={(e) => setFormData({ ...formData, requires_registration: e.target.value === "true" })}
              className="w-full text-xs font-semibold text-gray-900 outline-none bg-transparent h-6 cursor-pointer"
            >
              <option value="false">No (Acceso libre)</option>
              <option value="true">Sí (Exige registro)</option>
            </select>
          </div>

          <div className="bg-white border border-gray-200 rounded-xl p-3 shadow-2xs space-y-1">
            <Label htmlFor="has_access_text" className="text-[11px] font-medium text-gray-500 block">
              ¿Texto completo disponible?
            </Label>
            <select
              id="has_access_text"
              value={formData.has_access_text ? "true" : "false"}
              onChange={(e) => setFormData({ ...formData, has_access_text: e.target.value === "true" })}
              className="w-full text-xs font-semibold text-gray-900 outline-none bg-transparent h-6 cursor-pointer"
            >
              <option value="true">Sí (Texto completo)</option>
              <option value="false">No (Solo resúmenes / citas)</option>
            </select>
          </div>

          <div className="bg-white border border-gray-200 rounded-xl p-3 shadow-2xs space-y-1">
            <Label htmlFor="valid_sintaxis" className="text-[11px] font-medium text-gray-500 block">
              Sintaxis de búsqueda admitida
            </Label>
            <select
              id="valid_sintaxis"
              value={formData.valid_sintaxis}
              onChange={(e) => setFormData({ ...formData, valid_sintaxis: e.target.value })}
              className="w-full text-xs font-semibold text-gray-900 outline-none bg-transparent h-6 cursor-pointer"
            >
              <option value="">Seleccione sintaxis...</option>
              {catalogs.sintaxis.map((s) => (
                <option key={s.id} value={s.id}>
                  {capitalizeWords(s.name)}
                </option>
              ))}
            </select>
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
