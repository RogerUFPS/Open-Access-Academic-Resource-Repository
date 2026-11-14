"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import AccountFeedback from "@/shared/components/AccountFeedback";
import LoginField from "@/shared/components/LoginField";
import { MfaChallengeStep, MfaEnrollmentStep } from "@/shared/components/MfaSteps";
import { useAccountsApi } from "@/shared/components/AccountsProvider";
import { pendingAccountStep } from "@/shared/services/apiClient";

const STEP_COPY = {
  login: ["Iniciar sesión", "Ingresa con las credenciales administrativas asignadas por la biblioteca."],
  password: ["Cambiar contraseña", "Cambia tu contraseña provisional antes de continuar con la administración."],
  "mfa-enroll": ["Configurar verificación en dos pasos", "Las cuentas de superadministrador requieren una aplicación autenticadora para iniciar sesión."],
  "mfa-challenge": ["Verificación en dos pasos", "Ingresa el código de 6 dígitos de tu aplicación autenticadora para continuar."],
};

export default function AdminLoginForm() {
  const accountsApi = useAccountsApi();
  const router = useRouter();
  // "login" | "password" | "mfa-enroll" | "mfa-challenge"
  const [step, setStep] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState("");

  const enterApp = useCallback(() => {
    router.replace("/admin/usuarios");
    router.refresh();
  }, [router]);

  // Routes using only the signed-in account's own flags (login or /auth/me/).
  const advance = useCallback((account) => {
    const next = pendingAccountStep(account);
    if (next) setStep(next);
    else enterApp();
  }, [enterApp]);

  // Re-reads /auth/me/ after each password or MFA step, as the backend expects.
  const refreshStep = useCallback(async () => {
    try {
      advance(await accountsApi.currentUser());
    } catch (error) {
      setStep("login");
      if (error.status !== 401) setError(error);
    }
  }, [accountsApi, advance]);

  useEffect(() => {
    const controller = new AbortController();
    accountsApi.currentUser(controller.signal).then((user) => {
      const next = pendingAccountStep(user);
      if (!next) return;
      setEmail(user.email);
      setStep(next);
    }).catch(() => {});
    return () => controller.abort();
  }, [accountsApi]);

  async function signOut() {
    setBusy(true);
    try {
      await accountsApi.logout();
    } catch {
      // The session may already be gone; the login form is shown either way.
    }
    setPassword("");
    setNewPassword("");
    setConfirmation("");
    setError(null);
    setNotice("");
    setStep("login");
    setBusy(false);
    router.refresh();
  }

  async function submit(event) {
    event.preventDefault();
    if (busy) return;
    setError(null);
    setNotice("");
    if (step === "password" && newPassword !== confirmation) {
      setError(new Error("Las contraseñas nuevas no coinciden."));
      return;
    }
    setBusy(true);
    try {
      if (step === "password") {
        await accountsApi.changePassword({ current_password: password, new_password: newPassword });
        setPassword("");
        setNewPassword("");
        setConfirmation("");
        setNotice("Contraseña actualizada.");
        await refreshStep();
      } else {
        const result = await accountsApi.login({ email: email.trim(), password });
        setPassword("");
        advance(result);
      }
    } catch (error) {
      setError(error.status === 401 && step === "login" ? new Error("El correo o la contraseña son incorrectos.") : error);
    } finally {
      setBusy(false);
    }
  }

  const [title, description] = STEP_COPY[step];

  return <Card className="w-full max-w-md rounded-2xl border-0 bg-white p-2 shadow-[0_8px_30px_rgb(0,0,0,0.04)]">
    <CardHeader className="space-y-3 pb-6">
      <CardTitle className="text-3xl font-bold tracking-tight text-gray-900">{title}</CardTitle>
      <CardDescription className="text-base text-gray-500">{description}</CardDescription>
      {notice && <p role="status" className="rounded-lg border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-900">{notice}</p>}
    </CardHeader>
    {step === "mfa-enroll" && <MfaEnrollmentStep onCompleted={refreshStep} onStepChanged={refreshStep} onSignOut={signOut} />}
    {step === "mfa-challenge" && <MfaChallengeStep onCompleted={refreshStep} onStepChanged={refreshStep} onSignOut={signOut} />}
    {(step === "login" || step === "password") && <form onSubmit={submit} aria-busy={busy}>
      <CardContent className="space-y-5">
        {error && <AccountFeedback error={error} />}
        <fieldset disabled={busy} className="space-y-5">
          {step === "login" && <LoginField id="login-email" label="Correo institucional" type="email" autoComplete="username" placeholder="usuario@ufps.edu.co" value={email} onChange={(event) => setEmail(event.target.value)} />}
          <LoginField id="login-password" label={step === "password" ? "Contraseña actual o provisional" : "Contraseña"} type="password" autoComplete="current-password" placeholder="••••••••••••" value={password} onChange={(event) => setPassword(event.target.value)} />
          {step === "password" && <>
            <LoginField id="new-password" label="Nueva contraseña" type="password" autoComplete="new-password" minLength={12} value={newPassword} onChange={(event) => setNewPassword(event.target.value)} />
            <LoginField id="confirm-password" label="Confirmar nueva contraseña" type="password" autoComplete="new-password" minLength={12} value={confirmation} onChange={(event) => setConfirmation(event.target.value)} />
          </>}
        </fieldset>
        {step === "login" && <div className="flex justify-end">
          <Link href="/admin/recuperar-contrasena" className="text-sm font-medium text-[#7f1218] hover:underline">¿Olvidaste tu contraseña?</Link>
        </div>}
        <p className="pt-1 text-[13px] text-gray-500">{step === "password" ? "Usa al menos 12 caracteres. Evita claves comunes, solo numéricas o similares a tus datos personales." : "Usa tu correo institucional y la contraseña asignada."}</p>
      </CardContent>
      <CardFooter className="flex-col gap-4 pt-2 pb-4">
        <Button type="submit" disabled={busy} className="h-12 w-full rounded-lg bg-[#7f1218] text-[15px] font-medium text-white transition-colors hover:bg-[#6a0f14]">{busy ? "Procesando…" : step === "password" ? "Guardar contraseña" : "Iniciar sesión"}</Button>
        {step === "password" && <button type="button" onClick={signOut} disabled={busy} className="text-sm font-medium text-[#7f1218] hover:underline disabled:opacity-60">Cerrar sesión</button>}
      </CardFooter>
    </form>}
  </Card>;
}
