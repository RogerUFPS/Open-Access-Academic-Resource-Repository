"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Button from "@/shared/components/Button";
import FormField from "@/shared/components/FormField";
import AccountFeedback from "@/shared/components/AccountFeedback";
import { useAccountsApi } from "@/shared/components/AccountsProvider";
import { extractApiErrorText } from "@/shared/services/apiClient";

const outlineStyle = "!h-[42px] !border-[#7f1218] !text-[#7f1218]";
const primaryStyle = "!h-[42px] !border-[#7f1218] !bg-[#7f1218] hover:!bg-[#6a0f14]";

function createError(error) {
  if (error.status === 409) return new Error("Ese correo ya está asignado a otra cuenta. Usa una dirección diferente.");
  if (error.status === 503) return new Error("No se pudo enviar el correo con la contraseña temporal, así que la cuenta no se creó. Intenta nuevamente en unos minutos.");
  if (error.status === 400) return new Error(extractApiErrorText(error.data?.email) || error.message);
  return error;
}

function DeactivateDialog({ email, onClose }) {
  const accountsApi = useAccountsApi();
  const router = useRouter();
  const dialog = useRef(null);
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  useEffect(() => { dialog.current.showModal(); }, []);

  async function deactivate(event) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await accountsApi.deactivateSuperadmin();
      router.replace("/admin/login");
      router.refresh();
    } catch (error) {
      setError(error.status === 409
        ? new Error("No hay otro superadministrador activo que haya cambiado su contraseña y configurado MFA. Tu cuenta sigue activa; pide a la nueva cuenta que complete su primer inicio de sesión y vuelve a intentarlo.")
        : error);
      setBusy(false);
    }
  }

  return (
    <dialog ref={dialog} aria-labelledby="superadmin-deactivate-title" onCancel={(event) => { if (busy) event.preventDefault(); else onClose(); }} className="fixed inset-0 m-auto w-[calc(100%-2rem)] max-w-md rounded-xl border border-[#D1D6E0] bg-white p-6 text-[#1F242E] shadow-xl backdrop:bg-black/40">
      <form onSubmit={deactivate}>
        <h2 id="superadmin-deactivate-title" className="text-xl font-bold">Desactivar mi cuenta de superadministrador</h2>
        <p className="my-4 text-sm text-[#6B758A]">Se desactivará <strong>{email}</strong> y se cerrará tu sesión. Esta acción no se puede deshacer desde la aplicación.</p>
        <FormField compact id="superadmin-deactivate-confirm" label="Escribe tu correo para confirmar" type="email" autoComplete="off" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} disabled={busy} />
        {error && <div className="mt-4"><AccountFeedback error={error} /></div>}
        <div className="mt-5 flex justify-end gap-3">
          <Button variant="outline" className={outlineStyle} disabled={busy} onClick={onClose} autoFocus>Cancelar</Button>
          <Button type="submit" className={primaryStyle} disabled={busy || confirmation.trim().toLowerCase() !== email.toLowerCase()}>{busy ? "Desactivando…" : "Desactivar cuenta"}</Button>
        </div>
      </form>
    </dialog>
  );
}

export default function SuperadminAccounts() {
  const accountsApi = useAccountsApi();
  const [viewer, setViewer] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [created, setCreated] = useState(null);
  const [deactivating, setDeactivating] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    accountsApi.currentUser(controller.signal).then((user) => {
      if (!user.is_superadmin) throw new Error("Esta sección solo está disponible para superadministradores.");
      setViewer(user);
    }).catch((error) => {
      if (!controller.signal.aborted) setLoadError(error);
    });
    return () => controller.abort();
  }, [accountsApi]);

  async function create(event) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    setCreated(null);
    try {
      const account = await accountsApi.createSuperadmin(email.trim());
      setCreated(account);
      setEmail("");
    } catch (error) {
      setError(createError(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="space-y-5 text-[#1F242E]">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-[30px] leading-[41px] font-bold">Superadministración</h1>
          <p className="mt-3 max-w-2xl text-[15px] text-[#6B758A]">Crea cuentas de superadministrador de reemplazo y retira la tuya cuando otra cuenta ya esté lista.</p>
        </div>
        <Button variant="outline" className={outlineStyle} href="/admin/usuarios">Volver a usuarios</Button>
      </header>

      {loadError && <AccountFeedback error={loadError} />}
      {!viewer && !loadError && <p role="status" className="text-sm text-[#6B758A]">Cargando…</p>}

      {viewer && <>
        <form onSubmit={create} aria-busy={busy} className="space-y-4 rounded-[10px] bg-white p-5">
          <div>
            <h2 className="text-lg font-bold">Crear superadministrador</h2>
            <p className="mt-1 text-sm text-[#6B758A]">Se enviará una contraseña temporal al correo indicado. La nueva cuenta deberá cambiarla y configurar la verificación en dos pasos en su primer inicio de sesión.</p>
          </div>
          {error && <AccountFeedback error={error} />}
          {created && <p role="status" className="rounded-lg bg-[#E8FAF0] p-3 text-sm text-[#0F8C45]">Se creó la cuenta <strong>{created.email}</strong> y se envió su contraseña temporal. Quedará lista cuando complete el cambio de contraseña y la configuración de MFA.</p>}
          <div className="flex flex-wrap items-end gap-3">
            <div className="min-w-64 flex-1">
              <FormField compact id="superadmin-email" label="Correo del nuevo superadministrador" type="email" required autoComplete="off" value={email} onChange={(event) => setEmail(event.target.value)} disabled={busy} />
            </div>
            <Button type="submit" className={primaryStyle} disabled={busy || !email.trim()}>{busy ? "Creando…" : "Crear cuenta"}</Button>
          </div>
        </form>

        <div className="space-y-4 rounded-[10px] border border-[#F3D7D7] bg-white p-5">
          <div>
            <h2 className="text-lg font-bold">Desactivar mi cuenta</h2>
            <p className="mt-1 text-sm text-[#6B758A]">Solo es posible cuando existe otro superadministrador activo que ya cambió su contraseña y configuró MFA. Al desactivarla se cerrará tu sesión.</p>
          </div>
          <Button variant="outline" className={outlineStyle} onClick={() => setDeactivating(true)}>Desactivar mi cuenta</Button>
        </div>
      </>}

      {deactivating && viewer && <DeactivateDialog email={viewer.email} onClose={() => setDeactivating(false)} />}
    </section>
  );
}
