import "server-only";
import AccountsProvider from "@/shared/components/AccountsProvider";
import HarvestingProvider from "@/features/admin/harvesting/components/HarvestingProvider";

// Mutations go through the Server Actions in @/shared/actions/backendMutations,
// which own the session and CSRF cookies; the providers import them directly.
export default function AccountsGateway({ children, initialUser = null }) {
  return <AccountsProvider initialUser={initialUser}>
    <HarvestingProvider>{children}</HarvestingProvider>
  </AccountsProvider>;
}
