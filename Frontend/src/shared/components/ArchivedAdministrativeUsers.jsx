"use client";

import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { Open_Sans } from "next/font/google";
import Button from "@/shared/components/Button";
import AccountFeedback from "@/shared/components/AccountFeedback";
import { useAccountsApi } from "@/shared/components/AccountsProvider";
import { hasAccountPermission } from "@/shared/services/apiClient";
import { getUserDisplayName } from "@/shared/services/userService";
import { queryKeys } from "@/shared/query/queryKeys";

const outlineStyle = "!border-[#7f1218] !text-[#7f1218]";
const openSans = Open_Sans({ subsets: ["latin"], weight: ["400", "600", "700"], display: "swap" });

function deletionDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleDateString("es-CO", { day: "2-digit", month: "short", year: "numeric" }).replaceAll(" de ", " ").replace("sept", "sep");
}

export default function ArchivedAdministrativeUsers() {
  const accountsApi = useAccountsApi();
  const queryClient = useQueryClient();
  const [viewer, setViewer] = useState(null);
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [sessionRequired, setSessionRequired] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [search, setSearch] = useState("");
  const [restoring, setRestoring] = useState(null);
  const [restoreError, setRestoreError] = useState(null);
  const [notice, setNotice] = useState("");
  const pending = useRef(false);

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      setLoading(true);
      setError(null);
      setSessionRequired(false);
      setViewer(null);
      let authenticated = false;
      try {
        const current = await accountsApi.me(controller.signal);
        authenticated = true;
        if (current.force_password_change) throw new Error("Debes cambiar tu contraseña provisional desde el inicio de sesión.");
        setViewer(current);
        if (!hasAccountPermission(current, "view")) throw new Error("Tu cuenta no tiene permiso para consultar usuarios administrativos.");
        const data = await accountsApi.archivedUsers(controller.signal);
        if (!Array.isArray(data)) throw new Error("El servidor no devolvió un listado de usuarios eliminados válido.");

        const actorIds = [...new Set(data.map((user) => user.deleted_by).filter((actor) => typeof actor === "number"))];
        const actors = new Map(await Promise.all(actorIds.map(async (id) => {
          try {
            return [id, await accountsApi.user(id, controller.signal)];
          } catch (error) {
            if (controller.signal.aborted || error.authExpired) throw error;
            return [id, { full_name: `Usuario #${id}` }];
          }
        })));
        if (!controller.signal.aborted) setUsers(data.map((user) => ({ ...user, deleted_by: actors.get(user.deleted_by) || user.deleted_by })));
      } catch (error) {
        if (controller.signal.aborted) return;
        setError(error);
        setSessionRequired(!authenticated && [401, 403].includes(error.status));
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }
    load();
    return () => controller.abort();
  }, [accountsApi, refresh]);

  async function restore(user) {
    if (pending.current) return;
    pending.current = true;
    setRestoring(user.id);
    setRestoreError(null);
    setNotice("");
    try {
      await accountsApi.restoreUser(user.id);
      setUsers((current) => current.filter((item) => item.id !== user.id));
      // La lista principal está en caché: se revalida para mostrar la cuenta como activa.
      queryClient.invalidateQueries({ queryKey: queryKeys.accounts.users });
      setNotice(`La cuenta de ${getUserDisplayName(user)} fue restaurada correctamente.`);
    } catch (error) {
      setRestoreError(error);
    } finally {
      pending.current = false;
      setRestoring(null);
    }
  }

  const term = search.trim().toLocaleLowerCase("es");
  const filtered = users.filter((user) => [getUserDisplayName(user), user.email, user.collegue_code]
    .some((value) => String(value || "").toLocaleLowerCase("es").includes(term)));
  const count = !loading && !error && <span className="inline-flex h-[34px] min-w-[159px] items-center justify-center rounded-full bg-[#7f1218]/5 px-[18px] text-[13px] font-semibold text-[#7f1218]" aria-live="polite">{users.length} {users.length === 1 ? "eliminado" : "eliminados"}</span>;

  return (
    <section className={`${openSans.className} text-[#1F242E]`}>
      <Link href="/admin/usuarios" className="inline-flex h-[30px] items-center text-sm font-semibold text-[#7f1218] hover:underline">← Volver a usuarios administrativos</Link>
      <h1 className="mt-3 text-[30px] leading-[48px] font-bold">Cuentas administrativas eliminadas</h1>
      <p className="mt-[3px] text-[15px] leading-6 text-[#68707C]">Cuentas retiradas del acceso a administración. Al restaurarlas recuperan su acceso y sus permisos.</p>
      <div className="mt-11 flex flex-wrap items-center justify-between gap-4">
        <label className="w-full max-w-[560px]">
          <span className="sr-only">Buscar en usuarios administrativos eliminados</span>
          <input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Buscar en usuarios administrativos..." className="h-12 w-full rounded-lg border border-[#D1D6E0] bg-white px-4 text-sm outline-none placeholder:text-[#68707C] focus:border-[#7f1218] focus:ring-1 focus:ring-[#7f1218]" />
        </label>
        {count}
      </div>
      {notice && <p role="status" className="mt-4 rounded-lg bg-[#E8FAF0] p-3 text-sm text-[#0F8C45]">{notice}</p>}
      {restoreError && <div className="mt-4"><AccountFeedback error={restoreError} /></div>}
      {error && <div className="mt-4"><AccountFeedback error={error} sessionRequired={sessionRequired} retry={() => setRefresh((value) => value + 1)} /></div>}
      <div className="mt-6 min-h-[342px] overflow-hidden rounded-xl border border-[#D1D6E0] bg-white" aria-busy={loading}>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] table-fixed text-left">
            <caption className="sr-only">Usuarios administrativos eliminados</caption>
            <colgroup><col className="w-[40%]" /><col className="w-[18.5%]" /><col className="w-[19%]" /><col className="w-[22.5%]" /></colgroup>
            <thead className="h-12 bg-[#F5F6F9] text-xs text-[#68707C]">
              <tr>{["NOMBRE", "ELIMINADO EL", "ELIMINADO POR", "ACCIONES"].map((label) => <th key={label} scope="col" className="px-6 font-semibold">{label}</th>)}</tr>
            </thead>
            <tbody>
              {loading && <tr><td colSpan={4} role="status" className="p-10 text-center text-sm text-[#68707C]">Cargando usuarios eliminados…</td></tr>}
              {!loading && !error && filtered.map((user) => <tr key={user.id} className="h-20 border-b border-[#D1D6E0]/65 last:border-0">
                <td className="break-words px-6 py-3"><p className="text-sm font-semibold">{getUserDisplayName(user)}</p><p className="mt-1 text-xs text-[#68707C]">Cuenta administrativa</p></td>
                <td className="px-6 text-[13px]">{deletionDate(user.deleted_at)}</td>
                <td className="break-words px-6 text-[13px]">{getUserDisplayName(user.deleted_by)}</td>
                <td className="px-3">{hasAccountPermission(viewer, "restore") ? <Button variant="outline" size="small" className={`${outlineStyle} !h-[38px] min-w-[105px] !text-[13px]`} disabled={restoring !== null} onClick={() => restore(user)} aria-label={`Restaurar a ${getUserDisplayName(user)}`}>{restoring === user.id ? "Restaurando…" : "Restaurar"}</Button> : <span className="text-xs text-[#68707C]">Sin permiso para restaurar</span>}</td>
              </tr>)}
              {!loading && !error && !filtered.length && <tr><td colSpan={4} className="p-10 text-center text-sm text-[#68707C]">{users.length ? "No hay usuarios eliminados que coincidan con la búsqueda." : "No hay usuarios administrativos eliminados."}</td></tr>}
            </tbody>
          </table>
        </div>
        {!loading && !error && <p className="px-6 py-5 text-xs text-[#68707C]" aria-live="polite">Mostrando {filtered.length} de {users.length} registros</p>}
      </div>
    </section>
  );
}
