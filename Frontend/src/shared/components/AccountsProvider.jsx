"use client";

import { createContext, useContext, useMemo } from "react";
import { createAccountsApi } from "@/shared/services/apiClient";

const AccountsContext = createContext(null);

export default function AccountsProvider({ mutateAction, initialUser = null, children }) {
  // Protected pages reuse the user validated by the server layout. Login,
  // which has no initial user, keeps the normal session lookup.
  const me = useMemo(() => initialUser ? async (signal) => {
    signal?.throwIfAborted();
    return initialUser;
  } : undefined, [initialUser]);
  const api = useMemo(() => createAccountsApi(mutateAction, { me }), [mutateAction, me]);
  return <AccountsContext.Provider value={api}>{children}</AccountsContext.Provider>;
}

export function useAccountsApi() {
  const api = useContext(AccountsContext);
  if (!api) throw new Error("Los componentes de cuentas requieren AccountsGateway.");
  return api;
}
