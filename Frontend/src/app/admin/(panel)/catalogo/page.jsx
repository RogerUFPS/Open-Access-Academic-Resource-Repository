"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertCircle, Boxes } from "lucide-react";
import { useAccountsApi } from "@/shared/components/AccountsProvider";
import CatalogManager from "@/features/admin/catalogs/CatalogManager";
import { CATALOG_RESOURCES } from "@/features/admin/catalogs/catalogAdminService";
import { catalogResourcePermissions, viewableCatalogResources } from "@/features/admin/catalogs/catalogPermissions";
import { extractApiErrorText } from "@/shared/services/apiClient";

function permissionError(error) {
  if (error?.name === "TypeError") {
    return "No se pudo conectar con el servidor para consultar los permisos.";
  }
  return extractApiErrorText(error?.data) || error?.message || "No se pudieron consultar tus permisos.";
}

export default function CatalogsPage() {
  const accountsApi = useAccountsApi();
  const [viewer, setViewer] = useState(null);
  const [status, setStatus] = useState("loading");
  const [error, setError] = useState("");
  const [activeResource, setActiveResource] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);

  const retryViewer = useCallback(() => {
    setStatus("loading");
    setError("");
    setReloadKey((current) => current + 1);
  }, []);

  useEffect(() => {
    let active = true;
    accountsApi.me()
      .then((user) => {
        if (!active) return;
        const visible = viewableCatalogResources(user);
        setViewer(user);
        setActiveResource((current) => visible.includes(current) ? current : visible[0] ?? null);
        setStatus("ready");
      })
      .catch((requestFailure) => {
        if (!active) return;
        setError(permissionError(requestFailure));
        setStatus("error");
      });
    return () => {
      active = false;
    };
  }, [accountsApi, reloadKey]);

  const visibleResources = useMemo(
    () => viewableCatalogResources(viewer),
    [viewer]
  );

  return (
    <div className="min-h-screen font-sans text-slate-900">
      <main className="mx-auto max-w-6xl px-5 py-8 sm:py-10">
        <nav aria-label="Ruta" className="text-sm text-slate-600">
          Administración <span aria-hidden="true">/</span> <span className="font-medium text-slate-900">Catálogos</span>
        </nav>

        <header className="mt-4">
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-rose-100 text-[#7f1218]">
              <Boxes className="h-5 w-5" aria-hidden="true" />
            </span>
            <div>
              <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">Catálogos</h1>
              <p className="mt-1 text-sm text-slate-600">Gestiona las instituciones, idiomas y países del repositorio.</p>
            </div>
          </div>
        </header>

        {status === "loading" && (
          <p role="status" className="mt-8 rounded-md border border-slate-200 bg-white px-4 py-6 text-sm text-slate-600">
            Consultando permisos…
          </p>
        )}

        {status === "error" && (
          <div role="alert" className="mt-8 flex flex-wrap items-center justify-between gap-3 rounded-md border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">
            <span className="inline-flex items-center gap-2"><AlertCircle className="h-4 w-4" aria-hidden="true" />{error}</span>
            <button type="button" onClick={retryViewer} className="rounded-md border border-rose-300 bg-white px-3 py-1.5 font-medium hover:bg-rose-100">
              Reintentar
            </button>
          </div>
        )}

        {status === "ready" && visibleResources.length === 0 && (
          <div role="alert" className="mt-8 rounded-md border border-amber-200 bg-amber-50 px-4 py-4 text-sm text-amber-900">
            No tienes permiso para consultar estos catálogos.
          </div>
        )}

        {status === "ready" && visibleResources.length > 0 && (
          <>
            <div role="tablist" aria-label="Catálogos disponibles" className="mt-7 flex flex-wrap gap-1 border-b border-slate-200">
              {visibleResources.map((resource) => (
                <button
                  key={resource}
                  id={`catalog-tab-${resource}`}
                  type="button"
                  role="tab"
                  aria-selected={activeResource === resource}
                  aria-controls={`catalog-panel-${resource}`}
                  onClick={() => setActiveResource(resource)}
                  className={`-mb-px border-b-2 px-4 py-2.5 text-sm font-medium ${
                    activeResource === resource
                      ? "border-[#7f1218] text-[#7f1218]"
                      : "border-transparent text-slate-600 hover:text-slate-900"
                  }`}
                >
                  {CATALOG_RESOURCES[resource].label}
                </button>
              ))}
            </div>
            {visibleResources.map((resource) => (
              <CatalogManager
                key={resource}
                resource={resource}
                permissions={catalogResourcePermissions(viewer, resource)}
                active={activeResource === resource}
              />
            ))}
          </>
        )}
      </main>
    </div>
  );
}
