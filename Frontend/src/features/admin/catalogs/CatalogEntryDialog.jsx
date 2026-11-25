"use client";

import { useEffect, useState } from "react";
import { catalogAdminService, CATALOG_RESOURCES } from "./catalogAdminService";
import { extractApiErrorText, normalizeApiFieldErrors } from "@/shared/services/apiClient";
import FlagPicker from "./FlagPicker";
import { suggestCountryAbbreviation } from "./flagCountries";

const focus = "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#7f1218]";
const inputClass = `mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm ${focus}`;

function requestError(error, fallback) {
  if (error?.name === "TypeError") {
    return "No se pudo conectar con el servidor. Revisa tu conexión e inténtalo nuevamente.";
  }
  return extractApiErrorText(error?.data) || error?.message || fallback;
}

function DialogFrame({ title, children, onClose, busy, labelledBy }) {
  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-slate-950/40 p-4">
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-xl bg-white shadow-xl"
      >
        <header className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
          <h2 id={labelledBy} className="text-lg font-semibold text-slate-900">{title}</h2>
          <button type="button" onClick={onClose} disabled={busy} aria-label="Cerrar" className={`rounded px-2 py-1 text-slate-500 hover:bg-slate-100 disabled:opacity-50 ${focus}`}>
            ×
          </button>
        </header>
        {children}
      </section>
    </div>
  );
}

export function CatalogEntryDialog({ resource, item, onClose, onComplete }) {
  const config = CATALOG_RESOURCES[resource];
  const editing = Boolean(item);
  const [values, setValues] = useState(() =>
    Object.fromEntries(config.fields.map((field) => [field.name, String(item?.[field.name] ?? "")]))
  );
  const [loading, setLoading] = useState(editing);
  const [saving, setSaving] = useState(false);
  const [loadFailed, setLoadFailed] = useState(false);
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState({});

  useEffect(() => {
    if (!editing) return undefined;
    let active = true;
    catalogAdminService.get(resource, item.id)
      .then((record) => {
        if (active) {
          setValues(Object.fromEntries(config.fields.map((field) => [field.name, String(record?.[field.name] ?? "")])));
          setError("");
          setLoadFailed(false);
        }
      })
      .catch((requestFailure) => {
        if (active) {
          setError(requestError(requestFailure, `No se pudo cargar la ${config.singular}.`));
          setLoadFailed(true);
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [config.fields, config.singular, editing, item?.id, resource]);

  async function submit(event) {
    event.preventDefault();
    if (loadFailed) return;
    const missing = Object.fromEntries(
      config.fields
        .filter((field) => !values[field.name]?.trim())
        .map((field) => [field.name, `${field.label} es obligatorio.`])
    );
    if (Object.keys(missing).length) {
      setFieldErrors(missing);
      setError("Completa los campos obligatorios.");
      return;
    }

    const payload = Object.fromEntries(
      config.fields.map((field) => [field.name, values[field.name].trim()])
    );
    setSaving(true);
    setError("");
    setFieldErrors({});
    try {
      if (editing) await catalogAdminService.update(resource, item.id, payload);
      else await catalogAdminService.create(resource, payload);
      await onComplete(editing ? `${config.label}: cambios guardados.` : `${config.label}: registro creado.`);
    } catch (requestFailure) {
      setError(requestError(requestFailure, `No se pudo guardar la ${config.singular}.`));
      setFieldErrors(normalizeApiFieldErrors(requestFailure?.data));
    } finally {
      setSaving(false);
    }
  }

  return (
    <DialogFrame
      title={`${editing ? "Editar" : "Nuevo"} ${config.singular}`}
      labelledBy="catalog-entry-title"
      onClose={onClose}
      busy={loading || saving}
    >
      <form onSubmit={submit} noValidate>
        <div className="space-y-4 px-5 py-5">
          {error && <p role="alert" className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800">{error}</p>}
          {loading && <p role="status" className="text-sm text-slate-600">Cargando datos del registro…</p>}
          {config.fields.map((field) => field.name === "emoji_flag" ? (
            <div key={field.name}>
              <span id="catalog-emoji-flag-label" className="block text-sm font-medium text-slate-800">
                {field.label} <span aria-hidden="true" className="text-rose-700">*</span>
              </span>
              <FlagPicker
                value={values.emoji_flag}
                invalid={Boolean(fieldErrors.emoji_flag)}
                labelledBy="catalog-emoji-flag-label"
                describedBy={fieldErrors.emoji_flag ? "catalog-emoji-flag-error" : undefined}
                onChange={(emoji) => {
                  setValues((current) => ({ ...current, emoji_flag: emoji }));
                  setFieldErrors((current) => ({ ...current, emoji_flag: "" }));
                  setError("");
                }}
                onSelectCountry={(country) => {
                  setValues((current) => ({
                    ...current,
                    abbreviation: suggestCountryAbbreviation(current.abbreviation, country.code),
                  }));
                }}
              />
              {fieldErrors.emoji_flag && (
                <span id="catalog-emoji-flag-error" className="mt-1 block text-xs text-rose-700">
                  {fieldErrors.emoji_flag}
                </span>
              )}
            </div>
          ) : (
            <label key={field.name} htmlFor={`catalog-${field.name}`} className="block text-sm font-medium text-slate-800">
              {field.label} <span aria-hidden="true" className="text-rose-700">*</span>
              <input
                id={`catalog-${field.name}`}
                required
                autoComplete="off"
                value={values[field.name]}
                disabled={loading || saving || loadFailed}
                onChange={(event) => {
                  setValues((current) => ({ ...current, [field.name]: event.target.value }));
                  setFieldErrors((current) => ({ ...current, [field.name]: "" }));
                }}
                aria-invalid={Boolean(fieldErrors[field.name])}
                aria-describedby={fieldErrors[field.name] ? `catalog-${field.name}-error` : undefined}
                className={`${inputClass} ${fieldErrors[field.name] ? "border-rose-500" : ""}`}
              />
              {fieldErrors[field.name] && (
                <span id={`catalog-${field.name}-error`} className="mt-1 block text-xs text-rose-700">
                  {fieldErrors[field.name]}
                </span>
              )}
            </label>
          ))}
        </div>
        <footer className="flex flex-wrap justify-end gap-3 border-t border-slate-200 px-5 py-4">
          <button type="button" onClick={onClose} disabled={saving} className={`rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50 ${focus}`}>
            Cancelar
          </button>
          <button type="submit" disabled={loading || saving || loadFailed} className={`rounded-md bg-[#7f1218] px-4 py-2 text-sm font-semibold text-white hover:bg-[#6a0f14] disabled:opacity-50 ${focus}`}>
            {saving ? "Guardando…" : "Guardar"}
          </button>
        </footer>
      </form>
    </DialogFrame>
  );
}

export function CatalogActionDialog({ resource, item, mode, onClose, onComplete }) {
  const config = CATALOG_RESOURCES[resource];
  const archiving = mode === "archive";
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event) {
    event.preventDefault();
    if (archiving && !reason.trim()) {
      setError("El motivo de eliminación es obligatorio.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      if (archiving) await catalogAdminService.archive(resource, item.id, reason.trim());
      else await catalogAdminService.restore(resource, item.id);
      await onComplete(
        archiving
          ? `${config.label}: registro archivado.`
          : `${config.label}: registro restaurado.`
      );
    } catch (requestFailure) {
      setError(requestError(
        requestFailure,
        archiving ? `No se pudo archivar la ${config.singular}.` : `No se pudo restaurar la ${config.singular}.`
      ));
    } finally {
      setBusy(false);
    }
  }

  return (
    <DialogFrame
      title={archiving ? `Archivar ${config.singular}` : `Restaurar ${config.singular}`}
      labelledBy="catalog-action-title"
      onClose={onClose}
      busy={busy}
    >
      <form onSubmit={submit}>
        <div className="space-y-4 px-5 py-5">
          <p className="text-sm text-slate-700">
            {archiving
              ? `¿Deseas archivar «${item.name}»? El registro se conservará y podrás restaurarlo.`
              : `¿Deseas restaurar «${item.name}» y devolverlo al catálogo vigente?`}
          </p>
          {archiving && (
            <label htmlFor="catalog-delete-reason" className="block text-sm font-medium text-slate-800">
              Motivo de eliminación <span aria-hidden="true" className="text-rose-700">*</span>
              <textarea
                id="catalog-delete-reason"
                required
                rows={3}
                value={reason}
                disabled={busy}
                onChange={(event) => setReason(event.target.value)}
                className={inputClass}
              />
            </label>
          )}
          {error && <p role="alert" className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800">{error}</p>}
        </div>
        <footer className="flex flex-wrap justify-end gap-3 border-t border-slate-200 px-5 py-4">
          <button type="button" onClick={onClose} disabled={busy} className={`rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50 ${focus}`}>
            Cancelar
          </button>
          <button type="submit" disabled={busy || (archiving && !reason.trim())} className={`rounded-md px-4 py-2 text-sm font-semibold text-white disabled:opacity-50 ${archiving ? "bg-rose-700 hover:bg-rose-800" : "bg-[#7f1218] hover:bg-[#6a0f14]"} ${focus}`}>
            {busy ? "Procesando…" : archiving ? "Archivar" : "Restaurar"}
          </button>
        </footer>
      </form>
    </DialogFrame>
  );
}
