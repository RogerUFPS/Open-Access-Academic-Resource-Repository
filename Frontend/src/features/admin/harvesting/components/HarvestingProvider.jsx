"use client";

import { createContext, useContext } from "react";
import { mutateHarvest } from "@/shared/actions/backendMutations";
import { createHarvestingApi } from "@/features/admin/harvesting/harvesting";

const HarvestingContext = createContext(null);
// Module-level Server Action reference: the API never changes between renders.
const harvestingApi = createHarvestingApi(mutateHarvest);

export default function HarvestingProvider({ children }) {
  return <HarvestingContext.Provider value={harvestingApi}>{children}</HarvestingContext.Provider>;
}

export function useHarvestingApi() {
  const api = useContext(HarvestingContext);
  if (!api) throw new Error("Los componentes de cosecha requieren HarvestingProvider.");
  return api;
}
