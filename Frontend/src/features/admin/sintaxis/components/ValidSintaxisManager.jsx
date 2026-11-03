"use client";

import { useEffect, useState } from "react";
import { platformService } from "@/features/admin/databases/services/platformService";
import { AlertCircle, Pencil, Plus, Trash2, X } from "lucide-react";

const FIELD_KEYS = ["title", "author", "subject", "issn", "language", "year"];
const BOOLEAN_OPTIONS = ["AND", "OR", "XOR", "NAND", "NOR", "NOT"];
const EMPTY = { name: "", booleans: [], parenthesis: false, fields: Object.fromEntries(FIELD_KEYS.map((key) => [key, ""])) };

function getErrorMessage(error) {
  const data = error?.data;
  return data?.detail || data?.message || data?.error || error?.message || "Ocurrió un error.";
}

export default function ValidSintaxisManager() {
  const [items, setItems] = useState([]);
  const [form, setForm] = useState(EMPTY);
  const [editingId, setEditingId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [similarity, setSimilarity] = useState(null);
  const [pendingPayload, setPendingPayload] = useState(null);

  const reload = async () => {
    setLoading(true);
    try { setItems(await platformService.getValidSintaxisList()); }
    catch (err) { setError(getErrorMessage(err)); }
    finally { setLoading(false); }
  };
  useEffect(() => { reload(); }, []);

  const startEdit = (item) => {
    const sourceFields = item.fields || {};
    setEditingId(item.id);
    setForm({
      name: item.name || "",
      booleans: Array.isArray(item.booleans) ? item.booleans.map((value) => String(value).toUpperCase()).filter((value) => BOOLEAN_OPTIONS.includes(value)) : [],
      parenthesis: Boolean(item.parenthesis),
      fields: Object.fromEntries(FIELD_KEYS.map((key) => [key, String(sourceFields[key] ?? "")])),
    });
    setError("");
  };
  const reset = () => { setForm(EMPTY); setEditingId(null); setSimilarity(null); setPendingPayload(null); };
  const payload = () => ({
    name: form.name.trim(),
    booleans: form.booleans.map((value) => String(value).toUpperCase()).filter((value) => BOOLEAN_OPTIONS.includes(value)),
    parenthesis: Boolean(form.parenthesis),
    fields: Object.fromEntries(FIELD_KEYS.map((key) => [key, String(form.fields[key] || "")])),
  });

  const save = async (data) => {
    setSaving(true); setError("");
    try {
      if (editingId) await platformService.updateValidSintaxis(editingId, data);
      else await platformService.createValidSintaxis(data);
      reset(); await reload();
    } catch (err) {
      if (!editingId && err.status === 400 && err.data?.existing_id !== undefined) {
        setError(`Esta configuración de sintaxis ya existe con el ID ${err.data.existing_id}.`);
      } else setError(getErrorMessage(err));
    } finally { setSaving(false); }
  };

  const submit = async (event) => {
    event.preventDefault(); setError("");
    const data = payload();
    if (!data.name) { setError("El nombre es obligatorio."); return; }
    if (editingId) { await save(data); return; }
    setSaving(true);
    try {
      const result = await platformService.findSimilarSintaxis({ booleans: data.booleans, parenthesis: data.parenthesis, fields: data.fields });
      const matches = Array.isArray(result) ? result : result.results || result.similarities || (result.similarity !== undefined ? [result] : []);
      const highMatches = matches.filter((match) => Number(match.similarity ?? match.similarity_percentage ?? match.percentage ?? match.score ?? 0) >= 70);
      if (highMatches.length) { setPendingPayload(data); setSimilarity(highMatches); }
      else await save(data);
    } catch (err) {
      if (err.status === 400 && err.data?.existing_id !== undefined) setError(`Esta configuración de sintaxis ya existe con el ID ${err.data.existing_id}.`);
      else setError(getErrorMessage(err));
    } finally { setSaving(false); }
  };

  const remove = async (item) => {
    if (!window.confirm(`¿Eliminar la sintaxis “${item.name}”?`)) return;
    setError("");
    try { await platformService.deleteValidSintaxis(item.id); await reload(); }
    catch (err) { setError(getErrorMessage(err)); }
  };

  return <div className="mx-auto max-w-5xl space-y-6">
    <header className="flex items-center justify-between gap-4"><div><h1 className="text-2xl font-bold">Sintaxis válidas</h1><p className="mt-1 text-sm text-gray-500">Administra los formatos de búsqueda admitidos por las plataformas.</p></div></header>
    {error && <div role="alert" className="flex gap-2 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800"><AlertCircle className="h-5 w-5 shrink-0" />{error}</div>}
    <form onSubmit={submit} className="space-y-4 rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
      <div className="flex items-center justify-between"><h2 className="font-semibold">{editingId ? `Editar sintaxis #${editingId}` : "Crear sintaxis"}</h2>{editingId && <button type="button" onClick={reset} aria-label="Cancelar edición"><X className="h-4 w-4" /></button>}</div>
      <label className="block text-sm font-medium">Nombre<input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2" /></label>
      <fieldset><legend className="mb-2 text-sm font-medium">Operadores booleanos</legend><div className="flex flex-wrap gap-2">{BOOLEAN_OPTIONS.map((operator) => <label key={operator} className={`inline-flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-sm font-semibold ${form.booleans.includes(operator) ? "border-[#7f1218] bg-rose-50 text-[#7f1218]" : "border-gray-300 bg-white text-gray-700"}`}><input type="checkbox" checked={form.booleans.includes(operator)} onChange={(event) => setForm({ ...form, booleans: event.target.checked ? [...form.booleans, operator] : form.booleans.filter((value) => value !== operator) })} />{operator}</label>)}</div></fieldset>
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.parenthesis} onChange={(e) => setForm({ ...form, parenthesis: e.target.checked })} />Admite paréntesis</label>
      <fieldset><legend className="mb-2 text-sm font-semibold">Campos y sintaxis</legend><div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{FIELD_KEYS.map((key) => <label key={key} className="text-sm capitalize">{key}<input value={form.fields[key]} onChange={(e) => setForm({ ...form, fields: { ...form.fields, [key]: e.target.value } })} className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2" /></label>)}</div></fieldset>
      <button disabled={saving} className="inline-flex items-center gap-2 rounded-lg bg-[#7f1218] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"><Plus className="h-4 w-4" />{saving ? "Guardando…" : editingId ? "Guardar cambios" : "Crear sintaxis"}</button>
    </form>
    <section className="overflow-hidden rounded-2xl border border-gray-200 bg-white"><h2 className="border-b p-4 font-semibold">Configuraciones existentes</h2>{loading ? <p className="p-5 text-sm text-gray-500">Cargando…</p> : items.length === 0 ? <p className="p-5 text-sm text-gray-500">No hay sintaxis configuradas.</p> : <ul className="divide-y">{items.map((item) => <li key={item.id} className="flex items-center justify-between gap-3 p-4"><div><p className="font-medium">{item.name}</p><p className="mt-1 text-xs text-gray-500">ID {item.id} · {item.parenthesis ? "Con paréntesis" : "Sin paréntesis"} · {(item.booleans || []).join(", ") || "Sin operadores"}</p></div><div className="flex gap-2"><button type="button" onClick={() => startEdit(item)} aria-label={`Editar ${item.name}`} className="rounded-lg border p-2 hover:bg-gray-50"><Pencil className="h-4 w-4" /></button><button type="button" onClick={() => remove(item)} aria-label={`Eliminar ${item.name}`} className="rounded-lg border p-2 text-rose-700 hover:bg-rose-50"><Trash2 className="h-4 w-4" /></button></div></li>)}</ul>}</section>
    {similarity && <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"><div role="dialog" aria-modal="true" className="w-full max-w-lg space-y-4 rounded-2xl bg-white p-6 shadow-xl"><h2 className="text-lg font-bold">Se encontraron configuraciones similares</h2><p className="text-sm text-gray-600">Una o más configuraciones coinciden al menos en un 70%:</p><ul className="space-y-2 text-sm">{similarity.map((item, index) => <li key={item.id ?? index} className="rounded-lg bg-amber-50 p-3"><b>{item.name || `Sintaxis #${item.id}`}</b> · {item.similarity ?? item.percentage ?? item.score}%<p className="mt-1">Campos coincidentes: {(item.matching_fields || []).join(", ") || "No especificados"}</p></li>)}</ul><div className="flex justify-end gap-2"><button type="button" onClick={() => { setSimilarity(null); setPendingPayload(null); }} className="rounded-lg border px-4 py-2 text-sm">Cancelar</button><button type="button" onClick={() => { const data = pendingPayload; setSimilarity(null); setPendingPayload(null); if (data) save(data); }} className="rounded-lg bg-[#7f1218] px-4 py-2 text-sm font-semibold text-white">Crear de todas formas</button></div></div></div>}
  </div>;
}
