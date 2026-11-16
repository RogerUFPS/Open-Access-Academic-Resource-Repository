"use client";

import { useEffect, useRef, useState } from "react";
import Button from "@/shared/components/Button";
import FormField from "@/shared/components/FormField";
import AccountFeedback from "@/shared/components/AccountFeedback";
import { useAccountsApi } from "@/shared/components/AccountsProvider";
import { extractApiErrorText, isRecentAuthenticationRequired } from "@/shared/services/apiClient";

const outlineStyle = "!h-[42px] !border-[#7f1218] !text-[#7f1218]";
const primaryStyle = "!h-[42px] !border-[#7f1218] !bg-[#7f1218] hover:!bg-[#6a0f14]";

function createError(error) {
  if (error.status === 409) return new Error(error.data?.email
    ? "Ese correo ya está asignado a otra cuenta. Usa una dirección diferente."
    : "Ya existe un reemplazo pendiente. Puedes cancelar la invitación pendiente antes de invitar a otro sucesor.");
  if (error.status === 503) return new Error("No se pudo enviar el correo con la contraseña temporal, así que la cuenta no se creó. Intenta nuevamente en unos minutos.");
  if (error.status === 400) return new Error(extractApiErrorText(error.data?.email) || error.message);
  return error;
}

function CancelHandoffDialog({ onClose, onCancelled }) {
  const accountsApi = useAccountsApi();
  const dialog = useRef(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  useEffect(() => { dialog.current.showModal(); }, []);

  async function cancelHandoff(event) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await accountsApi.cancelSuperadminHandoff();
      onCancelled("Se canceló el reemplazo pendiente y se desactivó la cuenta invitada. Puedes invitar a otro sucesor.");
    } catch (error) {
      // Native dialogs sit above the layout dialogs. Close this one so the
      // session-expired or recent-authentication prompt remains actionable.
      if (error.status === 401 || isRecentAuthenticationRequired(error)) {
        onClose();
        return;
      }
      if (error.status === 404) {
        onCancelled("No hay un reemplazo pendiente para tu cuenta.");
        return;
      }
      setError(error);
      setBusy(false);
    }
  }

  return (
    <dialog ref={dialog} aria-labelledby="superadmin-cancel-title" onCancel={(event) => { if (busy) event.preventDefault(); else onClose(); }} className="fixed inset-0 m-auto w-[calc(100%-2rem)] max-w-md rounded-xl border border-[#D1D6E0] bg-white p-6 text-[#1F242E] shadow-xl backdrop:bg-black/40">
      <form onSubmit={cancelHandoff}>
        <h2 id="superadmin-cancel-title" className="text-xl font-bold">Cancelar reemplazo pendiente</h2>
        <p className="my-4 text-sm text-[#6B758A]">La cuenta invitada que aún no haya completado su incorporación quedará desactivada. Tu cuenta seguirá siendo el superadministrador activo.</p>
        {error && <div className="mt-4"><AccountFeedback error={error} /></div>}
        <div className="mt-5 flex justify-end gap-3">
          <Button variant="outline" className={outlineStyle} disabled={busy} onClick={onClose} autoFocus>Volver</Button>
          <Button type="submit" className={primaryStyle} disabled={busy}>{busy ? "Cancelando…" : "Cancelar reemplazo"}</Button>
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
  const [cancelling, setCancelling] = useState(false);
  const [notice, setNotice] = useState("");

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
    if (busy || cancelling || created) return;
    setBusy(true);
    setError(null);
    setNotice("");
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
          <p className="mt-3 max-w-2xl text-[15px] text-[#6B758A]">Invita a un único sucesor. Cuando cambie su contraseña y confirme MFA, el reemplazo se completará automáticamente y tu cuenta quedará desactivada.</p>
        </div>
        <Button variant="outline" className={outlineStyle} href="/admin/usuarios">Volver a usuarios</Button>
      </header>

      {loadError && <AccountFeedback error={loadError} />}
      {!viewer && !loadError && <p role="status" className="text-sm text-[#6B758A]">Cargando…</p>}

      {viewer && <>
        <form onSubmit={create} aria-busy={busy} className="space-y-4 rounded-[10px] bg-white p-5">
          <div>
            <h2 className="text-lg font-bold">Invitar sucesor</h2>
            <p className="mt-1 text-sm text-[#6B758A]">Se enviará una contraseña temporal al correo indicado. La nueva cuenta no tendrá acceso a la aplicación hasta cambiarla y confirmar la verificación en dos pasos. Mientras tanto, tú seguirás siendo el único superadministrador activo.</p>
          </div>
          {error && <AccountFeedback error={error} />}
          {notice && <p role="status" className="rounded-lg bg-[#E8FAF0] p-3 text-sm text-[#0F8C45]">{notice}</p>}
          {created && <p role="status" className="rounded-lg bg-[#E8FAF0] p-3 text-sm text-[#0F8C45]">Se invitó a <strong>{created.email}</strong> y se envió su contraseña temporal. El reemplazo está pendiente: al completar el cambio de contraseña y MFA, esa cuenta asumirá la superadministración y tu sesión se cerrará.</p>}
          <div className="flex flex-wrap items-end gap-3">
            <div className="min-w-64 flex-1">
              <FormField compact id="superadmin-email" label="Correo del nuevo superadministrador" type="email" required autoComplete="off" value={email} onChange={(event) => setEmail(event.target.value)} disabled={busy || cancelling || Boolean(created)} />
            </div>
            <Button type="submit" className={primaryStyle} disabled={busy || cancelling || Boolean(created) || !email.trim()}>{busy ? "Enviando…" : "Invitar sucesor"}</Button>
          </div>
        </form>

        <div className="space-y-4 rounded-[10px] border border-[#F3D7D7] bg-white p-5">
          <div>
            <h2 className="text-lg font-bold">Cancelar una invitación pendiente</h2>
            <p className="mt-1 text-sm text-[#6B758A]">Si el sucesor no completó su incorporación, puedes cancelar el reemplazo y desactivar la cuenta invitada. También puedes hacerlo si la invitación se creó en una sesión anterior.</p>
          </div>
          <Button variant="outline" className={outlineStyle} disabled={busy || cancelling} onClick={() => {
            if (!busy) setCancelling(true);
          }}>Cancelar reemplazo pendiente</Button>
        </div>
      </>}

      {cancelling && viewer && <CancelHandoffDialog onClose={() => setCancelling(false)} onCancelled={(message) => {
        setCancelling(false);
        setCreated(null);
        setError(null);
        setNotice(message);
      }} />}
    </section>
  );
}
