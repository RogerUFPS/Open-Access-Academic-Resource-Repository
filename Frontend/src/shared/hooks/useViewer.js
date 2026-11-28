"use client";

import { useEffect, useState } from "react";
import { useAccountsApi } from "@/shared/components/AccountsProvider";

/** Permiso efectivo del usuario (el superadmin tiene todos). */
export function canDo(user, app, resource, action) {
  return Boolean(user?.is_superadmin || user?.effective_permissions?.[app]?.[resource]?.[action] === true);
}

/**
 * Usuario autenticado (de /auth/me/). `user` es null mientras carga o si falla;
 * el Backend sigue siendo quien autoriza cada petición.
 */
export function useViewer() {
  const accountsApi = useAccountsApi();
  const [user, setUser] = useState(null);

  useEffect(() => {
    let active = true;
    accountsApi
      .me()
      .then((viewer) => {
        if (active) setUser(viewer);
      })
      .catch(() => {
        if (active) setUser(null);
      });
    return () => {
      active = false;
    };
  }, [accountsApi]);

  return user;
}
