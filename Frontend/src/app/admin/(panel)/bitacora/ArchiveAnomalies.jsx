"use client";

import { useCallback, useEffect, useState } from "react";
import { Modal, fmtDate, primary, secondary } from "./auditUi";
import {
  ARCHIVE_SOURCES,
  archiveErrorMessage,
  getAnomalies,
  getAnomalyRecords,
  resolveAnomaly,
  semesterLabelFromStart,
} from "./auditArchiveApi";

const PAGE_SIZE = 10;
const danger =
  "rounded-md bg-red-700 px-4 py-2 text-sm font-semibold text-white hover:bg-red-800 disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-red-700";

const sourceLabel = (source) => ARCHIVE_SOURCES[source]?.label ?? source;

/* Registros que siguen en la base dentro de un semestre ya comprimido. */
function RecordsDrawer({ anomaly, onClose }) {
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  // El estado solo se actualiza al responder la petición (no dentro del efecto).
  useEffect(() => {
    const ctl = new AbortController();
    getAnomalyRecords(anomaly.source, anomaly.snapshot_id, { page, pageSize: PAGE_SIZE }, { signal: ctl.signal })
      .then((result) => {
        setError("");
        setData(result);
      })
      .catch((err) => err.name !== "AbortError" && setError(archiveErrorMessage(err)));
    return () => ctl.abort();
  }, [anomaly, page]);

  const isLog = anomaly.source === "auditlog";
  const totalPages = data?.total_pages ?? 1;

  return (
    <Modal
      title={`Registros pendientes · ${semesterLabelFromStart(anomaly.start)}`}
      subtitle={`${sourceLabel(anomaly.source)} · ${anomaly.records} registros`}
      onClose={onClose}
    >
      <div className="flex-1 overflow-y-auto px-6 py-6">
        {!data && !error && <p className="text-sm text-slate-600" aria-live="polite">Cargando registros…</p>}
        {error && <p role="alert" className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p>}
        {data && (
          <ul className="divide-y divide-slate-100">
            {data.results.map((row) => (
              <li key={row.id} className="py-3 text-sm">
                <p className="font-semibold">
                  {isLog ? `${row.action_display || row.action_name} · ${row.object_repr || `#${row.object_id}`}` : row.action}
                </p>
                <p className="text-xs text-slate-600">
                  #{row.id} · {fmtDate(row.timestamp, true)}
                  {isLog && row.resource_display ? ` · ${row.resource_display}` : ""}
                  {" · "}
                  {isLog ? row.actor_name || "Anónimo" : row.actor_email || "—"}
                  {!isLog && row.target_email ? ` → ${row.target_email}` : ""}
                </p>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 px-6 py-4 text-sm">
        <div className="flex items-center gap-2">
          <button type="button" className={secondary} disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
            Anterior
          </button>
          <span className="text-slate-600">Página {page} de {totalPages}</span>
          <button type="button" className={secondary} disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
            Siguiente
          </button>
        </div>
        <button type="button" onClick={onClose} className={secondary}>Cerrar</button>
      </div>
    </Modal>
  );
}

/* Confirmación explícita: comprimir o eliminar los registros revisados. */
function ResolveDialog({ anomaly, action, busy, onConfirm, onClose }) {
  const compress = action === "compress";
  const semester = semesterLabelFromStart(anomaly.start);
  return (
    <Modal
      title={compress ? "Comprimir dentro del semestre" : "Eliminar registros"}
      subtitle={`${sourceLabel(anomaly.source)} · semestre ${semester}`}
      onClose={busy ? () => {} : onClose}
    >
      <div className="flex-1 space-y-4 overflow-y-auto px-6 py-6 text-sm">
        {compress ? (
          <p>
            Los <strong>{anomaly.records}</strong> registros se agregarán al archivo del semestre {semester}, se
            verificarán y luego se quitarán de la base de datos. En la consulta archivada aparecerán marcados como
            «Agregado posteriormente».
          </p>
        ) : (
          <p>
            Los <strong>{anomaly.records}</strong> registros se <strong>eliminarán sin archivar</strong>. Esta acción no
            se puede deshacer.
          </p>
        )}
        <p className="text-slate-600">
          Si la cantidad cambió desde que la revisaste, no se ejecutará nada y la lista se recargará. La decisión queda
          registrada en la bitácora.
        </p>
      </div>
      <div className="flex flex-wrap gap-3 border-t border-slate-200 px-6 py-4">
        <button type="button" className={compress ? primary : danger} disabled={busy} onClick={onConfirm}>
          {busy ? "Procesando…" : compress ? "Comprimir registros" : "Eliminar registros"}
        </button>
        <button type="button" className={secondary} disabled={busy} onClick={onClose}>Cancelar</button>
      </div>
    </Modal>
  );
}

export default function ArchiveAnomalies({ canResolve }) {
  const [anomalies, setAnomalies] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [viewing, setViewing] = useState(null);
  const [resolving, setResolving] = useState(null); // { anomaly, action }
  const [busy, setBusy] = useState(false);

  // Solo actualiza el estado cuando responde la petición.
  const fetchAnomalies = useCallback((signal) => {
    getAnomalies({ signal })
      .then((result) => {
        setError("");
        setAnomalies(result);
      })
      .catch((err) => err.name !== "AbortError" && setError(archiveErrorMessage(err)))
      .finally(() => {
        if (!signal?.aborted) setLoading(false);
      });
  }, []);

  useEffect(() => {
    const ctl = new AbortController();
    fetchAnomalies(ctl.signal);
    return () => ctl.abort();
  }, [fetchAnomalies]);

  // Recarga explícita (botón Actualizar o tras resolver una anomalía).
  const load = () => {
    setLoading(true);
    fetchAnomalies();
  };

  const confirmResolve = async () => {
    const { anomaly, action } = resolving;
    setBusy(true);
    setError("");
    try {
      const result = await resolveAnomaly({
        source: anomaly.source,
        snapshotId: anomaly.snapshot_id,
        action,
        expectedRows: anomaly.records,
      });
      setMessage(
        action === "compress"
          ? `Se comprimieron ${result.compressed_rows} registros en el semestre ${semesterLabelFromStart(anomaly.start)}.`
          : `Se eliminaron ${result.removed_rows} registros del semestre ${semesterLabelFromStart(anomaly.start)}.`
      );
    } catch (err) {
      setError(archiveErrorMessage(err));
    } finally {
      setBusy(false);
      setResolving(null);
      load();
    }
  };

  return (
    <section className="font-sans text-slate-900">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">Anomalías de archivado</h1>
          <p className="mt-2 max-w-3xl text-sm text-slate-600">
            Registros que aparecieron en la base de datos dentro de semestres ya comprimidos, normalmente por cambios
            manuales. Los duplicados se eliminan automáticamente; los registros nuevos esperan una decisión: comprimirlos
            dentro del semestre o eliminarlos.
          </p>
        </div>
        <button type="button" onClick={load} disabled={loading} className={secondary}>
          {loading ? "Actualizando…" : "Actualizar"}
        </button>
      </header>

      {message && (
        <p role="status" className="mt-4 rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-800">{message}</p>
      )}
      {error && <p role="alert" className="mt-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p>}

      {anomalies && anomalies.length === 0 && (
        <p className="mt-6 rounded-lg border border-slate-200 bg-white p-6 text-center text-sm text-slate-600">
          No hay anomalías pendientes.
        </p>
      )}

      {anomalies && anomalies.length > 0 && (
        <div className="mt-6 overflow-x-auto rounded-lg border border-slate-200 bg-white">
          <table className="w-full min-w-[640px] text-left text-sm">
            <caption className="sr-only">Anomalías pendientes</caption>
            <thead className="bg-slate-50 text-xs uppercase text-slate-600">
              <tr>
                <th scope="col" className="px-4 py-3">Fuente</th>
                <th scope="col" className="px-4 py-3">Semestre</th>
                <th scope="col" className="px-4 py-3">Registros</th>
                <th scope="col" className="px-4 py-3"><span className="sr-only">Acciones</span></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {anomalies.map((anomaly) => (
                <tr key={`${anomaly.source}-${anomaly.snapshot_id}`}>
                  <td className="px-4 py-3">{sourceLabel(anomaly.source)}</td>
                  <td className="px-4 py-3 font-semibold">{semesterLabelFromStart(anomaly.start)}</td>
                  <td className="px-4 py-3">{anomaly.records}</td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap justify-end gap-2">
                      <button type="button" className={secondary} onClick={() => setViewing(anomaly)}>
                        Ver registros
                      </button>
                      {canResolve && (
                        <>
                          <button
                            type="button"
                            className={primary}
                            onClick={() => setResolving({ anomaly, action: "compress" })}
                          >
                            Comprimir
                          </button>
                          <button
                            type="button"
                            className={danger}
                            onClick={() => setResolving({ anomaly, action: "delete" })}
                          >
                            Eliminar
                          </button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {viewing && <RecordsDrawer anomaly={viewing} onClose={() => setViewing(null)} />}
      {resolving && (
        <ResolveDialog
          anomaly={resolving.anomaly}
          action={resolving.action}
          busy={busy}
          onConfirm={confirmResolve}
          onClose={() => setResolving(null)}
        />
      )}
    </section>
  );
}
