"use client";

import { AlertCircle, Check, CheckCircle2, Circle, XCircle } from "lucide-react";
import { capitalizeWords } from "@/lib/utils";
import { errorSummary } from "@/shared/utils/formErrors";

export const fieldErrorId = (field) => `${field}-error`;
export const fieldAnchorId = (field) => `field-${field}`;

function toText(message) {
  if (!message) return "";
  return Array.isArray(message) ? message.join(" ") : String(message);
}

/** Mensaje bajo el control. Usar su id en `aria-describedby`. */
export function FieldError({ field, message }) {
  const text = toText(message);
  if (!text) return null;
  return (
    <p id={fieldErrorId(field)} className="text-[11px] text-rose-600 font-medium mt-1">
      {text}
    </p>
  );
}

/** Tarjeta de sección con título, descripción y separación visual. */
export function FormSection({ id, number, title, description, aside, children }) {
  const titleId = `${id}-title`;
  return (
    <section
      aria-labelledby={titleId}
      className="space-y-3 rounded-2xl border border-gray-200 bg-gray-50/60 p-4 sm:p-5"
    >
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 id={titleId} className="text-sm font-bold text-gray-900 flex items-center gap-2">
            {number != null && (
              <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-[#C8102E] text-[10px] font-bold text-white">
                {number}
              </span>
            )}
            {title}
          </h2>
          {description && <p className="text-[11px] text-gray-500 mt-0.5">{description}</p>}
        </div>
        {aside}
      </header>
      {children}
    </section>
  );
}

/** Resumen de errores en la parte superior del formulario. */
export function FormErrorSummary({ message, fieldErrors }) {
  const entries = errorSummary(fieldErrors).filter((entry) => entry.field !== "detail");
  const detail = toText(fieldErrors?.detail);
  const headline = message || detail;
  if (!headline && entries.length === 0) return null;

  const focusField = (field) => {
    const target = document.getElementById(fieldAnchorId(field));
    if (!target) return;
    target.scrollIntoView({ behavior: "smooth", block: "center" });
    target.querySelector("input, select, button, textarea")?.focus({ preventScroll: true });
  };

  return (
    <div
      role="alert"
      className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-xs font-medium flex items-start gap-3 shadow-2xs"
    >
      <AlertCircle className="w-5 h-5 text-rose-600 shrink-0 mt-0.5" aria-hidden="true" />
      <div className="min-w-0">
        <p className="font-bold text-sm">Atención en el formulario</p>
        {headline && <p className="mt-0.5 leading-relaxed">{headline}</p>}
        {entries.length > 0 && (
          <ul className="mt-2 space-y-1 list-disc pl-4">
            {entries.map((entry) => (
              <li key={entry.field}>
                <button
                  type="button"
                  onClick={() => focusField(entry.field)}
                  className="font-semibold underline-offset-2 hover:underline cursor-pointer"
                >
                  {entry.label}:
                </button>{" "}
                {entry.message}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

/** Lista de requisitos de publicación con su estado. */
export function PublishChecklist({ items, title = "Requisitos para publicar", description }) {
  const done = items.filter((item) => item.done).length;
  const complete = done === items.length;
  return (
    <div className="rounded-2xl border border-gray-200 bg-white p-4 shadow-2xs space-y-3">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-xs font-bold uppercase tracking-wide text-gray-700">{title}</h3>
        <span
          className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
            complete ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-800"
          }`}
        >
          {done}/{items.length}
        </span>
      </div>
      {description && <p className="text-[11px] text-gray-500">{description}</p>}
      <ul className="space-y-1.5">
        {items.map((item) => (
          <li key={item.key} className="flex items-start gap-2 text-xs">
            {item.done ? (
              <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-600" aria-hidden="true" />
            ) : item.failed ? (
              <XCircle className="w-4 h-4 shrink-0 text-rose-600" aria-hidden="true" />
            ) : (
              <Circle className="w-4 h-4 shrink-0 text-gray-400" aria-hidden="true" />
            )}
            <span className="min-w-0">
              <span className={item.done ? "text-gray-800" : "text-gray-600"}>{item.label}</span>
              <span className="sr-only">{item.done ? " (cumplido)" : " (pendiente)"}</span>
              {item.hint && <span className="block text-[10px] text-gray-500">{item.hint}</span>}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Selector múltiple en cuadrícula para catálogos cortos. */
export function CatalogCheckboxGrid({ field, label, items, selected, onToggle, renderLabel, error, required = false }) {
  const labelId = `${field}-label`;
  return (
    <div
      id={fieldAnchorId(field)}
      className={`bg-white border rounded-xl p-4 shadow-2xs space-y-2.5 ${error ? "border-rose-300 ring-1 ring-rose-200" : "border-gray-200"}`}
    >
      <div className="flex items-center justify-between pb-1 border-b border-gray-100">
        <span id={labelId} className="text-[11px] font-bold text-gray-700 uppercase tracking-wider block">
          {label}
          {required && <span className="text-[#C8102E]"> *</span>}
        </span>
        <span className="text-[10px] bg-slate-100 text-slate-600 font-semibold px-2 py-0.5 rounded-full">
          {selected.length} seleccionados
        </span>
      </div>
      <div
        role="group"
        aria-labelledby={labelId}
        aria-describedby={error ? fieldErrorId(field) : undefined}
        className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-64 sm:max-h-72 overflow-y-auto pr-1"
      >
        {items.length === 0 && <p className="text-[11px] text-gray-400 italic">Sin opciones disponibles.</p>}
        {items.map((item) => {
          const isSelected = selected.includes(item.id);
          return (
            <button
              type="button"
              role="checkbox"
              aria-checked={isSelected}
              key={item.id}
              onClick={() => onToggle(item.id)}
              className={`flex items-center justify-between p-2.5 rounded-lg text-xs text-left cursor-pointer border transition-all ${
                isSelected
                  ? "bg-rose-50/70 border-[#C8102E] text-gray-900 font-semibold shadow-2xs"
                  : "bg-white border-gray-200 text-gray-700 hover:bg-gray-50 hover:border-gray-300"
              }`}
            >
              <span className="truncate pr-1">{renderLabel ? renderLabel(item) : capitalizeWords(item.name)}</span>
              <span
                aria-hidden="true"
                className={`w-4 h-4 rounded flex items-center justify-center border transition-all shrink-0 ${
                  isSelected ? "bg-[#C8102E] border-[#C8102E] text-white" : "border-gray-300 bg-white"
                }`}
              >
                {isSelected && <Check className="w-3 h-3" />}
              </span>
            </button>
          );
        })}
      </div>
      <FieldError field={field} message={error} />
    </div>
  );
}
