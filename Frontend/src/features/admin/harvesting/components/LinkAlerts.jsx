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
import { formatDate, getLinkAlerts } from "@/features/admin/harvesting/harvesting";
import {
  CONFIRMED_FAILURES_QUERY,
  EXTRA_PARAM_KEYS,
  LINK_VIEWS,
  VIEW_PARAM_KEYS,
  buildQueryString,
  canCheckLinks,
  httpStatusLabel,
  linkActionError,
  linkStatus,
  matchView,
  pickParams,
  platformIdOf,
  relationIdOf,
  resolveLinkResources,
} from "@/features/admin/harvesting/linkMonitoring";
import { useHarvestingApi } from "./HarvestingProvider";

const PAGE_SIZE = 20;
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
            onChange={() => onToggle(String(item.id))}
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
  const requestKey = `${filterKey}#${revision}`;
  const [data, setData] = useState({ key: null, filterKey: null, links: [], confirmedIds: new Set(), error: null });
  const [resources, setResources] = useState(() => new Map());
  const resourceCache = useRef({ platforms: null, journals: new Map() });

  const [selectedRows, setSelectedRows] = useState(() => new Set());
  const [page, setPage] = useState(1);
  const [feedback, setFeedback] = useState(null);
  const [editing, setEditing] = useState(null);
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [canCheck, setCanCheck] = useState(null); // null mientras se consultan los permisos
  const requestPending = useRef(false);

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

  useEffect(() => {
    if (!hasCurrent) return undefined;
    const controller = new AbortController();
    const filters = JSON.parse(filterKey);
    // Para separar caída confirmada de fallo no confirmado se consulta el
    // filtro `failure_confirmed=true`; la fila no trae ese dato.
    const needsConfirmedSet =
      filters.current === "true" &&
      filters.failure_confirmed === undefined &&
      !["available", "unverified"].includes(filters.verification_status);
    const confirmedFilters = { ...pickParams(filters, EXTRA_PARAM_KEYS), ...CONFIRMED_FAILURES_QUERY };

    Promise.all([
      getLinkAlerts(filters, controller.signal),
      needsConfirmedSet ? getLinkAlerts(confirmedFilters, controller.signal) : Promise.resolve(null),
    ])
      .then(async ([links, confirmed]) => {
        if (controller.signal.aborted) return;
        const confirmedIds = new Set(
          filters.failure_confirmed === "true"
            ? links.map((row) => row.id)
            : (confirmed || []).map((row) => row.id)
        );
        setData({ key: requestKey, filterKey, links, confirmedIds, error: null });
        setSelectedRows((current) => new Set([...current].filter((id) => links.some((row) => String(row.id) === id))));
        const resolved = await resolveLinkResources(links, controller.signal, resourceCache.current);
        if (!controller.signal.aborted) setResources(resolved);
      })
      .catch((error) => {
        if (!controller.signal.aborted) setData((current) => ({ ...current, key: requestKey, filterKey, error }));
      });
    return () => controller.abort();
  }, [filterKey, requestKey, hasCurrent]);

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
  const { links, confirmedIds, error } = data;

  const totalPages = Math.max(1, Math.ceil(links.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const rows = links.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);
  const allPageSelected = rows.length > 0 && rows.every((row) => selectedRows.has(String(row.id)));
  const allFilteredSelected = links.length > 0 && links.every((row) => selectedRows.has(String(row.id)));
  const selectedLinks = links.filter((row) => selectedRows.has(String(row.id)));
  const selectedPlatformIds = [...new Set(selectedLinks.map((row) => String(platformIdOf(row))))];
  const confirmedCount = links.filter((row) => confirmedIds.has(row.id)).length;

  const navigate = (nextParams) => {
    setPage(1);
    setSelectedRows(new Set());
    setFeedback(null);
    setEditing(null);
    router.replace(`${pathname}?${buildQueryString(nextParams)}`);
  };

  function toggleSelection(rowId) {
    setSelectedRows((current) => {
      const next = new Set(current);
      if (next.has(rowId)) next.delete(rowId);
      else next.add(rowId);
      return next;
    });
  }

  function togglePageSelection(checked) {
    setSelectedRows((current) => {
      const next = new Set(current);
      rows.forEach((row) => (checked ? next.add(String(row.id)) : next.delete(String(row.id))));
      return next;
    });
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
        const label = links.find((row) => String(platformIdOf(row)) === id);
        const name = label ? resources.get(label.id)?.platformName || `Plataforma #${id}` : `Plataforma #${id}`;
        if (result.status === "rejected") return `${name}: ${linkActionError(result.reason)}`;
        const { checked, available, failed } = result.value || {};
        return `${name}: ${checked ?? 0} comprobados, ${available ?? 0} disponibles, ${failed ?? 0} con fallo`;
      });
      const anyFailed = results.some((result) => result.status === "rejected");
      setFeedback({ variant: anyFailed ? "error" : "success", text: lines.join(" · ") });
      setSelectedRows(new Set());
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

  let summary = null;
  if (!firstLoad && !error) {
    if (view?.key === "caidos") {
      summary = links.length
        ? { variant: "error", text: `${links.length} ${links.length === 1 ? "caída confirmada vigente" : "caídas confirmadas vigentes"} (5 o más fallos consecutivos).` }
        : { variant: "success", text: "No hay caídas confirmadas vigentes." };
    } else {
      summary = {
        variant: confirmedCount ? "error" : "neutral",
        text: `${links.length} ${links.length === 1 ? "enlace" : "enlaces"}${confirmedCount ? ` · ${confirmedCount} con caída confirmada` : ""}.`,
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
          summary && <Notice variant={summary.variant} live>{summary.text}</Notice>
        )}

        <div className="min-h-[300px] overflow-hidden rounded-xl border border-[#DCE0E5] bg-white" aria-busy={firstLoad || reloading || busy}>
          {!firstLoad && !error && (links.length ? (
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
                  selected={selectedRows.has(String(item.id))}
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
            <Button variant="quiet" size="small" disabled={currentPage <= 1} onClick={() => setPage(currentPage - 1)}>Anterior</Button>
            <span className="text-sm text-[#68707C]">Página {currentPage} de {totalPages}</span>
            <Button variant="quiet" size="small" disabled={currentPage >= totalPages} onClick={() => setPage(currentPage + 1)}>Siguiente</Button>
          </div>
        )}

        {/* Selección */}
        {!firstLoad && !error && links.length > 0 && (
          <div className="flex flex-wrap items-center gap-3 text-xs text-[#68707C]">
            <span>{selectedRows.size} {selectedRows.size === 1 ? "seleccionado" : "seleccionados"} de {links.length}.</span>
            <button
              type="button"
              className="font-semibold text-[#174C92] underline"
              onClick={() => setSelectedRows(allFilteredSelected ? new Set() : new Set(links.map((row) => String(row.id))))}
            >
              {allFilteredSelected ? "Quitar selección" : `Seleccionar los ${links.length} resultados filtrados`}
            </button>
          </div>
        )}

        {/* Acciones */}
        {canCheck ? (
          <section aria-labelledby="link-actions-title" className="flex flex-col gap-4 rounded-xl border border-[#DCE0E5] bg-white p-5">
            <h2 id="link-actions-title" className="text-base font-semibold">Acciones de verificación</h2>
            <div className="grid gap-4 md:grid-cols-3">
              <div className="flex flex-col gap-2">
                <Button
                  disabled={busy || !selectedPlatformIds.length}
                  onClick={() => verifyPlatforms(selectedPlatformIds)}
                >
                  {busy ? "Verificando…" : `Verificar plataformas seleccionadas (${selectedPlatformIds.length})`}
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
