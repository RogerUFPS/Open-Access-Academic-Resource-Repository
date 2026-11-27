"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { apiClient } from "@/shared/services/apiClient";
import { canDo } from "@/shared/hooks/useViewer";
import AuditChangeDetails from "./AuditChangeDetails";
import { Field, Modal, control, fmtDate, primary, secondary } from "./auditUi";
import {
  ARCHIVE_SOURCES,
  archiveErrorMessage,
  getArchivedPage,
  nextDay,
  pastSemesters,
} from "./auditArchiveApi";

const PAGE_SIZE = 10;
// En el archivo, `action` de la auditoría general es el entero de django-auditlog.
const LOG_ACTIONS = {
  0: { name: "create", text: "CREAR", cls: "text-emerald-700" },
  1: { name: "update", text: "ACTUALIZAR", cls: "text-amber-700" },
  2: { name: "delete", text: "ELIMINAR", cls: "text-red-700" },
  3: { name: "access", text: "ACCEDER", cls: "text-slate-600" },
};

function LateBadge() {
  return (
    <span
      title="Registro que apareció después de archivar el semestre y se comprimió por decisión de un administrador."
      className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-[11px] font-semibold text-amber-800"
    >
      Agregado posteriormente
    </span>
  );
}

function JsonBlock({ value }) {
  if (value == null || (typeof value === "object" && !Object.keys(value).length)) {
    return <span className="text-slate-600">—</span>;
  }
  return (
    <pre className="max-h-64 overflow-auto rounded-md bg-slate-50 p-3 text-xs text-slate-800">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

function ArchivedDetail({ source, row, resourceLabel, onClose }) {
  const isLog = source === "auditlog";
  const meta = isLog ? LOG_ACTIONS[row.action] : null;
  return (
    <Modal
      title={`Registro archivado #${row.id}`}
      subtitle={isLog ? row.object_repr : row.action}
      onClose={onClose}
    >
      <div className="flex-1 space-y-6 overflow-y-auto px-6 py-6">
        <dl className="space-y-3">
          <Field name="Fecha y hora">{fmtDate(row.timestamp, true)}</Field>
          {row.late_addition && (
            <Field name="Origen">
              <LateBadge />
            </Field>
          )}
          {isLog ? (
            <>
              <Field name="Acción">
                <span className={`font-semibold ${meta?.cls ?? ""}`}>{meta?.text ?? row.action}</span>
              </Field>
              <Field name="Entidad">{resourceLabel(row.content_type_id)}</Field>
              <Field name="ID del objeto">#{row.object_pk}</Field>
              <Field name="Objeto">{row.object_repr || "—"}</Field>
              <Field name="Responsable">
                {row.actor_email || (row.actor_id ? `Usuario #${row.actor_id}` : "Anónimo")}
              </Field>
              <Field name="Dirección IP">{row.remote_addr || "—"}</Field>
            </>
          ) : (
            <>
              <Field name="Acción">{row.action}</Field>
              <Field name="Responsable">{row.actor_email || "—"}</Field>
              <Field name="Cuenta afectada">{row.target_email || "—"}</Field>
            </>
          )}
        </dl>
        {isLog ? (
          <AuditChangeDetails
            changes={row.changes}
            action={meta?.name}
            objectLabel={row.object_repr}
            additionalData={row.additional_data}
          />
        ) : (
          <section>
            <h3 className="mb-2 text-sm font-semibold">Detalles</h3>
            <JsonBlock value={row.details} />
          </section>
        )}
      </div>
      <div className="border-t border-slate-200 px-6 py-4">
        <button type="button" onClick={onClose} className={secondary}>Cerrar</button>
      </div>
    </Modal>
  );
}

export default function ArchivedAuditLog({ viewer }) {
  const sources = useMemo(
    () =>
      Object.entries(ARCHIVE_SOURCES)
        .filter(([, config]) => canDo(viewer, "audit", config.permission, "view"))
        .map(([key, config]) => ({ key, ...config })),
    [viewer]
  );
  const semesters = useMemo(() => pastSemesters(8), []);

  const [source, setSource] = useState(sources[0]?.key ?? "auditlog");
  const [period, setPeriod] = useState(semesters[0]?.label ?? "custom");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [query, setQuery] = useState(null); // consulta enviada: {source, startDate, endDate}
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState(null);
  const [resources, setResources] = useState({});

  // Fuente efectiva: la elegida si sigue permitida, o la primera permitida.
  const activeSource = sources.some((item) => item.key === source) ? source : sources[0]?.key ?? "auditlog";

  // Nombres de las entidades auditadas (content_type_id → etiqueta). Ese
  // catálogo requiere audit.logs.view; sin él se muestra el id del tipo.
  const canReadResources = canDo(viewer, "audit", "logs", "view");
  useEffect(() => {
    if (!canReadResources) return undefined;
    const ctl = new AbortController();
    apiClient
      .get("/api/audit/logs/resources/", {}, { signal: ctl.signal })
      .then((list) =>
        setResources(Object.fromEntries((list || []).map((item) => [item.content_type_id, item.label])))
      )
      .catch(() => {});
    return () => ctl.abort();
  }, [canReadResources]);

  // Cada consulta se registra como acceso en la auditoría: solo se envía desde
  // una acción del usuario (Consultar o cambiar de página), nunca desde un efecto.
  const controllerRef = useRef(null);
  useEffect(() => () => controllerRef.current?.abort(), []);

  const fetchPage = (nextQuery, nextPage) => {
    controllerRef.current?.abort();
    const ctl = new AbortController();
    controllerRef.current = ctl;
    setQuery(nextQuery);
    setPage(nextPage);
    setLoading(true);
    setError("");
    getArchivedPage(nextQuery.source, { ...nextQuery, page: nextPage, pageSize: PAGE_SIZE }, { signal: ctl.signal })
      .then(setData)
      .catch((err) => {
        if (err.name === "AbortError") return;
        setData(null);
        setError(archiveErrorMessage(err));
      })
      .finally(() => {
        if (controllerRef.current === ctl) setLoading(false);
      });
  };

  const resourceLabel = (contentTypeId) => resources[contentTypeId] || `Tipo #${contentTypeId}`;

  const submit = (event) => {
    event.preventDefault();
    let range;
    if (period === "custom") {
      if (!from || !to || to < from) {
        setError("Indica un rango válido: la fecha final no puede ser anterior a la inicial.");
        return;
      }
      range = { startDate: from, endDate: nextDay(to) };
    } else {
      const semester = semesters.find((item) => item.label === period);
      range = { startDate: semester.startDate, endDate: semester.endDate };
    }
    fetchPage({ source: activeSource, ...range }, 1);
  };

  if (!sources.length) {
    return <p className="text-sm text-slate-600">No tienes permiso para consultar la auditoría archivada.</p>;
  }

  const totalPages = data?.total_pages ?? 1;
  const isLog = query?.source === "auditlog";

  return (
    <section className="font-sans text-slate-900">
      <header>
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">Auditoría archivada</h1>
        <p className="mt-2 text-sm text-slate-600">
          Semestres cerrados que se comprimieron, cifraron y verificaron fuera de la base de datos. Solo lectura; cada
          consulta queda registrada en la bitácora.
        </p>
      </header>

      <form onSubmit={submit} className="mt-7 grid gap-4 rounded-lg border border-slate-200 bg-white p-4 sm:grid-cols-2 lg:grid-cols-5 sm:p-5">
        <label className="text-sm font-medium">
          Fuente
          <select className={`${control} mt-2`} value={activeSource} onChange={(e) => setSource(e.target.value)}>
            {sources.map((item) => (
              <option key={item.key} value={item.key}>{item.label}</option>
            ))}
          </select>
        </label>
        <label className="text-sm font-medium">
          Período
          <select className={`${control} mt-2`} value={period} onChange={(e) => setPeriod(e.target.value)}>
            {semesters.map((item) => (
              <option key={item.label} value={item.label}>Semestre {item.label}</option>
            ))}
            <option value="custom">Personalizado</option>
          </select>
        </label>
        {period === "custom" && (
          <>
            <label className="text-sm font-medium">
              Desde
              <input type="date" className={`${control} mt-2`} value={from} onChange={(e) => setFrom(e.target.value)} />
            </label>
            <label className="text-sm font-medium">
              Hasta (incluido)
              <input type="date" className={`${control} mt-2`} value={to} onChange={(e) => setTo(e.target.value)} />
            </label>
          </>
        )}
        <div className="flex items-end">
          <button type="submit" className={primary} disabled={loading}>
            {loading ? "Consultando…" : "Consultar"}
          </button>
        </div>
      </form>

      {error && (
        <p role="alert" className="mt-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p>
      )}

      {!query && !error && (
        <p className="mt-6 text-sm text-slate-600">Elige la fuente y el período, y pulsa Consultar.</p>
      )}

      {data && (
        <div className="mt-6 overflow-x-auto rounded-lg border border-slate-200 bg-white">
          <table className="w-full min-w-[640px] text-left text-sm">
            <caption className="sr-only">Registros archivados</caption>
            <thead className="bg-slate-50 text-xs uppercase text-slate-600">
              <tr>
                <th scope="col" className="px-4 py-3">Fecha</th>
                <th scope="col" className="px-4 py-3">Acción</th>
                <th scope="col" className="px-4 py-3">{isLog ? "Objeto" : "Cuenta afectada"}</th>
                <th scope="col" className="px-4 py-3">Responsable</th>
                <th scope="col" className="px-4 py-3"><span className="sr-only">Detalle</span></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data.results.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-6 text-center text-slate-600">
                    No hay registros archivados en este período.
                  </td>
                </tr>
              )}
              {data.results.map((row) => {
                const meta = isLog ? LOG_ACTIONS[row.action] : null;
                return (
                  <tr key={`${row.id}-${row.item_number}`}>
                    <td className="whitespace-nowrap px-4 py-3">{fmtDate(row.timestamp)}</td>
                    <td className={`px-4 py-3 font-semibold ${meta?.cls ?? ""}`}>{meta?.text ?? row.action}</td>
                    <td className="px-4 py-3">
                      {isLog ? (
                        <>
                          {row.object_repr || `#${row.object_pk}`}
                          <span className="block text-xs text-slate-500">{resourceLabel(row.content_type_id)}</span>
                        </>
                      ) : (
                        row.target_email || "—"
                      )}
                      {row.late_addition && <LateBadge />}
                    </td>
                    <td className="px-4 py-3">{row.actor_email || "—"}</td>
                    <td className="px-4 py-3 text-right">
                      <button type="button" className={secondary} onClick={() => setSelected(row)}>
                        Ver
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 px-4 py-3 text-sm text-slate-600">
            <span>{data.total_items} registros</span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                className={secondary}
                disabled={loading || page <= 1}
                onClick={() => fetchPage(query, Math.max(1, page - 1))}
              >
                Anterior
              </button>
              <span>Página {page} de {totalPages}</span>
              <button
                type="button"
                className={secondary}
                disabled={loading || page >= totalPages}
                onClick={() => fetchPage(query, Math.min(totalPages, page + 1))}
              >
                Siguiente
              </button>
            </div>
          </div>
        </div>
      )}

      {selected && query && (
        <ArchivedDetail
          source={query.source}
          row={selected}
          resourceLabel={resourceLabel}
          onClose={() => setSelected(null)}
        />
      )}
    </section>
  );
}
