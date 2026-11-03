"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import AdminTable from "@/shared/components/AdminTable";
import Badge from "@/shared/components/Badge";
import Button from "@/shared/components/Button";
import FormField from "@/shared/components/FormField";
import Notice from "@/shared/components/Notice";
import { apiClient } from "@/shared/services/apiClient";
import { formatDate, getLinkAlerts } from "@/features/admin/harvesting/harvesting";
import { useHarvestingApi } from "./HarvestingProvider";
import { clampPage, sanitizePageValue } from "@/shared/utils/pagination";

const PAGE_SIZE = 10;

function httpStatus(row) {
  return row.http_status_code == null ? "Sin respuesta HTTP" : `HTTP ${row.http_status_code}`;
}

function platformId(row) {
  return typeof row.platform === "object" ? row.platform?.id : row.platform;
}

function journalRelationId(row) {
  return typeof row.journal_platform === "object" ? row.journal_platform?.id : row.journal_platform;
}

function AlertRow({ item, index, selected, onToggle, busy, loading, onVerify, onEdit }) {
  const [details, setDetails] = useState({ name: "Cargando...", href: "#", isReady: false });
  const isPlatformLink = item.journal_platform === null;
  const basePlatformId = platformId(item);

  useEffect(() => {
    const controller = new AbortController();
    setDetails({ name: "Cargando...", href: "#", isReady: false });

    async function resolveDetails() {
      try {
        if (isPlatformLink) {
          const data = await apiClient.get(`/api/platforms/${basePlatformId}/`, {}, { signal: controller.signal });
          if (!controller.signal.aborted) {
            setDetails({
              name: data?.name || `Plataforma (ID: ${basePlatformId})`,
              href: `/admin/bases-de-datos/vista/${basePlatformId}`,
              isReady: true,
            });
          }
          return;
        }

        const data = await apiClient.get("/api/journals/", { platform: basePlatformId }, { signal: controller.signal });
        const journals = Array.isArray(data) ? data : data?.results || [];
        const targetJournal = journals.find((journal) =>
          journal.platforms?.some((platform) => platform.journal_url === item.url),
        );
        if (!controller.signal.aborted) {
          setDetails(targetJournal
            ? { name: targetJournal.title, href: `/admin/revistas/vista/${targetJournal.id}`, isReady: true }
            : { name: `Revista (Relación ID: ${journalRelationId(item)})`, href: `/admin/bases-de-datos/vista/${basePlatformId}`, isReady: true });
        }
      } catch {
        if (!controller.signal.aborted) {
          setDetails({
            name: isPlatformLink ? `Plataforma (ID: ${basePlatformId})` : `Revista (Relación ID: ${journalRelationId(item)})`,
            href: `/admin/bases-de-datos/vista/${basePlatformId}`,
            isReady: true,
          });
        }
      }
    }

    resolveDetails();
    return () => controller.abort();
  }, [basePlatformId, isPlatformLink, item.id, item.url, item.journal_platform]);

  return (
    <tr className={selected ? "bg-[#DFECFF]" : index % 2 ? "bg-[#EEF0F3]" : ""}>
      <td className="h-[54px] px-3 py-[11px] align-middle">
        <div className="flex items-center gap-2">
          <span className="w-5 text-xs text-[#68707C]">{index + 1}</span>
          <input type="checkbox" aria-label={`Seleccionar fila ${index + 1}`} checked={selected} onChange={() => onToggle(String(item.id))} className="h-4 w-4 accent-[#174C92]" />
        </div>
      </td>
      <td className="h-[54px] px-3 py-[11px] align-middle">
        <div>
          {details.isReady
            ? <Link href={details.href} className="cursor-pointer break-words font-medium text-[#174C92] hover:underline focus-visible:outline-2 focus-visible:outline-offset-3 focus-visible:outline-primary">{details.name}</Link>
            : <span className="text-[#68707C]">Resolviendo recurso...</span>}
          <p className="mt-1 text-xs font-medium text-[#68707C]">{isPlatformLink ? "Enlace General de Plataforma" : "Enlace de Revista"}</p>
          <p className="mt-1 text-xs break-all text-[#68707C]">{item.url}</p>
        </div>
      </td>
      <td className="h-[54px] px-3 py-[11px] align-middle"><Badge state={item.failure_confirmed ? "error" : item.is_active ? "success" : "warning"}>{item.failure_confirmed ? "Caída confirmada" : item.is_active ? `Disponible · ${httpStatus(item)}` : httpStatus(item)}</Badge></td>
      <td className="h-[54px] px-3 py-[11px] align-middle text-[#68707C]">{formatDate(item.last_check)}</td>
      <td className="h-[54px] px-3 py-[11px] align-middle">
        {isPlatformLink && <div className="flex flex-wrap gap-2"><Button variant="secondary" size="small" disabled={busy || loading} aria-label={`Verificar: ${details.name}`} onClick={() => onVerify(item)}>Verificar URL</Button><Button variant="secondary" size="small" disabled={busy || loading} aria-label={`Corregir URL: ${details.name}`} onClick={() => onEdit(item)}>Corregir URL</Button></div>}
      </td>
    </tr>
  );
}

export default function LinkAlerts() {
  const { checkPlatformLink } = useHarvestingApi();
  const searchParams = useSearchParams();
  const filters = useMemo(() => Object.fromEntries(searchParams.entries()), [searchParams]);
  const filterKey = JSON.stringify(filters);
  const [links, setLinks] = useState([]);
  const [selectedRows, setSelectedRows] = useState(() => new Set());
  const [page, setPage] = useState(1);
  const [pageInput, setPageInput] = useState("1");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const [feedback, setFeedback] = useState(null);
  const [editing, setEditing] = useState(null);
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const requestPending = useRef(false);

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      try {
        const currentLinks = await getLinkAlerts(filters, controller.signal);
        if (!controller.signal.aborted) {
          setLinks(currentLinks);
          setSelectedRows((current) => new Set([...current].filter((id) => currentLinks.some((item) => String(item.id) === id))));
          setPage((current) => Math.min(current, Math.max(1, Math.ceil(currentLinks.length / PAGE_SIZE))));
          setError("");
        }
      } catch (error) {
        if (!controller.signal.aborted) setError(error.message);
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }
    load();
    return () => controller.abort();
  }, [revision, filterKey]);

  function refresh() {
    setLoading(true);
    setEditing(null);
    setRevision((current) => current + 1);
  }

  function toggleSelection(rowId) {
    setSelectedRows((current) => {
      const next = new Set(current);
      if (next.has(rowId)) next.delete(rowId);
      else next.add(rowId);
      return next;
    });
    setFeedback(null);
  }

  function togglePageSelection(checked) {
    setSelectedRows((current) => {
      const next = new Set(current);
      rows.forEach((row) => checked ? next.add(String(row.id)) : next.delete(String(row.id)));
      return next;
    });
    setFeedback(null);
  }

  function editUrl(row) {
    setEditing(row);
    setUrl(row.url || "");
    setFeedback(null);
  }

  async function verify(rows) {
    if (requestPending.current || loading) return;
    if (!rows.length) {
      setFeedback({ variant: "neutral", text: "Selecciona al menos un recurso por su nombre antes de solicitar la revisión." });
      return;
    }
    requestPending.current = true;
    setBusy(true);
    setEditing(null);
    setFeedback(null);
    try {
      const eligibleRows = rows.filter((row) => row.journal_platform === null);
      if (!eligibleRows.length) {
        setFeedback({ variant: "neutral", text: "La verificación manual está disponible solo para enlaces generales de plataforma." });
        return;
      }
      const results = await Promise.allSettled(eligibleRows.map((row) => checkPlatformLink(typeof row.platform === "object" ? row.platform.id : row.platform)));
      const succeeded = results.filter((result) => result.status === "fulfilled").length;
      const failures = results.flatMap((result, index) => result.status === "rejected" ? [`${eligibleRows[index].resource}: ${result.reason.message}`] : []);
      const details = results.flatMap((result, index) => result.status === "fulfilled" ? [`${eligibleRows[index].resource}: ${httpStatus(result.value)}`] : []);
      setFeedback({
        variant: failures.length ? "error" : "success",
        text: [`${succeeded} verificaciones registradas.`, ...details, ...failures].join(" · "),
      });
      setSelectedRows(new Set());
      refresh();
    } finally {
      requestPending.current = false;
      setBusy(false);
    }
  }

  async function saveUrl(event) {
    event.preventDefault();
    if (requestPending.current || loading) return;
    setFeedback(null);
    let parsed;
    try {
      parsed = new URL(url);
      if (!["http:", "https:"].includes(parsed.protocol)) throw new Error();
    } catch {
      setFeedback({ variant: "error", text: "Introduce una URL válida que comience por http:// o https://." });
      return;
    }
    requestPending.current = true;
    setBusy(true);
    try {
      if (editing.journal_platform !== null) throw new Error("La corrección manual está disponible solo para enlaces generales de plataforma.");
      const result = await checkPlatformLink(typeof editing.platform === "object" ? editing.platform.id : editing.platform, parsed.href);
      setFeedback({ variant: result.is_active ? "success" : "neutral", text: `URL registrada y verificada para ${editing.resource}: ${httpStatus(result)}. ${result.is_active ? "El enlace está disponible." : "El enlace sigue sin estar disponible."}` });
      refresh();
    } catch (error) {
      setFeedback({ variant: "error", text: error.message });
    } finally {
      requestPending.current = false;
      setBusy(false);
    }
  }

  const totalPages = Math.max(1, Math.ceil(links.length / PAGE_SIZE));
  const rows = links.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  const allPageSelected = rows.length > 0 && rows.every((row) => selectedRows.has(String(row.id)));
  const columns = [
    { key: "selection", label: <div className="flex items-center gap-2"><span>Nº</span><input type="checkbox" aria-label="Seleccionar todas las filas de esta página" checked={allPageSelected} onChange={(event) => togglePageSelection(event.target.checked)} className="h-4 w-4 accent-[#174C92]" /></div>, width: "8%" },
    { key: "resource", label: "RECURSO / CONTEXTO", width: "36%" },
    { key: "status", label: "ESTADO HTTP", width: "18%" },
    { key: "last_check", label: "ÚLTIMO CHEQUEO", width: "20%" },
    { key: "action", label: "ACCIÓN", width: "18%" },
  ];
  const requiringReview = links.filter((row) => row.failure_confirmed === true).length;
  function submitPageNumber() {
    const result = sanitizePageValue(pageInput, totalPages);
    if (!result.valid) {
      setPageInput(String(clampPage(page, totalPages)));
      return;
    }
    const nextPage = result.page;
    if (nextPage !== page) setPage(nextPage);
    setPageInput(String(nextPage));
  }

  return (
    <div className="flex-1 bg-[#F7F8FA] font-sans text-sm leading-[22px] text-[#171A1F]">
      <div className="mx-auto flex w-full max-w-[1088px] flex-col gap-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h1 className="text-[26px] leading-[34px] font-bold tracking-[-0.3px] min-[541px]:text-[32px] min-[541px]:leading-10">Disponibilidad de enlaces</h1>
          <Button variant="quiet" size="small" disabled={Boolean(loading || busy)} onClick={refresh}>Actualizar</Button>
        </div>
        {loading ? <Notice live>Cargando verificaciones de enlaces…</Notice> : error ? <Notice variant="error" live>{error}</Notice> : <Notice variant={requiringReview ? "error" : "success"} live>{requiringReview ? `${requiringReview} ${requiringReview === 1 ? "caída confirmada" : "caídas confirmadas"}.` : "No hay caídas confirmadas para los filtros seleccionados."}</Notice>}
        <div className="min-h-[300px] overflow-hidden rounded-xl border border-[#DCE0E5] bg-white" aria-busy={loading || busy}>
          {!loading && !error && (links.length ? <AdminTable caption="Disponibilidad de enlaces por contexto." variant="alerts" columns={columns} rows={rows} renderRow={(item, index) => <AlertRow key={item.id} item={item} index={(page - 1) * PAGE_SIZE + index} selected={selectedRows.has(String(item.id))} onToggle={toggleSelection} busy={busy} loading={loading} onVerify={(row) => verify([row])} onEdit={editUrl} />} /> : <p className="p-5 text-[#68707C]">No hay resultados para los filtros seleccionados.</p>)}
        </div>
        {!loading && !error && totalPages > 1 && <div className="flex flex-wrap items-center gap-3">
          <Button variant="quiet" size="small" disabled={page <= 1 || busy} onClick={() => {
            const nextPage = clampPage(page - 1, totalPages);
            setPage(nextPage);
            setPageInput(String(nextPage));
          }}>Anterior</Button>
          <label className="flex items-center gap-2 text-sm text-[#68707C]">
            <span>Página</span>
            <input
              aria-label="Número de página actual"
              type="number"
              min={1}
              max={totalPages}
              value={pageInput}
              onChange={(event) => setPageInput(event.target.value)}
              onBlur={() => setPageInput(String(clampPage(page, totalPages)))}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  submitPageNumber();
                }
              }}
              className="w-14 rounded-md border border-[#DCE0E5] bg-white px-2 py-1 text-center text-sm font-semibold text-[#171A1F] outline-none focus:border-[#A90D27]"
            />
            <span>de {totalPages}</span>
          </label>
          <Button variant="quiet" size="small" disabled={page >= totalPages || busy} onClick={() => {
            const nextPage = clampPage(page + 1, totalPages);
            setPage(nextPage);
            setPageInput(String(nextPage));
          }}>Siguiente</Button>
        </div>}
        <div><Button className="min-w-[260px]" disabled={loading || busy || Boolean(error) || !selectedRows.size || !links.some((row) => selectedRows.has(String(row.id)) && row.journal_platform === null)} onClick={() => verify(links.filter((row) => selectedRows.has(String(row.id)) && row.journal_platform === null))}>{busy ? "Verificando…" : "Revisar enlaces generales seleccionados"}</Button></div>
        <p className="text-xs leading-[18px] text-[#68707C]">Cada fila representa un contexto de enlace devuelto por el backend. {selectedRows.size > 0 && `${selectedRows.size} ${selectedRows.size === 1 ? "seleccionado" : "seleccionados"}.`} Fechas en America/Bogota.</p>
        {editing && (
          <form className="flex flex-col gap-5 rounded-xl border border-[#DCE0E5] bg-white p-5" onSubmit={saveUrl} aria-labelledby="correct-url-title" aria-busy={busy}>
            <h2 id="correct-url-title" className="text-[21px] leading-7 font-semibold min-[541px]:text-2xl min-[541px]:leading-8">Corregir URL · {editing.resource}</h2>
            <FormField id="resource-url" label="URL pública del recurso" type="url" placeholder="https://…" required disabled={busy} value={url} onChange={(event) => setUrl(event.target.value)} />
            <div className="flex flex-wrap items-center gap-3">
              <Button variant="quiet" disabled={busy} className="w-full min-w-[140px] min-[541px]:w-auto" onClick={() => setEditing(null)}>Cancelar</Button>
              <Button type="submit" disabled={busy} className="w-full min-w-[210px] min-[541px]:w-auto">{busy ? "Guardando…" : "Guardar y verificar URL"}</Button>
            </div>
          </form>
        )}
        {feedback && <Notice variant={feedback.variant} live>{feedback.text}</Notice>}
      </div>
    </div>
  );
}
