"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Button from "@/shared/components/Button";
import AccountFeedback from "@/shared/components/AccountFeedback";
import { useAccountsApi } from "@/shared/components/AccountsProvider";
import { formatWait } from "@/shared/hooks/useRetryCountdown";

const outlineStyle = "!h-[42px] !border-[#7f1218] !text-[#7f1218]";
const primaryStyle = "!h-[42px] !border-[#7f1218] !bg-[#7f1218] hover:!bg-[#6a0f14]";

const dateFormat = new Intl.DateTimeFormat("es-CO", { dateStyle: "long", timeStyle: "short" });

function formatDate(value) {
  if (!value) return "No disponible";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "No disponible" : dateFormat.format(date);
}

const BROWSERS = [
  [/Edg(?:e|A|iOS)?\//, "Microsoft Edge"],
  [/OPR\/|Opera/, "Opera"],
  [/Firefox\/|FxiOS\//, "Firefox"],
  [/Chrome\/|CriOS\//, "Chrome"],
  [/Safari\//, "Safari"],
];
const SYSTEMS = [
  [/Android/, "Android"],
  [/iPhone|iPad|iPod/, "iOS"],
  [/Windows/, "Windows"],
  [/Mac OS X|Macintosh/, "macOS"],
  [/CrOS/, "ChromeOS"],
  [/Linux/, "Linux"],
];

/** Human readable description of a user agent, computed locally. */
export function describeUserAgent(userAgent) {
  if (!userAgent) return "Navegador desconocido";
  const browser = BROWSERS.find(([pattern]) => pattern.test(userAgent))?.[1] ?? "Navegador desconocido";
  const system = SYSTEMS.find(([pattern]) => pattern.test(userAgent))?.[1];
  return system ? `${browser} en ${system}` : browser;
}

function maskIp(ip) {
  if (!ip) return "No disponible";
  if (ip.includes(":")) return `${ip.split(":").slice(0, 2).join(":")}:…`;
  const parts = ip.split(".");
  return parts.length === 4 ? `${parts[0]}.${parts[1]}.•••.•••` : "•••";
}

function useSecondsLeft(deadline) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!deadline) return undefined;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [deadline]);
  return deadline ? Math.max(0, Math.ceil((deadline - now) / 1000)) : 0;
}

function RevokeDialog({ onClose }) {
  const accountsApi = useAccountsApi();
  const router = useRouter();
  const dialog = useRef(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  useEffect(() => { dialog.current.showModal(); }, []);

  async function revoke(event) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await accountsApi.revokeSession();
      router.replace("/admin/login?motivo=sesion-revocada");
      router.refresh();
    } catch (error) {
      setError(error);
      setBusy(false);
    }
  }

  return (
    <dialog ref={dialog} aria-labelledby="session-revoke-title" onCancel={(event) => { if (busy) event.preventDefault(); else onClose(); }} className="fixed inset-0 m-auto w-[calc(100%-2rem)] max-w-md rounded-xl border border-[#D1D6E0] bg-white p-6 text-[#1F242E] shadow-xl backdrop:bg-black/40">
      <form onSubmit={revoke}>
        <h2 id="session-revoke-title" className="text-xl font-bold">Revocar esta sesión</h2>
        <p className="my-4 text-sm text-[#6B758A]">La sesión se invalidará en el servidor y tendrás que iniciar sesión de nuevo para continuar.</p>
        {error && <div className="mb-4"><AccountFeedback error={error} /></div>}
        <div className="flex justify-end gap-3">
          <Button variant="outline" className={outlineStyle} disabled={busy} onClick={onClose} autoFocus>Cancelar</Button>
          <Button type="submit" className={primaryStyle} disabled={busy}>{busy ? "Revocando…" : "Revocar sesión"}</Button>
        </div>
      </form>
    </dialog>
  );
}

function Detail({ label, children }) {
  return <div className="space-y-1">
    <dt className="text-[11px] font-semibold tracking-wider text-[#6B758A] uppercase">{label}</dt>
    <dd className="text-[15px] text-[#1F242E]">{children}</dd>
  </div>;
}

export default function SessionDetails() {
  const accountsApi = useAccountsApi();
  const [session, setSession] = useState(null);
  const [error, setError] = useState(null);
  const [reload, setReload] = useState(0);
  const [showIp, setShowIp] = useState(false);
  const [revoking, setRevoking] = useState(false);
  const recentAuthLeft = useSecondsLeft(session?.recentAuthDeadline);
  const expiresLeft = useSecondsLeft(session?.expiresAt);

  useEffect(() => {
    const controller = new AbortController();
    accountsApi.session(controller.signal).then((data) => {
      const remaining = Number(data?.recent_authentication_expires_in);
      const expiresAt = data?.expires_at ? Date.parse(data.expires_at) : NaN;
      setSession({
        ...data,
        expiresAt: Number.isNaN(expiresAt) ? null : expiresAt,
        recentAuthDeadline: data?.recent_authentication && remaining > 0 ? Date.now() + remaining * 1000 : null,
      });
    }).catch((error) => {
      // 401 is handled globally by the session-expired dialog.
      if (!controller.signal.aborted && !error.authExpired) setError(error);
    });
    return () => controller.abort();
  }, [accountsApi, reload]);

  const retry = useCallback(() => {
    setError(null);
    setSession(null);
    setReload((value) => value + 1);
  }, []);

  return (
    <section className="space-y-5 text-[#1F242E]">
      <header>
        <h1 className="text-[30px] leading-[41px] font-bold">Mi sesión</h1>
        <p className="mt-3 max-w-2xl text-[15px] text-[#6B758A]">Consulta los datos de la sesión activa y revócala si no reconoces el acceso o terminaste de trabajar.</p>
      </header>

      {error && <AccountFeedback error={error} retry={retry} />}
      {!session && !error && <p role="status" className="text-sm text-[#6B758A]">Cargando…</p>}

      {session && <>
        <dl className="grid gap-5 rounded-[10px] bg-white p-5 sm:grid-cols-2">
          <Detail label="Inicio">{formatDate(session.started_at)}</Detail>
          <Detail label="Expira">
            {formatDate(session.expires_at)}
            {session.expiresAt && <span className="block text-sm text-[#6B758A]">{expiresLeft > 0 ? `En ${formatWait(expiresLeft)}` : "Expirada"}</span>}
          </Detail>
          <Detail label="Navegador">{describeUserAgent(session.user_agent)}</Detail>
          <Detail label="Dirección IP">
            <span className="font-mono">{showIp ? session.ip_address || "No disponible" : maskIp(session.ip_address)}</span>
            {session.ip_address && <button type="button" onClick={() => setShowIp((value) => !value)} className="ml-3 text-sm font-medium text-[#7f1218] hover:underline">{showIp ? "Ocultar" : "Mostrar"}</button>}
          </Detail>
          <Detail label="Autenticación reciente">
            {recentAuthLeft > 0
              ? <>Vigente <span className="text-sm text-[#6B758A]">(durante {formatWait(recentAuthLeft)} más)</span></>
              : "Vencida: las operaciones críticas pedirán iniciar sesión de nuevo."}
          </Detail>
        </dl>

        <div className="space-y-4 rounded-[10px] border border-[#F3D7D7] bg-white p-5">
          <div>
            <h2 className="text-lg font-bold">Revocar sesión</h2>
            <p className="mt-1 text-sm text-[#6B758A]">Invalida esta sesión en el servidor. Para un cierre normal también puedes usar «Cerrar sesión» en el menú.</p>
          </div>
          <Button variant="outline" className={outlineStyle} onClick={() => setRevoking(true)}>Revocar esta sesión</Button>
        </div>
      </>}

      {revoking && <RevokeDialog onClose={() => setRevoking(false)} />}
    </section>
  );
}
