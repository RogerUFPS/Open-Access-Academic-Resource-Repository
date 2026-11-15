"use client";

import { useEffect, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { Check, Copy } from "lucide-react";
import { Button } from "@/components/ui/button";
import { CardContent, CardFooter } from "@/components/ui/card";
import AccountFeedback from "@/shared/components/AccountFeedback";
import LoginField from "@/shared/components/LoginField";
import RateLimitNotice from "@/shared/components/RateLimitNotice";
import { useAccountsApi } from "@/shared/components/AccountsProvider";
import useRetryCountdown, { formatWait } from "@/shared/hooks/useRetryCountdown";

const primaryButton = "h-12 w-full rounded-lg bg-[#7f1218] text-[15px] font-medium text-white transition-colors hover:bg-[#6a0f14]";

export function MfaCodeField({ id, value, onChange, autoFocus = false }) {
  return <LoginField
    id={id}
    label="Código de verificación"
    inputMode="numeric"
    autoComplete="one-time-code"
    pattern="[0-9]{6}"
    maxLength={6}
    placeholder="123456"
    title="Ingresa los 6 dígitos que muestra tu aplicación autenticadora."
    autoFocus={autoFocus}
    value={value}
    onChange={(event) => onChange(event.target.value.replace(/\D/g, "").slice(0, 6))}
  />;
}

function codeError(error) {
  if (error.status === 400) return new Error(error.message || "El código no es válido. Revisa la hora de tu dispositivo e intenta con el código actual.");
  return error;
}

/** Seconds left until the enrollment secret expires, ticking every second. */
function useExpiry(expiresAt) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!expiresAt) return undefined;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [expiresAt]);
  return expiresAt ? Math.max(0, Math.ceil((expiresAt - now) / 1000)) : null;
}

/**
 * Starts enrollment with POST and shows the TOTP secret for a superadmin
 * without MFA, then confirms the first code. The QR is generated locally: the
 * otpauth URI and the secret are never sent to external services or logs, and
 * live only in this component's state.
 * `onStepChanged` re-reads /auth/me/ when the backend says this step no longer applies.
 */
export function MfaEnrollmentStep({ onCompleted, onStepChanged, onSignOut }) {
  const accountsApi = useAccountsApi();
  const [enrollment, setEnrollment] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [reload, setReload] = useState(0);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [copied, setCopied] = useState(false);
  const { remaining, limited, handleRateLimit } = useRetryCountdown();
  const secondsLeft = useExpiry(enrollment?.expiresAt);
  const expired = secondsLeft === 0;

  useEffect(() => {
    let cancelled = false;
    accountsApi.startMfaEnrollment().then((data) => {
      if (cancelled) return;
      const ttl = Number(data?.expires_in);
      setEnrollment({
        secret: data.secret,
        otpauthUri: data.otpauth_uri,
        expiresAt: Number.isFinite(ttl) && ttl > 0 ? Date.now() + ttl * 1000 : null,
      });
    }).catch((error) => {
      if (cancelled) return;
      // 403: password change pending; 409: MFA was already enabled.
      if ([403, 409].includes(error.status)) onStepChanged();
      else setLoadError(error);
    });
    return () => { cancelled = true; };
  }, [accountsApi, onStepChanged, reload]);

  function restartEnrollment() {
    setEnrollment(null);
    setLoadError(null);
    setError(null);
    setCode("");
    setReload((value) => value + 1);
  }

  async function copySecret() {
    try {
      await navigator.clipboard.writeText(enrollment.secret);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  }

  async function submit(event) {
    event.preventDefault();
    if (busy || limited || expired) return;
    setError(null);
    setBusy(true);
    try {
      await accountsApi.confirmMfaEnrollment(code);
      await onCompleted();
    } catch (error) {
      if (error.status === 403) {
        await onStepChanged();
        return;
      }
      if (handleRateLimit(error)) {
        setCode("");
        return;
      }
      setError(codeError(error));
      setCode("");
    } finally {
      setBusy(false);
    }
  }

  const groupedSecret = enrollment?.secret.match(/.{1,4}/g)?.join(" ") ?? "";

  return <form onSubmit={submit} aria-busy={busy}>
    <CardContent className="space-y-5">
      {loadError && <AccountFeedback error={loadError} retry={restartEnrollment} />}
      {error && <AccountFeedback error={error} />}
      <RateLimitNotice remaining={remaining} />
      {!enrollment && !loadError && <p role="status" className="text-sm text-gray-500">Preparando la configuración…</p>}
      {enrollment && <>
        <ol className="list-decimal space-y-1 pl-5 text-sm text-gray-600">
          <li>Abre una aplicación autenticadora (Google Authenticator, Microsoft Authenticator, Aegis, 1Password…).</li>
          <li>Escanea el código QR o ingresa la clave manualmente.</li>
          <li>Escribe el código de 6 dígitos que genera la aplicación.</li>
        </ol>
        <div className="flex justify-center rounded-lg border border-gray-200 bg-white p-4">
          <QRCodeSVG value={enrollment.otpauthUri} size={176} marginSize={2} title="Código QR para configurar la aplicación autenticadora" />
        </div>
        <div className="space-y-1">
          <p className="text-[11px] font-medium tracking-wider text-gray-500 uppercase">Clave para ingreso manual</p>
          <div className="flex items-center gap-2 rounded-md border border-gray-200 bg-gray-50 px-3 py-2">
            <code className="min-w-0 flex-1 font-mono text-sm break-all text-gray-900" aria-label="Clave secreta">{groupedSecret}</code>
            <button type="button" onClick={copySecret} className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-gray-500 hover:text-gray-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gray-400" aria-label={copied ? "Clave copiada" : "Copiar clave"}>
              {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
            </button>
          </div>
          <p className="text-[12px] text-gray-500">Tipo: basada en tiempo (TOTP), 6 dígitos, 30 segundos.</p>
        </div>
        {secondsLeft !== null && (expired
          ? <div role="alert" className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
            <p>Esta configuración expiró. Genera una clave nueva y vuelve a escanear el código QR.</p>
            <button type="button" onClick={restartEnrollment} className="mt-2 font-semibold underline">Generar una clave nueva</button>
          </div>
          : <p role="timer" aria-live="off" className="text-[13px] text-gray-500">Esta clave expira en <span className="font-semibold tabular-nums">{formatWait(secondsLeft)}</span>. No la compartas ni la guardes fuera de tu aplicación autenticadora.</p>)}
        <fieldset disabled={busy}>
          <MfaCodeField id="mfa-enroll-code" value={code} onChange={setCode} />
        </fieldset>
      </>}
    </CardContent>
    <CardFooter className="flex-col gap-4 pt-2 pb-4">
      <Button type="submit" disabled={busy || limited || expired || !enrollment || code.length !== 6} className={primaryButton}>{busy ? "Verificando…" : "Activar verificación en dos pasos"}</Button>
      <button type="button" onClick={onSignOut} disabled={busy} className="text-sm font-medium text-[#7f1218] hover:underline disabled:opacity-60">Cerrar sesión</button>
    </CardFooter>
  </form>;
}

export function MfaChallengeStep({ onCompleted, onStepChanged, onSignOut }) {
  const accountsApi = useAccountsApi();
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const { remaining, limited, handleRateLimit } = useRetryCountdown();

  async function submit(event) {
    event.preventDefault();
    if (busy || limited) return;
    setError(null);
    setBusy(true);
    try {
      await accountsApi.mfaChallenge(code);
      await onCompleted();
    } catch (error) {
      if (error.status === 403) {
        await onStepChanged();
        return;
      }
      if (!handleRateLimit(error)) setError(codeError(error));
      setCode("");
    } finally {
      setBusy(false);
    }
  }

  return <form onSubmit={submit} aria-busy={busy}>
    <CardContent className="space-y-5">
      {error && <AccountFeedback error={error} />}
      <RateLimitNotice remaining={remaining} />
      <fieldset disabled={busy}>
        <MfaCodeField id="mfa-challenge-code" value={code} onChange={setCode} autoFocus />
      </fieldset>
      <p className="text-[13px] text-gray-500">Si perdiste acceso a tu aplicación autenticadora, contacta a otro superadministrador.</p>
    </CardContent>
    <CardFooter className="flex-col gap-4 pt-2 pb-4">
      <Button type="submit" disabled={busy || limited || code.length !== 6} className={primaryButton}>{busy ? "Verificando…" : "Verificar"}</Button>
      <button type="button" onClick={onSignOut} disabled={busy} className="text-sm font-medium text-[#7f1218] hover:underline disabled:opacity-60">Cerrar sesión</button>
    </CardFooter>
  </form>;
}
