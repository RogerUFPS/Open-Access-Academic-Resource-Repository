"use client";

const DEFAULT_FIELDS = ["title", "author", "subject", "issn", "language", "year"];

export function SyntaxFieldsEditor({ template, fields = {}, onChange }) {
  const keys = template && typeof template === "object"
    ? Object.keys(template).filter((key) => DEFAULT_FIELDS.includes(key))
    : DEFAULT_FIELDS;

  const enabledKeys = keys.filter((key) => Object.prototype.hasOwnProperty.call(fields, key));

  const toggleField = (key, enabled) => {
    const next = { ...fields };
    if (enabled) next[key] = typeof next[key] === "string" ? next[key] : "";
    else delete next[key];
    onChange(next);
  };

  return (
    <fieldset>
      <legend className="mb-2 text-sm font-semibold text-slate-800">Campos admitidos</legend>
      <div className="grid gap-3 sm:grid-cols-2">
        {keys.map((key) => (
          <div key={key} className="rounded-lg border border-slate-200 p-3">
            <label className="flex items-center gap-2 text-sm capitalize text-slate-700">
              <input
                type="checkbox"
                checked={enabledKeys.includes(key)}
                onChange={(event) => toggleField(key, event.target.checked)}
              />
              {key}
            </label>
            {enabledKeys.includes(key) && (
              <input
                value={typeof fields[key] === "string" ? fields[key] : ""}
                onChange={(event) => onChange({ ...fields, [key]: event.target.value })}
                placeholder="Prefijo (opcional)"
                className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              />
            )}
          </div>
        ))}
      </div>
    </fieldset>
  );
}
