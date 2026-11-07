"use client";

import { useEffect, useState } from "react";
import { platformService } from "../services/platformService";
import { SyntaxFieldsEditor } from "./SyntaxFieldsEditor";

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
  const fields = Object.fromEntries(
    Object.entries(form.fields).filter(([, value]) => typeof value === "string")
  );
  return {
    name: form.name.trim(),
    booleans: [...form.booleans],
    parenthesis: Boolean(form.parenthesis),
    fields,
  };
}

export function ValidSintaxisModal({ mode, item, canDelete, onClose, onSaved, onDeleted }) {
  const [form, setForm] = useState(() => toForm(item));
  const [template, setTemplate] = useState(item?.fields_template || null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState({});
  const [matches, setMatches] = useState(null);
  const [pendingPayload, setPendingPayload] = useState(null);
  const [existingId, setExistingId] = useState(null);
  const [deleteExplanation, setDeleteExplanation] = useState("");

  useEffect(() => {
    const load = async () => {
      if (mode !== "edit" || !item?.id) return;
      try {
        const current = await platformService.getValidSintaxisById(item.id);
        setForm(toForm(current));
        setTemplate(current.fields_template || item.fields_template || null);
      } catch (err) {
        setError(err.message || "No se pudo cargar la sintaxis.");
      }
    };
    load();
  }, [mode, item]);

  const operators = Array.from(new Set([...KNOWN_OPERATORS, ...form.booleans]));

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
      onSaved(saved);
    } catch (err) {
      if (!mode && err.status === 400 && err.data?.existing_id !== undefined) {
        setExistingId(Number(err.data.existing_id));
      } else {
        setError(err.data?.detail || err.message || "No se pudo guardar la sintaxis.");
        if (err.data && typeof err.data === "object") setFieldErrors(err.data);
      }
    } finally {
      setSaving(false);
    }
  };

  const submit = async (event) => {
    event.preventDefault();
    const payload = cleanPayload(form);
    if (!payload.name) {
      setFieldErrors({ name: ["El nombre es obligatorio."] });
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
      } else {
        await save(payload);
      }
    } catch (err) {
      setError(err.data?.detail || err.message || "No se pudo comprobar sintaxis similares.");
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    if (!window.confirm(`¿Eliminar la sintaxis "${item.name}"?`)) return;
    setSaving(true);
    try {
      await platformService.deleteValidSintaxis(item.id, deleteExplanation);
      onDeleted(item.id);
    } catch (err) {
      const detail = err.data?.detail || err.message || "";
      if (err.status === 400 && /delete_explanation|explicación/i.test(JSON.stringify(err.data))) {
        const explanation = window.prompt("Esta sintaxis requiere una explicación de eliminación:");
        if (explanation) {
          setDeleteExplanation(explanation);
          await platformService.deleteValidSintaxis(item.id, explanation);
          onDeleted(item.id);
        }
      } else {
        setError(detail);
      }
    } finally {
      setSaving(false);
    }
  };

  const unknown = form.booleans.filter((value) => !KNOWN_OPERATORS.includes(value));

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-slate-950/40 p-4" role="dialog" aria-modal="true">
      <form onSubmit={submit} className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-2xl bg-white shadow-xl">
        <div className="flex items-center justify-between border-b px-5 py-4">
          <h2 className="font-semibold text-slate-900">{mode === "edit" ? "Editar sintaxis" : "Crear sintaxis"}</h2>
          <button type="button" onClick={onClose} className="text-slate-500" aria-label="Cerrar">Cerrar</button>
        </div>
        <div className="space-y-5 p-5">
          {error && <div role="alert" className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error}</div>}
          {existingId && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm">
              La configuración ya existe.
              <button
                type="button"
                className="ml-2 font-semibold underline"
                onClick={async () => {
                  try {
                    const existing = await platformService.getValidSintaxisById(existingId);
                    onSaved(existing);
                  } catch (err) {
                    setError(err.message || "No se pudo cargar la sintaxis existente.");
                  }
                }}
              >
                Editar la existente
              </button>
            </div>
          )}
          <label className="block text-sm font-medium">
            Nombre
            <input required maxLength={150} value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2" />
            {fieldErrors.name && <span className="mt-1 block text-xs text-rose-600">{fieldErrors.name.join(", ")}</span>}
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
                <p key={match.id} className="mt-1 text-sm">{match.name} — {match.similarity}%</p>
              ))}
              <div className="mt-3 flex gap-2">
                <button type="button" onClick={() => setMatches(null)} className="rounded-lg border px-3 py-2 text-sm">Cancelar</button>
                <button type="button" disabled={saving} onClick={() => save(pendingPayload)} className="rounded-lg bg-[#C8102E] px-3 py-2 text-sm text-white">Crear de todas formas</button>
              </div>
            </div>
          )}
        </div>
        <div className="flex justify-between border-t px-5 py-4">
          {mode === "edit" && canDelete ? (
            <button type="button" disabled={saving} onClick={remove} className="rounded-lg text-sm font-semibold text-rose-700">Eliminar</button>
          ) : <span />}
          <div className="flex gap-2">
            <button type="button" onClick={onClose} className="rounded-lg border px-4 py-2 text-sm">Cancelar</button>
            <button type="submit" disabled={saving || Boolean(matches)} className="rounded-lg bg-[#C8102E] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">
              {saving ? "Guardando…" : "Guardar sintaxis"}
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}
