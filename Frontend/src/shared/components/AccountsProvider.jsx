"use client";

import { createContext, useContext, useMemo } from "react";
import { mutateAccount } from "@/shared/actions/backendMutations";
import { createAccountsApi } from "@/shared/services/apiClient";

const AccountsContext = createContext(null);

export default function AccountsProvider({ initialUser = null, children }) {
  // Protected pages reuse the user validated by the server layout. Login,
  // which has no initial user, keeps the normal session lookup.
  const me = useMemo(() => initialUser ? async (signal) => {
    signal?.throwIfAborted();
    return initialUser;
  } : undefined, [initialUser]);
  // `mutateAccount` is a module-level Server Action reference, so the API stays
  // stable across the re-renders that every mutation triggers.
  const api = useMemo(() => createAccountsApi(mutateAccount, { me }), [me]);
  return <AccountsContext.Provider value={api}>{children}</AccountsContext.Provider>;
}

export function useAccountsApi() {
  const api = useContext(AccountsContext);
  if (!api) throw new Error("Los componentes de cuentas requieren AccountsGateway.");
  return api;
}
