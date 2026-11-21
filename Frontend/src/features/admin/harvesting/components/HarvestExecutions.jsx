"use client";

import { useRef, useState } from "react";
import AdminTable from "@/shared/components/AdminTable";
import Badge from "@/shared/components/Badge";
import Button from "@/shared/components/Button";
import Notice from "@/shared/components/Notice";
import { formatDate, formatHarvestError, formatSelectionFilters } from "@/features/admin/harvesting/harvesting";
import { useHarvestingApi } from "./HarvestingProvider";

const STATES = {
  pending: { label: "Pendiente", badge: "info" },
  running: { label: "En ejecución", badge: "info" },
  pausing: { label: "Pausando", badge: "warning" },
  paused: { label: "Pausada", badge: "warning" },
  completed: { label: "Completada", badge: "success" },
  failed: { label: "Fallida", badge: "error" },
  cancelled: { label: "Cancelada", badge: "warning" },
};

export default function HarvestExecutions({ rows, onRefresh, busy = false, caption = "Ejecuciones recientes de cosecha", countryNames, onShowHistory }) {
  const { pauseHarvest, resumeHarvest } = useHarvestingApi();
  const [actions, setActions] = useState({});
  const [feedback, setFeedback] = useState(null);
  const requestPending = useRef(new Set());

  async function control(row, resume) {
    const key = `${row.id}:${resume ? "resume" : "pause"}`;
    if (busy || requestPending.current.has(key)) return;
    requestPending.current.add(key);
    setActions((current) => ({ ...current, [key]: true }));
    setFeedback(null);
    try {
      const harvest = await (resume ? resumeHarvest(row.id) : pauseHarvest(row.id));
      setFeedback({
        variant: "neutral",
        message: harvest.state === "pausing"
          ? `Pausa solicitada para ${row.platform_name}. Terminará la página en curso antes de quedar pausada.`
          : resume ? `Reanudación procesada para ${row.platform_name}. Consulta su estado actualizado.` : `Cosecha de ${row.platform_name} pausada.`,
      });
    } catch (error) {
      setFeedback({ variant: "error", message: error.message });
    } finally {
      // Also refresh on errors: a timeout or incompatible state can follow a server-side change.
      onRefresh();
      requestPending.current.delete(key);
      setActions((current) => {
        const next = { ...current };
        delete next[key];
        return next;
      });
    }
  }

  const columns = [
    { key: "platform_name", label: "FUENTE", width: "16%", render: (row) => (
      <div>
        <span>{row.platform_name}</span>
        <span className="mt-1 block text-xs leading-[18px] text-[#68707C] [overflow-wrap:anywhere]">{formatSelectionFilters(row.selection_filters, countryNames)}</span>
        {onShowHistory && <button type="button" className="mt-1 text-left text-xs leading-[18px] font-semibold text-[#A90D27] underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary" aria-label={`Ver historial del recorrido de ${row.platform_name} (#${row.id})`} onClick={() => onShowHistory(row)}>Ver historial del recorrido</button>}
      </div>
    ) },
    { key: "state", label: "ESTADO", width: "14%", render: (row) => {
      const state = STATES[row.state] || { label: row.state, badge: "info" };
      return (
        <div className="flex flex-col items-start gap-1">
          <Badge state={row.state === "completed" && row.records_failed > 0 ? "warning" : state.badge}>{state.label}</Badge>
          {row.source_exhausted
            ? <span className="text-xs leading-[18px] text-[#68707C]" title="El proveedor ya no devolvió continuación para esta selección.">Recorrido agotado</span>
            : row.state === "completed" && <span className="text-xs leading-[18px] text-[#68707C]" title="Terminó esta ejecución (por cantidad o tiempo). Una nueva ejecución de la misma selección continúa donde quedó.">Puede continuar</span>}
        </div>
      );
    } },
    { key: "started_at", label: "INICIO", width: "17%", muted: true, render: (row) => formatDate(row.started_at) },
    { key: "duration", label: "DURACIÓN", width: "12%", muted: true, render: (row) => (
      <span className="whitespace-nowrap tabular-nums" title="Horas:minutos:segundos">{row.duration?.split(".")[0] || "—"}</span>
    ) },
    { key: "result", label: "RESULTADO", width: "25%", render: (row) => {
      const errorMessage = formatHarvestError(row.error_message);
      return (
        <div>
          <span>{row.records_added} nuevas · {row.records_updated} actualizadas · {row.records_failed} fallidas</span>
          <span className="block text-xs leading-[18px] text-[#68707C]" title="Registros examinados que no coincidieron con la selección o cuyos metadatos ya estaban importados sin cambios.">{row.records_skipped ?? 0} omitidas (no incorporadas)</span>
          {errorMessage && <div className="mt-2 rounded-lg border border-[#820A1F]/15 bg-[#FFE1E3] p-3 text-xs leading-relaxed text-[#820A1F]">
            <p className="whitespace-pre-wrap [overflow-wrap:anywhere]">{errorMessage}</p>
          </div>}
        </div>
      );
    } },
    { key: "actions", label: "ACCIONES", width: "16%", render: (row) => {
      if (row.state === "completed") return <Button
        href={`/admin/cosecha?vista=revistas&cosecha=${row.id}`}
        variant="quiet"
        size="small"
        aria-label={`Ver revistas de la cosecha de ${row.platform_name} (#${row.id})`}
      >Ver revistas</Button>;
      if (row.state === "pausing") return <span className="text-xs text-[#68707C]">Esperando pausa…</span>;
      const resume = row.state === "paused";
      if (!resume && row.state !== "pending" && row.state !== "running") return <span className="text-[#68707C]">—</span>;
      const pending = actions[`${row.id}:${resume ? "resume" : "pause"}`];
      return <Button variant="quiet" size="small" disabled={busy || Boolean(pending)} aria-label={`${resume ? "Reanudar" : "Pausar"} cosecha de ${row.platform_name} (#${row.id})`} onClick={() => control(row, resume)}>
        {pending ? resume ? "Reanudando…" : "Solicitando…" : resume ? "Reanudar" : "Pausar"}
      </Button>;
    } },
  ];

  return (
    <>
      {feedback && <Notice variant={feedback.variant} live>{feedback.message}</Notice>}
      {rows.length ? <AdminTable caption={caption} columns={columns} rows={rows} /> : <Notice>Todavía no hay ejecuciones de cosecha.</Notice>}
      <p className="text-xs text-[#68707C]">La pausa espera a que termine la página en curso. Reanudar continúa desde el punto guardado; el tiempo pausado no consume el límite de ejecución. Una ejecución pausada conserva su selección: para cambiar filtros edita la programación, que aplicará a ejecuciones futuras.</p>
      <p className="text-xs text-[#68707C]">«Recorrido agotado» indica que el proveedor ya no devolvió más registros para esa selección. «Puede continuar» indica que la ejecución terminó por cantidad o tiempo y una nueva ejecución de la misma selección seguirá donde quedó. Las omitidas no se suman a las revistas incorporadas.</p>
    </>
  );
}
