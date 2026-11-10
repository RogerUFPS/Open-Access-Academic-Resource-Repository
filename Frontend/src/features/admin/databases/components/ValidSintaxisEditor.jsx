"use client";

import { useEffect, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { platformService } from "../services/platformService";
import { SyntaxFieldsEditor } from "./SyntaxFieldsEditor";
import { extractApiErrorText, normalizeApiFieldErrors } from "@/shared/services/apiClient";

const KNOWN_OPERATORS = ["AND", "OR", "NOT", "XOR", "NAND", "NOR"];

function toForm(item) {
  return {
    name: item?.name || "",
    booleans: Array.isArray(item?.booleans) ? item.booleans.map(String) : [],
    parenthesis: Boolean(item?.parenthesis),
    fields: item?.fields && typeof item.fields === "object" ? { ...item.fields } : {},
  };
}

function cleanPayload(form) {
  const fields = Object.fromEntries(Object.entries(form.fields).filter(([, value]) => typeof value === "string"));
  return {
    name: form.name.trim(),
    booleans: [...form.booleans],
    parenthesis: Boolean(form.parenthesis),
    fields,
  };
}

/**
 * Editor en línea de ValidSintaxis (sin modal). Se renderiza dentro del
 * formulario de la plataforma, así que no usa <form>: Enter no debe enviar
 * la plataforma y los botones son type="button".
 */
export function ValidSintaxisEditor({ mode, item, usageCount, canDelete, onCancel, onSaved, onDeleted, onUseExisting }) {
  const [form, setForm] = useState(() => toForm(item));
  const [template, setTemplate] = useState(item?.fields_template || null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState({});
  const [matches, setMatches] = useState(null);
  const [pendingPayload, setPendingPayload] = useState(null);
  const [existingId, setExistingId] = useState(null);

  useEffect(() => {
    if (mode !== "edit" || !item?.id) return undefined;
    let cancelled = false;
    platformService
      .getValidSintaxisById(item.id)
      .then((current) => {
        if (cancelled) return;
        setForm(toForm(current));
        setTemplate(current.fields_template || item.fields_template || null);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message || "No se pudo cargar la sintaxis.");
      });
    return () => {
      cancelled = true;
    };
  }, [mode, item]);

  const operators = Array.from(new Set([...KNOWN_OPERATORS, ...form.booleans]));
  const unknown = form.booleans.filter((value) => !KNOWN_OPERATORS.includes(value));

  const setBoolean = (operator, checked) => {
    setForm((current) => ({
      ...current,
      booleans: checked
        ? [...current.booleans.filter((value) => value !== operator), operator]
        : current.booleans.filter((value) => value !== operator),
    }));
  };

  const save = async (payload) => {
    setSaving(true);
    setError("");
    setFieldErrors({});
    try {
      const saved = mode === "edit"
        ? await platformService.updateValidSintaxis(item.id, payload)
        : await platformService.createValidSintaxis(payload);
      onSaved(saved, mode);
    } catch (err) {
      if (mode === "create" && err.status === 400 && err.data?.existing_id !== undefined) {
        setExistingId(Number(err.data.existing_id));
      } else {
        setError(extractApiErrorText(err.data) || err.message || "No se pudo guardar la sintaxis.");
        if (err.data && typeof err.data === "object") setFieldErrors(normalizeApiFieldErrors(err.data));
      }
    } finally {
      setSaving(false);
    }
  };

  const submit = async () => {
    const payload = cleanPayload(form);
    if (!payload.name) {
      setFieldErrors({ name: "El nombre es obligatorio." });
      return;
    }
    if (mode === "edit") {
      await save(payload);
      return;
    }
    setSaving(true);
    try {
      const result = await platformService.findSimilarSintaxis({
        booleans: payload.booleans,
        parenthesis: payload.parenthesis,
        fields: payload.fields,
      });
      const found = (Array.isArray(result) ? result : result?.results || []).filter(
        (match) => Number(match.similarity) >= 70
      );
      if (found.length) {
        setMatches(found);
        setPendingPayload(payload);
        setSaving(false);
      } else {
        await save(payload);
      }
    } catch (err) {
      setError(extractApiErrorText(err.data) || err.message || "No se pudo comprobar sintaxis similares.");
      setSaving(false);
    }
  };

  const remove = async () => {
    if (!window.confirm(`¿Eliminar la sintaxis "${item.name}"? Las plataformas que la usan quedarán sin sintaxis.`)) return;
    setSaving(true);
    setError("");
    try {
      await platformService.deleteValidSintaxis(item.id);
      onDeleted(item.id);
    } catch (err) {
      if (err.status === 400 && /delete_explanation|explicación/i.test(JSON.stringify(err.data))) {
        const explanation = window.prompt("Esta sintaxis requiere una explicación de eliminación:");
        if (explanation) {
          try {
            await platformService.deleteValidSintaxis(item.id, explanation);
            onDeleted(item.id);
          } catch (retryError) {
            setError(extractApiErrorText(retryError.data) || retryError.message || "No se pudo eliminar la sintaxis.");
          }
        }
      } else {
        setError(extractApiErrorText(err.data) || err.message || "No se pudo eliminar la sintaxis.");
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="space-y-4 rounded-xl border border-slate-300 bg-slate-50 p-4"
      aria-label={mode === "edit" ? "Editar sintaxis existente" : "Crear nueva sintaxis"}
      role="group"
      onKeyDown={(event) => {
        // Evita que Enter envíe el formulario de la plataforma.
        if (event.key === "Enter" && event.target.tagName === "INPUT") event.preventDefault();
      }}
    >
      <h3 className="text-sm font-semibold text-slate-900">
        {mode === "edit" ? `Editar sintaxis existente: ${item?.name || ""}` : "Crear nueva sintaxis"}
      </h3>

      {mode === "edit" && (
        <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <p>
            Esta sintaxis es compartida. Al guardar, el cambio se aplica a{" "}
            <strong>
              {usageCount == null
                ? "todas las plataformas que la usan"
                : `las ${usageCount} ${usageCount === 1 ? "plataforma que la usa" : "plataformas que la usan"}`}
            </strong>
            , no solo a esta. Si solo esta plataforma necesita algo distinto, crea una sintaxis nueva.
          </p>
        </div>
      )}

      {error && <div role="alert" className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error}</div>}
      {existingId && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm">
          Ya existe una sintaxis con esta configuración.
          <button type="button" className="ml-2 font-semibold underline" onClick={() => onUseExisting(existingId)}>
            Usar la existente
          </button>
        </div>
      )}

      <label className="block text-sm font-medium">
        Nombre
        <input
          required
          maxLength={150}
          value={form.name}
          onChange={(event) => setForm({ ...form, name: event.target.value })}
          className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2"
        />
        {fieldErrors.name && <span className="mt-1 block text-xs text-rose-600">{fieldErrors.name}</span>}
      </label>

      <fieldset>
        <legend className="mb-2 text-sm font-semibold">Operadores booleanos</legend>
        <div className="flex flex-wrap gap-4">
          {operators.map((operator) => (
            <label key={operator} className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={form.booleans.includes(operator)} onChange={(event) => setBoolean(operator, event.target.checked)} />
              {operator}
            </label>
          ))}
        </div>
        {unknown.length > 0 && <p className="mt-2 text-xs text-slate-500">Operadores conservados: {unknown.join(", ")}</p>}
      </fieldset>

      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={form.parenthesis} onChange={(event) => setForm({ ...form, parenthesis: event.target.checked })} />
        Admite paréntesis
      </label>

      <SyntaxFieldsEditor template={template} fields={form.fields} onChange={(fields) => setForm({ ...form, fields })} />

      {matches && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
          <p className="font-semibold">Se encontraron sintaxis similares</p>
          {matches.map((match) => (
            <p key={match.id} className="mt-1 text-sm">
              {match.name} — {match.similarity}%{" "}
              <button type="button" className="ml-1 font-semibold underline" onClick={() => onUseExisting(match.id)}>
                Usar esta
              </button>
            </p>
          ))}
          <div className="mt-3 flex gap-2">
            <button type="button" onClick={() => setMatches(null)} className="rounded-lg border bg-white px-3 py-2 text-sm">Volver</button>
            <button type="button" disabled={saving} onClick={() => save(pendingPayload)} className="rounded-lg bg-[#C8102E] px-3 py-2 text-sm text-white">
              Crear de todas formas
            </button>
          </div>
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-200 pt-3">
        {mode === "edit" && canDelete ? (
          <button type="button" disabled={saving} onClick={remove} className="rounded-lg text-sm font-semibold text-rose-700">
            Eliminar sintaxis
          </button>
        ) : <span />}
        <div className="flex gap-2">
          <button type="button" disabled={saving} onClick={onCancel} className="rounded-lg border bg-white px-4 py-2 text-sm">
            Cancelar
          </button>
          <button
            type="button"
            disabled={saving || Boolean(matches)}
            onClick={submit}
            className="rounded-lg bg-[#C8102E] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
          >
            {saving ? "Guardando…" : mode === "edit" ? "Guardar cambios en la sintaxis" : "Crear sintaxis"}
          </button>
        </div>
      </div>
    </div>
  );
}
