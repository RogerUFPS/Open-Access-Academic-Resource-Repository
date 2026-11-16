"use client";

import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// Caché de datos del panel en memoria: al volver a una pestaña se muestra lo
// último visto y se revalida en segundo plano (staleTime 0).
//
// El cliente vive en el estado de este componente, montado dentro del layout
// del panel: al cerrar sesión el layout se desmonta y la caché se descarta, de
// modo que nunca se muestran datos de la sesión anterior. Por lo mismo no se
// persiste en localStorage.
export default function QueryProvider({ children }) {
  const [client] = useState(() => new QueryClient({
    defaultOptions: {
      queries: {
        gcTime: 30 * 60 * 1000,
        // Igual que antes de la caché: un fallo se muestra de inmediato.
        retry: false,
      },
    },
  }));
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
