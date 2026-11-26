"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  AlertCircle,
  BookOpenCheck,
  CalendarDays,
  Clock3,
  Link2,
  RefreshCw,
} from "lucide-react";
import Button from "@/shared/components/Button";
import Notice from "@/shared/components/Notice";
import { queryKeys } from "@/shared/query/queryKeys";
import { formatPublicationMonth, getIndicators, sortPublicationMonths } from "@/features/admin/indicators/indicatorsService";

const numberFormatter = new Intl.NumberFormat("es-CO");
const percentageFormatter = new Intl.NumberFormat("es-CO", { maximumFractionDigits: 2 });
const monthFormatter = new Intl.DateTimeFormat("es-CO", { month: "short", timeZone: "UTC" });

const SUMMARY_CARDS = [
  { key: "published_journals", label: "Revistas publicadas", icon: BookOpenCheck, accent: "bg-[#F8E9EC] text-[#7f1218]" },
  { key: "published_journals_this_month", label: "Publicadas este mes", icon: CalendarDays, accent: "bg-[#EAF2FF] text-[#285A9F]" },
  { key: "pending_journals", label: "Revistas pendientes", icon: Clock3, accent: "bg-[#FFF3DB] text-[#875B0A]" },
];

function MetricTile({ value, label, icon: Icon, accent }) {
  return (
    <article className="flex min-h-[140px] items-start justify-between gap-4 rounded-xl border border-[#DCE0E5] bg-white p-5">
      <div className="flex min-w-0 flex-col gap-3">
        <p className="text-[32px] leading-10 font-bold tracking-[-0.3px] text-[#1F242E]">
          {value == null ? "—" : numberFormatter.format(value)}
        </p>
        <p className="text-sm leading-5 text-[#68707C]">{label}</p>
      </div>
      <span className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl ${accent}`}>
        <Icon className="h-5 w-5" aria-hidden="true" />
      </span>
    </article>
  );
}

function LoadingPanel() {
  return (
    <div role="status" aria-label="Cargando indicadores" className="space-y-5">
      <span className="sr-only">Cargando indicadores administrativos…</span>
      <div className="grid grid-cols-1 gap-4 min-[541px]:grid-cols-2 min-[1100px]:grid-cols-4">
        {Array.from({ length: 4 }, (_, index) => (
          <div key={index} className="h-[140px] animate-pulse rounded-xl border border-[#DCE0E5] bg-white p-5">
            <div className="h-9 w-24 rounded bg-[#EEF0F3]" />
            <div className="mt-5 h-4 w-36 rounded bg-[#EEF0F3]" />
          </div>
        ))}
      </div>
      <div className="grid grid-cols-1 gap-5 min-[900px]:grid-cols-2">
        {Array.from({ length: 2 }, (_, index) => (
          <div key={index} className="h-[330px] animate-pulse rounded-xl border border-[#DCE0E5] bg-white p-5">
            <div className="h-6 w-48 rounded bg-[#EEF0F3]" />
            <div className="mt-8 h-56 rounded bg-[#F7F8FA]" />
          </div>
        ))}
      </div>
    </div>
  );
}

function errorMessage(error) {
  if (error?.status === 401) {
    return "Tu sesión no está autenticada. Inicia sesión nuevamente para consultar los indicadores.";
  }
  if (error?.status === 403) {
    return error.recentAuthRequired
      ? "Debes completar la verificación MFA o volver a autenticarte para consultar los indicadores."
      : "No tienes permiso para consultar los indicadores. Si tu cuenta requiere MFA, complétalo e inténtalo de nuevo.";
  }
  if (error instanceof TypeError || error?.name === "AbortError" || !error?.status) {
    return "No fue posible conectar con el servidor. Revisa tu conexión e inténtalo nuevamente.";
  }
  return "Ocurrió un error inesperado al cargar los indicadores. Inténtalo nuevamente.";
}

function ErrorPanel({ error, retry, loading }) {
  return (
    <section className="rounded-xl border border-[#F2BFC4] bg-white p-6" aria-labelledby="indicators-error-title">
      <div className="flex items-start gap-3">
        <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-[#A90D27]" aria-hidden="true" />
        <div className="flex-1">
          <h2 id="indicators-error-title" className="font-semibold text-[#1F242E]">
            No se pudieron cargar los indicadores
          </h2>
          <p role="alert" className="mt-1 text-sm leading-6 text-[#68707C]">{errorMessage(error)}</p>
          <Button className="mt-4" size="small" disabled={loading} onClick={retry}>
            <RefreshCw className="mr-2 h-4 w-4" aria-hidden="true" />
            {loading ? "Reintentando…" : "Reintentar"}
          </Button>
        </div>
      </div>
    </section>
  );
}

function LinkAvailability({ availability }) {
  const percentage = availability?.percentage;
  const available = availability?.available;
  const total = availability?.total;
  const progress = typeof percentage === "number" ? Math.min(100, Math.max(0, percentage)) : 0;

  return (
    <article className="flex min-h-[140px] flex-col justify-between gap-4 rounded-xl border border-[#DCE0E5] bg-white p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[32px] leading-10 font-bold tracking-[-0.3px] text-[#1F242E]">
            {percentage == null ? "—" : `${percentageFormatter.format(percentage)}%`}
          </p>
          <p className="mt-3 text-sm leading-5 text-[#68707C]">Disponibilidad de enlaces</p>
        </div>
        <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-[#E7F5EE] text-[#17643A]">
          <Link2 className="h-5 w-5" aria-hidden="true" />
        </span>
      </div>
      <div>
        <div
          className="h-2 overflow-hidden rounded-full bg-[#EEF0F3]"
          role="progressbar"
          aria-label="Porcentaje de enlaces disponibles"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={percentage == null ? 0 : progress}
        >
          <div className="h-full rounded-full bg-[#218553] transition-[width]" style={{ width: `${progress}%` }} />
        </div>
        <p className="mt-2 text-xs text-[#68707C]">
          {available == null || total == null
            ? "Enlaces vigentes no disponibles"
            : `${numberFormatter.format(available)} de ${numberFormatter.format(total)} enlaces vigentes disponibles`}
        </p>
      </div>
    </article>
  );
}

function PublicationsChart({ months }) {
  const orderedMonths = sortPublicationMonths(months);
  const chartWidth = 720;
  const chartHeight = 250;
  const left = 44;
  const right = 12;
  const top = 18;
  const bottom = 194;
  const maxCount = Math.max(0, ...orderedMonths.map(({ count }) => count));
  const scaleMax = Math.max(1, maxCount);
  const plotWidth = chartWidth - left - right;
  const slotWidth = orderedMonths.length ? plotWidth / orderedMonths.length : plotWidth;
  const barWidth = Math.min(32, slotWidth * 0.58);
  const gridValues = [scaleMax, Math.ceil(scaleMax / 2), 0].filter((value, index, values) => values.indexOf(value) === index);

  return (
    <section className="min-w-0 rounded-xl border border-[#DCE0E5] bg-white p-4 min-[541px]:p-5" aria-labelledby="publications-title">
      <div className="mb-4">
        <h2 id="publications-title" className="text-lg leading-7 font-semibold text-[#1F242E]">Publicaciones por mes</h2>
        <p className="mt-1 text-sm text-[#68707C]">Revistas publicadas en los últimos 12 meses</p>
      </div>
      {orderedMonths.length === 0 ? (
        <p className="flex min-h-[230px] items-center justify-center text-sm text-[#68707C]">No hay datos de publicaciones por mes.</p>
      ) : (
        <div className="w-full overflow-x-auto">
          <svg
            viewBox={`0 0 ${chartWidth} ${chartHeight}`}
            className="h-auto min-h-[210px] w-full min-w-[560px]"
            role="img"
            aria-labelledby="publications-chart-title publications-chart-description"
          >
            <title id="publications-chart-title">Revistas publicadas por mes</title>
            <desc id="publications-chart-description">
              Gráfica de barras con {orderedMonths.length} meses en orden cronológico y su cantidad de revistas publicadas.
            </desc>
            {gridValues.map((value) => {
              const y = bottom - (value / scaleMax) * (bottom - top);
              return (
                <g key={value}>
                  <line x1={left} x2={chartWidth - right} y1={y} y2={y} stroke="#E8EAED" strokeDasharray={value === 0 ? undefined : "4 4"} />
                  <text x={left - 10} y={y + 4} textAnchor="end" fill="#68707C" fontSize="11">{numberFormatter.format(value)}</text>
                </g>
              );
            })}
            {orderedMonths.map(({ month, count }, index) => {
              const x = left + slotWidth * index + (slotWidth - barWidth) / 2;
              const barHeight = (count / scaleMax) * (bottom - top);
              const y = bottom - barHeight;
              const label = formatPublicationMonth(month);
              const monthOnly = monthFormatter.format(new Date(Date.UTC(Number(month.slice(0, 4)), Number(month.slice(5, 7)) - 1, 1)));
              return (
                <g key={month}>
                  <title>{`${label}: ${numberFormatter.format(count)} ${count === 1 ? "revista" : "revistas"}`}</title>
                  {count > 0 && <rect x={x} y={y} width={barWidth} height={barHeight} rx="4" fill="#A90D27" />}
                  <text
                    x={x + barWidth / 2}
                    y={count > 0 ? Math.max(top - 2, y - 6) : bottom - 6}
                    textAnchor="middle"
                    fill="#343A43"
                    fontSize="10"
                  >
                    {numberFormatter.format(count)}
                  </text>
                  <text x={x + barWidth / 2} y={bottom + 24} textAnchor="middle" fill="#68707C" fontSize="11">{monthOnly.replace(".", "")}</text>
                </g>
              );
            })}
          </svg>
        </div>
      )}
    </section>
  );
}

function KnowledgeAreas({ areas }) {
  const orderedAreas = [...(areas ?? [])].sort((first, second) => (
    second.journals - first.journals || first.name.localeCompare(second.name, "es")
  ));
  const maxCount = Math.max(0, ...orderedAreas.map(({ journals }) => journals));

  return (
    <section className="min-w-0 rounded-xl border border-[#DCE0E5] bg-white p-4 min-[541px]:p-5" aria-labelledby="areas-title">
      <div className="mb-4">
        <h2 id="areas-title" className="text-lg leading-7 font-semibold text-[#1F242E]">Revistas por área de conocimiento</h2>
        <p className="mt-1 text-sm text-[#68707C]">Comparación de revistas publicadas asociadas a cada área</p>
      </div>
      {orderedAreas.length === 0 ? (
        <p className="flex min-h-[230px] items-center justify-center text-sm text-[#68707C]">No hay áreas de conocimiento para mostrar.</p>
      ) : (
        <ul className="max-h-[360px] space-y-4 overflow-y-auto pr-2">
          {orderedAreas.map(({ id, name, journals }) => {
            const width = maxCount === 0 ? 0 : (journals / maxCount) * 100;
            return (
              <li key={id} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-2">
                <span className="min-w-0 text-sm leading-5 text-[#343A43] [overflow-wrap:anywhere]">{name}</span>
                <span className="text-sm font-semibold tabular-nums text-[#1F242E]">{numberFormatter.format(journals)}</span>
                <div
                  className="col-span-2 h-2 overflow-hidden rounded-full bg-[#EEF0F3]"
                  role="progressbar"
                  aria-label={`Revistas en ${name}`}
                  aria-valuemin={0}
                  aria-valuemax={Math.max(1, maxCount)}
                  aria-valuenow={journals}
                >
                  <div className="h-full rounded-full bg-[#A90D27]" style={{ width: `${width}%` }} />
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

export default function AdminIndicatorsPage() {
  const indicatorsQuery = useQuery({
    queryKey: queryKeys.indicators.overview,
    queryFn: ({ signal }) => getIndicators(signal),
  });
  const { data, error, isError, isFetching, isPending, refetch } = indicatorsQuery;

  if (isPending) return <LoadingPanel />;
  if (isError && !data) {
    return <ErrorPanel error={error} retry={refetch} loading={isFetching} />;
  }

  return (
    <div className="space-y-5 text-[#1F242E]" aria-busy={isFetching}>
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-[26px] leading-[34px] font-bold tracking-[-0.3px] min-[541px]:text-[32px] min-[541px]:leading-10">
            Indicadores administrativos
          </h1>
          <p className="mt-2 text-sm leading-6 text-[#68707C] min-[541px]:text-base">
            Resumen de revistas, enlaces y áreas de conocimiento.
          </p>
        </div>
        <Button variant="quiet" size="small" disabled={isFetching} onClick={() => refetch()}>
          <RefreshCw className={`mr-2 h-4 w-4 ${isFetching ? "animate-spin" : ""}`} aria-hidden="true" />
          Actualizar
        </Button>
      </header>

      {isError && data && (
        <Notice variant="error" live>
          No fue posible actualizar los indicadores. Se mantienen los últimos datos cargados. {errorMessage(error)}
        </Notice>
      )}

      <section aria-label="Resumen de indicadores" className="grid grid-cols-1 gap-4 min-[541px]:grid-cols-2 min-[1100px]:grid-cols-4">
        {SUMMARY_CARDS.map(({ key, label, icon, accent }) => (
          <MetricTile key={key} value={data?.[key]} label={label} icon={icon} accent={accent} />
        ))}
        <LinkAvailability availability={data?.link_availability} />
      </section>

      <div className="grid min-w-0 grid-cols-1 gap-5 min-[900px]:grid-cols-2">
        <PublicationsChart months={data?.publications_by_month ?? []} />
        <KnowledgeAreas areas={data?.journals_by_knowledge_area ?? []} />
      </div>
      <p className="flex items-center gap-2 text-xs text-[#68707C]">
        <Activity className="h-4 w-4 shrink-0" aria-hidden="true" />
        Datos consultados desde los indicadores administrativos del directorio.
      </p>
    </div>
  );
}
