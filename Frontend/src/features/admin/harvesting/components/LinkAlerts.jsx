"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import AdminTable from "@/shared/components/AdminTable";
import Badge from "@/shared/components/Badge";
import Button from "@/shared/components/Button";
import FormField from "@/shared/components/FormField";
import Notice from "@/shared/components/Notice";
import { useAccountsApi } from "@/shared/components/AccountsProvider";
import { formatDate, getConfirmedIdsOnPage, getFilteredPlatformIds, getLinkAlertsPage, LINK_ALERTS_PAGE_SIZE } from "@/features/admin/harvesting/harvesting";
import {
  EXTRA_PARAM_KEYS,
  LINK_VIEWS,
  VIEW_PARAM_KEYS,
  buildQueryString,
  canCheckLinks,
  emptySelection,
  explicitPlatformIds,
  httpStatusLabel,
  isEverythingSelected,
  isRowSelected,
  linkActionError,
  linkStatus,
  matchView,
  pickParams,
  platformIdOf,
  relationIdOf,
  resolveLinkResources,
  selectAllFiltered,
  selectionCount,
  setRowsSelected,
  toggleRow,
} from "@/features/admin/harvesting/linkMonitoring";
import { isMissingPage, readPage } from "@/shared/utils/pagination";
import { useHarvestingApi } from "./HarvestingProvider";

const PAGE_SIZE = LINK_ALERTS_PAGE_SIZE;
const POLL_INTERVAL_MS = 2 * 60 * 1000;
const ASYNC_REFRESH_DELAY_MS = 30 * 1000;

const SCOPE_OPTIONS = [
  { value: "", label: "Todos los enlaces" },
  { value: "true", label: "Solo URLs generales de plataformas" },
  { value: "false", label: "Solo enlaces de revistas" },
];

function emptyMessage(view) {
  if (view?.key === "caidos") {
    return "No hay caídas confirmadas vigentes. Si llegaste desde un correo de alerta, es posible que el enlace se haya recuperado después de enviarse.";
  }
  return "No hay enlaces para los filtros seleccionados.";
}

function loadErrorMessage(error) {
  if (error?.status === 401) return "La sesión expiró. Inicia sesión nuevamente.";
  if (error?.status === 403) return "Tu cuenta no tiene el permiso platforms.link-check-logs.view para consultar los enlaces.";
  return error?.message || "No se pudieron cargar las verificaciones de enlaces.";
}

function AlertRow({ item, index, resource, confirmed, isHistory, selected, onToggle, busy, canCheck, onVerifyUrl, onVerifyPlatform, onEdit }) {
  const status = linkStatus(item, confirmed);
  const isPlatformLink = relationIdOf(item) === null;
  const name = resource?.name || "Resolviendo recurso…";
  return (
    <tr className={selected ? "bg-[#DFECFF]" : index % 2 ? "bg-[#EEF0F3]" : ""}>
      <td className="h-[54px] px-3 py-[11px] align-middle">
        <div className="flex items-center gap-2">
          <span className="w-6 text-xs text-[#68707C]">{index + 1}</span>
          <input
            type="checkbox"
            aria-label={`Seleccionar ${name}`}
            checked={selected}
            onChange={() => onToggle(item)}
            className="h-4 w-4 accent-[#174C92]"
          />
        </div>
      </td>
      <td className="px-3 py-[11px] align-middle">
        {resource ? (
          <Link href={resource.href} className="break-words font-medium text-[#174C92] hover:underline">
            {resource.name}
          </Link>
        ) : (
          <span className="text-[#68707C]">{name}</span>
        )}
        <p className="mt-1 text-xs font-medium text-[#68707C]">{resource?.context || (isPlatformLink ? "Enlace general de la plataforma" : "Enlace de revista")}</p>
        <p className="mt-1 text-xs break-all text-[#68707C]">{item.url}</p>
      </td>
      <td className="px-3 py-[11px] align-middle">
        <Badge state={status.state}>{status.label}</Badge>
        <p className="mt-1 text-xs text-[#68707C]">
          {item.verification_status === "unverified" ? "Nunca comprobada" : httpStatusLabel(item)}
          {item.verification_status === "unavailable" && ` · ${item.fail_count} ${item.fail_count === 1 ? "fallo consecutivo" : "fallos consecutivos"}`}
        </p>
        {isHistory && <p className="mt-1 text-xs text-[#68707C]">URL sustituida (no vigente)</p>}
        {item.failure_notified_at && (
          <p className="mt-1 text-xs text-[#68707C]">Aviso por correo enviado el {formatDate(item.failure_notified_at)}</p>
        )}
      </td>
      <td className="px-3 py-[11px] align-middle text-[#68707C]">{item.last_check ? formatDate(item.last_check) : "Sin verificar"}</td>
      <td className="px-3 py-[11px] align-middle">
        {canCheck && !isHistory && (
          <div className="flex flex-wrap gap-2">
            {isPlatformLink ? (
              <>
                <Button variant="secondary" size="small" disabled={busy} aria-label={`Verificar URL general de ${name}`} onClick={() => onVerifyUrl(item)}>
                  Verificar URL
                </Button>
                <Button variant="secondary" size="small" disabled={busy} aria-label={`Corregir URL de ${name}`} onClick={() => onEdit(item)}>
                  Corregir URL
                </Button>
              </>
            ) : (
              <Button
                variant="secondary"
                size="small"
                disabled={busy}
                title="No existe verificación individual de enlaces de revista: se comprueba la plataforma completa."
                aria-label={`Verificar todos los enlaces de ${resource?.platformName || "la plataforma"}`}
                onClick={() => onVerifyPlatform(item)}
              >
                Verificar plataforma
              </Button>
            )}
          </div>
        )}
      </td>
    </tr>
  );
}

export default function LinkAlerts() {
  const { checkPlatformLink, checkPlatformLinks, checkAllLinksAsync, checkFailedLinksAsync } = useHarvestingApi();
  const accountsApi = useAccountsApi();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const params = useMemo(() => Object.fromEntries(searchParams.entries()), [searchParams]);
  const viewParams = pickParams(params, VIEW_PARAM_KEYS);
  const extraParams = pickParams(params, EXTRA_PARAM_KEYS);
  const filterKey = JSON.stringify({ ...viewParams, ...extraParams });
  const view = matchView(params);
  const hasCurrent = params.current !== undefined;
  const isHistory = params.current === "false";

  const [revision, setRevision] = useState(0);
  const [page, setPage] = useState(1);
  const requestKey = `${filterKey}#${page}#${revision}`;
  const [data, setData] = useState({ key: null, filterKey: null, rows: [], total: 0, totalPages: 1, confirmedIds: new Set(), confirmedCount: 0, error: null });
  const [resources, setResources] = useState(() => new Map());
  const resourceCache = useRef({ platforms: null, journals: new Map() });

  const [selection, setSelection] = useState(emptySelection);
  const [summary, setSummary] = useState({ key: null, count: 0, platformIds: [], error: null });
  const [feedback, setFeedback] = useState(null);
  const [editing, setEditing] = useState(null);
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [canCheck, setCanCheck] = useState(null); // null mientras se consultan los permisos
  const requestPending = useRef(false);

  // Si el filtro cambia desde fuera (enlaces, historial), se vuelve a la
  // primera página y se descarta la selección del filtro anterior.
  const [seenFilterKey, setSeenFilterKey] = useState(filterKey);
  if (seenFilterKey !== filterKey) {
    setSeenFilterKey(filterKey);
    setPage(1);
    setSelection(emptySelection());
  }

  // Omitir `current` no equivale a `current=false`: se fuerza la vista vigente.
  useEffect(() => {
    if (!hasCurrent) {
      router.replace(`${pathname}?${buildQueryString({ ...extraParams, current: "true" })}`);
    }
  }, [hasCurrent]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const controller = new AbortController();
    accountsApi
      .me(controller.signal)
      .then((user) => setCanCheck(canCheckLinks(user)))
      .catch(() => setCanCheck(false));
    return () => controller.abort();
  }, [accountsApi]);

  // Una página del servidor; filtros, orden y totales los resuelve el backend.
  useEffect(() => {
    if (!hasCurrent) return undefined;
    const controller = new AbortController();
    const filters = JSON.parse(filterKey);
    const allConfirmed = filters.failure_confirmed === "true";
    // `failure_confirmed` es un filtro, no un campo de la fila: para marcar
    // caídas confirmadas se consulta el mismo filtro acotado a la página.
    const needsConfirmed =
      !allConfirmed &&
      filters.current === "true" &&
      filters.failure_confirmed === undefined &&
      !["available", "unverified"].includes(filters.verification_status);
    const confirmedFilters = { ...filters, failure_confirmed: "true" };

    async function load() {
      const [pageResponse, confirmedTotal] = await Promise.all([
        getLinkAlertsPage(filters, { page, pageSize: PAGE_SIZE }, controller.signal),
        needsConfirmed ? getLinkAlertsPage(confirmedFilters, { pageSize: 1 }, controller.signal) : null,
      ]);
      const { results: rows, totalItems, totalPages } = readPage(pageResponse, PAGE_SIZE);
      let confirmedIds = new Set(allConfirmed ? rows.map((row) => row.id) : []);
      if (needsConfirmed && rows.length && confirmedTotal?.total_items) {
        confirmedIds = await getConfirmedIdsOnPage(rows, controller.signal);
      }
      return {
        rows,
        total: totalItems,
        totalPages,
        confirmedIds,
        confirmedCount: allConfirmed ? totalItems : confirmedTotal?.total_items ?? 0,
      };
    }

    load()
      .then(async (result) => {
        if (controller.signal.aborted) return;
        setData({ key: requestKey, filterKey, ...result, error: null });
        // Nombres de recursos solo para las filas de la página visible.
        const resolved = await resolveLinkResources(result.rows, controller.signal, resourceCache.current);
        if (!controller.signal.aborted) setResources(resolved);
      })
      .catch((error) => {
        if (controller.signal.aborted) return;
        if (isMissingPage(error, page)) {
          setPage(1);
          return;
        }
        setData((current) => ({ ...current, key: requestKey, filterKey, error }));
      });
    return () => controller.abort();
  }, [filterKey, requestKey, hasCurrent, page]);

  // "Todos los filtrados": las plataformas implicadas se calculan recorriendo
  // las páginas del filtro (la API no ofrece un resumen de selección).
  const excludedKey = selection.mode === "all" ? [...selection.excluded.keys()].join(",") : "";
  const summaryKey = `${filterKey}#${revision}#${excludedKey}`;
  const needsSummary = hasCurrent && selection.mode === "all";
  useEffect(() => {
    if (!needsSummary) return undefined;
    const controller = new AbortController();
    const excluded = excludedKey ? excludedKey.split(",") : [];
    getFilteredPlatformIds(JSON.parse(filterKey), excluded, controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) setSummary({ key: summaryKey, count: result.count, platformIds: result.platformIds, error: null });
      })
      .catch((error) => {
        if (!controller.signal.aborted) setSummary({ key: summaryKey, count: 0, platformIds: [], error });
      });
    return () => controller.abort();
  }, [summaryKey, needsSummary]); // eslint-disable-line react-hooks/exhaustive-deps

  const refresh = useCallback(() => setRevision((value) => value + 1), []);

  // Sondeo moderado: solo con la pestaña visible; al volver al primer plano se refresca.
  useEffect(() => {
    let timer = null;
    const start = () => {
      if (timer === null) timer = setInterval(refresh, POLL_INTERVAL_MS);
    };
    const stop = () => {
      clearInterval(timer);
      timer = null;
    };
    const onVisibility = () => {
      if (document.visibilityState === "visible") {
        refresh();
        start();
      } else {
        stop();
      }
    };
    if (document.visibilityState === "visible") start();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      stop();
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [refresh]);

  // Al cambiar de filtro no se muestran datos de la vista anterior.
  const firstLoad = data.key === null || data.filterKey !== filterKey;
  const reloading = !firstLoad && data.key !== requestKey;
  const { rows, total, confirmedIds, confirmedCount, error } = data;

  const totalPages = Math.max(1, data.totalPages);
  const currentPage = Math.min(page, totalPages);
  const allPageSelected = rows.length > 0 && rows.every((row) => isRowSelected(selection, row));
  const allFilteredSelected = isEverythingSelected(selection, total);
  const summaryCurrent = summary.key === summaryKey;
  // En "todos los filtrados" el servidor confirma cuántas filas siguen coincidiendo.
  const selectedCount = selection.mode === "all" && summaryCurrent && !summary.error
    ? summary.count
    : selectionCount(selection, total);
  // Selección explícita: plataformas conocidas al instante; "todos": del servidor.
  const selectedPlatformIds = selection.mode === "all"
    ? (summaryCurrent && !summary.error ? summary.platformIds : [])
    : explicitPlatformIds(selection);
  const selectionPending = selection.mode === "all" && needsSummary && !summaryCurrent;

  const navigate = (nextParams) => {
    setPage(1);
    setSelection(emptySelection());
    setFeedback(null);
    setEditing(null);
    router.replace(`${pathname}?${buildQueryString(nextParams)}`);
  };

  function toggleSelection(row) {
    setSelection((current) => toggleRow(current, row));
  }

  function togglePageSelection(checked) {
    setSelection((current) => setRowsSelected(current, rows, checked));
  }

  async function runAction(action) {
    if (requestPending.current) return;
    requestPending.current = true;
    setBusy(true);
    setFeedback(null);
    try {
      await action();
    } finally {
      requestPending.current = false;
      setBusy(false);
    }
  }

  const resourceName = (row) => resources.get(row.id)?.name || `Plataforma #${platformIdOf(row)}`;

  const verifyUrl = (row) =>
    runAction(async () => {
      try {
        const result = await checkPlatformLink(platformIdOf(row));
        const status = linkStatus(result, false);
        setFeedback({ variant: result.verification_status === "available" ? "success" : "neutral", text: `${resourceName(row)}: ${status.label} · ${httpStatusLabel(result)}.` });
        refresh();
      } catch (err) {
        setFeedback({ variant: "error", text: linkActionError(err) });
      }
    });

  const verifyPlatforms = (platformIds) =>
    runAction(async () => {
      const results = await Promise.allSettled(platformIds.map((id) => checkPlatformLinks(id)));
      const lines = results.map((result, index) => {
        const id = platformIds[index];
        const label = rows.find((row) => String(platformIdOf(row)) === id);
        const name = label ? resources.get(label.id)?.platformName || `Plataforma #${id}` : `Plataforma #${id}`;
        if (result.status === "rejected") return `${name}: ${linkActionError(result.reason)}`;
        const { checked, available, failed } = result.value || {};
        return `${name}: ${checked ?? 0} comprobados, ${available ?? 0} disponibles, ${failed ?? 0} con fallo`;
      });
      const anyFailed = results.some((result) => result.status === "rejected");
      setFeedback({ variant: anyFailed ? "error" : "success", text: lines.join(" · ") });
      setSelection(emptySelection());
      refresh();
    });

  const enqueue = (kind) => {
    const scope =
      kind === "all"
        ? "Se encolará la verificación de TODOS los enlaces vigentes del sistema."
        : "Se encolarán reintentos de los enlaces vigentes con 1 a 4 fallos consecutivos (no confirmados).";
    if (!window.confirm(`${scope}\n\nLos resultados aparecerán en el listado a medida que se procesen. ¿Continuar?`)) return;
    runAction(async () => {
      try {
        const response = kind === "all" ? await checkAllLinksAsync() : await checkFailedLinksAsync();
        setFeedback({
          variant: "neutral",
          text: `Verificación iniciada${response?.run_id ? ` (ronda #${response.run_id})` : ""}. Todavía no hay resultados: el listado se actualizará automáticamente.`,
        });
        setTimeout(refresh, ASYNC_REFRESH_DELAY_MS);
      } catch (err) {
        setFeedback({ variant: "error", text: linkActionError(err) });
      }
    });
  };

  function editUrl(row) {
    setEditing(row);
    setUrl(row.url || "");
    setFeedback(null);
  }

  async function saveUrl(event) {
    event.preventDefault();
    let parsed;
    try {
      parsed = new URL(url);
      if (!["http:", "https:"].includes(parsed.protocol)) throw new Error();
    } catch {
      setFeedback({ variant: "error", text: "Introduce una URL válida que comience por http:// o https://." });
      return;
    }
    const row = editing;
    await runAction(async () => {
      try {
        const result = await checkPlatformLink(platformIdOf(row), parsed.href);
        setFeedback({
          variant: result.verification_status === "available" ? "success" : "neutral",
          text: `URL registrada y verificada para ${resourceName(row)}: ${linkStatus(result, false).label} · ${httpStatusLabel(result)}.`,
        });
        setEditing(null);
        refresh();
      } catch (err) {
        setFeedback({ variant: "error", text: linkActionError(err) });
      }
    });
  }

  const columns = [
    {
      key: "selection",
      label: (
        <div className="flex items-center gap-2">
          <span>Nº</span>
          <input
            type="checkbox"
            aria-label="Seleccionar todas las filas de esta página"
            checked={allPageSelected}
            onChange={(event) => togglePageSelection(event.target.checked)}
            className="h-4 w-4 accent-[#174C92]"
          />
        </div>
      ),
      width: "8%",
    },
    { key: "resource", label: "RECURSO / CONTEXTO", width: "36%" },
    { key: "status", label: "ESTADO", width: "22%" },
    { key: "last_check", label: "ÚLTIMO CHEQUEO", width: "14%" },
    { key: "action", label: "ACCIÓN", width: "20%" },
  ];

  let overview = null;
  if (!firstLoad && !error) {
    if (view?.key === "caidos") {
      overview = total
        ? { variant: "error", text: `${total} ${total === 1 ? "caída confirmada vigente" : "caídas confirmadas vigentes"} (5 o más fallos consecutivos).` }
        : { variant: "success", text: "No hay caídas confirmadas vigentes." };
    } else {
      overview = {
        variant: confirmedCount ? "error" : "neutral",
        text: `${total} ${total === 1 ? "enlace" : "enlaces"}${confirmedCount ? ` · ${confirmedCount} con caída confirmada` : ""}.`,
      };
    }
  }

  return (
    <div className="flex-1 bg-[#F7F8FA] font-sans text-sm leading-[22px] text-[#171A1F]">
      <div className="mx-auto flex w-full max-w-[1088px] flex-col gap-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h1 className="text-[26px] leading-[34px] font-bold tracking-[-0.3px] min-[541px]:text-[32px] min-[541px]:leading-10">
            Disponibilidad de enlaces
          </h1>
          <div className="flex items-center gap-2">
            {reloading && <span className="text-xs text-[#68707C]" role="status">Actualizando…</span>}
            <Button variant="quiet" size="small" disabled={busy || reloading} onClick={() => {
              resourceCache.current = { platforms: null, journals: new Map() };
              refresh();
            }}>
              Actualizar
            </Button>
          </div>
        </div>

        {/* Vistas */}
        <nav aria-label="Filtrar enlaces por estado" className="flex flex-wrap gap-2">
          {LINK_VIEWS.map((option) => {
            const active = view?.key === option.key;
            return (
              <button
                key={option.key}
                type="button"
                aria-pressed={active}
                onClick={() => navigate({ ...extraParams, ...option.query })}
                className={`rounded-full border px-3 py-1 text-xs font-semibold transition-colors ${
                  active ? "border-[#7f1218] bg-[#7f1218] text-white" : "border-[#DCE0E5] bg-white text-[#171A1F] hover:bg-[#F2F5FA]"
                }`}
              >
                {option.label}
              </button>
            );
          })}
          {!view && hasCurrent && (
            <span className="rounded-full border border-dashed border-[#DCE0E5] px-3 py-1 text-xs text-[#68707C]">Filtro personalizado</span>
          )}
        </nav>

        <div className="grid gap-3 sm:grid-cols-[320px_1fr] sm:items-end">
          <FormField
            compact
            id="link-scope"
            label="Tipo de enlace"
            value={extraParams.journal_platform__isnull || ""}
            onChange={(event) => {
              const next = { ...viewParams, ...extraParams };
              if (event.target.value) next.journal_platform__isnull = event.target.value;
              else delete next.journal_platform__isnull;
              navigate(next);
            }}
            options={SCOPE_OPTIONS}
          />
          {(extraParams.platform || extraParams.journal_platform) && (
            <div className="text-xs text-[#68707C]">
              Filtrado por {extraParams.platform ? `plataforma #${extraParams.platform}` : `relación #${extraParams.journal_platform}`}.{" "}
              <button
                type="button"
                className="font-semibold text-[#174C92] underline"
                onClick={() => {
                  const next = { ...viewParams, ...extraParams };
                  delete next.platform;
                  delete next.journal_platform;
                  navigate(next);
                }}
              >
                Quitar filtro
              </button>
            </div>
          )}
        </div>

        {firstLoad ? (
          <Notice live>Cargando verificaciones de enlaces…</Notice>
        ) : error ? (
          <Notice variant="error" live>{loadErrorMessage(error)}</Notice>
        ) : (
          overview && <Notice variant={overview.variant} live>{overview.text}</Notice>
        )}

        <div className="min-h-[300px] overflow-hidden rounded-xl border border-[#DCE0E5] bg-white" aria-busy={firstLoad || reloading || busy}>
          {!firstLoad && !error && (rows.length ? (
            <AdminTable
              caption="Disponibilidad de enlaces por contexto."
              variant="alerts"
              columns={columns}
              rows={rows}
              renderRow={(item, index) => (
                <AlertRow
                  key={item.id}
                  item={item}
                  index={(currentPage - 1) * PAGE_SIZE + index}
                  resource={resources.get(item.id)}
                  confirmed={confirmedIds.has(item.id)}
                  isHistory={isHistory}
                  selected={isRowSelected(selection, item)}
                  onToggle={toggleSelection}
                  busy={busy}
                  canCheck={Boolean(canCheck)}
                  onVerifyUrl={verifyUrl}
                  onVerifyPlatform={(row) => verifyPlatforms([String(platformIdOf(row))])}
                  onEdit={editUrl}
                />
              )}
            />
          ) : (
            <p className="p-5 text-[#68707C]">{emptyMessage(view)}</p>
          ))}
        </div>

        {!firstLoad && !error && totalPages > 1 && (
          <div className="flex flex-wrap items-center gap-3">
            <Button variant="quiet" size="small" disabled={reloading || currentPage <= 1} onClick={() => setPage(currentPage - 1)}>Anterior</Button>
            <span className="text-sm text-[#68707C]">Página {currentPage} de {totalPages}</span>
            <Button variant="quiet" size="small" disabled={reloading || currentPage >= totalPages} onClick={() => setPage(currentPage + 1)}>Siguiente</Button>
          </div>
        )}

        {/* Selección */}
        {!firstLoad && !error && total > 0 && (
          <div className="flex flex-wrap items-center gap-3 text-xs text-[#68707C]">
            <span>{selectedCount} {selectedCount === 1 ? "seleccionado" : "seleccionados"} de {total}.</span>
            <button
              type="button"
              className="font-semibold text-[#174C92] underline"
              onClick={() => setSelection(allFilteredSelected ? emptySelection() : selectAllFiltered())}
            >
              {allFilteredSelected ? "Quitar selección" : `Seleccionar los ${total} resultados filtrados`}
            </button>
            {selectedCount > 0 && !allFilteredSelected && (
              <button type="button" className="font-semibold text-[#174C92] underline" onClick={() => setSelection(emptySelection())}>
                Quitar selección
              </button>
            )}
            {summary.error && summary.key === summaryKey && (
              <span className="text-[#A90D27]">No se pudo calcular la selección: {summary.error.message}</span>
            )}
          </div>
        )}

        {/* Acciones */}
        {canCheck ? (
          <section aria-labelledby="link-actions-title" className="flex flex-col gap-4 rounded-xl border border-[#DCE0E5] bg-white p-5">
            <h2 id="link-actions-title" className="text-base font-semibold">Acciones de verificación</h2>
            <div className="grid gap-4 md:grid-cols-3">
              <div className="flex flex-col gap-2">
                <Button
                  disabled={busy || selectionPending || !selectedPlatformIds.length}
                  onClick={() => verifyPlatforms(selectedPlatformIds)}
                >
                  {busy ? "Verificando…" : selectionPending ? "Calculando selección…" : `Verificar plataformas seleccionadas (${selectedPlatformIds.length})`}
                </Button>
                <p className="text-xs text-[#68707C]">
                  Comprueba ahora la URL general y todos los enlaces de revistas de cada plataforma de las filas seleccionadas. No existe verificación de un conjunto arbitrario de enlaces.
                </p>
              </div>
              <div className="flex flex-col gap-2">
                <Button variant="outline" disabled={busy} onClick={() => enqueue("failed")}>Reintentar enlaces fallidos</Button>
                <p className="text-xs text-[#68707C]">Encola reintentos de enlaces vigentes con 1 a 4 fallos (sin confirmar). Se ejecuta en segundo plano.</p>
              </div>
              <div className="flex flex-col gap-2">
                <Button variant="outline" disabled={busy} onClick={() => enqueue("all")}>Verificar todos</Button>
                <p className="text-xs text-[#68707C]">Encola la verificación de todos los enlaces vigentes del sistema. Se ejecuta en segundo plano.</p>
              </div>
            </div>
          </section>
        ) : canCheck === false ? (
          <p className="text-xs text-[#68707C]">Las acciones de verificación requieren el permiso platforms.platforms.check_link.</p>
        ) : null}

        {editing && (
          <form className="flex flex-col gap-5 rounded-xl border border-[#DCE0E5] bg-white p-5" onSubmit={saveUrl} aria-labelledby="correct-url-title" aria-busy={busy}>
            <h2 id="correct-url-title" className="text-[21px] leading-7 font-semibold min-[541px]:text-2xl min-[541px]:leading-8">
              Corregir URL · {resourceName(editing)}
            </h2>
            <FormField id="resource-url" label="URL pública del recurso" type="url" placeholder="https://…" required disabled={busy} value={url} onChange={(event) => setUrl(event.target.value)} />
            <div className="flex flex-wrap items-center gap-3">
              <Button variant="quiet" disabled={busy} className="w-full min-w-[140px] min-[541px]:w-auto" onClick={() => setEditing(null)}>Cancelar</Button>
              <Button type="submit" disabled={busy} className="w-full min-w-[210px] min-[541px]:w-auto">{busy ? "Guardando…" : "Guardar y verificar URL"}</Button>
            </div>
          </form>
        )}

        {feedback && <Notice variant={feedback.variant} live>{feedback.text}</Notice>}
        <p className="text-xs leading-[18px] text-[#68707C]">
          Cada fila es el evento de verificación de un contexto (URL general de plataforma o relación revista–plataforma). El listado se actualiza cada 2 minutos mientras la pestaña está visible. Fechas en America/Bogota.
        </p>
      </div>
    </div>
  );
}
